import os
import uvicorn
from .server import app
if __name__ == "__main__":
    uvicorn.run(app, host=os.getenv("API_HOST","127.0.0.1"), port=int(os.getenv("API_PORT","8000")))
