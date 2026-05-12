import threading
from reachy_mini import ReachyMini, ReachyMiniApp
from reachy_mini.utils import create_head_pose
import numpy as np
import time
from pydantic import BaseModel


class Coquille(ReachyMiniApp):
    # Optional: URL to a custom configuration page for the app
    # eg. "http://localhost:8042"
    custom_app_url: str | None = "http://0.0.0.0:8042"
    # Optional: specify a media backend ("gstreamer", "gstreamer_no_video", "default", etc.)
    # On the wireless, use gstreamer_no_video to optimise CPU usage if the app does not use video streaming
    request_media_backend: str | None = "no_media"

    def run(self, reachy_mini: ReachyMini, stop_event: threading.Event):
        t0 = time.time()

        antennas_enabled = True
        sound_play_requested = False

        # You can ignore this part if you don't want to add settings to your app. If you set custom_app_url to None, you have to remove this part as well.
        # === vvv ===
        class AntennaState(BaseModel):
            enabled: bool

        @self.settings_app.post("/antennas")
        def update_antennas_state(state: AntennaState):
            nonlocal antennas_enabled
            antennas_enabled = state.enabled
            return {"antennas_enabled": antennas_enabled}

        @self.settings_app.post("/play_sound")
        def request_sound_play():
            nonlocal sound_play_requested
            sound_play_requested = True

        # === ^^^ ===

        # Main control loop
        while not stop_event.is_set():
            t = time.time() - t0

            yaw_deg = 30.0 * np.sin(2.0 * np.pi * 0.2 * t)
            head_pose = create_head_pose(yaw=yaw_deg, degrees=True)

            if antennas_enabled:
                amp_deg = 25.0
                a = amp_deg * np.sin(2.0 * np.pi * 0.5 * t)
                antennas_deg = np.array([a, -a])
            else:
                antennas_deg = np.array([0.0, 0.0])

            if sound_play_requested:
                print("Playing sound...")
                reachy_mini.media.play_sound("wake_up.wav")
                sound_play_requested = False

            antennas_rad = np.deg2rad(antennas_deg)

            reachy_mini.set_target(
                head=head_pose,
                antennas=antennas_rad,
            )

            time.sleep(0.02)

import sys
import os

# Ajout du dossier courant au path pour garantir le fonctionnement des imports
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

# Import des autres modules du projet
DATA_DIR = os.path.abspath(os.path.join(current_dir, "..", "data"))

try:
    from experiments.poc.poc import main as run_poc_menu
    from experiments.programmes_test import select_program as run_tests
except ImportError as e:
    print(f"[INFO] Impossible d'importer certains modules : {e}")
    run_poc_menu = None
    run_tests = None

try:
    from extracteur import analyser_video
    from tools.visualiseur import visualiser_video
except ImportError as e:
    print(f"[INFO] Impossible d'importer les modules Jalon 2 : {e}")
    analyser_video = None
    visualiser_video = None

try:
    from mapper import lancer_mapping
    from rejoueur import lancer_rejeu
    from webcam_direct import lancer_webcam_direct
except ImportError as e:
    print(f"[INFO] Impossible d'importer les modules Jalon 3 : {e}")
    lancer_mapping = None
    lancer_rejeu = None
    lancer_webcam_direct = None

def menu_principal():
    while True:
        print("\n" + "="*40)
        print("       PROJET COQUILLE - HUB PRINCIPAL")
        print("="*40)
        print("1. Lancer l'App Coquille (Web Interface + Robot)")
        print("2. Lancer le menu des POC (Vision, Audio, YouTube)")
        print("3. Lancer les programmes de test (Sinusoïdes, Cercles)")
        print("4. Analyse de vidéo - extraction de signaux (Jalon 2)")
        print("5. Générer un mouvement robot depuis les signaux (Jalon 3)")
        print("6. Rejouer un mouvement en simulation (Jalon 3)")
        print("7. Mode webcam direct (webcam → robot en temps réel)")
        print("q. Quitter")

        choix = input("\nVotre choix : ").lower()

        if choix == '1':
            print("\nLancement de l'application Reachy Mini...")
            app = Coquille()
            try:
                app.wrapped_run()
            except KeyboardInterrupt:
                app.stop()

        elif choix == '2':
            if run_poc_menu:
                print("\nOuverture du menu POC...")
                run_poc_menu()
            else:
                print("\n[ERREUR] Le module POC n'a pas pu être chargé. Vérifier les dossiers.")

        elif choix == '3':
            if run_tests:
                print("\nOuverture des programmes de test...")
                run_tests()
            else:
                print("\n[ERREUR] Le module de test n'a pas pu être chargé. Vérifier les dossiers.")

        elif choix == '4':
            if not analyser_video:
                print("\n[ERREUR] Les modules Jalon 2 n'ont pas pu être chargés.")
            else:
                filename = input("\nNom du fichier vidéo dans data/ (ex: haine.mp4) : ").strip()
                video_path = os.path.join(DATA_DIR, filename)
                if not os.path.exists(video_path):
                    print(f"[ERREUR] '{video_path}' introuvable.")
                else:
                    json_path = analyser_video(video_path)
                    if json_path:
                        visualiser_video(video_path, json_path)

        elif choix == '5':
            if lancer_mapping:
                lancer_mapping()
            else:
                print("\n[ERREUR] Le module mapper n'a pas pu être chargé.")

        elif choix == '6':
            if lancer_rejeu:
                lancer_rejeu()
            else:
                print("\n[ERREUR] Le module rejoueur n'a pas pu être chargé.")

        elif choix == '7':
            if lancer_webcam_direct:
                lancer_webcam_direct()
            else:
                print("\n[ERREUR] Le module webcam_direct n'a pas pu être chargé.")

        elif choix == 'q':
            print("Fermeture du hub. À bientôt !")
            break

        else:
            print("Option invalide. Réessayer.")

if __name__ == "__main__":
    try:
        menu_principal()
    except KeyboardInterrupt:
        print("\nArrêt forcé du programme.")