"""Pipeline steps: preprocess, transcribe, LLM analysis. All models from Hugging Face, run locally."""
import logging
import re
import sys
import time
from pathlib import Path

# Add project root for config
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from pydub import AudioSegment
from pydub.effects import normalize

# Prompts from docs/prompt-pipeline.md
PROMPT_MAIN_TOPIC = "What is the main topic of this transcribed meeting:\n\n{transcription}"
PROMPT_SUBTOPICS = "From a meeting about {main_topic}, find subtopics that were talked about from this transcription:\n\n{transcription}"
PROMPT_TRUTH_STATEMENTS = """You are a Logic and Epistemology Auditor. Your job is to analyze a meeting transcript and extract "Truth Statements." You must be rigorous, objective, and precise.

Definition of a Truth Statement: For the purpose of this task, a "Truth Statement" is defined as one of the following three categories:
- Objective Fact: A statement about the world, data, or past events presented as verifiable (e.g., "Revenue increased by 15% last quarter").
- Consensus Decision: An action or conclusion explicitly agreed upon by the group (e.g., "The team agreed to delay the launch").
- Attributed Stance: A definitive statement of a speaker's position or belief, explicitly attributed to them (e.g., "Sarah stated that the timeline is unrealistic").

Input Text:
{transcription}

Instructions: Analyze the transcript and extract truth statements based on the definitions above. Follow these rules strictly:
- Resolve Pronouns: Do not use "he," "she," or "they." Replace pronouns with the specific speaker's name or the specific department/entity being discussed.
- Filter Speculation: Ignore sentences that are hypothetical ("If we do X..."), conditional ("I might go..."), or interrogative ("Did we fix the bug?").
- Handle Disagreement: If two speakers contradict each other regarding a fact, record both statements as "Attributed Stances".
- Strip Filler: Remove verbal tics (um, ah, like) and conversational fluff.
- Verbatim Accuracy: Do not summarize the gist of the fact; preserve the specific metrics, dates, and nouns used.

Output Format: Present the output as a Markdown table with the following columns:
| Category | Truth Statement | Confidence Score (1-5) | Context/Quote |
| :--- | :--- | :--- | :--- |
Category: (Objective Fact / Consensus Decision / Attributed Stance). Truth Statement: The extracted statement in full. Confidence Score: 5 = Absolute certainty; 1 = Ambiguous. Context/Quote: A brief snippet of the original text proving the statement."""

# Chunked-path prompts (no main_topic for subtopics; main topic from subtopics list)
PROMPT_SUBTOPICS_CHUNK = "From this meeting transcript excerpt, find subtopics that were discussed:\n\n{transcription}"
PROMPT_MAIN_TOPIC_FROM_SUBTOPICS = """The following subtopics were discussed in a meeting. What is the main topic of this meeting?

Subtopics:
{subtopics_list}"""


def _chunk_transcript(tokenizer, text: str, max_tokens: int) -> list[str]:
    """Split transcript into chunks of at most max_tokens, preferring sentence boundaries."""
    text = text.strip()
    if not text:
        return []
    # Split on sentence boundaries (period, question, exclamation followed by space or newline)
    sentences = re.split(r"(?<=[.!?])\s+", text)
    sentences = [s.strip() for s in sentences if s.strip()]
    if not sentences:
        return [text] if text else []

    chunks = []
    current: list[str] = []
    current_tokens = 0

    for sent in sentences:
        n = len(tokenizer.encode(sent, add_special_tokens=False))
        if n > max_tokens:
            # Single sentence exceeds limit: hard cut by tokens
            if current:
                chunks.append(" ".join(current))
                current = []
                current_tokens = 0
            ids = tokenizer.encode(sent, add_special_tokens=False)
            for i in range(0, len(ids), max_tokens):
                chunk_ids = ids[i : i + max_tokens]
                chunks.append(tokenizer.decode(chunk_ids, skip_special_tokens=True))
            continue
        if current_tokens + n > max_tokens and current:
            chunks.append(" ".join(current))
            current = []
            current_tokens = 0
        current.append(sent)
        current_tokens += n

    if current:
        chunks.append(" ".join(current))
    return chunks


def _merge_dedup_subtopics(raw_lists: list[list[str]]) -> list[str]:
    """Merge subtopic lists and deduplicate by normalized text (lowercase, collapse spaces)."""
    seen: set[str] = set()
    result: list[str] = []
    for lst in raw_lists:
        for s in lst:
            norm = " ".join(s.lower().split())
            if norm and len(norm) > 2 and norm not in seen:
                seen.add(norm)
                result.append(s.strip())
    return result


def _parse_truth_table_rows(md: str) -> list[str]:
    """Extract table body rows (lines with |) from a markdown table; skip header and separator lines."""
    rows = []
    for line in md.strip().splitlines():
        line = line.strip()
        if not line or not line.startswith("|"):
            continue
        # Skip separator line (e.g. | :--- | :--- |)
        if re.match(r"^\|\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$", line):
            continue
        # Skip header row (contains "Category" / "Truth Statement")
        if "category" in line.lower() or "truth statement" in line.lower():
            continue
        rows.append(line)
    return rows


def _merge_dedup_truth_md(tables: list[str]) -> str:
    """Merge multiple markdown truth-statement tables into one and deduplicate by Truth Statement column."""
    header = "| Category | Truth Statement | Confidence Score (1-5) | Context/Quote |"
    separator = "| :--- | :--- | :--- | :--- |"
    all_rows = []
    seen_statements: set[str] = set()

    for md in tables:
        rows = _parse_truth_table_rows(md)
        for row in rows:
            # Second column is Truth Statement (index 1 when split by |)
            parts = [p.strip() for p in row.split("|") if p.strip()]
            if len(parts) >= 2:
                stmt = " ".join(parts[1].lower().split())
                if stmt and stmt not in seen_statements:
                    seen_statements.add(stmt)
                    all_rows.append(row)
            elif row.strip():
                all_rows.append(row)

    if not all_rows:
        return header + "\n" + separator + "\n(No truth statements extracted.)"
    return header + "\n" + separator + "\n" + "\n".join(all_rows)


class PipelineContext:
    """Data passed between pipeline steps."""
    def __init__(self, job_id: str, upload_path: Path, original_filename: str):
        self.job_id = job_id
        self.upload_path = upload_path
        self.original_filename = original_filename
        self.audio_path: Path | None = None  # After preprocess (wav)
        self.transcription: str = ""
        self.timestamps: list[dict] = []  # [{"start": float, "end": float, "text": str}]
        self.main_topic: str = ""
        self.subtopics: list[str] = []
        self.truth_statements_md: str = ""
        self.error: str | None = None


def check_ffmpeg_available() -> tuple[bool, str]:
    """Return (True, '') if ffmpeg and ffprobe are on PATH; else (False, message)."""
    import shutil
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg:
        return False, "ffmpeg not found on PATH. Install FFmpeg and add it to PATH (see README)."
    if not ffprobe:
        return False, "ffprobe not found on PATH. Install FFmpeg (includes ffprobe) and add it to PATH."
    return True, ""


def ensure_ffmpeg_available() -> tuple[bool, str]:
    """Use system ffmpeg if on PATH; otherwise try bundled static-ffmpeg (no admin). Then return check_ffmpeg_available()."""
    try:
        import static_ffmpeg
        static_ffmpeg.add_paths(weak=True)
    except ImportError:
        pass
    return check_ffmpeg_available()


def preprocess(ctx: PipelineContext, on_progress: callable = None) -> None:
    """Convert to WAV and normalize. Requires ffmpeg/ffprobe on PATH for .mp3/.mp4."""
    from config import OUTPUT_DIR

    path = ctx.upload_path
    suffix = path.suffix.lower()
    out_path = OUTPUT_DIR / f"{ctx.job_id}_audio.wav"

    if on_progress:
        on_progress("Loading file...", 10.0)

    # .mp3 and .mp4 need ffmpeg/ffprobe (pydub uses them); ensure_ffmpeg uses bundled static-ffmpeg if no system install
    if suffix in (".mp3", ".mp4"):
        ok, msg = ensure_ffmpeg_available()
        if not ok:
            raise FileNotFoundError(msg)

    try:
        if suffix == ".wav":
            audio = AudioSegment.from_wav(str(path))
        elif suffix == ".mp3":
            audio = AudioSegment.from_mp3(str(path))
        elif suffix == ".mp4":
            audio = AudioSegment.from_file(str(path), format="mp4")
        else:
            raise ValueError(f"Unsupported format: {suffix}")
    except FileNotFoundError as e:
        _, msg = ensure_ffmpeg_available()
        raise FileNotFoundError(msg or str(e))
    except OSError as e:
        err = getattr(e, "winerror", None) or getattr(e, "errno", None)
        if err == 2 or "ffmpeg" in str(e).lower() or "ffprobe" in str(e).lower():
            _, msg = ensure_ffmpeg_available()
            raise FileNotFoundError(msg or "FFmpeg failed. Ensure ffmpeg and ffprobe are on PATH.")
        raise

    if on_progress:
        on_progress("Normalizing...", 50.0)
    audio = normalize(audio)
    if on_progress:
        on_progress("Exporting WAV...", 80.0)
    audio.export(str(out_path), format="wav")
    ctx.audio_path = out_path
    if on_progress:
        on_progress("Done", 100.0)


def _merge_segments_by_min_words(chunks: list, min_words: int = 10) -> list[dict]:
    """Merge Whisper chunks so each segment has at least min_words; join pause-separated parts with commas."""
    raw = []
    for c in chunks:
        ts = c.get("timestamp") or (0.0, 0.0)
        start, end = (float(ts[0]), float(ts[1])) if isinstance(ts, (list, tuple)) else (0.0, 0.0)
        seg_text = (c.get("text") or "").strip()
        if seg_text:
            raw.append({"start": start, "end": end, "text": seg_text})

    if not raw:
        return []

    merged: list[dict] = []
    acc_start = raw[0]["start"]
    acc_end = raw[0]["end"]
    acc_texts: list[str] = [raw[0]["text"]]
    acc_words = len(raw[0]["text"].split())

    for i in range(1, len(raw)):
        seg = raw[i]
        seg_words = len(seg["text"].split())
        if acc_words + seg_words < min_words:
            acc_texts.append(seg["text"])
            acc_words += seg_words
            acc_end = seg["end"]
        else:
            merged.append({
                "start": acc_start,
                "end": acc_end,
                "text": ", ".join(acc_texts),
            })
            acc_start = seg["start"]
            acc_end = seg["end"]
            acc_texts = [seg["text"]]
            acc_words = seg_words

    merged.append({
        "start": acc_start,
        "end": acc_end,
        "text": ", ".join(acc_texts),
    })
    # If the last segment has fewer than min_words, merge it into the previous one
    if len(merged) > 1 and len(merged[-1]["text"].split()) < min_words:
        prev = merged.pop()
        last = merged[-1]
        merged[-1] = {
            "start": last["start"],
            "end": prev["end"],
            "text": last["text"] + ", " + prev["text"],
        }
    return merged


def transcribe(ctx: PipelineContext, on_progress: callable = None, is_cancelled: callable = None) -> None:
    """Transcribe with distil-whisper from Hugging Face (transformers pipeline, native format)."""
    from transformers import pipeline
    import torch
    from config import WHISPER_MODEL_NAME

    if not ctx.audio_path or not ctx.audio_path.exists():
        raise FileNotFoundError("Preprocessed audio not found")

    if is_cancelled and is_cancelled():
        return
    if on_progress:
        on_progress("Loading Whisper model...", 5.0)
    step_log = logging.getLogger("audio_pipeline.runner")
    step_log.info("Transcribe: loading Whisper model %s (first job only, not on page load)...", WHISPER_MODEL_NAME)
    t0 = time.perf_counter()
    device = 0 if torch.cuda.is_available() else "cpu"
    pipe = pipeline(
        "automatic-speech-recognition",
        model=WHISPER_MODEL_NAME,
        device=device,
        torch_dtype=torch.float16 if device == 0 else torch.float32,
        generate_kwargs={"language": "en", "task": "transcribe"},
    )
    step_log.info("Transcribe: Whisper model loaded in %.3fs", time.perf_counter() - t0)
    if on_progress:
        on_progress("Model loaded", 30.0)

    if is_cancelled and is_cancelled():
        return
    if on_progress:
        on_progress("Transcribing audio...", 40.0)
    # Pipeline accepts file path; returns {"text": ..., "chunks": [{"timestamp": (start, end), "text": ...}]}
    result = pipe(str(ctx.audio_path), return_timestamps=True)
    if is_cancelled and is_cancelled():
        return
    if on_progress:
        on_progress("Processing transcription...", 90.0)
    text = result.get("text") or ""
    chunks = result.get("chunks") or []
    pipe = None  # free GPU

    ctx.transcription = text.strip()
    # Merge chunks so each segment has at least MIN_WORDS_PER_SEGMENT; join with commas (pause boundaries)
    ctx.timestamps = _merge_segments_by_min_words(chunks, min_words=10)
    if on_progress:
        on_progress("Done", 100.0)


# Cached Hugging Face LLM (loaded once per process)
_llm_pipeline = None
_llm_model_id = None


def _get_llm_pipeline(on_progress=None):
    """Load and cache the Hugging Face text-generation model and tokenizer."""
    global _llm_pipeline, _llm_model_id
    from config import LLM_MODEL_NAME

    if _llm_pipeline is not None and _llm_model_id == LLM_MODEL_NAME:
        return _llm_pipeline
    from transformers import AutoModelForCausalLM, AutoTokenizer
    import torch

    step_log = logging.getLogger("audio_pipeline.runner")
    step_log.info("LLM: loading %s (first job only, not on page load)...", LLM_MODEL_NAME)
    t0 = time.perf_counter()
    if on_progress:
        on_progress("Loading Hugging Face model...")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    tokenizer = AutoTokenizer.from_pretrained(LLM_MODEL_NAME, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(
        LLM_MODEL_NAME,
        trust_remote_code=True,
        torch_dtype=torch.float16 if device == "cuda" else torch.float32,
        low_cpu_mem_usage=True,
    ).to(device)
    step_log.info("LLM: model loaded in %.3fs", time.perf_counter() - t0)
    _llm_pipeline = (model, tokenizer, device)
    _llm_model_id = LLM_MODEL_NAME
    return _llm_pipeline


def _generate(prompt: str, model, tokenizer, device: str, max_new_tokens: int = 512) -> str:
    """Run one prompt through the local LLM and return the generated text."""
    from config import LLM_MAX_INPUT_TOKENS, LLM_REPETITION_PENALTY
    import torch

    # Use chat template if available (e.g. Qwen, Zephyr), else plain prompt
    try:
        messages = [{"role": "user", "content": prompt}]
        text = tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
    except Exception:
        text = prompt + "\n\n"

    inputs = tokenizer(
        text,
        return_tensors="pt",
        truncation=True,
        max_length=LLM_MAX_INPUT_TOKENS,
        padding=False,
    ).to(device)
    with torch.no_grad():
        out = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=False,
            repetition_penalty=LLM_REPETITION_PENALTY,
            pad_token_id=tokenizer.eos_token_id or tokenizer.pad_token_id,
            eos_token_id=tokenizer.eos_token_id,
        )
    # Decode only the new part
    gen = out[0][inputs["input_ids"].shape[1] :]
    return tokenizer.decode(gen, skip_special_tokens=True).strip()


def _parse_subtopics_response(raw: str) -> list[str]:
    """Parse LLM subtopics response into a list of strings."""
    items = [s.strip() for s in raw.replace("-", "\n").split("\n") if s.strip() and len(s.strip()) > 2]
    return items if items else ([raw] if raw else [])


def analyze_llm(ctx: PipelineContext, on_progress: callable = None, is_cancelled: callable = None) -> None:
    """Extract main topic, subtopics, and truth statements via local Hugging Face LLM."""
    from config import LLM_CHUNK_TRANSCRIPT_TOKENS, LLM_MODEL_NAME

    text = ctx.transcription
    if not text:
        ctx.main_topic = "(No transcription)"
        ctx.subtopics = []
        ctx.truth_statements_md = "(No transcription.)"
        return

    try:
        model, tokenizer, device = _get_llm_pipeline(on_progress=on_progress)
    except Exception as e:
        ctx.main_topic = f"(Model load failed: {e})"
        ctx.subtopics = []
        ctx.truth_statements_md = f"(Could not load {LLM_MODEL_NAME}. Check install and disk.)"
        return

    if is_cancelled and is_cancelled():
        return

    # Decide single-call vs chunked: compare transcript token count to one chunk
    transcript_tokens = tokenizer.encode(text, add_special_tokens=False)
    use_chunked = len(transcript_tokens) > LLM_CHUNK_TRANSCRIPT_TOKENS

    if not use_chunked:
        # Short transcript: existing single-call path
        if is_cancelled and is_cancelled():
            return
        if on_progress:
            on_progress("Extracting main topic...", 20.0)
        ctx.main_topic = _generate(
            PROMPT_MAIN_TOPIC.format(transcription=text), model, tokenizer, device, max_new_tokens=128
        )
        if is_cancelled and is_cancelled():
            return
        if on_progress:
            on_progress("Extracting subtopics...", 50.0)
        raw_sub = _generate(
            PROMPT_SUBTOPICS.format(main_topic=ctx.main_topic, transcription=text),
            model, tokenizer, device, max_new_tokens=256,
        )
        ctx.subtopics = _parse_subtopics_response(raw_sub)
        if is_cancelled and is_cancelled():
            return
        if on_progress:
            on_progress("Extracting truth statements...", 75.0)
        ctx.truth_statements_md = _generate(
            PROMPT_TRUTH_STATEMENTS.format(transcription=text), model, tokenizer, device, max_new_tokens=1024
        )
        if on_progress:
            on_progress("Done", 100.0)
        return

    # Long transcript: chunked path — subtopics per chunk → merge → main topic from subtopics → truth per chunk → merge
    chunks = _chunk_transcript(tokenizer, text, LLM_CHUNK_TRANSCRIPT_TOKENS)
    n_chunks = len(chunks)

    # Subtopics per chunk (0-30%)
    subtopic_lists: list[list[str]] = []
    for i, chunk in enumerate(chunks):
        if is_cancelled and is_cancelled():
            return
        progress = 5.0 + (i / n_chunks) * 25.0
        if on_progress:
            on_progress(f"Extracting subtopics (chunk {i + 1}/{n_chunks})...", progress)
        raw_sub = _generate(
            PROMPT_SUBTOPICS_CHUNK.format(transcription=chunk), model, tokenizer, device, max_new_tokens=256
        )
        subtopic_lists.append(_parse_subtopics_response(raw_sub))
    ctx.subtopics = _merge_dedup_subtopics(subtopic_lists)

    if is_cancelled and is_cancelled():
        return
    # Main topic from merged subtopics (30-35%)
    if on_progress:
        on_progress("Composing main topic from subtopics...", 32.0)
    subtopics_list = "\n".join(f"- {s}" for s in ctx.subtopics) if ctx.subtopics else "(None extracted)"
    ctx.main_topic = _generate(
        PROMPT_MAIN_TOPIC_FROM_SUBTOPICS.format(subtopics_list=subtopics_list),
        model, tokenizer, device, max_new_tokens=128,
    )

    # Truth statements per chunk (35-95%)
    truth_tables: list[str] = []
    for i, chunk in enumerate(chunks):
        if is_cancelled and is_cancelled():
            return
        progress = 35.0 + (i / n_chunks) * 60.0
        if on_progress:
            on_progress(f"Extracting truth statements (chunk {i + 1}/{n_chunks})...", progress)
        md = _generate(
            PROMPT_TRUTH_STATEMENTS.format(transcription=chunk), model, tokenizer, device, max_new_tokens=1024
        )
        truth_tables.append(md)
    ctx.truth_statements_md = _merge_dedup_truth_md(truth_tables)
    if on_progress:
        on_progress("Done", 100.0)