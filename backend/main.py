#!/usr/bin/env python3
"""
Main entry point — starts the FastAPI server.
Run with:  python main.py
Or:        uvicorn api.main:app --reload
"""
import uvicorn
from core.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.app_env == "development",
        log_level=settings.log_level.lower(),
    )
