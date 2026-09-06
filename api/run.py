"""Standalone API launcher.

Use from the project root with: python -m api.run
"""
import os
import uvicorn

from .server import app

if __name__ == "__main__":
    host = os.getenv("API_HOST", "0.0.0.0").strip() or "0.0.0.0"
    port = int(os.getenv("API_PORT") or os.getenv("PORT") or "8000")
    uvicorn.run(app, host=host, port=port, log_level=os.getenv("API_LOG_LEVEL", "info"))
