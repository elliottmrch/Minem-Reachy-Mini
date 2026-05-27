"""
Boucle de commande robot à 100 Hz (moteur principal du rejeu).

Ce module contient l'unique boucle temps-réel de l'application.
Elle s'exécute dans le thread principal de Coquille.run() et est
responsable d'envoyer les frames de mouvement au robot physique.

Fonctionnement :
    Toutes les 10 ms (1 / ROBOT_FPS), la boucle :
      1. Lit un snapshot thread-safe de l'état (is_replaying, frames, t0…).
      2. Si mode live actif → LiveProcessor gère directement le robot, on attend.
      3. Si rejeu actif et non pausé :
           idx = int((time.now - t0) * 100)   ← index de la frame courante
           - Si idx >= len(frames) : fin du mouvement → reset + position neutre.
           - Sinon : envoie head_pose + antennes + body_yaw au robot.
      4. sleep(10ms).

Séparation des rôles :
    robot_loop ne JAMAIS écrire dans state["processing_status"] sauf en fin de rejeu.
    Les routes FastAPI (routes_playback) initialisent et réinitialisent le state.
    robot_loop se contente de LIRE et d'ENVOYER des commandes.
"""

import threading
import time

import numpy as np
from reachy_mini.utils import create_head_pose

from app_context import ROBOT_FPS, AppContext, set_neutral


def run(ctx: AppContext, stop_event: threading.Event) -> None:
    """Boucle de commande bloquante à 100 Hz.

    Tourne jusqu'à ce que stop_event soit déclenché (arrêt propre).
    C'est la dernière instruction de Coquille.run() — elle bloque le thread
    principal pendant toute la durée de vie de l'application.

    Args:
        ctx        : contexte partagé (state, lock, reachy_mini).
        stop_event : Event SDK déclenché lors d'un arrêt propre (Ctrl+C, app.stop()).
    """
    state = ctx.state
    lock = ctx.lock
    reachy_mini = ctx.reachy_mini

    # Période cible entre deux envois de commande : 10 ms à 100 Hz
    period = 1.0 / ROBOT_FPS

    # Position neutre initiale : garantit que le robot part d'un état connu
    set_neutral(reachy_mini)

    while not stop_event.is_set():

        # ── Lecture thread-safe de l'état courant ────────────────────────────
        # On copie les valeurs nécessaires sous le verrou pour avoir un snapshot cohérent.
        # Hors du verrou, on travaille sur les copies locales → section critique courte.
        with lock:
            replaying = state["is_replaying"]
            is_paused = state["is_paused"]
            frames = state["movement_frames"]   # référence à la liste (lecture seule ici)
            t0 = state["replay_start_time"]     # float ou None
            is_live = state["is_live_mode"]

        # ── Mode live ────────────────────────────────────────────────────────
        # En mode live, c'est LiveProcessor qui envoie les commandes robot dans son propre thread.
        # La boucle attend simplement sans interférer.
        if is_live:
            time.sleep(period)
            continue

        # ── Rejeu actif ──────────────────────────────────────────────────────
        if replaying and not is_paused and frames and t0 is not None:

            # Calcul de l'index de frame à envoyer.
            # t = temps écoulé depuis le départ du rejeu (ou la reprise après pause).
            # idx = numéro de la frame à 100 fps correspondant à ce temps.
            t = time.time() - t0
            idx = int(t * ROBOT_FPS)

            if idx >= len(frames):
                # ── Fin du mouvement ─────────────────────────────────────────
                # Toutes les frames ont été envoyées : on reset l'état et revient neutre.
                with lock:
                    state["is_replaying"] = False
                    # Arrêt de l'audio si une lecture est en cours
                    if state["audio_lecteur"] is not None:
                        state["audio_lecteur"].arreter()
                        state["audio_lecteur"] = None
                    state["processing_status"] = "ready"
                    state["status_message"] = "Rejeu terminé"
                set_neutral(reachy_mini)

            else:
                # ── Envoi de la frame courante au robot ──────────────────────
                f = frames[idx]
                h = f["head"]

                # Conversion des angles tête en HeadPose SDK (yaw/pitch/roll en degrés + translations)
                head_pose = create_head_pose(
                    yaw=h["yaw"],
                    pitch=h["pitch"],
                    roll=h["roll"],
                    x=h["x"],      # translation latérale (mètres)
                    y=h["y"],      # translation avant/arrière
                    z=h["z"],      # translation verticale
                    degrees=True,
                )
                reachy_mini.set_target(
                    head=head_pose,
                    antennas=np.array(f["antennas"], dtype=float),  # [antenne_gauche, antenne_droite]
                    body_yaw=float(f.get("body_yaw", 0.0)),         # rotation du torse
                )

        # ── Cadence 100 Hz ───────────────────────────────────────────────────
        # sleep(10ms) pour éviter de brûler un cœur CPU et respecter la fréquence cible
        time.sleep(period)
