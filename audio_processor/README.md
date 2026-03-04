# Audio Processor

Standalone service that processes media from a queue and writes results to the **output bucket** (so the web_server can index them). Same layout: `job_state/`, `outputs/`.

## Modes

### Local

- Watches the **`upload_queue`** folder (by default `audio_processor/upload_queue`, or `UPLOAD_QUEUE_DIR`).
- Processes media files (`.mp3`, `.wav`, `.mp4`), removes them from the folder as they are processed.
- Writes results to local `outputs/` and `job_state/` (repo root); if `GCS_OUTPUT_BUCKET` is set, also uploads there.

### Cloud

- Set **`GCS_UPLOAD_BUCKET`** (and optionally **`RUN_CLOUD=1`**) so the processor uses the upload bucket.
- Reads from **`upload_queue/`** in that bucket; processes each file; uploads results to **`GCS_OUTPUT_BUCKET`** (`job_state/`, `outputs/`); then **deletes** the file from `upload_queue/`.

## Run

From the **repo root** (so `app.pipeline` and `config` resolve):

```bash
# Local: process files from ./audio_processor/upload_queue (or UPLOAD_QUEUE_DIR)
python -m audio_processor.main

# Cloud: set env and run (reads from gs://GCS_UPLOAD_BUCKET/upload_queue/, writes to GCS_OUTPUT_BUCKET)
set GCS_UPLOAD_BUCKET=your-uploads
set GCS_OUTPUT_BUCKET=your-outputs
set RUN_CLOUD=1
python -m audio_processor.main
```

- **UPLOAD_QUEUE_DIR**: local folder for queue (default: `audio_processor/upload_queue`).
- **POLL_INTERVAL_SEC**: seconds to sleep when queue is empty (default: 10).

Uses the same pipeline and config as the main app (Whisper, LLM, etc.); ensure `.env` and dependencies (e.g. `torch`, `transformers`, `pydub`) are installed at repo root.
