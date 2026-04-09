"""
Static file serving for web UI
"""

from fastapi import APIRouter
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pathlib import Path

router = APIRouter()

# Path to static files
STATIC_DIR = Path(__file__).parent.parent.parent / "static"

# Only serve files with these extensions as static files
STATIC_EXTENSIONS = {
    '.html', '.css', '.js', '.jsx', '.ts', '.tsx',
    '.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico', '.webp',
    '.woff', '.woff2', '.ttf', '.eot',
    '.json', '.map', '.txt', '.xml', '.webmanifest',
}


@router.get("/{file_path:path}")
async def serve_static(file_path: str):
    """Serve static files — only for actual file paths, NOT API routes."""
    # Skip API-like paths (no extension or non-static extension)
    suffix = Path(file_path).suffix.lower()
    if not suffix or suffix not in STATIC_EXTENSIONS:
        # Return 404 so FastAPI tries other routes
        return JSONResponse(status_code=404, content={"error": "Not found"})
    
    file_full_path = STATIC_DIR / file_path
    if file_full_path.exists() and file_full_path.is_file():
        return FileResponse(file_full_path)
    return JSONResponse(status_code=404, content={"error": "File not found"})

