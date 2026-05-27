"""
Mode live : traitement du flux caméra en temps réel.

Ce module capture les frames de la webcam, détecte les landmarks faciaux
avec MediaPipe FaceMesh, mappe les signaux sur les commandes du robot,
et envoie les commandes directement à Reachy Mini — le tout dans un thread dédié.

Pipeline par frame :
  cap.read() → MediaPipe FaceMesh → ExtracteurSignaux.extraire()
    → [phase calibration : accumulation ~30 frames]
    → _mapper_frame() : signaux → commandes robot (yaw/pitch/roll/antennes/torse)
    → _appliquer_robot() : send_target au robot

Phase de calibration :
    Les 30 premières frames avec visage servent à calculer les "baselines"
    (valeurs médianes de l'expression neutre). Toutes les valeurs sont ensuite
    soustraites de ces baselines pour que le visage au repos = robot au repos.
    Cela compense les variations morphologiques entre personnes.

Séparation des responsabilités :
    - live.py gère la capture, la calibration et l'application au robot
    - mapper.py fournit les constantes et la fonction _clamp (réutilisation)
    - extracteur.py fournit ExtracteurSignaux (calcul des signaux depuis landmarks)
"""

import threading
import time

import cv2
import mediapipe as mp
import numpy as np
from reachy_mini.utils import create_head_pose

# ExtracteurSignaux calcule yaw/pitch/roll/EAR/smile/sourcils depuis les landmarks MediaPipe
from extracteur import ExtracteurSignaux

# Constantes de mapping et _clamp importés depuis mapper.py (réutilisation du pipeline offline)
from mapper import (
    ANT_BROW_DEAD,        # zone morte pour les sourcils (évite le bruit)
    ANT_EYEBROW_FACTOR,   # gain sourcils → antennes
    ANTENNA_MAX,          # valeur max des antennes (radians)
    BODY_YAW_DEAD,        # zone morte position horizontale du visage
    BODY_YAW_FACTOR,      # gain position horizontale → rotation torse
    BODY_YAW_MAX,         # valeur max rotation torse
    HEAD_X_EYE_DEAD,      # zone morte ouverture des yeux → translation latérale tête
    HEAD_X_EYE_FACTOR,    # gain
    HEAD_Z_SMILE_FACTOR,  # gain sourire → translation verticale tête
    PITCH_FACTOR,         # gain pitch visage → pitch tête robot
    PITCH_MAX,            # valeur max pitch (degrés)
    PITCH_MOUTH_FACTOR,   # contribution de l'ouverture de bouche au pitch
    ROLL_FACTOR,          # gain roll visage → roll tête robot
    ROLL_MAX,             # valeur max roll (degrés)
    ROLL_MOUTH_FACTOR,    # contribution de l'ouverture de bouche au roll
    TRANS_MAX,            # valeur max des translations (mètres)
    YAW_FACTOR,           # gain yaw visage → yaw tête robot
    YAW_MAX,              # valeur max yaw (degrés)
    _clamp,               # clamp(val, lo, hi) : borne une valeur dans un intervalle
)

# Nombre de frames utilisées pour calculer les baselines de calibration
# ~30 frames à 30 fps ≈ 1 seconde de "pose neutre" requise
CALIB_FRAMES = 30


class LiveProcessor:
    """Capture et traite le flux caméra en temps réel pour piloter le robot.

    Cycle de vie :
        processor = LiveProcessor(reachy_mini)
        processor.start()   → démarre le thread de capture
        processor.is_calibrated()  → True après ~1s avec visage détecté
        processor.get_latest_frame() → bytes JPEG de la frame courante
        processor.stop()    → arrête le thread et libère la caméra
    """

    def __init__(self, reachy_mini, camera_index: int = 0):
        """
        Args:
            reachy_mini    : instance du robot pour envoyer les commandes.
            camera_index   : index de la webcam (0 = première caméra détectée).
        """
        self._reachy = reachy_mini
        self._camera_index = camera_index
        self._running = False
        self._lock = threading.Lock()          # protège _latest_frame et _calibrated
        self._latest_frame: bytes | None = None  # dernière frame JPEG encodée
        self._calibrated = False               # True une fois les baselines calculées
        self._thread: threading.Thread | None = None

    def start(self):
        """Démarre le thread de capture si pas déjà en cours."""
        if self._running:
            return  # idempotent : start() sur un processor déjà actif est sans effet
        self._running = True
        self._calibrated = False
        self._latest_frame = None
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Arrête le thread de capture et libère les ressources.

        join() avec timeout=3s pour ne pas bloquer indéfiniment si la caméra
        ne répond plus (ex: déconnexion USB en cours).
        """
        self._running = False
        if self._thread:
            self._thread.join(timeout=3.0)
            self._thread = None
        with self._lock:
            self._latest_frame = None
            self._calibrated = False

    def get_latest_frame(self) -> bytes | None:
        """Retourne la dernière frame JPEG encodée (thread-safe).

        Utilisé par la route /live/stream pour construire le flux MJPEG.
        Retourne None si aucune frame n'est encore disponible.
        """
        with self._lock:
            return self._latest_frame

    def is_calibrated(self) -> bool:
        """Retourne True si la calibration de l'expression neutre est terminée (thread-safe)."""
        with self._lock:
            return self._calibrated

    def _loop(self):
        """Boucle principale de capture et traitement (exécutée dans le thread dédié).

        Phases :
          1. Ouverture de la caméra et initialisation MediaPipe FaceMesh
          2. Pour chaque frame : détection + extraction des signaux
             a. Phase calibration : accumulation de CALIB_FRAMES frames
                → calcul des baselines (médianes = expression neutre)
             b. Phase traitement : mapping signaux → commandes → robot
          3. Encodage JPEG de la frame pour le flux MJPEG
        """
        # Ouverture de la caméra via OpenCV
        cap = cv2.VideoCapture(self._camera_index)
        if not cap.isOpened():
            print("[LIVE] Impossible d'ouvrir la caméra")
            self._running = False
            return

        # Initialisation de MediaPipe FaceMesh
        # refine_landmarks=True active les 478 landmarks (vs 468) pour meilleure précision yeux/lèvres
        mp_face = mp.solutions.face_mesh.FaceMesh(
            static_image_mode=False,       # mode vidéo : tracking entre frames (plus rapide)
            max_num_faces=1,               # on ne traite qu'un visage
            refine_landmarks=True,         # landmarks additionnels pour iris et lèvres
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )

        extracteur: ExtracteurSignaux | None = None
        calib_buf: list[dict] = []   # buffer de frames pour la calibration
        baselines: dict | None = None  # valeurs neutres calculées

        try:
            while self._running:
                ok, frame = cap.read()
                if not ok:
                    time.sleep(0.01)  # pause courte en cas d'erreur de lecture caméra
                    continue

                h, w = frame.shape[:2]
                # Initialisation de l'extracteur avec les dimensions réelles de la caméra
                if extracteur is None:
                    extracteur = ExtracteurSignaux(w, h)

                # MediaPipe attend du RGB (OpenCV fournit du BGR)
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                results = mp_face.process(rgb)

                if results.multi_face_landmarks:
                    # ── Visage détecté : extraction des signaux ───────────────
                    signaux = extracteur.extraire(results.multi_face_landmarks[0])

                    if baselines is None:
                        # ── Phase calibration : accumulation des frames neutres ─
                        calib_buf.append(signaux)
                        if len(calib_buf) >= CALIB_FRAMES:
                            # Calcul des baselines une fois le buffer plein
                            baselines = self._calibrer(calib_buf)
                            with self._lock:
                                self._calibrated = True
                            print("[LIVE] Calibration terminée")
                    else:
                        # ── Phase traitement : mapping → robot ─────────────────
                        mouvement = self._mapper_frame(signaux, baselines)
                        self._appliquer_robot(mouvement)

                # Encodage JPEG de la frame pour le flux MJPEG (/live/stream)
                _, jpeg = cv2.imencode(".jpg", frame)
                with self._lock:
                    self._latest_frame = jpeg.tobytes()

        finally:
            # Libération des ressources dans tous les cas (arrêt normal ou exception)
            cap.release()
            mp_face.close()

    def _calibrer(self, frames: list[dict]) -> dict:
        """Calcule les baselines de l'expression neutre depuis les frames de calibration.

        On utilise la médiane (et non la moyenne) pour être robuste aux frames
        parasites avec expression momentanée (clignement, sourire involontaire).

        Args:
            frames : liste de dicts de signaux (sortie de ExtracteurSignaux.extraire()).

        Returns:
            Dict des valeurs neutres : {"pitch_offset": float, "smile_index": float, …}
        """
        # Correction du pitch : on soustrait la médiane pour que "tête droite" = 0°
        pitches = [f["head_orientation"]["pitch"] for f in frames]
        pitch_offset = float(np.median(pitches))

        # Baselines des expressions faciales (sourire, bouche, yeux, sourcils)
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
        """Mappe les signaux faciaux (relatifs aux baselines) sur les commandes robot.

        Même logique que mapper._appliquer_mapping() mais en temps réel :
        chaque signal est d'abord centré sur sa baseline, puis multiplié par
        un facteur de gain et borné (clamp) dans la plage du robot.

        Mapping :
            yaw visage      → yaw tête (rotation gauche/droite)
            pitch visage    → pitch tête + contribution bouche (haut/bas)
            roll visage     → roll tête + contribution bouche (inclinaison)
            yeux (EAR moyen)→ translation latérale tête (head_x)
            sourire         → translation verticale tête (head_z)
            sourcil gauche  → antenne gauche (levée = antenne haute)
            sourcil droit   → antenne droite
            position cx     → rotation torse (body_yaw)

        Args:
            signaux   : dict extrait par ExtracteurSignaux.extraire()
            baselines : dict calculé par _calibrer()

        Returns:
            Dict de commandes : {"head": {yaw, pitch, roll, x, y, z}, "antennas": [l, r], "body_yaw": float}
        """
        ho = signaux["head_orientation"]
        fp = signaux["face_position"]

        # Valeurs relatives aux baselines (centrage sur l'expression neutre)
        yaw_deg   = ho["yaw"]
        pitch_deg = ho["pitch"] - baselines["pitch_offset"]  # compensé par la calibration
        roll_deg  = ho["roll"]

        mouth_c = signaux["mouth_opening"]    - baselines["mouth_opening"]
        smile   = signaux["smile_index"]      - baselines["smile_index"]
        eye_l   = signaux["left_eye_opening"] - baselines["left_eye_opening"]
        eye_r   = signaux["right_eye_opening"]- baselines["right_eye_opening"]
        eb_l    = signaux["eyebrow_raise_left"] - baselines["eyebrow_raise_left"]
        eb_r    = signaux["eyebrow_raise_right"]- baselines["eyebrow_raise_right"]

        # ── Orientation tête ──────────────────────────────────────────────────
        yaw   = _clamp(yaw_deg * YAW_FACTOR, -YAW_MAX, YAW_MAX)
        pitch = _clamp(
            pitch_deg * PITCH_FACTOR + mouth_c * PITCH_MOUTH_FACTOR,
            -PITCH_MAX, PITCH_MAX
        )  # la bouche ouverte fait légèrement incliner la tête vers le bas
        roll  = _clamp(
            roll_deg * ROLL_FACTOR + mouth_c * ROLL_MOUTH_FACTOR,
            -ROLL_MAX, ROLL_MAX
        )

        # ── Translations tête ─────────────────────────────────────────────────
        # Moyenne des deux yeux → translation latérale (clignement fort = légère translation)
        eye_mean = (eye_l + eye_r) / 2.0
        eye_mean = eye_mean if abs(eye_mean) > HEAD_X_EYE_DEAD else 0.0  # zone morte
        head_x = _clamp(eye_mean * HEAD_X_EYE_FACTOR, -TRANS_MAX, TRANS_MAX)

        # Sourire → légère élévation de la tête (head_z)
        head_z = _clamp(smile * HEAD_Z_SMILE_FACTOR, -TRANS_MAX, TRANS_MAX)

        # ── Antennes ──────────────────────────────────────────────────────────
        # Sourcil haut → antenne haute (sourcil gauche → antenne GAUCHE inversée)
        eb_l = eb_l if abs(eb_l) > ANT_BROW_DEAD else 0.0  # zone morte anti-bruit
        eb_r = eb_r if abs(eb_r) > ANT_BROW_DEAD else 0.0
        ant_l = _clamp(-eb_l * ANT_EYEBROW_FACTOR, -ANTENNA_MAX, ANTENNA_MAX)
        ant_r = _clamp( eb_r * ANT_EYEBROW_FACTOR, -ANTENNA_MAX, ANTENNA_MAX)

        # ── Rotation du torse ─────────────────────────────────────────────────
        # Position horizontale du visage dans l'image → rotation torse gauche/droite
        cx_dev = fp["cx"] - 0.5  # déviation par rapport au centre (0.5 = milieu)
        if abs(cx_dev) < BODY_YAW_DEAD:
            cx_dev = 0.0  # zone morte : petits déplacements ignorés
        body_yaw = _clamp(cx_dev * BODY_YAW_FACTOR, -BODY_YAW_MAX, BODY_YAW_MAX)

        return {
            "head": {"yaw": yaw, "pitch": pitch, "roll": roll, "x": head_x, "y": 0.0, "z": head_z},
            "antennas": [ant_l, ant_r],
            "body_yaw": body_yaw,
        }

    def _appliquer_robot(self, mouvement: dict):
        """Envoie un dict de commandes au robot physique.

        Convertit les angles tête en HeadPose SDK et appelle set_target().
        Même structure que robot_loop.run() pour la cohérence.

        Args:
            mouvement : dict {"head": {yaw, pitch, roll, x, y, z}, "antennas": [l, r], "body_yaw": float}
        """
        h = mouvement["head"]
        head_pose = create_head_pose(
            yaw=h["yaw"],
            pitch=h["pitch"],
            roll=h["roll"],
            x=h["x"],
            y=h["y"],
            z=h["z"],
            degrees=True,  # les angles sont en degrés (pas en radians)
        )
        self._reachy.set_target(
            head=head_pose,
            antennas=np.array(mouvement["antennas"], dtype=float),
            body_yaw=float(mouvement["body_yaw"]),
        )
