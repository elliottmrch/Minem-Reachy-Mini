import os
import threading
from dataclasses import dataclass
from typing import Any

import numpy as np
from reachy_mini import ReachyMini
from reachy_mini.utils import create_head_pose


current_dir = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.abspath(os.path.join(current_dir, "..", "data"))

ALLOWED_VIDEO_EXT = (".mp4", ".avi", ".mov", ".webm", ".mkv")
ROBOT_FPS = 100


@dataclass
class AppContext:
    state: dict
    lock: threading.Lock
    reachy_mini: ReachyMini
    settings_app: Any


def create_initial_state() -> dict:
    return {
        "is_replaying": False,
        "replay_start_time": None,
        "movement_frames": [],
        "movement_duration": 0.0,
        "current_video": None,
        "current_movement": None,
        "processing_status": "idle",
        "status_message": "Prêt",
        "audio_data": None,
        "audio_lecteur": None,
        "is_paused": False,
        "paused_elapsed": 0.0,
        "is_live_mode": False,
        "live_processor": None,
    }


def set_neutral(reachy_mini: ReachyMini) -> None:
    head_neutre = create_head_pose(yaw=0.0, pitch=0.0, roll=0.0, degrees=True)
    reachy_mini.set_target(
        head=head_neutre,
        antennas=np.array([0.0, 0.0]),
        body_yaw=0.0,
    )


def get_processed_videos() -> list[str]:
    result = []
    if not os.path.isdir(DATA_DIR):
        return result
    for fname in sorted(os.listdir(DATA_DIR)):
        if not fname.lower().endswith(ALLOWED_VIDEO_EXT):
            continue
        stem = os.path.splitext(fname)[0]
        mvt = os.path.join(DATA_DIR, f"{stem}_signaux_mouvement.json")
        if os.path.exists(mvt):
            result.append(fname)
    return result
