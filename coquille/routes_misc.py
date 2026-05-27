import os

from fastapi import HTTPException
from fastapi.responses import FileResponse

from app_context import DATA_DIR, AppContext


def register(ctx: AppContext) -> None:
    state = ctx.state
    lock = ctx.lock
    settings_app = ctx.settings_app

    @settings_app.get("/status")
    def get_status():
        with lock:
            return {
                "processing_status": state["processing_status"],
                "status_message": state["status_message"],
                "current_video": state["current_video"],
                "duration": state["movement_duration"],
                "is_replaying": state["is_replaying"],
                "is_paused": state["is_paused"],
                "paused_elapsed": state["paused_elapsed"],
                "frame_count": len(state["movement_frames"]),
            }

    @settings_app.get("/video/{name}")
    def get_video(name: str):
        safe = os.path.basename(name)
        path = os.path.join(DATA_DIR, safe)
        if not os.path.exists(path):
            raise HTTPException(status_code=404, detail="Vidéo introuvable")
        return FileResponse(path)
