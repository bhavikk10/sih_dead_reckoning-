"""Run the local development IDR navigation service."""

from __future__ import annotations

import uvicorn
import os

from .api import create_app


if __name__ == "__main__":
    uvicorn.run(
        create_app(),
        host=os.environ.get("IDR_HOST", "127.0.0.1"),
        port=int(os.environ.get("IDR_PORT", "8000")),
    )
