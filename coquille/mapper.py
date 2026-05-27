"""
Génération du mouvement robot depuis les signaux faciaux extraits (Jalon 3).

Ce module prend en entrée un fichier JSON de signaux faciaux (*_signaux.json)
produit par extracteur.py, et produit un fichier JSON de mouvement robot
(*_signaux_mouvement.json) utilisable par rejoueur.py et l'app web.

Pipeline complet (generer_mouvement) :
  1. _charger_signaux()    → chargement + calibration (pitch neutre + expressions neutres)
  2. _appliquer_mapping()  → conversion signaux → commandes robot (yaw/pitch/roll/antennes/torse)
  3. _interpoler()         → rééchantillonnage à ROBOT_FPS (100 Hz) par interpolation linéaire
  4. _sauvegarder()        → écriture du JSON final avec metadata

Constantes de mapping :
    Chaque constante contrôle un aspect de la transposition "visage → robot".
    YAW/PITCH/ROLL_FACTOR : gains d'orientation tête (1.0 = 1:1, 0.8 = légèrement atténué)
    *_MAX                 : bornes de sécurité pour ne pas dépasser les limites mécaniques
    PITCH_MOUTH_FACTOR    : la bouche ouverte fait pencher la tête vers le bas (renforcement expressif)
    ROLL_MOUTH_FACTOR     : idem pour le roll (légère inclinaison)
    ANT_EYEBROW_FACTOR    : gain sourcils → antennes (sourcil haut = antenne haute)
    ANT_BROW_DEAD         : zone morte des sourcils (filtre le bruit de détection)
    BODY_YAW_FACTOR       : position horizontale du visage → rotation torse
    HEAD_X_EYE_FACTOR     : ouverture des yeux → translation latérale tête
    HEAD_Z_SMILE_FACTOR   : sourire → légère élévation de la tête
"""

import json
import os
import numpy as np


# ── Constantes de mapping tête ────────────────────────────────────────────────

# Gains d'orientation : facteur multiplicatif appliqué aux angles du visage
# avant de les envoyer au robot. < 1.0 = mouvement atténué (plus naturel).
YAW_FACTOR   = 0.8   # rotation gauche/droite
YAW_MAX      = 30.0  # degrés max (limite mécanique / confort visuel)
PITCH_FACTOR = 0.8   # inclinaison haut/bas
PITCH_MAX    = 15.0  # degrés max
ROLL_FACTOR  = 0.5   # rotation sur l'axe avant-arrière (inclinaison latérale)
ROLL_MAX     = 15.0  # degrés max

# Contribution de l'ouverture de bouche à l'orientation de la tête
# Négatif pour PITCH : bouche ouverte → tête légèrement vers le bas
PITCH_MOUTH_FACTOR = -80.0
# Positif pour ROLL : bouche ouverte → légère inclinaison (mimique "ahh")
ROLL_MOUTH_FACTOR  = 15.0

# ── Constantes de mapping translations tête ────────────────────────────────────

# Valeur max de translation de la tête en mètres (limites du SDK)
TRANS_MAX         = 0.02
# Ouverture des yeux (Eye Aspect Ratio) → translation latérale de la tête
HEAD_X_EYE_FACTOR = -0.2   # négatif : yeux plus ouverts = tête légèrement à gauche
HEAD_X_EYE_DEAD   = 0.04   # zone morte : variations < 0.04 ignorées (bruit)
# Sourire → élévation légère de la tête (sourire = tête qui se lève)
HEAD_Z_SMILE_FACTOR = 0.05

# ── Constantes de mapping antennes ────────────────────────────────────────────

# Valeur max des antennes en radians
ANTENNA_MAX       = 1.2
# Gain sourcils → antennes : sourcil levé de 1 unité → antenne à ±25 rad
ANT_EYEBROW_FACTOR = 25.0
# Zone morte : variations de sourcil < 0.012 ignorées (bruit de détection)
ANT_BROW_DEAD     = 0.012

# ── Constantes de mapping torse ───────────────────────────────────────────────

# Gain position horizontale du visage (cx en [0,1]) → rotation torse
BODY_YAW_FACTOR = 1.2
# Zone morte : déplacements < 0.06 par rapport au centre ignorés
BODY_YAW_DEAD   = 0.06
# Valeur max de rotation torse en radians
BODY_YAW_MAX    = 0.35

# ── Constantes diverses ───────────────────────────────────────────────────────

# Fréquence de commande du robot (Hz) : le mouvement est interpolé à cette résolution
ROBOT_FPS   = 100

# Répertoire du script et dossier data/ par défaut
SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
DATA_DIR    = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "data"))


def _clamp(val, lo, hi):
    """Borne une valeur dans l'intervalle [lo, hi].

    Utilisé après chaque multiplication par un facteur de gain pour s'assurer
    qu'on ne dépasse jamais les limites mécaniques ou les bornes du SDK.
    """
    return max(lo, min(hi, val))


def _charger_signaux(json_path: str) -> list[dict]:
    """Charge le fichier *_signaux.json et calibre les valeurs neutres.

    Deux calibrations sont appliquées :
    1. Calibration du pitch : soustraction de la médiane de pitch
       → le robot a la tête droite quand la personne a la tête droite.
    2. Calibration des expressions : soustraction de la médiane de chaque signal
       → un visage neutre produit des commandes nulles.

    La médiane est utilisée car plus robuste aux pics ponctuels (clignements,
    expressions fugaces) que la moyenne.

    Args:
        json_path : chemin vers le fichier *_signaux.json.

    Returns:
        Liste de dicts de frames calibrées (face_detected, yaw_deg, pitch_deg, etc.)
    """
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Extraction des champs utiles pour le mapping (on ignore landmarks_vis non nécessaire ici)
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
            # Frame sans visage : on garde le timestamp mais sans données
            frames.append({
                "timestamp": frame["timestamp"],
                "face_detected": False,
            })

    # ── Calibration 1 : pitch neutre ─────────────────────────────────────────
    # Médiane du pitch sur toutes les frames avec visage = "tête droite" de la personne
    pitches = [f["pitch_deg"] for f in frames if f.get("face_detected")]
    if pitches:
        pitch_offset = float(np.median(pitches))
        print(f"[INFO] Correction pitch neutre : {pitch_offset:+.1f}°")
        for f in frames:
            if f.get("face_detected"):
                f["pitch_deg"] -= pitch_offset

    # ── Calibration 2 : expressions neutres ──────────────────────────────────
    # Pour chaque signal facial, la médiane est la valeur de repos.
    # En la soustrayant, on obtient des variations relatives autour de 0.
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
                f[k] -= v  # centrage : valeur neutre = 0

    return frames


def _appliquer_mapping(frames: list[dict]) -> list[dict]:
    """Convertit les signaux faciaux en commandes robot (après calibration).

    Pour chaque frame avec visage :
      - Applique les facteurs de gain et clamp sur chaque degré de liberté
      - Si pas de visage : réutilise la dernière commande valide (freeze)

    Le "freeze" sur les frames sans visage évite que le robot saute
    brutalement à la position neutre lors d'occultations momentanées.

    Args:
        frames : liste de dicts calibrés (sortie de _charger_signaux).

    Returns:
        Liste de dicts de commandes {timestamp, yaw, pitch, roll, x, y, z, ant_l, ant_r, body_yaw}.
    """
    result = []
    # Dernière commande valide (position neutre au départ)
    last = {"yaw": 0.0, "pitch": 0.0, "roll": 0.0,
            "x": 0.0, "y": 0.0, "z": 0.0,
            "ant_l": 0.0, "ant_r": 0.0, "body_yaw": 0.0}

    for frame in frames:
        if frame["face_detected"]:
            mouth_c = frame["mouth_opening"]  # déjà centré sur la baseline

            # ── Orientation tête ──────────────────────────────────────────────
            yaw   = _clamp(frame["yaw_deg"]   * YAW_FACTOR,   -YAW_MAX,   YAW_MAX)
            pitch = _clamp(frame["pitch_deg"] * PITCH_FACTOR + mouth_c * PITCH_MOUTH_FACTOR,
                           -PITCH_MAX, PITCH_MAX)
            roll  = _clamp(frame["roll_deg"]  * ROLL_FACTOR  + mouth_c * ROLL_MOUTH_FACTOR,
                           -ROLL_MAX, ROLL_MAX)

            # ── Translations tête ─────────────────────────────────────────────
            # Moyenne EAR (Eye Aspect Ratio) gauche et droit → translation latérale
            eye_mean = (frame["left_eye_opening"] + frame["right_eye_opening"]) / 2.0
            eye_mean = eye_mean if abs(eye_mean) > HEAD_X_EYE_DEAD else 0.0
            head_x = _clamp(eye_mean * HEAD_X_EYE_FACTOR, -TRANS_MAX, TRANS_MAX)
            head_y = 0.0  # translation avant/arrière non utilisée
            head_z = _clamp(frame["smile_index"] * HEAD_Z_SMILE_FACTOR, -TRANS_MAX, TRANS_MAX)

            # ── Antennes ──────────────────────────────────────────────────────
            # Zone morte puis gain : sourcil levé = antenne haute
            # Signe inversé pour l'antenne gauche (symétrie miroir)
            eb_l = frame["eyebrow_raise_left"]  if abs(frame["eyebrow_raise_left"])  > ANT_BROW_DEAD else 0.0
            eb_r = frame["eyebrow_raise_right"] if abs(frame["eyebrow_raise_right"]) > ANT_BROW_DEAD else 0.0
            ant_l = _clamp(-eb_l * ANT_EYEBROW_FACTOR, -ANTENNA_MAX, ANTENNA_MAX)
            ant_r = _clamp( eb_r * ANT_EYEBROW_FACTOR, -ANTENNA_MAX, ANTENNA_MAX)

            # ── Rotation torse ────────────────────────────────────────────────
            # cx en [0, 1] : 0.5 = centre de l'image. La déviation par rapport au centre
            # pilote la rotation du torse (visage à gauche = torse tourne à gauche).
            cx_dev = frame["face_cx"] - 0.5
            if abs(cx_dev) < BODY_YAW_DEAD:
                cx_dev = 0.0
            body_yaw = _clamp(cx_dev * BODY_YAW_FACTOR, -BODY_YAW_MAX, BODY_YAW_MAX)

            last = {"yaw": yaw, "pitch": pitch, "roll": roll,
                    "x": head_x, "y": head_y, "z": head_z,
                    "ant_l": ant_l, "ant_r": ant_r, "body_yaw": body_yaw}

        # Ajout de la commande (valide ou dernière connue si pas de visage)
        result.append({"timestamp": frame["timestamp"], **last})

    return result


def _interpoler(mapped: list[dict]) -> list[dict]:
    """Rééchantillonne le mouvement à ROBOT_FPS Hz par interpolation linéaire.

    Les timestamps du fichier source correspondent au fps de la vidéo (ex: 25 fps).
    Le robot Reachy Mini est commandé à 100 fps → on interpole chaque signal
    entre les points connus pour obtenir 100 frames par seconde.

    Args:
        mapped : liste de commandes à l'fps de la vidéo source.

    Returns:
        Liste de commandes uniformément espacées à 1/ROBOT_FPS secondes.
    """
    # Extraction des timestamps et des valeurs de chaque degré de liberté
    ts = np.array([f["timestamp"] for f in mapped])
    keys = ["yaw", "pitch", "roll", "x", "y", "z", "ant_l", "ant_r", "body_yaw"]
    sigs = {k: np.array([f[k] for f in mapped]) for k in keys}

    # Génération de la grille de temps à 100 Hz entre le premier et le dernier timestamp
    t_interp = np.arange(ts[0], ts[-1], 1.0 / ROBOT_FPS)

    # Interpolation linéaire de chaque signal sur la nouvelle grille
    result = []
    for t in t_interp:
        frame = {"timestamp": round(float(t), 4)}
        for k in keys:
            frame[k] = round(float(np.interp(t, ts, sigs[k])), 4)
        result.append(frame)

    return result


def _sauvegarder(frames: list[dict], source_path: str, output_path: str):
    """Sauvegarde les frames de mouvement interpolées dans un fichier JSON.

    Le format de sortie (*_signaux_mouvement.json) est structuré avec metadata
    et frames au format attendu par charger_mouvement() et robot_loop.run().

    Args:
        frames      : frames interpolées à 100 Hz (sortie de _interpoler).
        source_path : chemin du fichier *_signaux.json d'origine (pour metadata).
        output_path : chemin de sortie du JSON de mouvement.
    """
    duration = round(frames[-1]["timestamp"] - frames[0]["timestamp"], 3) if frames else 0.0

    # Structure JSON finale avec metadata pour identifier l'origine du fichier
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
                "antennas": [f["ant_l"], f["ant_r"]],  # [gauche, droite]
                "body_yaw": f["body_yaw"],
                "head": {
                    "yaw":   f["yaw"],
                    "pitch": f["pitch"],
                    "roll":  f["roll"],
                    "x":     f["x"],
                    "y":     f["y"],
                    "z":     f["z"],
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
    """Exécute le pipeline complet signaux → mouvement robot.

    Enchaîne : chargement+calibration → mapping → interpolation → sauvegarde.

    Args:
        input_json  : chemin vers le fichier *_signaux.json (produit par extracteur.py).
        output_json : chemin de sortie. Par défaut : <stem>_mouvement.json dans DATA_DIR.

    Returns:
        Chemin absolu du fichier JSON de mouvement généré.
    """
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
    """Lance le mapping via menu CLI interactif ou directement depuis un chemin.

    Si input_json est None, liste les fichiers *_signaux.json dans DATA_DIR
    et propose à l'utilisateur d'en choisir un.

    Args:
        input_json : chemin vers le fichier *_signaux.json (None = sélection interactive).

    Returns:
        Chemin du JSON de mouvement généré, ou None en cas d'erreur.
    """
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
    # Lancement direct : python mapper.py [input.json [output.json]]
    import sys
    if len(sys.argv) < 2:
        lancer_mapping()
    else:
        generer_mouvement(sys.argv[1], sys.argv[2] if len(sys.argv) >= 3 else None)
