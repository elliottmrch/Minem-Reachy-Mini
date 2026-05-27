import json
import os
import numpy as np

YAW_FACTOR = 0.8
YAW_MAX = 30.0
PITCH_FACTOR = 0.55
PITCH_MAX = 13.0
ROLL_FACTOR = 0.5
ROLL_MAX = 10.0

PITCH_MOUTH_FACTOR = -8.00
ROLL_MOUTH_FACTOR = 8.00

TRANS_MAX = 0.02
HEAD_X_EYE_FACTOR = -0.2
HEAD_Z_SMILE_FACTOR = 0.05

ANTENNA_MAX = 1.2
ANT_EYEBROW_FACTOR = 25.0

BODY_YAW_FACTOR = 1.2
BODY_YAW_DEAD = 0.06
BODY_YAW_MAX = 0.35

ROBOT_FPS = 100

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "data"))

def _clamp(val, lo, hi):
    return max(lo, min(hi, val))

def _charger_signaux(json_path: str) -> list[dict]:
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    frames = []
    for frame in data["frames"]:
        if frame["face_detected"]:
            ho = frame["head_orientation"]
            eb_l = frame["eyebrow_raise_left"]
            eb_r = frame["eyebrow_raise_right"]
            frames.append({
                "timestamp": frame["timestamp"],
                "face_detected": True,
                "yaw_deg": ho["yaw"],
                "pitch_deg": ho["pitch"],
                "roll_deg": ho["roll"],
                "mouth_opening": frame["mouth_opening"],
                "smile_index": frame["smile_index"],
                "eyebrow_raise_left": eb_l,
                "eyebrow_raise_right": eb_r,
                "left_eye_opening": frame["left_eye_opening"],
                "right_eye_opening": frame["right_eye_opening"],
                "face_cx": frame["face_position"]["cx"],
            })
        else:
            frames.append({
                "timestamp": frame["timestamp"],
                "face_detected": False,
            })

    # Calibration meton nez
    pitches = [f["pitch_deg"] for f in frames if f.get("face_detected")]
    if pitches:
        pitch_offset = float(np.median(pitches))
        print(f"[INFO] Correction pitch neutre : {pitch_offset:+.1f}°")
        for f in frames:
            if f.get("face_detected"):
                f["pitch_deg"] -= pitch_offset

    # Calibration émotions neutres
    signals = ("smile_index", "mouth_opening",
               "left_eye_opening", "right_eye_opening",
               "eyebrow_raise_left", "eyebrow_raise_right")
    detected = [f for f in frames if f.get("face_detected")]
    if detected:
        offsets = {k: float(np.median([f[k] for f in detected])) for k in signals}
        print(f"[INFO] Médianes : smile={offsets['smile_index']:.3f} "
              f"mouth={offsets['mouth_opening']:.3f} "
              f"eye_l={offsets['left_eye_opening']:.3f} "
              f"eye_r={offsets['right_eye_opening']:.3f} "
              f"brow_l={offsets['eyebrow_raise_left']:.3f} "
              f"brow_r={offsets['eyebrow_raise_right']:.3f}")
        for f in detected:
            for k, v in offsets.items():
                f[k] -= v

    return frames

def _appliquer_mapping(frames: list[dict]) -> list[dict]:
    result = []
    last = {"yaw": 0.0, "pitch": 0.0, "roll": 0.0,
            "x": 0.0, "y": 0.0, "z": 0.0,
            "ant_l": 0.0, "ant_r": 0.0, "body_yaw": 0.0}

    for frame in frames:
        if frame["face_detected"]:
            mouth_c = frame["mouth_opening"]
            yaw = _clamp(frame["yaw_deg"] * YAW_FACTOR, -YAW_MAX, YAW_MAX)
            pitch = _clamp(frame["pitch_deg"] * PITCH_FACTOR + mouth_c * PITCH_MOUTH_FACTOR,
                           -PITCH_MAX, PITCH_MAX)
            roll = _clamp(frame["roll_deg"] * ROLL_FACTOR + mouth_c * ROLL_MOUTH_FACTOR,
                          -ROLL_MAX, ROLL_MAX)

            eye_mean = (frame["left_eye_opening"] + frame["right_eye_opening"]) / 2.0
            head_x = _clamp(eye_mean * HEAD_X_EYE_FACTOR, -TRANS_MAX, TRANS_MAX)
            head_y = 0.0
            head_z = _clamp(frame["smile_index"] * HEAD_Z_SMILE_FACTOR, -TRANS_MAX, TRANS_MAX)

            ant_l = _clamp(-frame["eyebrow_raise_left"] * ANT_EYEBROW_FACTOR, -ANTENNA_MAX, ANTENNA_MAX)
            ant_r = _clamp(frame["eyebrow_raise_right"] * ANT_EYEBROW_FACTOR, -ANTENNA_MAX, ANTENNA_MAX)

            cx_dev = frame["face_cx"] - 0.5
            if abs(cx_dev) < BODY_YAW_DEAD:
                cx_dev = 0.0
            body_yaw = _clamp(cx_dev * BODY_YAW_FACTOR, -BODY_YAW_MAX, BODY_YAW_MAX)

            last = {"yaw": yaw, "pitch": pitch, "roll": roll,
                    "x": head_x, "y": head_y, "z": head_z,
                    "ant_l": ant_l, "ant_r": ant_r, "body_yaw": body_yaw}

        result.append({"timestamp": frame["timestamp"], **last})

    return result

def _interpoler(mapped: list[dict]) -> list[dict]:
    ts = np.array([f["timestamp"] for f in mapped])
    keys = ["yaw", "pitch", "roll", "x", "y", "z", "ant_l", "ant_r", "body_yaw"]
    sigs = {k: np.array([f[k] for f in mapped]) for k in keys}

    t_interp = np.arange(ts[0], ts[-1], 1.0 / ROBOT_FPS)

    result = []
    for t in t_interp:
        frame = {"timestamp": round(float(t), 4)}
        for k in keys:
            frame[k] = round(float(np.interp(t, ts, sigs[k])), 4)
        result.append(frame)

    return result

def _sauvegarder(frames: list[dict], source_path: str, output_path: str):
    duration = round(frames[-1]["timestamp"] - frames[0]["timestamp"], 3) if frames else 0.0

    output = {
        "metadata": {
            "source_file": os.path.basename(source_path),
            "duration_s": duration,
            "fps_robot": ROBOT_FPS,
            "total_frames": len(frames),
        },
        "frames": [
            {
                "timestamp": f["timestamp"],
                "antennas": [f["ant_l"], f["ant_r"]],
                "body_yaw": f["body_yaw"],
                "head": {
                    "yaw": f["yaw"],
                    "pitch": f["pitch"],
                    "roll": f["roll"],
                    "x": f["x"],
                    "y": f["y"],
                    "z": f["z"],
                },
            }
            for f in frames
        ],
    }

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as fp:
        json.dump(output, fp, indent=2, ensure_ascii=False)

    print(f"[OK] {len(frames)} frames sauvegardees -> {output_path}")

def generer_mouvement(input_json: str, output_json: str | None = None) -> str:
    stem = os.path.splitext(os.path.basename(input_json))[0]

    if output_json is None:
        output_json = os.path.join(DATA_DIR, stem + "_mouvement.json")

    print(f"\n[INFO] Chargement : {os.path.basename(input_json)}")
    frames = _charger_signaux(input_json)
    print(f"[INFO] {len(frames)} frames chargées")

    mapped = _appliquer_mapping(frames)
    print(f"[INFO] Mapping appliqué")

    interpolated = _interpoler(mapped)
    print(f"[INFO] Interpolation {ROBOT_FPS} Hz -> {len(interpolated)} frames")

    _sauvegarder(interpolated, input_json, output_json)
    return output_json

def lancer_mapping(input_json: str | None = None) -> str | None:
    if input_json is None:
        fichiers = sorted(f for f in os.listdir(DATA_DIR) if f.endswith("_signaux.json"))
        if not fichiers:
            print(f"[ERREUR] Aucun fichier *_signaux.json trouvé dans {DATA_DIR}")
            print("Lancez d'abord l'extraction (option 4) pour générer les signaux.")
            return None

        print("\nFichiers de signaux disponibles :")
        for i, f in enumerate(fichiers):
            print(f"  {i + 1}. {f}")

        choix = input("\nNuméro du fichier à convertir : ").strip()
        try:
            input_json = os.path.join(DATA_DIR, fichiers[int(choix) - 1])
        except (ValueError, IndexError):
            print("[ERREUR] Choix invalide.")
            return None

    return generer_mouvement(input_json)

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        lancer_mapping()
    else:
        generer_mouvement(sys.argv[1], sys.argv[2] if len(sys.argv) >= 3 else None)
