"""Run the Audio Processing Pipeline web app."""
import uvicorn

from config import SERVER_HOST, SERVER_PORT

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=SERVER_HOST,
        port=SERVER_PORT,
        reload=True,
    )
