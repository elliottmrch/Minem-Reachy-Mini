import os
import json
import cv2
import numpy as np
import mediapipe as mp

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "data"))

_VIS_CONNECTIONS = {
    "lips": mp.solutions.face_mesh.FACEMESH_LIPS,
    "left_eye": mp.solutions.face_mesh.FACEMESH_LEFT_EYE,
    "right_eye": mp.solutions.face_mesh.FACEMESH_RIGHT_EYE,
    "left_eyebrow": mp.solutions.face_mesh.FACEMESH_LEFT_EYEBROW,
    "right_eyebrow": mp.solutions.face_mesh.FACEMESH_RIGHT_EYEBROW,
}

_VIS_INDICES = frozenset(
    idx
    for conns in _VIS_CONNECTIONS.values()
    for (a, b) in conns
    for idx in (a, b)
)

class ExtracteurSignaux:
    def __init__(self, frame_width: int, frame_height: int):
        self.w = frame_width
        self.h = frame_height

    def extraire(self, face_landmarks) -> dict:
        lm = face_landmarks.landmark
        face_pos = self._calc_face_position(lm)
        face_h = face_pos["height"]
        eb = self._calc_eyebrow_raise(lm)
        return {
            "face_position": face_pos,
            "head_orientation": self._calc_head_orientation(lm),
            "mouth_opening": round(self._calc_mouth_opening(lm, face_h), 4),
            "left_eye_opening": round(self._calc_ear(lm, gauche=True), 4),
            "right_eye_opening": round(self._calc_ear(lm, gauche=False), 4),
            "smile_index": round(self._calc_smile_index(lm), 4),
            "eyebrow_raise_left": round(eb["left"], 4),
            "eyebrow_raise_right": round(eb["right"], 4),
            "landmarks_vis": self._collect_vis_landmarks(lm),
        }

    def _calc_face_position(self, lm) -> dict:
        xs = [l.x for l in lm]
        ys = [l.y for l in lm]
        x_min, x_max = min(xs), max(xs)
        y_min, y_max = min(ys), max(ys)
        cx = (x_min + x_max) / 2.0
        cy = (y_min + y_max) / 2.0
        return {
            "cx": round(cx, 4),
            "cy": round(cy, 4),
            "width": round(x_max - x_min, 4),
            "height": round(y_max - y_min, 4),
        }

    def _calc_head_orientation(self, lm) -> dict:
        def pt(i):
            return np.array([lm[i].x * self.w, lm[i].y * self.h, lm[i].z * self.w])

        eye_l = pt(33)
        eye_r = pt(263)
        nose = pt(1)
        chin = pt(152)

        # ROLL
        dx_eye = lm[33].x - lm[263].x
        dy_eye = lm[33].y - lm[263].y
        roll = np.degrees(np.arctan2(dy_eye, abs(dx_eye)))

        # YAW / PITCH
        v_eye = eye_l - eye_r # vecteur horizontal
        mag_eye = np.linalg.norm(v_eye)
        if mag_eye < 1e-6:
            return {"yaw": 0.0, "pitch": 0.0, "roll": round(roll, 2)}
        v_eye_n = v_eye / mag_eye

        v_down = chin - nose # vecteur vertical
        v_down -= np.dot(v_down, v_eye_n) * v_eye_n # forcer la perpendicularité
        mag_down = np.linalg.norm(v_down)
        if mag_down < 1e-6: 
            return {"yaw": 0.0, "pitch": 0.0, "roll": round(roll, 2)}
        v_down_n = v_down / mag_down

        normal = np.cross(v_eye_n, v_down_n)
        mag_n = np.linalg.norm(normal)
        if mag_n < 1e-6:
            return {"yaw": 0.0, "pitch": 0.0, "roll": round(roll, 2)}
        normal /= mag_n

        if normal[2] > 0:
            normal = -normal
        denom = -normal[2] + 1e-6

        yaw = np.degrees(np.arctan2(normal[0], denom))
        pitch = np.degrees(np.arctan2(normal[1], denom))

        return {
            "yaw": round(yaw, 2),
            "pitch": round(pitch, 2),
            "roll": round(roll, 2),
        }

    def _calc_mouth_opening(self, lm, face_height: float) -> float:
        return abs(lm[13].y - lm[14].y) / (face_height + 1e-6)

    def _calc_ear(self, lm, gauche: bool) -> float:
        if gauche:
            v = abs(lm[159].y - lm[145].y)
            h = abs(lm[33].x - lm[133].x)
        else:
            v = abs(lm[386].y - lm[374].y)
            h = abs(lm[362].x - lm[263].x)
        return v / (h + 1e-6)

    def _calc_smile_index(self, lm) -> float:
        mouth_w = abs(lm[291].x - lm[61].x) # Largeur bouche
        iod = abs(lm[362].x - lm[33].x) # Ecartement des yeux (reference stable)
        return mouth_w / (iod + 1e-6) # 0.55 = neutre / 0.80 = grand sourire

    def _collect_vis_landmarks(self, lm) -> dict:
        return {
            str(i): [round(lm[i].x, 4), round(lm[i].y, 4)]
            for i in _VIS_INDICES
        }

    def _calc_eyebrow_raise(self, lm) -> dict:
        ex = lm[263].x - lm[33].x
        ey = lm[263].y - lm[33].y
        eye_dist_sq = ex * ex + ey * ey + 1e-12
        def _proj(brow, eye):
            dx = brow.x - eye.x
            dy = brow.y - eye.y
            return (dx * ey - dy * ex) / eye_dist_sq
        return {"left": _proj(lm[70], lm[33]), "right": _proj(lm[300], lm[362])}

def analyser_video(video_path: str) -> str | None:
    if not os.path.exists(video_path):
        print(f"[ERREUR] Fichier introuvable : {video_path}")
        return None

    video_name = os.path.splitext(os.path.basename(video_path))[0]

    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    duration_s = round(total_frames / fps, 3)

    print(f"\n[INFO] {video_name}.mp4  |  {w}×{h}  |  {fps:.1f} fps  |  {duration_s}s  |  {total_frames} frames")
    print("[INFO] Extraction des signaux...\n")

    extracteur = ExtracteurSignaux(w, h)
    mp_face = mp.solutions.face_mesh.FaceMesh(
        static_image_mode=False,
        max_num_faces=1,
        refine_landmarks=True,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5,
    )

    frames_data = []
    faces_detected = 0

    for frame_idx in range(total_frames):
        ok, frame = cap.read()
        if not ok:
            break

        timestamp = round(frame_idx / fps, 3)
        results = mp_face.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))

        if results.multi_face_landmarks:
            signaux = extracteur.extraire(results.multi_face_landmarks[0])
            record = {"timestamp": timestamp, "face_detected": True, **signaux}
            faces_detected += 1
        else:
            record = {
                "timestamp": timestamp, "face_detected": False,
                "face_position": None, "head_orientation": None,
                "mouth_opening": None, "left_eye_opening": None,
                "right_eye_opening": None, "smile_index": None,
                "eyebrow_raise_left": None,
                "eyebrow_raise_right": None, "landmarks_vis": None,
            }

        frames_data.append(record)

        if frame_idx % 50 == 0:
            print(f"  [{frame_idx}/{total_frames}]", end="\r", flush=True)

    cap.release()
    mp_face.close()

    output = {
        "metadata": {
            "video_file": os.path.basename(video_path),
            "fps": round(fps, 3),
            "duration_s": duration_s,
            "total_frames": total_frames,
            "frames_with_face": faces_detected,
        },
        "frames": frames_data,
    }

    os.makedirs(DATA_DIR, exist_ok=True)
    json_path = os.path.join(DATA_DIR, f"{video_name}_signaux.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n[OK] {faces_detected}/{total_frames} frames avec visage détecté")
    print(f"[OK] JSON → {json_path}")

    return json_path