"""
AgentX — Backend Entry Point
Run with: python main.py  OR  uvicorn main:app --reload
"""

import uvicorn
from app import app
from config.settings import settings

if __name__ == "__main__":
    uvicorn.run(
        "app:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=not settings.is_production,
        log_level=settings.app_log_level.lower(),
        access_log=True,
        workers=1,  # Single worker — pipeline uses asyncio internally
    )
