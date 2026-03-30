"""Run the spec editor backend."""

import sys
from pathlib import Path

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).parent))

import uvicorn

from editor.backend.app import app

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
