# Web Server

Search-only service over results in the **output bucket**. Same bucket layout: `job_state/`, `outputs/`, `rag_db/`.

## Responsibilities

- Serve a **search page** for users to search transcript segments and meetings.
- On startup (and optionally via `POST /api/sync`): check the output bucket for `job_state/`; if there are **new** completed jobs, re-index them into the local RAG and upload the updated RAG to the bucket. If there are no new jobs, use the current RAG.

## Run

```bash
cd web_server
pip install -r requirements.txt
cp .env.example .env   # then edit .env with your values
python run.py
```

## Configuration

All configuration is via environment variables. Copy `web_server/.env.example` to `web_server/.env` and set values. **Cloud Run**: set variables (and secrets) in the service’s Variables & Secrets; do not set `PORT` (Cloud Run sets it).

| Variable | Required | Description |
|----------|----------|-------------|
| `GCS_OUTPUT_BUCKET` | Yes (for search/sync) | GCS bucket with `job_state/`, `outputs/`, `rag_db/`, `metadata/`. Same as the pipeline output bucket. |
| `GCS_SIGNING_KEY_JSON` | No | Full JSON of a service account key. Needed on Cloud Run for signed URLs (`/api/audio/{job_id}`). Locally optional if using `gcloud auth application-default login`. |
| `RAG_EMBEDDING_MODEL` | No (default: `all-MiniLM-L6-v2`) | Hugging Face model for embeddings. |
| `RAG_SEARCH_LIMIT` | No (default: `20`) | Max results per search. |
| `SERVER_HOST` / `SERVER_PORT` | No | Bind address and port. Cloud Run sets `PORT` automatically. |

## Endpoints

- `GET /` – Search hub (links to transcript/meeting search).
- `GET /search/transcripts`, `GET /search/meetings` – Search UIs.
- `GET /api/search/transcripts`, `GET /api/search/meetings` – Search API.
- `GET /api/result/{job_id}` – Full result from bucket `job_state/`.
- `GET /api/audio/{job_id}` – Redirect to signed URL for WAV in `outputs/`.
- `GET /api/folders` – Folders from bucket `metadata/folders.json`.
- `POST /api/sync` – Run RAG sync in the foreground; streams progress as Server-Sent Events. Progress is saved after each indexed job, so if the request times out you can run sync again and it will continue from where it left off.
