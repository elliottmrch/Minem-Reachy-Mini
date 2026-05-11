import json
import os
import numpy as np

# Tête
# Les angles viennent désormais de la géométrie MediaPipe (pas solvePnP) :
# les valeurs sont cohérentes en degrés, ajuste les FACTOR selon le ressenti.
# Si un axe est inversé sur le robot, passe son FACTOR en négatif.
YAW_FACTOR     = 0.8
YAW_MAX        = 30.0   # degrés
PITCH_FACTOR   = 0.8
PITCH_MAX      = 20.0   # degrés
ROLL_FACTOR    = 0.5
ROLL_MAX       = 15.0   # degrés

# Antennes
ANTENNA_MAX         = 2
ANT_MOUTH_FACTOR    = 4.0
ANT_SMILE_NEUTRAL   = 0.55
ANT_SMILE_FACTOR    = 0.6
ANT_EYEBROW_BASE    = 0.05
ANT_EYEBROW_FACTOR  = 3.0
ANT_EYE_DIFF_FACTOR = 0.20

# Corps
BODY_YAW_FACTOR = 1.2
BODY_YAW_DEAD   = 0.06
BODY_YAW_MAX    = 0.35

ROBOT_FPS      = 100

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR   = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "data"))

# Helpers
def _clamp(val, lo, hi):
    return max(lo, min(hi, val))

# Chargement + calibration automatique du pitch
def _charger_signaux(json_path: str) -> list[dict]:
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    frames = []
    for frame in data["frames"]:
        if frame["face_detected"]:
            ho = frame["head_orientation"]
            frames.append({
                "timestamp":          frame["timestamp"],
                "face_detected":      True,
                "yaw_deg":            ho["yaw"],
                "pitch_deg":          ho["pitch"],
                "roll_deg":           ho["roll"],
                "mouth_opening":      frame["mouth_opening"],
                "smile_index":        frame["smile_index"],
                "eyebrow_raise":      frame["eyebrow_raise"],
                "left_eye_opening":   frame["left_eye_opening"],
                "right_eye_opening":  frame["right_eye_opening"],
                "face_cx":            frame["face_position"]["cx"],
            })
        else:
            frames.append({
                "timestamp":     frame["timestamp"],
                "face_detected": False,
            })

    # Calibration du pitch : la géométrie MediaPipe introduit un biais constant
    # (menton légèrement plus reculé que le nez → normale un peu inclinée vers le bas).
    # On soustrait la médiane du pitch sur toute la vidéo pour que la pose "moyenne"
    # corresponde à pitch = 0°. Ne touche pas au yaw ni au roll.
    pitches = [f["pitch_deg"] for f in frames if f.get("face_detected")]
    if pitches:
        pitch_offset = float(np.median(pitches))
        print(f"[INFO] Correction pitch neutre : {pitch_offset:+.1f}°")
        for f in frames:
            if f.get("face_detected"):
                f["pitch_deg"] -= pitch_offset

    return frames

# Mapping
def _appliquer_mapping(frames: list[dict]) -> list[dict]:
    result = []
    # Position neutre maintenue tant que le visage n'est pas encore détecté
    # puis gelée sur la dernière valeur connue si la détection se perd en cours de vidéo.
    last = {"yaw": 0.0, "pitch": 0.0, "roll": 0.0, "ant_l": 0.0, "ant_r": 0.0, "body_yaw": 0.0}

    for frame in frames:
        if frame["face_detected"]:
            yaw   = _clamp(frame["yaw_deg"]   * YAW_FACTOR,   -YAW_MAX,   YAW_MAX)
            pitch = _clamp(frame["pitch_deg"] * PITCH_FACTOR, -PITCH_MAX, PITCH_MAX)
            roll  = _clamp(frame["roll_deg"]  * ROLL_FACTOR,  -ROLL_MAX,  ROLL_MAX)

            # Antennes en pause (focus tête uniquement)
            ant_l = 0.0
            ant_r = 0.0

            cx_dev = frame["face_cx"] - 0.5
            if abs(cx_dev) < BODY_YAW_DEAD:
                cx_dev = 0.0
            body_yaw = _clamp(cx_dev * BODY_YAW_FACTOR, -BODY_YAW_MAX, BODY_YAW_MAX)

            last = {"yaw": yaw, "pitch": pitch, "roll": roll,
                    "ant_l": ant_l, "ant_r": ant_r, "body_yaw": body_yaw}

        result.append({"timestamp": frame["timestamp"], **last})

    return result

# Interpolation
def _interpoler(mapped: list[dict]) -> list[dict]:
    ts   = np.array([f["timestamp"] for f in mapped])
    keys = ["yaw", "pitch", "roll", "ant_l", "ant_r", "body_yaw"]
    sigs = {k: np.array([f[k] for f in mapped]) for k in keys}

    t_interp = np.arange(ts[0], ts[-1], 1.0 / ROBOT_FPS)

    result = []
    for t in t_interp:
        frame = {"timestamp": round(float(t), 4)}
        for k in keys:
            frame[k] = round(float(np.interp(t, ts, sigs[k])), 4)
        result.append(frame)

    return result

# Sauvegarde
def _sauvegarder(frames: list[dict], source_path: str, output_path: str):
    duration = round(frames[-1]["timestamp"] - frames[0]["timestamp"], 3) if frames else 0.0

    output = {
        "metadata": {
            "source_file":  os.path.basename(source_path),
            "duration_s":   duration,
            "fps_robot":    ROBOT_FPS,
            "total_frames": len(frames),
        },
        "frames": [
            {
                "timestamp": f["timestamp"],
                "antennas":  [f["ant_l"], f["ant_r"]],
                "body_yaw":  f["body_yaw"],
                "head": {
                    "yaw":   f["yaw"],
                    "pitch": f["pitch"],
                    "roll":  f["roll"],
                },
            }
            for f in frames
        ],
    }

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as fp:
        json.dump(output, fp, indent=2, ensure_ascii=False)

    print(f"[OK] {len(frames)} frames sauvegardees -> {output_path}")

# Point d'entrée principal
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

# Lancement interactif
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

# Lancement direct
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        lancer_mapping()
    else:
        generer_mouvement(sys.argv[1], sys.argv[2] if len(sys.argv) >= 3 else None)
