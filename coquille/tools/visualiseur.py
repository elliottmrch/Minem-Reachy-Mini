import os
import json
import math
import cv2
import numpy as np
import mediapipe as mp

SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
COQUILLE_DIR = os.path.dirname(SCRIPT_DIR)
DATA_DIR     = os.path.abspath(os.path.join(COQUILLE_DIR, "..", "data"))

# Même connexions que dans extracteur.py (mêmes constantes MediaPipe)
_VIS_CONNECTIONS = {
    "lips":           mp.solutions.face_mesh.FACEMESH_LIPS,
    "left_eye":       mp.solutions.face_mesh.FACEMESH_LEFT_EYE,
    "right_eye":      mp.solutions.face_mesh.FACEMESH_RIGHT_EYE,
    "left_eyebrow":   mp.solutions.face_mesh.FACEMESH_LEFT_EYEBROW,
    "right_eyebrow":  mp.solutions.face_mesh.FACEMESH_RIGHT_EYEBROW,
}
# Couleurs BGR par feature
_COLORS = {
    "lips":          (60,  100, 255),  # rouge-orangé
    "left_eye":      (255, 200, 50 ),  # cyan-jaune
    "right_eye":     (255, 200, 50 ),
    "left_eyebrow":  (50,  220, 80 ),  # vert
    "right_eyebrow": (50,  220, 80 ),
}


def visualiser_video(video_path: str, json_path: str) -> None:
    """
    Lit la vidéo originale et le JSON de signaux, produit une vidéo annotée
    et la joue dans une fenêtre OpenCV. Appuyer sur 'q' pour quitter.
    Les annotations proviennent uniquement du JSON (pas de re-traitement MediaPipe).
    """
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    frames_data = data["frames"]
    video_name  = os.path.splitext(os.path.basename(video_path))[0]
    annot_path  = os.path.join(DATA_DIR, f"{video_name}_annote.mp4")

    cap = cv2.VideoCapture(video_path)
    fps = data["metadata"]["fps"]
    w   = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h   = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total = data["metadata"]["total_frames"]

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(annot_path, fourcc, fps, (w, h))

    print(f"\n[INFO] Génération de la vidéo annotée + affichage (appuyer sur 'q' pour arrêter)...")

    for frame_idx, record in enumerate(frames_data):
        ok, frame = cap.read()
        if not ok:
            break

        annotated = _annoter_frame(frame, record, w, h)
        writer.write(annotated)

        cv2.imshow("Coquille — Jalon 2 — Vérification signaux", annotated)
        wait_ms = max(1, int(1000 / fps))
        if cv2.waitKey(wait_ms) & 0xFF == ord("q"):
            break

        if frame_idx % 50 == 0:
            print(f"  [{frame_idx}/{total}]", end="\r", flush=True)

    cap.release()
    writer.release()
    cv2.destroyAllWindows()

    print(f"\n[OK] Vidéo annotée → {annot_path}")


def _annoter_frame(frame: np.ndarray, record: dict, w: int, h: int) -> np.ndarray:
    _draw_timestamp(frame, record["timestamp"])

    if not record["face_detected"]:
        cv2.putText(frame, "Pas de visage", (10, 50),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 200), 2)
        return frame

    fp = record["face_position"]
    ho = record["head_orientation"]

    # Rectangle englobant (vert)
    x1 = int((fp["cx"] - fp["width"]  / 2) * w)
    y1 = int((fp["cy"] - fp["height"] / 2) * h)
    x2 = int((fp["cx"] + fp["width"]  / 2) * w)
    y2 = int((fp["cy"] + fp["height"] / 2) * h)
    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 200, 0), 2)

    # Landmarks : connexions colorées + points blancs
    if record["landmarks_vis"]:
        _draw_landmarks(frame, record["landmarks_vis"], w, h)

    # Flèche d'orientation 2D (yaw + pitch → direction dans l'image)
    cx_px    = int(fp["cx"] * w)
    cy_px    = int(fp["cy"] * h)
    arrow_r  = int(fp["height"] * h * 0.35)
    dx = int(arrow_r * math.sin(math.radians(ho["yaw"])))
    dy = int(-arrow_r * math.sin(math.radians(ho["pitch"])))
    cv2.arrowedLine(frame, (cx_px, cy_px), (cx_px + dx, cy_px + dy),
                    (0, 220, 255), 2, tipLength=0.3)

    # Overlay signaux (bas-gauche)
    lines = [
        f"Yaw  : {ho['yaw']:+.1f}deg",
        f"Pitch: {ho['pitch']:+.1f}deg",
        f"Roll : {ho['roll']:+.1f}deg",
        f"Bouche : {record['mouth_opening']:.3f}",
        f"OeilG  : {record['left_eye_opening']:.3f}",
        f"OeilD  : {record['right_eye_opening']:.3f}",
        f"Sourire: {record['smile_index']:.3f}",
        f"Sourcil: {record['eyebrow_raise']:.3f}",
    ]
    _draw_overlay(frame, lines, h)

    return frame


def _draw_timestamp(frame: np.ndarray, timestamp: float) -> None:
    cv2.putText(frame, f"t={timestamp:.3f}s", (8, 22),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (220, 220, 220), 1, cv2.LINE_AA)


def _draw_overlay(frame: np.ndarray, lines: list[str], h: int) -> None:
    font   = cv2.FONT_HERSHEY_SIMPLEX
    scale  = 0.45
    line_h = 18
    pad    = 6
    box_h  = len(lines) * line_h + pad * 2
    box_w  = 185
    y0     = h - box_h - 8
    overlay = frame.copy()
    cv2.rectangle(overlay, (6, y0), (6 + box_w, y0 + box_h), (20, 20, 20), -1)
    cv2.addWeighted(overlay, 0.55, frame, 0.45, 0, frame)
    for i, line in enumerate(lines):
        y = y0 + pad + (i + 1) * line_h - 4
        cv2.putText(frame, line, (10, y), font, scale, (200, 230, 200), 1, cv2.LINE_AA)


def _draw_landmarks(frame: np.ndarray, landmarks_vis: dict, w: int, h: int) -> None:
    # Traits colorés par feature
    for feature, connections in _VIS_CONNECTIONS.items():
        color = _COLORS[feature]
        for (a, b) in connections:
            pa = landmarks_vis.get(str(a))
            pb = landmarks_vis.get(str(b))
            if pa and pb:
                cv2.line(frame,
                         (int(pa[0] * w), int(pa[1] * h)),
                         (int(pb[0] * w), int(pb[1] * h)),
                         color, 1, cv2.LINE_AA)
    # Points blancs sur chaque landmark
    for coords in landmarks_vis.values():
        cv2.circle(frame, (int(coords[0] * w), int(coords[1] * h)), 1, (255, 255, 255), -1)
