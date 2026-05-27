"""
Routes FastAPI — Utilitaires (statut global et accès aux fichiers vidéo).

Ce module enregistre 2 routes légères :

    GET /status        → snapshot complet de l'état de l'application
    GET /video/{name}  → sert un fichier vidéo depuis DATA_DIR

/status est la route la plus appelée de l'application : le frontend
la poll toutes les 500 ms pendant les traitements pour suivre la progression
et synchroniser l'état de l'UI avec l'état réel du backend.
"""

import os

from fastapi import HTTPException
from fastapi.responses import FileResponse

from app_context import DATA_DIR, AppContext


def register(ctx: AppContext) -> None:
    """Enregistre les routes utilitaires sur settings_app.

    Args:
        ctx : contexte partagé (state, lock, reachy_mini, settings_app).
    """
    state = ctx.state
    lock = ctx.lock
    settings_app = ctx.settings_app

    # ── GET /status ───────────────────────────────────────────────────────────
    @settings_app.get("/status")
    def get_status():
        """Retourne un snapshot thread-safe de l'état de l'application.

        Ce snapshot est construit sous le verrou pour garantir la cohérence
        (on ne veut pas lire is_replaying=True mais paused_elapsed d'une pause future).

        Clés retournées :
            processing_status : phase courante ("idle", "ready", "playing", "paused", "error"…)
            status_message    : message lisible pour l'utilisateur
            current_video     : nom de la vidéo sélectionnée (ou None)
            duration          : durée totale du mouvement en secondes
            is_replaying      : le robot est-il en train de rejouer ?
            is_paused         : le rejeu est-il en pause ?
            paused_elapsed    : position temporelle de la pause (secondes)
            frame_count       : nombre de frames du mouvement chargé (0 = rien chargé)
        """
        with lock:
            return {
                "processing_status": state["processing_status"],
                "status_message": state["status_message"],
                "current_video": state["current_video"],
                "duration": state["movement_duration"],
                "is_replaying": state["is_replaying"],
                "is_paused": state["is_paused"],
                "paused_elapsed": state["paused_elapsed"],
                "frame_count": len(state["movement_frames"]),
            }

    # ── GET /video/{name} ─────────────────────────────────────────────────────
    @settings_app.get("/video/{name}")
    def get_video(name: str):
        """Sert un fichier vidéo depuis DATA_DIR.

        Utilisé par le player HTML (<video src="/video/nom.mp4">)
        pour afficher la vidéo source côté navigateur pendant le rejeu.
        os.path.basename() empêche les attaques de traversée de répertoire.
        """
        safe = os.path.basename(name)   # sécurité : retire tout chemin relatif/absolu
        path = os.path.join(DATA_DIR, safe)
        if not os.path.exists(path):
            raise HTTPException(status_code=404, detail="Vidéo introuvable")
        return FileResponse(path)
