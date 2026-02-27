"""Run the Audio Processing Pipeline web app or process a single file via CLI."""
import sys
import uuid
from pathlib import Path

from config import ALLOWED_EXTENSIONS, SERVER_HOST, SERVER_PORT


def run_cli(media_path: Path) -> None:
    """Process a single media file and print pipeline results to the console."""
    from app.pipeline.runner import get_job, run_pipeline
    from app.pipeline.steps import ensure_ffmpeg_available

    import logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    log = logging.getLogger("audio_pipeline")
    log.setLevel(logging.INFO)

    path = media_path.resolve()
    if not path.is_file():
        print(f"Error: file not found: {path}", file=sys.stderr)
        sys.exit(1)

    suffix = path.suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        print(
            f"Error: unsupported format '{suffix}'. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
            file=sys.stderr,
        )
        sys.exit(1)

    ok, msg = ensure_ffmpeg_available()
    if not ok:
        if suffix != ".wav":
            print(f"Warning: {msg}. Non-WAV files may fail.", file=sys.stderr)

    job_id = uuid.uuid4().hex
    print(f"Processing: {path.name} (job_id={job_id})\n")
    run_pipeline(path, path.name, job_id=job_id, file_hash=None, folder_id=None)

    state = get_job(job_id)
    if not state:
        print("Error: pipeline finished but job state not found.", file=sys.stderr)
        sys.exit(1)

    # Print step results
    print("--- Pipeline steps ---")
    for step_id, step in state.steps.items():
        status = step.status.value
        detail = step.detail or step.message
        print(f"  {step.name}: {status}" + (f" — {detail}" if detail else ""))

    if state.status == "failed":
        print(f"\nPipeline failed: {state.error}", file=sys.stderr)
        sys.exit(1)
    if state.status == "cancelled":
        print("\nPipeline cancelled.", file=sys.stderr)
        sys.exit(1)

    # Print final result
    r = state.result
    print("\n--- Transcription ---")
    print(r.get("transcription", "(none)"))
    if r.get("timestamps"):
        print(f"\nSegments: {len(r['timestamps'])}")
    print("\n--- Main topic ---")
    print(r.get("main_topic", "(none)"))
    if r.get("subtopics"):
        print("\n--- Subtopics ---")
        for s in r["subtopics"]:
            print(f"  • {s}")
    if r.get("truth_statements_md"):
        print("\n--- Truth statements ---")
        print(r["truth_statements_md"])
    print()


if __name__ == "__main__":
    if len(sys.argv) >= 2:
        arg = sys.argv[1]
        path = Path(arg)
        if path.suffix.lower() in ALLOWED_EXTENSIONS:
            run_cli(path)
            sys.exit(0)

    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=SERVER_HOST,
        port=SERVER_PORT,
        reload=True,
    )
