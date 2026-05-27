"""
Point d'entrée principal de l'application Coquille.

Ce module crée l'instance de l'app Reachy Mini (classe Coquille),
instancie le contexte partagé (AppContext), enregistre toutes les routes
FastAPI via les sous-modules routes_*, puis démarre la boucle robot 100 Hz.

Architecture de Coquille.run() :
    AppContext (state + lock + robot + fastapi)
        ├─ routes_video.register(ctx)      → gestion des vidéos (upload, YouTube, liste…)
        ├─ routes_processing.register(ctx) → pipeline extraction → mapping → audio
        ├─ routes_playback.register(ctx)   → play / stop / pause / resume / seek
        ├─ routes_live.register(ctx)       → mode caméra live temps réel
        ├─ routes_misc.register(ctx)       → statut global et accès fichiers vidéo
        └─ robot_loop.run(ctx, stop_event) → boucle 100 Hz de commande du robot
"""

import os
import sys
import threading

from reachy_mini import ReachyMini, ReachyMiniApp

# Ajout du répertoire courant (coquille/) dans sys.path.
# Nécessaire pour que les imports absolus des modules du package fonctionnent
# quel que soit le répertoire de travail depuis lequel l'app est lancée.
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

# Contexte partagé et tous les modules de routes/boucle
from app_context import AppContext, create_initial_state
import robot_loop
import routes_live
import routes_misc
import routes_playback
import routes_processing
import routes_video


class Coquille(ReachyMiniApp):
    """Application principale héritant de ReachyMiniApp (SDK Reachy Mini).

    Le SDK appelle automatiquement wrapped_run() qui :
      1. Initialise la connexion au robot physique
      2. Appelle self.run(reachy_mini, stop_event)
      3. Expose self.settings_app (FastAPI) sur l'URL custom_app_url

    Attributs de classe :
        custom_app_url        : URL d'écoute du serveur FastAPI.
                                "http://0.0.0.0:8042" → accessible sur le réseau local.
        request_media_backend : active la gestion audio ("default")
                                ou la désactive ("no_media").
    """

    custom_app_url: str | None = "http://0.0.0.0:8042"
    request_media_backend: str | None = "default"

    def run(self, reachy_mini: ReachyMini, stop_event: threading.Event):
        """Corps principal de l'application, appelé par wrapped_run() après init robot.

        Étapes :
          1. Crée l'AppContext (état runtime + verrou + robot + FastAPI).
          2. Enregistre les routes FastAPI de chaque module thématique.
          3. Démarre la boucle bloquante robot_loop.run() à 100 Hz.
             Cette boucle ne retourne que lorsque stop_event est déclenché.

        Args:
            reachy_mini : connexion au robot physique, injectée par le SDK.
            stop_event  : Event déclenché lors d'un arrêt propre (Ctrl+C, app.stop()).
        """
        # Création du contexte partagé entre toutes les routes et la boucle robot.
        # Une seule instance, partagée par référence → toutes les routes manipulent
        # le MÊME dict state et le MÊME verrou.
        ctx = AppContext(
            state=create_initial_state(),    # dict mutable : tout l'état runtime
            lock=threading.Lock(),            # verrou protégeant les accès concurrents à state
            reachy_mini=reachy_mini,          # connexion au robot (set_target, media…)
            settings_app=self.settings_app,  # instance FastAPI sur laquelle enregistrer les routes
        )

        # Enregistrement des routes par thématique.
        # Chaque register() définit des fonctions locales décorées avec @settings_app.post/get
        # et les injecte directement dans l'instance FastAPI.
        routes_video.register(ctx)       # /upload_video, /download_youtube, /videos, /select_video
        routes_processing.register(ctx)  # /process_video (pipeline complet)
        routes_playback.register(ctx)    # /play, /stop, /pause, /resume, /seek
        routes_live.register(ctx)        # /live/start, /live/stop, /live/stream, /live/status
        routes_misc.register(ctx)        # /status, /video/<name>

        # Boucle bloquante 100 Hz — ne retourne pas avant l'arrêt de l'app
        robot_loop.run(ctx, stop_event)


if __name__ == "__main__":
    # Lancement direct : python -m coquille.main
    # Lance uniquement l'app web sans menu CLI.
    # Pour le menu interactif (options Jalons 2/3, POC…) : python -m coquille.cli
    app = Coquille()
    try:
        app.wrapped_run()
    except KeyboardInterrupt:
        app.stop()
