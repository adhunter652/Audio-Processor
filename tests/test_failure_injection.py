"""
Failure injection tests for Assignment 2.

These tests intentionally break the system in two ways and verify the documented
behavior: (1) unit mismatch — wrong sample rate; (2) silent truncation of LLM input.

Run: python -m unittest tests.test_failure_injection
Or: pytest tests/test_failure_injection.py -v

See docs/assignment2-pipeline-architecture.md §4 for the analysis of each failure.
"""
import os
import tempfile
import unittest
from pathlib import Path

# Project root
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class TestFailureInjectionSampleRate(unittest.TestCase):
    """
    Failure 1: Unit mismatch (sample rate).

    We create a WAV at 8 kHz; Whisper expects 16 kHz. The system does not crash
    but may produce degraded transcription (silent failure).
    Boundary: Representation → Model Inference.
    """

    @unittest.skipIf(
        os.getenv("RUN_FAILURE_INJECTION_SLOW") != "1",
        "Set RUN_FAILURE_INJECTION_SLOW=1 to run (loads Whisper, slow)",
    )
    def test_transcribe_accepts_8khz_wav_without_crashing(self):
        from pydub import AudioSegment
        from app.pipeline.steps import PipelineContext, transcribe
        from app.pipeline.steps import ensure_ffmpeg_available

        ok, _ = ensure_ffmpeg_available()
        self.assertTrue(ok, "FFmpeg required for this test")

        # Create 1 second of silence at 8 kHz (wrong for Whisper's 16 kHz expectation)
        silence = AudioSegment.silent(duration=1000, frame_rate=8000)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            wav_path = Path(f.name)
        try:
            silence.export(str(wav_path), format="wav")
            ctx = PipelineContext(
                job_id="failure-inject-8k",
                upload_path=wav_path,
                original_filename="test_8k.wav",
            )
            ctx.audio_path = wav_path
            transcribe(ctx)
            # System did not crash (silent failure: output may be empty or wrong)
            self.assertIsInstance(ctx.transcription, str)
            self.assertIsInstance(ctx.timestamps, list)
        finally:
            wav_path.unlink(missing_ok=True)


class TestFailureInjectionSilentTruncation(unittest.TestCase):
    """
    Failure 2: Silent truncation of input (LLM context).

    When transcript exceeds max_length, tokenizer truncates with truncation=True.
    Content at the end is lost without warning. This test demonstrates that
    (1) a long transcript exceeds one chunk, and (2) truncating to max_length
    drops a sentinel placed at the end.
    Boundary: Representation → Model Inference.
    """

    def test_long_transcript_exceeds_single_chunk_and_truncation_drops_tail(self):
        """Demonstrate that tokenizer truncation drops the end of long input."""
        from transformers import AutoTokenizer
        from config import LLM_MODEL_NAME, LLM_MAX_INPUT_TOKENS

        tokenizer = AutoTokenizer.from_pretrained(LLM_MODEL_NAME, trust_remote_code=True)
        # Build a transcript long enough to exceed one chunk
        sentinel = " UNIQUE_SENTINEL_AT_END_12345 "
        repeat = "The meeting discussed project timeline and budget. "
        long_transcript = (repeat * 500) + sentinel
        ids = tokenizer.encode(long_transcript, add_special_tokens=False)
        self.assertGreater(
            len(ids),
            LLM_MAX_INPUT_TOKENS,
            "Transcript should exceed max input tokens to demonstrate truncation",
        )
        # Simulate what _generate does: truncate to max_length
        truncated_ids = ids[: LLM_MAX_INPUT_TOKENS]
        decoded = tokenizer.decode(truncated_ids, skip_special_tokens=True)
        self.assertNotIn(
            "UNIQUE_SENTINEL_AT_END",
            decoded,
            "Truncation silently dropped the end of the input (failure injection 2)",
        )


if __name__ == "__main__":
    unittest.main()
