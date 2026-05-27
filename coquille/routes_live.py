from fastapi import HTTPException
from fastapi.responses import StreamingResponse

from app_context import AppContext, set_neutral

try:
    from live import LiveProcessor
except ImportError as e:
    print(f"[INFO] Module live indisponible : {e}")
    LiveProcessor = None


def register(ctx: AppContext) -> None:
    state = ctx.state
    lock = ctx.lock
    reachy_mini = ctx.reachy_mini
    settings_app = ctx.settings_app

    @settings_app.post("/live/start")
    def live_start():
        if LiveProcessor is None:
            raise HTTPException(status_code=500, detail="Module live indisponible")
        with lock:
            if state["is_replaying"]:
                state["is_replaying"] = False
                if state["audio_lecteur"] is not None:
                    state["audio_lecteur"].arreter()
                    state["audio_lecteur"] = None
                state["is_paused"] = False
                state["paused_elapsed"] = 0.0
                state["processing_status"] = "ready" if state["movement_frames"] else "idle"
            if state["live_processor"] is not None:
                state["live_processor"].stop()
            proc = LiveProcessor(reachy_mini)
            proc.start()
            state["live_processor"] = proc
            state["is_live_mode"] = True
        return {"started": True}

    @settings_app.post("/live/stop")
    def live_stop():
        with lock:
            proc = state["live_processor"]
            state["is_live_mode"] = False
            state["live_processor"] = None
        if proc is not None:
            proc.stop()
        set_neutral(reachy_mini)
        return {"stopped": True}

    @settings_app.get("/live/stream")
    async def live_stream():
        import asyncio

        async def _mjpeg():
            with lock:
                proc = state["live_processor"]
            while True:
                with lock:
                    proc = state["live_processor"]
                if proc is None:
                    break
                frame = proc.get_latest_frame()
                if frame:
                    yield (
                        b"--frame\r\n"
                        b"Content-Type: image/jpeg\r\n\r\n"
                        + frame
                        + b"\r\n"
                    )
                await asyncio.sleep(1 / 30)

        return StreamingResponse(
            _mjpeg(),
            media_type="multipart/x-mixed-replace; boundary=frame",
        )

    @settings_app.get("/live/status")
    def live_status():
        with lock:
            proc = state["live_processor"]
            is_live = state["is_live_mode"]
        calibrated = proc.is_calibrated() if proc is not None else False
        return {"is_live": is_live, "calibrated": calibrated}
