import os
import sys
import threading

from reachy_mini import ReachyMini, ReachyMiniApp

# Ajout du dossier courant au path pour garantir le fonctionnement des imports
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

from app_context import AppContext, create_initial_state
import robot_loop
import routes_live
import routes_misc
import routes_playback
import routes_processing
import routes_video


class Coquille(ReachyMiniApp):
    custom_app_url: str | None = "http://0.0.0.0:8042"
    request_media_backend: str | None = "default"

    def run(self, reachy_mini: ReachyMini, stop_event: threading.Event):
        ctx = AppContext(
            state=create_initial_state(),
            lock=threading.Lock(),
            reachy_mini=reachy_mini,
            settings_app=self.settings_app,
        )

        routes_video.register(ctx)
        routes_processing.register(ctx)
        routes_playback.register(ctx)
        routes_live.register(ctx)
        routes_misc.register(ctx)

        robot_loop.run(ctx, stop_event)


if __name__ == "__main__":
    app = Coquille()
    try:
        app.wrapped_run()
    except KeyboardInterrupt:
        app.stop()
