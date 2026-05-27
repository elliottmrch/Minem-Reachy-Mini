"""
Routes FastAPI — Mode caméra live.

Ce module enregistre 4 routes pour le mode live :

    POST /live/start   → démarre LiveProcessor (capture + traitement caméra)
    POST /live/stop    → arrête LiveProcessor et remet le robot en position neutre
    GET  /live/stream  → flux MJPEG (multipart/x-mixed-replace) pour affichage dans <img>
    GET  /live/status  → état courant (is_live, calibrated)

En mode live, LiveProcessor capture les frames de la webcam dans son propre thread,
détecte les landmarks faciaux (MediaPipe), mappe les signaux sur les commandes
du robot (en utilisant mapper.py), et envoie les commandes directement.
La boucle robot_loop.run() est suspendue pendant ce mode (is_live_mode=True).

Le flux MJPEG est un générateur asynchrone qui lit les JPEG encodés depuis
LiveProcessor.get_latest_frame() et les envoie en continu au navigateur.
"""

from fastapi import HTTPException
from fastapi.responses import StreamingResponse

from app_context import AppContext, set_neutral

# Import optionnel : si mediapipe n'est pas installé, la route renvoie HTTP 500
try:
    from live import LiveProcessor
except ImportError as e:
    print(f"[INFO] Module live indisponible : {e}")
    LiveProcessor = None


def register(ctx: AppContext) -> None:
    """Enregistre toutes les routes live sur settings_app.

    Args:
        ctx : contexte partagé (state, lock, reachy_mini, settings_app).
    """
    state = ctx.state
    lock = ctx.lock
    reachy_mini = ctx.reachy_mini
    settings_app = ctx.settings_app

    # ── POST /live/start ──────────────────────────────────────────────────────
    @settings_app.post("/live/start")
    def live_start():
        """Démarre le mode live caméra.

        Si un rejeu est en cours, il est interrompu avant le démarrage.
        Si un LiveProcessor existait déjà, il est arrêté puis remplacé.
        La calibration de l'expression neutre prend ~30 frames au démarrage.
        """
        if LiveProcessor is None:
            raise HTTPException(status_code=500, detail="Module live indisponible")

        with lock:
            # Interruption propre d'un éventuel rejeu en cours
            if state["is_replaying"]:
                state["is_replaying"] = False
                if state["audio_lecteur"] is not None:
                    state["audio_lecteur"].arreter()
                    state["audio_lecteur"] = None
                state["is_paused"] = False
                state["paused_elapsed"] = 0.0
                state["processing_status"] = "ready" if state["movement_frames"] else "idle"

            # Arrêt d'un éventuel processor précédent (sécurité en cas de double appel)
            if state["live_processor"] is not None:
                state["live_processor"].stop()

            # Création et démarrage du nouveau LiveProcessor
            proc = LiveProcessor(reachy_mini)
            proc.start()  # démarre le thread de capture caméra
            state["live_processor"] = proc
            state["is_live_mode"] = True  # signal pour robot_loop de ne pas interferer

        return {"started": True}

    # ── POST /live/stop ───────────────────────────────────────────────────────
    @settings_app.post("/live/stop")
    def live_stop():
        """Arrête le mode live et remet le robot en position neutre.

        proc.stop() est appelé HORS du verrou pour ne pas bloquer
        le thread pendant la terminaison du thread caméra (join avec timeout).
        """
        with lock:
            proc = state["live_processor"]
            state["is_live_mode"] = False      # robot_loop peut reprendre le contrôle
            state["live_processor"] = None
        if proc is not None:
            proc.stop()  # arrête le thread caméra (join timeout=3s)
        set_neutral(reachy_mini)  # retour position neutre
        return {"stopped": True}

    # ── GET /live/stream ──────────────────────────────────────────────────────
    @settings_app.get("/live/stream")
    async def live_stream():
        """Retourne un flux MJPEG continu pour affichage dans un <img> HTML.

        Le format multipart/x-mixed-replace est le format MJPEG standard :
        chaque frame est une partie MIME avec Content-Type: image/jpeg.
        Le navigateur remplace l'image précédente dès qu'une nouvelle arrive.
        La boucle tourne à ~30 fps (asyncio.sleep(1/30)).
        """
        import asyncio

        async def _mjpeg():
            """Générateur asynchrone de frames JPEG."""
            # Lecture initiale du processor (peut être None si stop a déjà été appelé)
            with lock:
                proc = state["live_processor"]

            while True:
                # Relecture à chaque itération car le processor peut changer
                with lock:
                    proc = state["live_processor"]
                if proc is None:
                    break  # Le mode live a été arrêté → on ferme le flux

                frame = proc.get_latest_frame()  # bytes JPEG ou None
                if frame:
                    # Format MJPEG : séparateur + en-tête MIME + données JPEG + saut de ligne
                    yield (
                        b"--frame\r\n"
                        b"Content-Type: image/jpeg\r\n\r\n"
                        + frame
                        + b"\r\n"
                    )
                # ~30 fps : pas besoin d'aller plus vite pour affichage UI
                await asyncio.sleep(1 / 30)

        return StreamingResponse(
            _mjpeg(),
            media_type="multipart/x-mixed-replace; boundary=frame",
        )

    # ── GET /live/status ──────────────────────────────────────────────────────
    @settings_app.get("/live/status")
    def live_status():
        """Retourne l'état courant du mode live.

        Le frontend poll cette route pour savoir quand la calibration est terminée
        (is_calibrated=True après ~30 frames, soit ~1 seconde).

        Returns:
            {"is_live": bool, "calibrated": bool}
        """
        with lock:
            proc = state["live_processor"]
            is_live = state["is_live_mode"]
        # is_calibrated() est thread-safe (verrou interne dans LiveProcessor)
        calibrated = proc.is_calibrated() if proc is not None else False
        return {"is_live": is_live, "calibrated": calibrated}
