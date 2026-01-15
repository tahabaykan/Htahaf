"""
Static file serving for web UI
"""

from fastapi import APIRouter
from fastapi.responses import FileResponse, HTMLResponse
from pathlib import Path

router = APIRouter()

# Path to static files
STATIC_DIR = Path(__file__).parent.parent.parent / "static"


@router.get("/", response_class=HTMLResponse)
async def index():
    """Serve index.html"""
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return HTMLResponse("<h1>Static files not found</h1><p>Please create static/index.html</p>")


@router.get("/{file_path:path}")
async def serve_static(file_path: str):
    """Serve static files"""
    file_full_path = STATIC_DIR / file_path
    if file_full_path.exists() and file_full_path.is_file():
        return FileResponse(file_full_path)
    return {"error": "File not found"}

