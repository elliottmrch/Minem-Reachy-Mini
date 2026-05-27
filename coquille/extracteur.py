"""
Extraction des signaux faciaux depuis une vidéo (Jalon 2).

Ce module fournit deux outils complémentaires :

1. ExtracteurSignaux (classe) : calcule les signaux faciaux depuis un objet
   FaceLandmarks MediaPipe. Utilisé à la fois pour l'analyse vidéo offline
   (analyser_video) et le mode live temps réel (live.LiveProcessor).

2. analyser_video(video_path) : lit une vidéo frame par frame avec OpenCV,
   lance MediaPipe FaceMesh sur chaque frame, collecte les signaux via
   ExtracteurSignaux, et sauvegarde un fichier JSON *_signaux.json.

Signaux extraits par frame :
    face_position     : centre et dimensions du visage dans l'image (cx, cy, width, height)
    head_orientation  : yaw, pitch, roll en degrés (estimés depuis la géométrie 3D des landmarks)
    mouth_opening     : ouverture de la bouche normalisée par la hauteur du visage
    left_eye_opening  : EAR (Eye Aspect Ratio) de l'œil gauche
    right_eye_opening : EAR de l'œil droit
    smile_index       : largeur bouche / écartement des yeux (indicateur de sourire)
    eyebrow_raise_left/right : élévation des sourcils normalisée par l'écartement des yeux
    landmarks_vis     : coordonnées (x, y) des landmarks visibles (pour visualisation)

Landmarks MediaPipe FaceMesh utilisés (indices) :
    1   : pointe du nez
    13  : lèvre supérieure intérieure
    14  : lèvre inférieure intérieure
    33  : coin interne œil gauche
    61  : coin gauche de la bouche
    70  : sourcil gauche (milieu)
    133 : coin externe œil gauche
    145 : paupière inférieure œil gauche
    152 : menton
    159 : paupière supérieure œil gauche
    263 : coin interne œil droit
    291 : coin droit de la bouche
    300 : sourcil droit (milieu)
    362 : coin externe œil droit
    374 : paupière inférieure œil droit
    386 : paupière supérieure œil droit
"""

import os
import json
import cv2
import numpy as np
import mediapipe as mp

# Répertoire du script et dossier data/ de sortie
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "data"))

# ── Landmarks pour la visualisation ──────────────────────────────────────────
# MediaPipe FaceMesh définit des connexions (paires d'indices) pour les contours
# des lèvres, yeux et sourcils. On les regroupe ici pour visualiser les signaux.

_VIS_CONNECTIONS = {
    "lips":           mp.solutions.face_mesh.FACEMESH_LIPS,
    "left_eye":       mp.solutions.face_mesh.FACEMESH_LEFT_EYE,
    "right_eye":      mp.solutions.face_mesh.FACEMESH_RIGHT_EYE,
    "left_eyebrow":   mp.solutions.face_mesh.FACEMESH_LEFT_EYEBROW,
    "right_eyebrow":  mp.solutions.face_mesh.FACEMESH_RIGHT_EYEBROW,
}

# Ensemble des indices de landmarks apparaissant dans au moins une connexion de visualisation
_VIS_INDICES = frozenset(
    idx
    for conns in _VIS_CONNECTIONS.values()
    for (a, b) in conns
    for idx in (a, b)
)


class ExtracteurSignaux:
    """Calcule les signaux faciaux depuis un objet FaceLandmarks MediaPipe.

    Réutilisé dans deux contextes :
      - analyser_video() : traitement offline frame par frame
      - live.LiveProcessor : traitement temps réel

    Les coordonnées des landmarks sont normalisées [0, 1] par MediaPipe.
    Cette classe les convertit en pixels (x * width, y * height) pour les
    calculs géométriques qui nécessitent des distances en pixels.
    """

    def __init__(self, frame_width: int, frame_height: int):
        """
        Args:
            frame_width  : largeur de la frame en pixels.
            frame_height : hauteur de la frame en pixels.
        """
        self.w = frame_width
        self.h = frame_height

    def extraire(self, face_landmarks) -> dict:
        """Calcule et retourne tous les signaux depuis un objet FaceLandmarks.

        Args:
            face_landmarks : premier élément de results.multi_face_landmarks.

        Returns:
            Dict contenant tous les signaux (face_position, head_orientation,
            mouth_opening, left_eye_opening, right_eye_opening, smile_index,
            eyebrow_raise_left, eyebrow_raise_right, landmarks_vis).
        """
        lm = face_landmarks.landmark
        face_pos = self._calc_face_position(lm)
        face_h = face_pos["height"]  # hauteur normalisée [0,1], utilisée pour normaliser la bouche
        eb = self._calc_eyebrow_raise(lm)
        return {
            "face_position":      face_pos,
            "head_orientation":   self._calc_head_orientation(lm),
            "mouth_opening":      round(self._calc_mouth_opening(lm, face_h), 4),
            "left_eye_opening":   round(self._calc_ear(lm, gauche=True), 4),
            "right_eye_opening":  round(self._calc_ear(lm, gauche=False), 4),
            "smile_index":        round(self._calc_smile_index(lm), 4),
            "eyebrow_raise_left": round(eb["left"],  4),
            "eyebrow_raise_right":round(eb["right"], 4),
            "landmarks_vis":      self._collect_vis_landmarks(lm),
        }

    def _calc_face_position(self, lm) -> dict:
        """Calcule le centre et les dimensions de la boîte englobante du visage.

        Utilise tous les landmarks (468+) pour trouver les extrêmes.
        cx, cy ∈ [0, 1] : position normalisée du centre.
        width, height ∈ [0, 1] : dimensions normalisées.
        """
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
        """Estime yaw, pitch, roll de la tête depuis 4 landmarks clés.

        Méthode géométrique sans modèle 3D rigide :
          - ROLL  : angle de l'axe inter-yeux par rapport à l'horizontale.
          - YAW   : estimé depuis la normale au plan du visage (produit vectoriel).
          - PITCH : idem, depuis la normale.

        Les 4 landmarks utilisés :
          - 33  : coin interne œil gauche
          - 263 : coin interne œil droit
          - 1   : pointe du nez
          - 152 : menton

        La normale au plan du visage est calculée en faisant le produit vectoriel
        de l'axe inter-yeux et de l'axe nez-menton (après orthogonalisation par Gram-Schmidt).
        Yaw et Pitch sont extraits de la normale par atan2.
        """
        def pt(i):
            """Retourne le landmark i en coordonnées pixels 3D (z est relatif en unités de largeur)."""
            return np.array([lm[i].x * self.w, lm[i].y * self.h, lm[i].z * self.w])

        eye_l = pt(33)   # coin interne œil gauche
        eye_r = pt(263)  # coin interne œil droit
        nose  = pt(1)    # pointe du nez
        chin  = pt(152)  # menton

        # ── Roll : angle de l'axe des yeux dans le plan image ────────────────
        dx_eye = lm[33].x - lm[263].x
        dy_eye = lm[33].y - lm[263].y
        roll = np.degrees(np.arctan2(dy_eye, abs(dx_eye)))

        # ── Yaw et Pitch : depuis la normale au plan du visage ────────────────
        v_eye = eye_l - eye_r  # vecteur horizontal (axe inter-yeux)
        mag_eye = np.linalg.norm(v_eye)
        if mag_eye < 1e-6:
            return {"yaw": 0.0, "pitch": 0.0, "roll": round(roll, 2)}
        v_eye_n = v_eye / mag_eye  # normalisé

        v_down = chin - nose  # vecteur vertical approximatif (nez → menton)
        # Orthogonalisation par Gram-Schmidt : on retire la composante sur v_eye_n
        # pour forcer v_down perpendiculaire à l'axe des yeux
        v_down -= np.dot(v_down, v_eye_n) * v_eye_n
        mag_down = np.linalg.norm(v_down)
        if mag_down < 1e-6:
            return {"yaw": 0.0, "pitch": 0.0, "roll": round(roll, 2)}
        v_down_n = v_down / mag_down

        # Normale au plan du visage = v_eye × v_down (règle de la main droite)
        normal = np.cross(v_eye_n, v_down_n)
        mag_n = np.linalg.norm(normal)
        if mag_n < 1e-6:
            return {"yaw": 0.0, "pitch": 0.0, "roll": round(roll, 2)}
        normal /= mag_n

        # La normale pointe vers la caméra quand le visage est face à elle (z < 0 en convention OpenCV).
        # On la force vers la caméra pour que les angles soient cohérents.
        if normal[2] > 0:
            normal = -normal

        # Projection de la normale sur les plans horizontal (yaw) et vertical (pitch)
        # Utilise une approximation arctangente valide pour de petits angles
        denom = -normal[2] + 1e-6  # distance à la caméra (évite la division par 0)
        yaw   = np.degrees(np.arctan2(normal[0], denom))  # rotation gauche/droite
        pitch = np.degrees(np.arctan2(normal[1], denom))  # inclinaison haut/bas

        return {
            "yaw":   round(yaw,  2),
            "pitch": round(pitch, 2),
            "roll":  round(roll,  2),
        }

    def _calc_mouth_opening(self, lm, face_height: float) -> float:
        """Calcule l'ouverture de la bouche normalisée par la hauteur du visage.

        Distance verticale entre lèvre supérieure (13) et inférieure (14),
        divisée par face_height pour être indépendante de la distance à la caméra.
        Valeur ≈ 0.0 = bouche fermée, ≈ 0.15 = bouche grande ouverte.
        """
        return abs(lm[13].y - lm[14].y) / (face_height + 1e-6)

    def _calc_ear(self, lm, gauche: bool) -> float:
        """Calcule l'Eye Aspect Ratio (EAR) d'un œil.

        EAR = distance verticale paupières / distance horizontale coins œil.
        EAR ≈ 0.3 = œil ouvert normal, ≈ 0.1 = œil fermé.
        La division par la largeur horizontale normalise par rapport à la distance caméra.

        Landmarks utilisés :
          Gauche : vertical [159, 145], horizontal [33, 133]
          Droit  : vertical [386, 374], horizontal [362, 263]
        """
        if gauche:
            v = abs(lm[159].y - lm[145].y)  # paupière sup. - paupière inf.
            h = abs(lm[33].x  - lm[133].x)  # coin interne - coin externe
        else:
            v = abs(lm[386].y - lm[374].y)
            h = abs(lm[362].x - lm[263].x)
        return v / (h + 1e-6)

    def _calc_smile_index(self, lm) -> float:
        """Calcule un indice de sourire : largeur bouche / écartement inter-yeux.

        Référence stable : l'écartement inter-yeux varie peu selon les expressions
        et est robuste à la distance caméra.
        Valeur typique ≈ 0.55 (neutre) à ≈ 0.80 (grand sourire).
        La calibration dans mapper.py soustrait la médiane → 0 = neutre.

        Landmarks : 61 et 291 = coins gauche et droit de la bouche.
                    33 et 362 = coins internes des yeux (référence).
        """
        mouth_w = abs(lm[291].x - lm[61].x)   # largeur de la bouche
        iod     = abs(lm[362].x - lm[33].x)   # écartement inter-yeux (référence stable)
        return mouth_w / (iod + 1e-6)

    def _collect_vis_landmarks(self, lm) -> dict:
        """Collecte les coordonnées (x, y) des landmarks utilisés pour la visualisation.

        Retourne un dict {str(index): [x, y]} pour les landmarks appartenant
        aux contours lèvres/yeux/sourcils. Utilisé par tools/visualiseur.py.
        """
        return {
            str(i): [round(lm[i].x, 4), round(lm[i].y, 4)]
            for i in _VIS_INDICES
        }

    def _calc_eyebrow_raise(self, lm) -> dict:
        """Calcule l'élévation des sourcils normalisée par l'écartement inter-yeux.

        Méthode : projection du vecteur (œil → sourcil) sur la direction "vers le haut"
        du visage, normalisée par la distance inter-yeux pour être indépendante de la distance.

        La direction "haut" est calculée par Gram-Schmidt :
          1. v = menton - nez (vecteur vertical approximatif)
          2. On orthogonalise v par rapport à l'axe des yeux
          3. up_n = -v normalisé (vers le haut du visage)

        Landmarks sourcils : 70 (gauche milieu), 300 (droit milieu).
        Landmarks yeux de référence : 33 (gauche), 263 (droit).
        """
        def pt(i):
            """Landmark i en pixels 3D."""
            return np.array([lm[i].x * self.w, lm[i].y * self.h, lm[i].z * self.w])

        eye_l, eye_r = pt(33), pt(263)
        E = eye_r - eye_l                       # vecteur de l'axe inter-yeux
        eye_dist = np.linalg.norm(E) + 1e-6
        E_n = E / eye_dist                      # normalisé

        # Direction "haut" du visage en 3D via Gram-Schmidt
        down = pt(152) - pt(1)                  # vecteur nez → menton
        down -= np.dot(down, E_n) * E_n         # orthogonalisation
        up_n = -down / (np.linalg.norm(down) + 1e-6)  # inversé = "vers le haut"

        def _raise(brow_idx, eye_idx):
            """Projection (sourcil - œil) sur up_n, normalisée par l'écartement inter-yeux."""
            return float(np.dot(pt(brow_idx) - pt(eye_idx), up_n)) / eye_dist

        return {"left": _raise(70, 33), "right": _raise(300, 263)}


def analyser_video(video_path: str) -> str | None:
    """Analyse une vidéo et extrait les signaux faciaux frame par frame.

    Pipeline :
      1. Ouverture OpenCV → fps, dimensions, durée
      2. MediaPipe FaceMesh → détection landmarks par frame
      3. ExtracteurSignaux.extraire() → signaux par frame
      4. Sauvegarde JSON (*_signaux.json) dans DATA_DIR

    Args:
        video_path : chemin absolu vers la vidéo source.

    Returns:
        Chemin absolu du fichier JSON de signaux créé.
        None si le fichier vidéo n'existe pas.

    Raises:
        ValueError : si aucun visage n'est détecté dans toute la vidéo.
    """
    if not os.path.exists(video_path):
        print(f"[ERREUR] Fichier introuvable : {video_path}")
        return None

    video_name = os.path.splitext(os.path.basename(video_path))[0]

    # Lecture des métadonnées vidéo (fps, taille, nombre de frames)
    cap = cv2.VideoCapture(video_path)
    fps          = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    w            = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h            = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    duration_s   = round(total_frames / fps, 3)

    print(f"\n[INFO] {video_name}.mp4  |  {w}×{h}  |  {fps:.1f} fps  |  {duration_s}s  |  {total_frames} frames")
    print("[INFO] Extraction des signaux...\n")

    extracteur = ExtracteurSignaux(w, h)

    # MediaPipe FaceMesh en mode vidéo (static_image_mode=False → tracking entre frames)
    mp_face = mp.solutions.face_mesh.FaceMesh(
        static_image_mode=False,
        max_num_faces=1,
        refine_landmarks=True,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5,
    )

    frames_data   = []
    faces_detected = 0

    for frame_idx in range(total_frames):
        ok, frame = cap.read()
        if not ok:
            break  # fin de vidéo ou erreur de lecture

        # Timestamp de la frame en secondes (précis au 1000ème)
        timestamp = round(frame_idx / fps, 3)

        # MediaPipe attend RGB ; OpenCV fournit BGR
        results = mp_face.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))

        if results.multi_face_landmarks:
            # Visage détecté : extraction de tous les signaux
            signaux = extracteur.extraire(results.multi_face_landmarks[0])
            record = {"timestamp": timestamp, "face_detected": True, **signaux}
            faces_detected += 1
        else:
            # Pas de visage : on note l'absence mais on garde le timestamp pour l'interpolation
            record = {
                "timestamp": timestamp, "face_detected": False,
                "face_position": None, "head_orientation": None,
                "mouth_opening": None, "left_eye_opening": None,
                "right_eye_opening": None, "smile_index": None,
                "eyebrow_raise_left": None,
                "eyebrow_raise_right": None, "landmarks_vis": None,
            }

        frames_data.append(record)

        # Affichage de la progression tous les 50 frames (overwrite de ligne)
        if frame_idx % 50 == 0:
            print(f"  [{frame_idx}/{total_frames}]", end="\r", flush=True)

    cap.release()
    mp_face.close()

    # Si aucun visage détecté sur toute la vidéo → le pipeline ne peut pas continuer
    if faces_detected == 0:
        print(f"[ERREUR] Aucun visage détecté dans la vidéo ({total_frames} frames analysées)")
        raise ValueError("Aucun visage détecté dans la vidéo")

    # Structuration du JSON de sortie avec metadata et frames
    output = {
        "metadata": {
            "video_file":        os.path.basename(video_path),
            "fps":               round(fps, 3),
            "duration_s":        duration_s,
            "total_frames":      total_frames,
            "frames_with_face":  faces_detected,
        },
        "frames": frames_data,
    }

    # Sauvegarde dans DATA_DIR sous le nom <stem>_signaux.json
    os.makedirs(DATA_DIR, exist_ok=True)
    json_path = os.path.join(DATA_DIR, f"{video_name}_signaux.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n[OK] {faces_detected}/{total_frames} frames avec visage détecté")
    print(f"[OK] JSON -> {json_path}")

    return json_path
