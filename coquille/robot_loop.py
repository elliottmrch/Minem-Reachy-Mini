import threading
import time

import numpy as np
from reachy_mini.utils import create_head_pose

from app_context import ROBOT_FPS, AppContext, set_neutral


def run(ctx: AppContext, stop_event: threading.Event) -> None:
    state = ctx.state
    lock = ctx.lock
    reachy_mini = ctx.reachy_mini

    period = 1.0 / ROBOT_FPS
    set_neutral(reachy_mini)

    while not stop_event.is_set():
        with lock:
            replaying = state["is_replaying"]
            is_paused = state["is_paused"]
            frames = state["movement_frames"]
            t0 = state["replay_start_time"]
            is_live = state["is_live_mode"]

        if is_live:
            time.sleep(period)
            continue

        if replaying and not is_paused and frames and t0 is not None:
            t = time.time() - t0
            idx = int(t * ROBOT_FPS)
            if idx >= len(frames):
                with lock:
                    state["is_replaying"] = False
                    if state["audio_lecteur"] is not None:
                        state["audio_lecteur"].arreter()
                        state["audio_lecteur"] = None
                    state["processing_status"] = "ready"
                    state["status_message"] = "Rejeu terminé"
                set_neutral(reachy_mini)
            else:
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

        time.sleep(period)
