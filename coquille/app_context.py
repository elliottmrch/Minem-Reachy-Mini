"""
Contexte partagé de l'application Coquille.

Ce module est le socle commun de toute l'application. Il définit :
  - Les constantes globales (chemins, extensions, FPS robot)
  - La dataclass AppContext : le "bus" passé à chaque module de routes
    et à robot_loop pour qu'ils partagent le même état et le même verrou
  - La factory create_initial_state() : structure centralisée de l'état runtime
  - Les helpers robot set_neutral() et get_processed_videos()

Principe de cohérence :
    Une seule instance AppContext est créée dans Coquille.run().
    Tous les modules reçoivent une référence à cet objet → même dict, même Lock.
    Toute modification de state doit se faire sous `with ctx.lock:` pour être
    thread-safe (les routes FastAPI et la boucle robot tournent en parallèle).
"""

import os
import threading
from dataclasses import dataclass
from typing import Any

import numpy as np
from reachy_mini import ReachyMini
from reachy_mini.utils import create_head_pose


# ── Chemins ───────────────────────────────────────────────────────────────────

# Répertoire contenant ce fichier (coquille/)
current_dir = os.path.dirname(os.path.abspath(__file__))

# Dossier data/ à la racine du projet.
# Contient : vidéos source (.mp4…), signaux extraits (*_signaux.json),
#            mouvements générés (*_signaux_mouvement.json), audio (*_audio.wav).
DATA_DIR = os.path.abspath(os.path.join(current_dir, "..", "data"))


# ── Constantes ────────────────────────────────────────────────────────────────

# Extensions vidéo acceptées à l'upload et lors de la validation des noms de fichiers
ALLOWED_VIDEO_EXT = (".mp4", ".avi", ".mov", ".webm", ".mkv")

# Fréquence de commande du robot en Hz.
# Le fichier JSON de mouvement est interpolé à exactement 100 fps par mapper.py,
# donc chaque frame correspond à 10 ms. La boucle robot_loop respecte cette cadence.
ROBOT_FPS = 100


# ── Contexte partagé ──────────────────────────────────────────────────────────

@dataclass
class AppContext:
    """Conteneur de toutes les ressources partagées entre les modules.

    Passé par référence à routes_video.register(), routes_playback.register(),
    robot_loop.run(), etc. Tous opèrent sur le même state et le même lock.

    Champs :
        state       : dict mutable (voir create_initial_state()) contenant
                      l'intégralité de l'état runtime de l'application.
        lock        : threading.Lock() à acquérir avant toute lecture ou
                      écriture dans state (accès concurrent routes + boucle robot).
        reachy_mini : instance du robot physique (méthodes set_target, media…).
        settings_app: instance FastAPI sur laquelle sont enregistrées les routes.
                      Typé Any pour éviter l'import circulaire avec FastAPI.
    """

    state: dict
    lock: threading.Lock
    reachy_mini: ReachyMini
    settings_app: Any


def create_initial_state() -> dict:
    """Retourne le dict d'état initial de l'application (14 clés).

    Ce dict est créé UNE SEULE FOIS au démarrage (dans Coquille.run()),
    puis partagé par référence entre toutes les routes et la boucle robot.
    Il ne doit jamais être remplacé entièrement — on modifie ses valeurs sur place.

    Clés et rôles :
        is_replaying       : booléen — le rejeu robot est-il en cours ?
        replay_start_time  : time.time() au moment du démarrage (ou reprise) du rejeu.
                             Utilisé par robot_loop pour calculer l'index de frame.
        movement_frames    : liste de dicts [{head, antennas, body_yaw, timestamp}]
                             représentant le mouvement à 100 fps. Vide = rien de chargé.
        movement_duration  : durée totale du mouvement en secondes (méta-donnée JSON).
        current_video      : nom du fichier vidéo sélectionné (ex: "discours.mp4").
        current_movement   : chemin absolu du JSON de mouvement chargé.
        processing_status  : phase courante du pipeline ou du rejeu.
                             Valeurs : "idle" | "downloading" | "extracting" | "mapping"
                                     | "ready" | "playing" | "paused" | "error"
        status_message     : message lisible correspondant, affiché dans la status bar UI.
        audio_data         : tableau NumPy (N, 1) float32 16kHz prêt pour LecteurAudio.
                             None si pas d'audio disponible.
        audio_lecteur      : instance LecteurAudio active (thread de lecture en cours).
                             None si pas de lecture audio.
        is_paused          : booléen — le rejeu est-il en pause ?
        paused_elapsed     : temps écoulé (secondes) au moment de la mise en pause.
                             Utilisé pour reprendre au bon endroit (resume, seek).
        is_live_mode       : booléen — le mode caméra live est-il actif ?
        live_processor     : instance LiveProcessor active. None sinon.
    """
    return {
        "is_replaying": False,
        "replay_start_time": None,
        "movement_frames": [],
        "movement_duration": 0.0,
        "current_video": None,
        "current_movement": None,
        "processing_status": "idle",
        "status_message": "Prêt",
        "audio_data": None,
        "audio_lecteur": None,
        "is_paused": False,
        "paused_elapsed": 0.0,
        "is_live_mode": False,
        "live_processor": None,
    }


# ── Helpers robot ─────────────────────────────────────────────────────────────

def set_neutral(reachy_mini: ReachyMini) -> None:
    """Envoie la position neutre au robot : tête droite, antennes à 0, rotation à 0.

    Appelé systématiquement :
      - Au démarrage de robot_loop (position initiale garantie)
      - Après un stop (/stop)
      - Après une fin de rejeu (index dépassé)
      - Après l'arrêt du mode live (/live/stop)
    Cela évite que le robot reste bloqué dans la dernière pose envoyée.
    """
    head_neutre = create_head_pose(yaw=0.0, pitch=0.0, roll=0.0, degrees=True)
    reachy_mini.set_target(
        head=head_neutre,
        antennas=np.array([0.0, 0.0]),
        body_yaw=0.0,
    )


def get_processed_videos() -> list[str]:
    """Retourne la liste des vidéos dans DATA_DIR ayant un fichier de mouvement associé.

    Une vidéo est considérée "traitée et rejouable" si le fichier
    `<stem>_signaux_mouvement.json` existe dans DATA_DIR.
    C'est ce fichier qui est utilisé lors du rejeu (charger_mouvement).

    Returns:
        Liste triée alphabétiquement des noms de fichiers vidéo prêts.
        Liste vide si DATA_DIR n'existe pas encore.
    """
    result = []
    if not os.path.isdir(DATA_DIR):
        return result

    for fname in sorted(os.listdir(DATA_DIR)):
        # Ne traiter que les fichiers vidéo reconnus
        if not fname.lower().endswith(ALLOWED_VIDEO_EXT):
            continue
        stem = os.path.splitext(fname)[0]
        # Le fichier *_signaux_mouvement.json est le produit final du pipeline
        mvt = os.path.join(DATA_DIR, f"{stem}_signaux_mouvement.json")
        if os.path.exists(mvt):
            result.append(fname)

    return result
