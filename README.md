# Audio Processing Pipeline

Web-based pipeline that accepts audio/video uploads (`.mp3`, `.wav`, `.mp4`), transcribes them with **distil-whisper**, then uses a **local Hugging Face LLM** to extract main topic, subtopics, and truth statements. **All models are from Hugging Face and run locally.** The UI shows per-step status and final results.

## Models (Hugging Face, local)

| Step       | Model | Source |
|-----------|--------|--------|
| Transcribe | `distil-whisper/distil-large-v3` | Hugging Face (transformers pipeline) |
| Analyze    | `Qwen/Qwen2.5-0.5B-Instruct` (default) | Hugging Face (transformers) |

Override via environment:

- `WHISPER_MODEL` – ASR model id (default: `distil-whisper/distil-large-v3`)
- `LLM_MODEL` – instruction model id (default: `Qwen/Qwen2.5-0.5B-Instruct`; e.g. `HuggingFaceH4/zephyr-3b-beta` for better quality, more RAM)
- `LLM_MAX_INPUT_TOKENS` – max context length for the LLM (default: 2048)

## Prerequisites: FFmpeg

**FFmpeg** (and **ffprobe**) are required for `.mp3` and `.mp4` uploads. Without them, preprocessing will fail with a clear error; `.wav` may work if pydub can open it without ffprobe.

**No admin / no system install:** The project’s `requirements.txt` includes **static-ffmpeg**, which provides bundled ffmpeg/ffprobe. If you cannot install ffmpeg system-wide (e.g. no admin on Linux), just run `pip install -r requirements.txt`; the app will use the bundled binaries with no admin rights. System ffmpeg is used when available; the bundle is used only when it is not on PATH.

**With admin (optional):** You can install ffmpeg system-wide so the app uses it instead of the bundle.

**Windows (pick one):** Winget: `winget install Gyan.FFmpeg` (then restart the terminal). Chocolatey: `choco install ffmpeg`. Manual: download from [ffmpeg.org](https://ffmpeg.org/download.html) (Windows builds), unzip, and add the `bin` folder to your system PATH.

**macOS:** `brew install ffmpeg`  
**Linux:** `sudo apt install ffmpeg` (Debian/Ubuntu) or equivalent.

Check: `ffmpeg -version` and `ffprobe -version` should run in a new terminal.

## Setup

1. **Create a virtual environment and install dependencies**

   ```bash
   python -m venv .venv
   .venv\Scripts\activate   # Windows
   # source .venv/bin/activate  # macOS/Linux
   pip install -r requirements.txt
   ```

   First run will download the Whisper and LLM models from Hugging Face (several GB for the LLM depending on model).

2. **Run the server**

   From the project root:

   ```bash
   python run.py
   ```

   Then open **http://localhost:8000** in your browser.

3. **Access from other devices on your network** (optional)

   The server binds to `0.0.0.0` by default, so it listens on all interfaces. From another device on the same LAN:

   - Find this machine’s IP (e.g. `ipconfig` on Windows, `ifconfig` or `ip addr` on macOS/Linux).
   - Open **http://\<your-IP\>:8000** (e.g. `http://192.168.1.100:8000`).
   - On Windows, allow inbound connections for Python on port 8000 in **Windows Defender Firewall** (or run: `netsh advfirewall firewall add rule name="Audio Pipeline" dir=in action=allow protocol=TCP localport=8000`).

## Network uploads and queue behavior

- **Sending files over the network** works the same as local uploads. Files are streamed to disk in chunks (no full-file buffering), so large uploads over Wi‑Fi may take longer but won’t exhaust memory. Multiple clients can upload at the same time; each file gets a unique path and is appended to the queue.
- **Queue is global and FIFO.** Uploads from any device (this machine or others on the LAN) go into a single queue. The **current job is never interrupted**: new uploads are only appended. The worker runs one job at a time and starts the next only after the current one finishes (or fails/cancels). So you can safely upload from other computers while a job is running; new files will wait in line and process in order.

## Usage

- **Upload**: Choose or drag-and-drop an `.mp3`, `.wav`, or `.mp4` file (max 1 GB). The pipeline runs in the background.
- **Jobs**: Each upload appears as a job with status `pending` → `running` → `completed` or `failed`.
- **Status**: Click a job to see the three steps (Preprocess, Transcribe, Analyze) and their status/messages.
- **Results**: When completed, the same panel shows transcription, main topic, sub-topics, key timestamps, and the truth-statements table.

- **Search transcripts** (`/search/transcripts`): Search transcription segments with a local RAG model (sentence-transformers + ChromaDB). Click a timestamp to play the corresponding audio from that point.

- **Search meetings** (`/search/meetings`): Search processed meetings by main topic (separate RAG index). Click a meeting to view its full processing results (transcription, topics, truth statements).

Completed jobs are automatically indexed into both RAG databases. Override the embedding model with `RAG_EMBEDDING_MODEL` (default: `all-MiniLM-L6-v2`).

## Pipeline steps (from docs)

1. **Preprocess** – Convert to WAV and normalize.
2. **Transcribe** – **distil-whisper/distil-large-v3** (Hugging Face, transformers ASR pipeline) for English transcription and timestamps.
3. **Analyze** – Local Hugging Face LLM with prompts from `docs/prompt-pipeline.md`: main topic, subtopics, and truth statements (Objective Fact / Consensus Decision / Attributed Stance).

## Project layout

- `app/main.py` – FastAPI app and API routes
- `app/pipeline/runner.py` – Pipeline orchestration and job state
- `app/pipeline/steps.py` – Preprocess, transcribe, LLM steps (all models from Hugging Face, local)
- `config.py` – Paths, limits, Hugging Face model names
- `templates/index.html` – Web UI (upload, job list, step status, results)
- `uploads/` – Uploaded files
- `outputs/` – Preprocessed WAV and intermediates

## Constraints (from project-overview)

- Max file size: 1 GB (configurable in `config.py`).
- Supported formats: `.mp3`, `.wav`, `.mp4`.
