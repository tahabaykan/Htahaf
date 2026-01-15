"""app/api/log_routes.py

Log Analysis and Reporting API
==============================

REST API endpoints for log viewing, filtering, and reporting.
"""

from fastapi import APIRouter, Query, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from typing import Optional
from datetime import datetime

from app.core.logger import logger
from app.core.log_capture import get_log_capture

router = APIRouter(prefix="/api/logs", tags=["Logs"])


@router.get("/")
async def get_logs(
    level: Optional[str] = Query(None, description="Filter by log level"),
    keyword: Optional[str] = Query(None, description="Filter by keyword"),
    module: Optional[str] = Query(None, description="Filter by module"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0)
) -> dict:
    """Get filtered logs"""
    try:
        log_capture = get_log_capture()
        logs = log_capture.get_logs(
            level=level,
            keyword=keyword,
            module=module,
            limit=limit,
            offset=offset
        )
        return {
            "success": True,
            "logs": logs,
            "count": len(logs),
            "limit": limit,
            "offset": offset
        }
    except Exception as e:
        logger.error(f"Error getting logs: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/statistics")
async def get_log_statistics() -> dict:
    """Get log statistics"""
    try:
        log_capture = get_log_capture()
        stats = log_capture.get_statistics()
        return {"success": True, "statistics": stats}
    except Exception as e:
        logger.error(f"Error getting statistics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/export")
async def export_logs(
    format: str = Query("json", description="json or csv"),
    level: Optional[str] = None,
    keyword: Optional[str] = None,
    module: Optional[str] = None
) -> Response:
    """Export logs"""
    try:
        log_capture = get_log_capture()
        exported = log_capture.export_logs(format=format, level=level, keyword=keyword, module=module)
        
        if format.lower() == "json":
            return Response(
                content=exported,
                media_type="application/json",
                headers={"Content-Disposition": f'attachment; filename="logs_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json"'}
            )
        elif format.lower() == "csv":
            return Response(
                content=exported,
                media_type="text/csv",
                headers={"Content-Disposition": f'attachment; filename="logs_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv"'}
            )
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported format: {format}")
    except Exception as e:
        logger.error(f"Error exporting logs: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/errors")
async def get_errors(limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0)) -> dict:
    """Get ERROR and CRITICAL logs"""
    try:
        log_capture = get_log_capture()
        error_logs = log_capture.get_logs(level="ERROR", limit=limit, offset=offset)
        critical_logs = log_capture.get_logs(level="CRITICAL", limit=limit, offset=offset)
        all_errors = error_logs + critical_logs
        all_errors.sort(key=lambda x: x['timestamp'], reverse=True)
        paginated = all_errors[offset:offset + limit]
        return {"success": True, "errors": paginated, "count": len(paginated), "total_errors": len(all_errors)}
    except Exception as e:
        logger.error(f"Error getting error logs: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/warnings")
async def get_warnings(limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0)) -> dict:
    """Get WARNING logs"""
    try:
        log_capture = get_log_capture()
        logs = log_capture.get_logs(level="WARNING", limit=limit, offset=offset)
        return {"success": True, "warnings": logs, "count": len(logs)}
    except Exception as e:
        logger.error(f"Error getting warning logs: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/failed")
async def get_failed(limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0)) -> dict:
    """Get logs with 'failed' keyword"""
    try:
        log_capture = get_log_capture()
        logs = log_capture.get_logs(keyword="failed", limit=limit, offset=offset)
        return {"success": True, "failed": logs, "count": len(logs)}
    except Exception as e:
        logger.error(f"Error getting failed logs: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/clear")
async def clear_logs() -> dict:
    """Clear all logs"""
    try:
        log_capture = get_log_capture()
        log_capture.clear_logs()
        return {"success": True, "message": "All logs cleared"}
    except Exception as e:
        logger.error(f"Error clearing logs: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.websocket("/stream")
async def websocket_log_stream(websocket: WebSocket):
    """WebSocket for real-time log streaming"""
    await websocket.accept()
    try:
        log_capture = get_log_capture()
        log_capture.add_subscriber(websocket)
        logger.info("📡 Log stream WebSocket connected")
        while True:
            try:
                data = await websocket.receive_text()
                if data == "ping":
                    await websocket.send_text("pong")
            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
                break
    except Exception as e:
        logger.error(f"Error in log stream: {e}", exc_info=True)
    finally:
        log_capture.remove_subscriber(websocket)
        logger.info("📡 Log stream WebSocket disconnected")
