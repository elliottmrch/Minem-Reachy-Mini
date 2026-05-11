import os
import json
import cv2
import numpy as np
import mediapipe as mp

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "data"))

# Points 3D du modèle de visage générique (mm, origine au nez)
_MODEL_3D = np.array([
    [0.0,    0.0,    0.0],   # 1   : Nez (origine)
    [0.0,   -63.6,  -12.5],  # 152 : Menton
    [-43.3,  32.7,  -26.0],  # 33  : Coin œil gauche (ext.)
    [ 43.3,  32.7,  -26.0],  # 362 : Coin œil droit (ext.)
    [-28.9, -28.9,  -24.1],  # 61  : Coin bouche gauche
    [ 28.9, -28.9,  -24.1],  # 291 : Coin bouche droit
], dtype=np.float64)

_PNP_INDICES = [1, 152, 33, 362, 61, 291]

# Connexions MediaPipe pour les features visuelles (yeux, sourcils, bouche)
_VIS_CONNECTIONS = {
    "lips":           mp.solutions.face_mesh.FACEMESH_LIPS,
    "left_eye":       mp.solutions.face_mesh.FACEMESH_LEFT_EYE,
    "right_eye":      mp.solutions.face_mesh.FACEMESH_RIGHT_EYE,
    "left_eyebrow":   mp.solutions.face_mesh.FACEMESH_LEFT_EYEBROW,
    "right_eyebrow":  mp.solutions.face_mesh.FACEMESH_RIGHT_EYEBROW,
}
# Ensemble de tous les indices landmarks nécessaires pour tracer ces connexions
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
        focal = float(frame_width)
        cx, cy = frame_width / 2.0, frame_height / 2.0
        self.camera_matrix = np.array([
            [focal, 0,     cx],
            [0,     focal, cy],
            [0,     0,     1 ],
        ], dtype=np.float64)
        self.dist_coeffs = np.zeros((4, 1), dtype=np.float64)

    def extraire(self, face_landmarks) -> dict:
        lm = face_landmarks.landmark
        face_pos = self._calc_face_position(lm)
        face_h = face_pos["height"]
        return {
            "face_position":     face_pos,
            "head_orientation":  self._calc_head_orientation(lm),
            "mouth_opening":     round(self._calc_mouth_opening(lm, face_h), 4),
            "left_eye_opening":  round(self._calc_ear(lm, gauche=True), 4),
            "right_eye_opening": round(self._calc_ear(lm, gauche=False), 4),
            "smile_index":       round(self._calc_smile_index(lm), 4),
            "eyebrow_raise":     round(self._calc_eyebrow_raise(lm, face_h), 4),
            "landmarks_vis":     self._collect_vis_landmarks(lm),
        }

    def _calc_face_position(self, lm) -> dict:
        xs = [l.x for l in lm]
        ys = [l.y for l in lm]
        x_min, x_max = min(xs), max(xs)
        y_min, y_max = min(ys), max(ys)
        cx = (x_min + x_max) / 2.0
        cy = (y_min + y_max) / 2.0
        return {
            "cx":     round(cx, 4),
            "cy":     round(cy, 4),
            "width":  round(x_max - x_min, 4),
            "height": round(y_max - y_min, 4),
        }

    def _calc_head_orientation(self, lm) -> dict:
        image_points = np.array(
            [[lm[i].x * self.w, lm[i].y * self.h] for i in _PNP_INDICES],
            dtype=np.float64,
        )
        try:
            ok, rvec, tvec = cv2.solvePnP(
                _MODEL_3D, image_points,
                self.camera_matrix, self.dist_coeffs,
                flags=cv2.SOLVEPNP_ITERATIVE,
            )
            if not ok:
                raise ValueError
            rot_mat, _ = cv2.Rodrigues(rvec)
            angles, _, _, _, _, _ = cv2.RQDecomp3x3(rot_mat)
            # angles[0]=pitch, [1]=yaw, [2]=roll ; inversion yaw (convention caméra)
            return {
                "yaw":   round(-float(angles[1]), 2),
                "pitch": round(float(angles[0]), 2),
                "roll":  round(float(angles[2]), 2),
            }
        except Exception:
            return {"yaw": 0.0, "pitch": 0.0, "roll": 0.0}

    def _calc_mouth_opening(self, lm, face_height: float) -> float:
        return abs(lm[13].y - lm[14].y) / (face_height + 1e-6)

    def _calc_ear(self, lm, gauche: bool) -> float:
        if gauche:
            v = abs(lm[159].y - lm[145].y)
            h = abs(lm[33].x  - lm[133].x)
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

    def _calc_eyebrow_raise(self, lm, face_height: float) -> float:
        left  = abs(lm[70].y  - lm[33].y)
        right = abs(lm[300].y - lm[362].y)
        return ((left + right) / 2.0) / (face_height + 1e-6)

def analyser_video(video_path: str) -> str | None:
    """
    Charge une vidéo MP4, détecte le visage frame par frame et extrait
    les signaux faciaux. Sauvegarde le résultat en JSON dans data/.
    Retourne le chemin du JSON, ou None si erreur.
    """
    if not os.path.exists(video_path):
        print(f"[ERREUR] Fichier introuvable : {video_path}")
        return None

    video_name = os.path.splitext(os.path.basename(video_path))[0]

    cap = cv2.VideoCapture(video_path)
    fps          = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    w            = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h            = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    duration_s   = round(total_frames / fps, 3)

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

    frames_data    = []
    faces_detected = 0

    for frame_idx in range(total_frames):
        ok, frame = cap.read()
        if not ok:
            break

        timestamp = round(frame_idx / fps, 3)
        results   = mp_face.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)) # BGR -> RGB

        if results.multi_face_landmarks:
            signaux = extracteur.extraire(results.multi_face_landmarks[0])
            record  = {"timestamp": timestamp, "face_detected": True, **signaux}
            faces_detected += 1
        else:
            record = {
                "timestamp": timestamp, "face_detected": False,
                "face_position": None, "head_orientation": None,
                "mouth_opening": None, "left_eye_opening": None,
                "right_eye_opening": None, "smile_index": None,
                "eyebrow_raise": None, "landmarks_vis": None,
            }

        frames_data.append(record)

        if frame_idx % 50 == 0:
            print(f"  [{frame_idx}/{total_frames}]", end="\r", flush=True)

    cap.release()
    mp_face.close()

    output = {
        "metadata": {
            "video_file":      os.path.basename(video_path),
            "fps":             round(fps, 3),
            "duration_s":      duration_s,
            "total_frames":    total_frames,
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
