"""
Routes FastAPI — Contrôle du rejeu (playback).

Ce module enregistre 5 routes de contrôle du rejeu robot :

    POST /play   → démarre le rejeu depuis le début (ou depuis paused_elapsed)
    POST /stop   → arrête le rejeu et retourne à la position neutre
    POST /pause  → met le rejeu en pause (capture l'instant courant)
    POST /resume → reprend depuis la position de pause
    POST /seek   → avance/recule de N secondes (uniquement en pause)

Toutes ces routes modifient state["is_replaying"], state["is_paused"],
state["replay_start_time"] et/ou state["audio_lecteur"].

La boucle robot_loop.run() lit ces mêmes valeurs à 100 Hz pour décider
quoi envoyer au robot → cohérence garantie par le verrou partagé.
"""

import time

import numpy as np
from fastapi import HTTPException
from pydantic import BaseModel
from reachy_mini.utils import create_head_pose

from app_context import ROBOT_FPS, AppContext, set_neutral

# Import optionnel : si audio_player est absent, le rejeu fonctionne sans son
try:
    from audio_player import LecteurAudio
except ImportError as e:
    print(f"[INFO] Module audio indisponible : {e}")
    LecteurAudio = None


# ── Modèle Pydantic ───────────────────────────────────────────────────────────

class SeekReq(BaseModel):
    """Corps de la requête POST /seek.

    delta : décalage en secondes (positif = avance, négatif = recule).
    Exemple : {"delta": -10} recule de 10 secondes.
    """
    delta: float


# ── Enregistrement des routes ─────────────────────────────────────────────────

def register(ctx: AppContext) -> None:
    """Enregistre toutes les routes de playback sur settings_app.

    Args:
        ctx : contexte partagé (state, lock, reachy_mini, settings_app).
    """
    state = ctx.state
    lock = ctx.lock
    reachy_mini = ctx.reachy_mini
    settings_app = ctx.settings_app

    # ── POST /play ────────────────────────────────────────────────────────────
    @settings_app.post("/play")
    def play():
        """Démarre le rejeu depuis le début.

        - Arrête un éventuel lecteur audio en cours
        - Crée un nouveau LecteurAudio et le démarre
        - Met is_replaying=True et enregistre l'heure de départ
        - robot_loop.run() détectera is_replaying=True dès le prochain tick
        """
        with lock:
            if not state["movement_frames"]:
                # Impossible de jouer si aucun mouvement n'est chargé
                raise HTTPException(status_code=400, detail="Aucun mouvement chargé")

            # Nettoyage d'un éventuel lecteur audio résiduel
            if state["audio_lecteur"] is not None:
                state["audio_lecteur"].arreter()
                state["audio_lecteur"] = None

            # Démarrage de l'audio si disponible
            if LecteurAudio is not None and state["audio_data"] is not None:
                lecteur = LecteurAudio(reachy_mini, state["audio_data"])
                lecteur.demarrer()  # lance le thread de lecture audio depuis le début
                state["audio_lecteur"] = lecteur

            # Activation du rejeu : robot_loop utilisera replay_start_time pour calculer idx
            state["is_paused"] = False
            state["paused_elapsed"] = 0.0
            state["is_replaying"] = True
            state["replay_start_time"] = time.time()  # t0 = maintenant
            state["processing_status"] = "playing"
            state["status_message"] = "Rejeu en cours..."
        return {"started": True}

    # ── POST /stop ────────────────────────────────────────────────────────────
    @settings_app.post("/stop")
    def stop_play():
        """Arrête le rejeu et repositionne le robot en position neutre.

        set_neutral() est appelé HORS du verrou pour ne pas bloquer
        les autres threads pendant la commande réseau au robot.
        """
        with lock:
            state["is_replaying"] = False
            state["is_paused"] = False
            state["paused_elapsed"] = 0.0
            # Arrêt audio immédiat
            if state["audio_lecteur"] is not None:
                state["audio_lecteur"].arreter()
                state["audio_lecteur"] = None
            # Le mouvement est toujours chargé → status "ready" pour pouvoir relancer
            state["processing_status"] = "ready" if state["movement_frames"] else "idle"
            state["status_message"] = "Rejeu arrêté"
        # Retour à la position neutre (hors verrou pour ne pas bloquer)
        set_neutral(reachy_mini)
        return {"stopped": True}

    # ── POST /pause ───────────────────────────────────────────────────────────
    @settings_app.post("/pause")
    def pause_play():
        """Met le rejeu en pause et capture l'instant courant.

        paused_elapsed = temps écoulé depuis t0 au moment de la pause.
        Ce temps est utilisé par resume() et seek() pour reprendre au bon endroit.
        """
        with lock:
            if not state["is_replaying"] or state["is_paused"]:
                raise HTTPException(status_code=400, detail="Pas en cours de rejeu")
            # Capture du temps écoulé AVANT de couper l'audio (pour la précision)
            state["paused_elapsed"] = time.time() - state["replay_start_time"]
            state["is_paused"] = True
            # L'audio est arrêté — il sera recréé depuis le bon offset au resume
            if state["audio_lecteur"] is not None:
                state["audio_lecteur"].arreter()
                state["audio_lecteur"] = None
            state["processing_status"] = "paused"
            state["status_message"] = "Rejeu en pause"
        return {"paused": True, "elapsed": state["paused_elapsed"]}

    # ── POST /resume ──────────────────────────────────────────────────────────
    @settings_app.post("/resume")
    def resume_play():
        """Reprend le rejeu depuis la position de pause.

        On recalcule replay_start_time pour que robot_loop considère
        que le rejeu a démarré il y a `elapsed` secondes.
        L'audio repart depuis le même offset via demarrer_depuis().
        """
        with lock:
            if not state["is_replaying"] or not state["is_paused"]:
                raise HTTPException(status_code=400, detail="Pas en pause")
            elapsed = state["paused_elapsed"]
            # Recalcul du t0 fictif : "comme si" on avait démarré il y a `elapsed` secondes
            state["replay_start_time"] = time.time() - elapsed
            state["is_paused"] = False
            state["processing_status"] = "playing"
            state["status_message"] = "Rejeu en cours..."
            # Reprise de l'audio depuis l'offset exact de la pause
            if LecteurAudio is not None and state["audio_data"] is not None:
                lecteur = LecteurAudio(reachy_mini, state["audio_data"])
                lecteur.demarrer_depuis(elapsed)  # reprend à elapsed secondes dans le fichier audio
                state["audio_lecteur"] = lecteur
        return {"resumed": True, "elapsed": elapsed}

    # ── POST /seek ────────────────────────────────────────────────────────────
    @settings_app.post("/seek")
    def seek_play(req: SeekReq):
        """Avance ou recule de req.delta secondes dans le mouvement (uniquement en pause).

        Calcule la nouvelle position temporelle, clamp entre 0 et la durée totale,
        puis envoie immédiatement la frame correspondante au robot
        pour visualiser la nouvelle position sans attendre la reprise.

        Le seek n'est disponible qu'en pause pour éviter les désynchronisations
        entre l'index robot et la position vidéo côté frontend.
        """
        with lock:
            if not state["is_replaying"] or not state["is_paused"]:
                raise HTTPException(status_code=400, detail="Seek uniquement en pause")
            # Calcul de la nouvelle position temporelle avec clamp [0, durée_totale]
            new_elapsed = state["paused_elapsed"] + req.delta
            new_elapsed = max(0.0, min(new_elapsed, state["movement_duration"]))
            state["paused_elapsed"] = new_elapsed
            frames = state["movement_frames"]
            # Calcul de l'index correspondant (clamp pour ne pas dépasser la liste)
            idx = min(int(new_elapsed * ROBOT_FPS), len(frames) - 1)

        # Envoi immédiat de la frame cible au robot (hors verrou pour ne pas bloquer)
        f = frames[idx]
        h = f["head"]
        head_pose = create_head_pose(
            yaw=h["yaw"],
            pitch=h["pitch"],
            roll=h["roll"],
            x=h["x"],
            y=h["y"],
            z=h["z"],
            degrees=True,
        )
        reachy_mini.set_target(
            head=head_pose,
            antennas=np.array(f["antennas"], dtype=float),
            body_yaw=float(f.get("body_yaw", 0.0)),
        )
        return {"elapsed": new_elapsed}
