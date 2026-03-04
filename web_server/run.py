"""Run the web server (search over output bucket results)."""
import os
import sys
from pathlib import Path

# Ensure web_server is on path so "config" and "app" resolve
sys.path.insert(0, str(Path(__file__).resolve().parent))

if __name__ == "__main__":
    import uvicorn
    from config import SERVER_HOST, SERVER_PORT
    uvicorn.run(
        "app.main:app",
        host=SERVER_HOST,
        port=SERVER_PORT,
        reload=os.getenv("RELOAD", "0").strip().lower() in ("1", "true", "yes"),
    )
