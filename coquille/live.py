import threading
import time

import cv2
import mediapipe as mp
import numpy as np
from reachy_mini.utils import create_head_pose

from extracteur import ExtracteurSignaux
from mapper import (
    ANT_BROW_DEAD,
    ANT_EYEBROW_FACTOR,
    ANTENNA_MAX,
    BODY_YAW_DEAD,
    BODY_YAW_FACTOR,
    BODY_YAW_MAX,
    HEAD_X_EYE_DEAD,
    HEAD_X_EYE_FACTOR,
    HEAD_Z_SMILE_FACTOR,
    PITCH_FACTOR,
    PITCH_MAX,
    PITCH_MOUTH_FACTOR,
    ROLL_FACTOR,
    ROLL_MAX,
    ROLL_MOUTH_FACTOR,
    TRANS_MAX,
    YAW_FACTOR,
    YAW_MAX,
    _clamp,
)

CALIB_FRAMES = 30


class LiveProcessor:
    def __init__(self, reachy_mini, camera_index: int = 0):
        self._reachy = reachy_mini
        self._camera_index = camera_index
        self._running = False
        self._lock = threading.Lock()
        self._latest_frame: bytes | None = None
        self._calibrated = False
        self._thread: threading.Thread | None = None

    def start(self):
        if self._running:
            return
        self._running = True
        self._calibrated = False
        self._latest_frame = None
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=3.0)
            self._thread = None
        with self._lock:
            self._latest_frame = None
            self._calibrated = False

    def get_latest_frame(self) -> bytes | None:
        with self._lock:
            return self._latest_frame

    def is_calibrated(self) -> bool:
        with self._lock:
            return self._calibrated

    def _loop(self):
        cap = cv2.VideoCapture(self._camera_index)
        if not cap.isOpened():
            print("[LIVE] Impossible d'ouvrir la caméra")
            self._running = False
            return

        mp_face = mp.solutions.face_mesh.FaceMesh(
            static_image_mode=False,
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )

        extracteur: ExtracteurSignaux | None = None
        calib_buf: list[dict] = []
        baselines: dict | None = None

        try:
            while self._running:
                ok, frame = cap.read()
                if not ok:
                    time.sleep(0.01)
                    continue

                h, w = frame.shape[:2]
                if extracteur is None:
                    extracteur = ExtracteurSignaux(w, h)

                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                results = mp_face.process(rgb)

                if results.multi_face_landmarks:
                    signaux = extracteur.extraire(results.multi_face_landmarks[0])

                    if baselines is None:
                        calib_buf.append(signaux)
                        if len(calib_buf) >= CALIB_FRAMES:
                            baselines = self._calibrer(calib_buf)
                            with self._lock:
                                self._calibrated = True
                            print("[LIVE] Calibration terminée")
                    else:
                        mouvement = self._mapper_frame(signaux, baselines)
                        self._appliquer_robot(mouvement)

                _, jpeg = cv2.imencode(".jpg", frame)
                with self._lock:
                    self._latest_frame = jpeg.tobytes()

        finally:
            cap.release()
            mp_face.close()

    def _calibrer(self, frames: list[dict]) -> dict:
        pitches = [f["head_orientation"]["pitch"] for f in frames]
        pitch_offset = float(np.median(pitches))

        keys = (
            "smile_index",
            "mouth_opening",
            "left_eye_opening",
            "right_eye_opening",
            "eyebrow_raise_left",
            "eyebrow_raise_right",
        )
        offsets = {k: float(np.median([f[k] for f in frames])) for k in keys}

        print(
            f"[LIVE] pitch_offset={pitch_offset:+.1f}° "
            f"smile={offsets['smile_index']:.3f} "
            f"mouth={offsets['mouth_opening']:.3f}"
        )
        return {"pitch_offset": pitch_offset, **offsets}

    def _mapper_frame(self, signaux: dict, baselines: dict) -> dict:
        ho = signaux["head_orientation"]
        fp = signaux["face_position"]

        yaw_deg = ho["yaw"]
        pitch_deg = ho["pitch"] - baselines["pitch_offset"]
        roll_deg = ho["roll"]

        mouth_c = signaux["mouth_opening"] - baselines["mouth_opening"]
        smile = signaux["smile_index"] - baselines["smile_index"]
        eye_l = signaux["left_eye_opening"] - baselines["left_eye_opening"]
        eye_r = signaux["right_eye_opening"] - baselines["right_eye_opening"]
        eb_l = signaux["eyebrow_raise_left"] - baselines["eyebrow_raise_left"]
        eb_r = signaux["eyebrow_raise_right"] - baselines["eyebrow_raise_right"]

        yaw = _clamp(yaw_deg * YAW_FACTOR, -YAW_MAX, YAW_MAX)
        pitch = _clamp(
            pitch_deg * PITCH_FACTOR + mouth_c * PITCH_MOUTH_FACTOR, -PITCH_MAX, PITCH_MAX
        )
        roll = _clamp(
            roll_deg * ROLL_FACTOR + mouth_c * ROLL_MOUTH_FACTOR, -ROLL_MAX, ROLL_MAX
        )

        eye_mean = (eye_l + eye_r) / 2.0
        eye_mean = eye_mean if abs(eye_mean) > HEAD_X_EYE_DEAD else 0.0
        head_x = _clamp(eye_mean * HEAD_X_EYE_FACTOR, -TRANS_MAX, TRANS_MAX)
        head_z = _clamp(smile * HEAD_Z_SMILE_FACTOR, -TRANS_MAX, TRANS_MAX)

        eb_l = eb_l if abs(eb_l) > ANT_BROW_DEAD else 0.0
        eb_r = eb_r if abs(eb_r) > ANT_BROW_DEAD else 0.0
        ant_l = _clamp(-eb_l * ANT_EYEBROW_FACTOR, -ANTENNA_MAX, ANTENNA_MAX)
        ant_r = _clamp(eb_r * ANT_EYEBROW_FACTOR, -ANTENNA_MAX, ANTENNA_MAX)

        cx_dev = fp["cx"] - 0.5
        if abs(cx_dev) < BODY_YAW_DEAD:
            cx_dev = 0.0
        body_yaw = _clamp(cx_dev * BODY_YAW_FACTOR, -BODY_YAW_MAX, BODY_YAW_MAX)

        return {
            "head": {"yaw": yaw, "pitch": pitch, "roll": roll, "x": head_x, "y": 0.0, "z": head_z},
            "antennas": [ant_l, ant_r],
            "body_yaw": body_yaw,
        }

    def _appliquer_robot(self, mouvement: dict):
        h = mouvement["head"]
        head_pose = create_head_pose(
            yaw=h["yaw"],
            pitch=h["pitch"],
            roll=h["roll"],
            x=h["x"],
            y=h["y"],
            z=h["z"],
            degrees=True,
        )
        self._reachy.set_target(
            head=head_pose,
            antennas=np.array(mouvement["antennas"], dtype=float),
            body_yaw=float(mouvement["body_yaw"]),
        )
