import threading
import time

import cv2
import mediapipe as mp
import numpy as np
from reachy_mini import ReachyMini, ReachyMiniApp
from reachy_mini.utils import create_head_pose

from extracteur import ExtracteurSignaux, _VIS_CONNECTIONS
from mapper import (
    ANT_EYEBROW_FACTOR, ANTENNA_MAX,
    BODY_YAW_DEAD, BODY_YAW_FACTOR, BODY_YAW_MAX,
    HEAD_X_EYE_FACTOR, HEAD_Z_SMILE_FACTOR,
    PITCH_FACTOR, PITCH_MAX, PITCH_MOUTH_FACTOR,
    ROLL_FACTOR, ROLL_MAX,
    TRANS_MAX,
    YAW_FACTOR, YAW_MAX,
    _clamp,
)

WARMUP_SECONDS = 3
SEND_HZ        = 25

# Détection de parole — oscillation de roll basée sur la vélocité de la bouche
SPEECH_ROLL_AMP    = 5.0   # amplitude max de l'oscillation (degrés)
SPEECH_FREQ        = 2.5   # fréquence d'oscillation (Hz) — rythme naturel de parole
SPEECH_DECAY       = 0.88  # décroissance par frame (~300ms de sustain à 25Hz)
SPEECH_SENSITIVITY = 60.0  # amplification de la vélocité bouche → énergie [0–1]

ANT_SMOOTH = 0.35  # lissage EMA des antennes (plus bas = plus doux, plus lent)

# Couleurs par région de landmarks
_REGION_COLORS = {
    "lips":          (80,  200, 80),
    "left_eye":      (255, 180, 50),
    "right_eye":     (255, 180, 50),
    "left_eyebrow":  (80,  180, 255),
    "right_eyebrow": (80,  180, 255),
}


def _annoter_frame(frame: np.ndarray, signaux: dict | None, robot: dict) -> np.ndarray:
    frame = cv2.flip(frame, 1)
    h, w = frame.shape[:2]

    if signaux and signaux.get("landmarks_vis"):
        lm = signaux["landmarks_vis"]
        for region, conns in _VIS_CONNECTIONS.items():
            color = _REGION_COLORS.get(region, (200, 200, 200))
            for a, b in conns:
                ka, kb = str(a), str(b)
                if ka in lm and kb in lm:
                    # flip x pour le miroir
                    ax = int((1.0 - lm[ka][0]) * w)
                    ay = int(lm[ka][1] * h)
                    bx = int((1.0 - lm[kb][0]) * w)
                    by = int(lm[kb][1] * h)
                    cv2.line(frame, (ax, ay), (bx, by), color, 1, cv2.LINE_AA)

    # Overlay signal
    lines_left = []
    if signaux:
        ho = signaux.get("head_orientation") or {}
        lines_left = [
            f"Yaw  : {ho.get('yaw', 0):+.1f}",
            f"Pitch: {ho.get('pitch', 0):+.1f}",
            f"Roll : {ho.get('roll', 0):+.1f}",
            f"Bouche  : {signaux.get('mouth_opening', 0):.3f}",
            f"OeilG   : {signaux.get('left_eye_opening', 0):.3f}",
            f"OeilD   : {signaux.get('right_eye_opening', 0):.3f}",
            f"Sourire : {signaux.get('smile_index', 0):.3f}",
            f"SourcilG: {signaux.get('eyebrow_raise_left', 0):.3f}",
            f"SourcilD: {signaux.get('eyebrow_raise_right', 0):.3f}",
        ]
    else:
        lines_left = ["Aucun visage detecte"]

    lines_right = [
        "-- Robot --",
        f"AntG: {robot['ant_l']:+.2f}",
        f"AntD: {robot['ant_r']:+.2f}",
        f"BodyY: {robot['body_yaw']:+.3f}",
    ]

    for i, line in enumerate(lines_left):
        cv2.putText(frame, line, (8, 20 + i * 18),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (30, 30, 30), 3, cv2.LINE_AA)
        cv2.putText(frame, line, (8, 20 + i * 18),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 100), 1, cv2.LINE_AA)

    for i, line in enumerate(lines_right):
        cv2.putText(frame, line, (w - 140, 20 + i * 18),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (30, 30, 30), 3, cv2.LINE_AA)
        cv2.putText(frame, line, (w - 140, 20 + i * 18),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (80, 180, 255), 1, cv2.LINE_AA)

    cv2.putText(frame, "q : quitter", (w // 2 - 40, h - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (160, 160, 160), 1, cv2.LINE_AA)
    return frame


class WebcamDirect(ReachyMiniApp):
    custom_app_url: str | None = None
    request_media_backend: str | None = "no_media"

    cam_index: int = 0

    def run(self, reachy_mini: ReachyMini, stop_event: threading.Event):
        cap = cv2.VideoCapture(self.cam_index)
        if not cap.isOpened():
            print(f"[ERREUR] Impossible d'ouvrir la webcam {self.cam_index}")
            return

        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        extracteur = ExtracteurSignaux(w, h)

        mp_face = mp.solutions.face_mesh.FaceMesh(
            static_image_mode=False,
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )

        # --- Calibration ---
        print(f"\n[INFO] Calibration ({WARMUP_SECONDS}s) — restez face à la caméra, visage neutre...")
        buf = {k: [] for k in ("pitch_deg", "smile_index", "mouth_opening",
                               "left_eye_opening", "right_eye_opening",
                               "eyebrow_raise_left", "eyebrow_raise_right")}

        t_end = time.time() + WARMUP_SECONDS
        while time.time() < t_end and not stop_event.is_set():
            ok, frame = cap.read()
            if not ok:
                continue
            results = mp_face.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            if results.multi_face_landmarks:
                s = extracteur.extraire(results.multi_face_landmarks[0])
                buf["pitch_deg"].append(s["head_orientation"]["pitch"])
                for k in ("smile_index", "mouth_opening", "left_eye_opening",
                          "right_eye_opening", "eyebrow_raise_left", "eyebrow_raise_right"):
                    buf[k].append(s[k])

            remaining = t_end - time.time()
            display = cv2.flip(frame, 1)
            cv2.putText(display, f"Calibration... {remaining:.1f}s",
                        (w // 2 - 120, h // 2),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 200, 255), 2, cv2.LINE_AA)
            cv2.putText(display, "Restez face a la camera, visage neutre",
                        (w // 2 - 210, h // 2 + 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1, cv2.LINE_AA)
            cv2.imshow("Webcam Direct - Reachy Mini", display)
            cv2.waitKey(1)

        offsets = {k: float(np.median(v)) if v else 0.0 for k, v in buf.items()}
        print(f"\n[OK] Calibration terminée — pitch={offsets['pitch_deg']:+.1f}° "
              f"bouche={offsets['mouth_opening']:.3f} sourire={offsets['smile_index']:.3f}")
        print("[INFO] Démarrage. Appuyez sur 'q' dans la fenêtre ou Ctrl+C pour arrêter.\n")

        # --- Boucle principale ---
        interval = 1.0 / SEND_HZ
        last = {"yaw": 0.0, "pitch": 0.0, "roll": 0.0,
                "x": 0.0, "y": 0.0, "z": 0.0,
                "ant_l": 0.0, "ant_r": 0.0, "body_yaw": 0.0}
        last_signaux  = None
        speech_energy = 0.0
        prev_mouth_c  = 0.0
        t_start       = time.time()

        while not stop_event.is_set():
            t0 = time.time()

            ok, frame = cap.read()
            if not ok:
                time.sleep(interval)
                continue

            results = mp_face.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            if results.multi_face_landmarks:
                s  = extracteur.extraire(results.multi_face_landmarks[0])
                ho = s["head_orientation"]
                last_signaux = s

                pitch_c = ho["pitch"]              - offsets["pitch_deg"]
                mouth_c = s["mouth_opening"]       - offsets["mouth_opening"]
                smile_c = s["smile_index"]         - offsets["smile_index"]
                eye_l_c = s["left_eye_opening"]    - offsets["left_eye_opening"]
                eye_r_c = s["right_eye_opening"]   - offsets["right_eye_opening"]
                eb_l_c  = s["eyebrow_raise_left"]  - offsets["eyebrow_raise_left"]
                eb_r_c  = s["eyebrow_raise_right"] - offsets["eyebrow_raise_right"]

                # Énergie de parole : vélocité de la bouche lissée par décroissance
                mouth_velocity = abs(mouth_c - prev_mouth_c)
                speech_energy  = (SPEECH_DECAY * speech_energy
                                  + (1 - SPEECH_DECAY) * min(mouth_velocity * SPEECH_SENSITIVITY, 1.0))
                prev_mouth_c   = mouth_c

                t_elapsed = time.time() - t_start
                speech_roll = speech_energy * SPEECH_ROLL_AMP * np.sin(2 * np.pi * SPEECH_FREQ * t_elapsed)

                yaw   = _clamp(ho["yaw"] * YAW_FACTOR, -YAW_MAX, YAW_MAX)
                pitch = _clamp(pitch_c   * PITCH_FACTOR + mouth_c * PITCH_MOUTH_FACTOR,
                               -PITCH_MAX, PITCH_MAX)
                roll  = _clamp(ho["roll"] * ROLL_FACTOR + speech_roll, -ROLL_MAX, ROLL_MAX)

                eye_mean = (eye_l_c + eye_r_c) / 2.0
                head_x = _clamp(eye_mean * HEAD_X_EYE_FACTOR, -TRANS_MAX, TRANS_MAX)
                head_z = _clamp(smile_c  * HEAD_Z_SMILE_FACTOR, -TRANS_MAX, TRANS_MAX)

                ant_l_raw = float(np.clip(-eb_l_c * ANT_EYEBROW_FACTOR, -ANTENNA_MAX, ANTENNA_MAX))
                ant_r_raw = float(np.clip( eb_r_c * ANT_EYEBROW_FACTOR, -ANTENNA_MAX, ANTENNA_MAX))
                ant_l = ANT_SMOOTH * ant_l_raw + (1 - ANT_SMOOTH) * last["ant_l"]
                ant_r = ANT_SMOOTH * ant_r_raw + (1 - ANT_SMOOTH) * last["ant_r"]

                cx_dev = s["face_position"]["cx"] - 0.5
                if abs(cx_dev) < BODY_YAW_DEAD:
                    cx_dev = 0.0
                body_yaw = _clamp(cx_dev * BODY_YAW_FACTOR, -BODY_YAW_MAX, BODY_YAW_MAX)

                last = {"yaw": yaw, "pitch": pitch, "roll": roll,
                        "x": head_x, "y": 0.0, "z": head_z,
                        "ant_l": ant_l, "ant_r": ant_r, "body_yaw": body_yaw}

            # Envoi au robot
            head_pose = create_head_pose(
                yaw=last["yaw"], pitch=last["pitch"], roll=last["roll"],
                x=last["x"], y=last["y"], z=last["z"],
                degrees=True,
            )
            reachy_mini.set_target(
                head=head_pose,
                antennas=np.array([last["ant_l"], last["ant_r"]]),
                body_yaw=last["body_yaw"],
            )

            # Affichage
            annotated = _annoter_frame(frame.copy(), last_signaux, last)
            cv2.imshow("Webcam Direct - Reachy Mini", annotated)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

            time.sleep(max(0.0, interval - (time.time() - t0)))

        # Retour neutre + nettoyage
        head_neutre = create_head_pose(yaw=0.0, pitch=0.0, roll=0.0, degrees=True)
        reachy_mini.set_target(head=head_neutre, antennas=np.array([0.0, 0.0]))
        cap.release()
        mp_face.close()
        cv2.destroyAllWindows()
        print("\n[OK] Mode webcam arrêté.")


def lancer_webcam_direct(cam_index: int = 0):
    print(f"\n[INFO] Démarrage du mode webcam direct (caméra {cam_index})...")
    app = WebcamDirect()
    app.cam_index = cam_index
    try:
        app.wrapped_run()
    except KeyboardInterrupt:
        app.stop()


if __name__ == "__main__":
    import sys
    idx = int(sys.argv[1]) if len(sys.argv) >= 2 else 0
    lancer_webcam_direct(idx)
