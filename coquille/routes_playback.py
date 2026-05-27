import time

import numpy as np
from fastapi import HTTPException
from pydantic import BaseModel
from reachy_mini.utils import create_head_pose

from app_context import ROBOT_FPS, AppContext, set_neutral

try:
    from audio_player import LecteurAudio
except ImportError as e:
    print(f"[INFO] Module audio indisponible : {e}")
    LecteurAudio = None


class SeekReq(BaseModel):
    delta: float


def register(ctx: AppContext) -> None:
    state = ctx.state
    lock = ctx.lock
    reachy_mini = ctx.reachy_mini
    settings_app = ctx.settings_app

    @settings_app.post("/play")
    def play():
        with lock:
            if not state["movement_frames"]:
                raise HTTPException(status_code=400, detail="Aucun mouvement chargé")
            if state["audio_lecteur"] is not None:
                state["audio_lecteur"].arreter()
                state["audio_lecteur"] = None
            if LecteurAudio is not None and state["audio_data"] is not None:
                lecteur = LecteurAudio(reachy_mini, state["audio_data"])
                lecteur.demarrer()
                state["audio_lecteur"] = lecteur
            state["is_paused"] = False
            state["paused_elapsed"] = 0.0
            state["is_replaying"] = True
            state["replay_start_time"] = time.time()
            state["processing_status"] = "playing"
            state["status_message"] = "Rejeu en cours..."
        return {"started": True}

    @settings_app.post("/stop")
    def stop_play():
        with lock:
            state["is_replaying"] = False
            state["is_paused"] = False
            state["paused_elapsed"] = 0.0
            if state["audio_lecteur"] is not None:
                state["audio_lecteur"].arreter()
                state["audio_lecteur"] = None
            state["processing_status"] = "ready" if state["movement_frames"] else "idle"
            state["status_message"] = "Rejeu arrêté"
        set_neutral(reachy_mini)
        return {"stopped": True}

    @settings_app.post("/pause")
    def pause_play():
        with lock:
            if not state["is_replaying"] or state["is_paused"]:
                raise HTTPException(status_code=400, detail="Pas en cours de rejeu")
            state["paused_elapsed"] = time.time() - state["replay_start_time"]
            state["is_paused"] = True
            if state["audio_lecteur"] is not None:
                state["audio_lecteur"].arreter()
                state["audio_lecteur"] = None
            state["processing_status"] = "paused"
            state["status_message"] = "Rejeu en pause"
        return {"paused": True, "elapsed": state["paused_elapsed"]}

    @settings_app.post("/resume")
    def resume_play():
        with lock:
            if not state["is_replaying"] or not state["is_paused"]:
                raise HTTPException(status_code=400, detail="Pas en pause")
            elapsed = state["paused_elapsed"]
            state["replay_start_time"] = time.time() - elapsed
            state["is_paused"] = False
            state["processing_status"] = "playing"
            state["status_message"] = "Rejeu en cours..."
            if LecteurAudio is not None and state["audio_data"] is not None:
                lecteur = LecteurAudio(reachy_mini, state["audio_data"])
                lecteur.demarrer_depuis(elapsed)
                state["audio_lecteur"] = lecteur
        return {"resumed": True, "elapsed": elapsed}

    @settings_app.post("/seek")
    def seek_play(req: SeekReq):
        with lock:
            if not state["is_replaying"] or not state["is_paused"]:
                raise HTTPException(status_code=400, detail="Seek uniquement en pause")
            new_elapsed = state["paused_elapsed"] + req.delta
            new_elapsed = max(0.0, min(new_elapsed, state["movement_duration"]))
            state["paused_elapsed"] = new_elapsed
            frames = state["movement_frames"]
            idx = min(int(new_elapsed * ROBOT_FPS), len(frames) - 1)
        f = frames[idx]
        h = f["head"]
        head_pose = create_head_pose(
            yaw=h["yaw"],
            pitch=h["pitch"],
            roll=h["roll"],
            x=h["x"],
            y=h["y"],
            z=h["z"],
            degrees=True,
        )
        reachy_mini.set_target(
            head=head_pose,
            antennas=np.array(f["antennas"], dtype=float),
            body_yaw=float(f.get("body_yaw", 0.0)),
        )
        return {"elapsed": new_elapsed}
