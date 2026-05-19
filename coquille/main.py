import os
import sys
import threading
import time

import numpy as np
from fastapi import File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from reachy_mini import ReachyMini, ReachyMiniApp
from reachy_mini.utils import create_head_pose

# Ajout du dossier courant au path pour garantir le fonctionnement des imports
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

DATA_DIR = os.path.abspath(os.path.join(current_dir, "..", "data"))

# Import des autres modules du projet
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
    from mapper import generer_mouvement, lancer_mapping
    from rejoueur import charger_mouvement, lancer_rejeu
except ImportError as e:
    print(f"[INFO] Impossible d'importer les modules Jalon 3 : {e}")
    generer_mouvement = None
    lancer_mapping = None
    lancer_rejeu = None
    charger_mouvement = None

try:
    import yt_dlp as _yt_dlp
except ImportError:
    _yt_dlp = None


ALLOWED_VIDEO_EXT = (".mp4", ".avi", ".mov", ".webm", ".mkv")
ROBOT_FPS = 100


class Coquille(ReachyMiniApp):
    custom_app_url: str | None = "http://localhost:8042"
    request_media_backend: str | None = "no_media"

    def run(self, reachy_mini: ReachyMini, stop_event: threading.Event):
        state = {
            "is_replaying": False,
            "replay_start_time": None,
            "movement_frames": [],
            "movement_duration": 0.0,
            "current_video": None,
            "current_movement": None,
            "processing_status": "idle",
            "status_message": "Prêt",
        }
        lock = threading.Lock()

        def _set_neutral():
            head_neutre = create_head_pose(yaw=0.0, pitch=0.0, roll=0.0, degrees=True)
            reachy_mini.set_target(
                head=head_neutre,
                antennas=np.array([0.0, 0.0]),
                body_yaw=0.0,
            )

        # === Endpoints FastAPI ===

        @self.settings_app.post("/upload_video")
        async def upload_video(file: UploadFile = File(...)):
            if not file.filename or not file.filename.lower().endswith(ALLOWED_VIDEO_EXT):
                raise HTTPException(status_code=400, detail="Format non supporté")
            safe_name = os.path.basename(file.filename)
            os.makedirs(DATA_DIR, exist_ok=True)
            dest = os.path.join(DATA_DIR, safe_name)
            content = await file.read()
            with open(dest, "wb") as fp:
                fp.write(content)
            with lock:
                state["current_video"] = safe_name
                state["movement_frames"] = []
                state["current_movement"] = None
                state["movement_duration"] = 0.0
                state["processing_status"] = "idle"
                state["status_message"] = f"Vidéo chargée : {safe_name}"
            return {"filename": safe_name}

        class DownloadReq(BaseModel):
            url: str

        @self.settings_app.post("/download_youtube")
        def download_youtube(req: DownloadReq):
            if _yt_dlp is None:
                raise HTTPException(status_code=500, detail="yt_dlp non installé")
            if not ("youtube.com" in req.url or "youtu.be" in req.url):
                raise HTTPException(status_code=400, detail="URL YouTube invalide")

            def _download():
                try:
                    with lock:
                        state["processing_status"] = "downloading"
                        state["status_message"] = "Téléchargement YouTube..."

                    def _progress(d):
                        if d["status"] == "downloading":
                            total = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
                            downloaded = d.get("downloaded_bytes", 0)
                            if total > 0:
                                pct = int(downloaded / total * 100)
                                with lock:
                                    state["status_message"] = f"Téléchargement... {pct}%"

                    os.makedirs(DATA_DIR, exist_ok=True)
                    ydl_opts = {
                        "format": "best[ext=mp4]/best",
                        "outtmpl": os.path.join(DATA_DIR, "%(id)s.%(ext)s"),
                        "noplaylist": True,
                        "quiet": True,
                        "progress_hooks": [_progress],
                    }
                    with _yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(req.url, download=True)

                    safe_name = f"{info['id']}.{info.get('ext', 'mp4')}"
                    final_path = os.path.join(DATA_DIR, safe_name)
                    if not os.path.exists(final_path):
                        raise RuntimeError("Fichier téléchargé introuvable")

                    with lock:
                        state["current_video"] = safe_name
                        state["movement_frames"] = []
                        state["current_movement"] = None
                        state["movement_duration"] = 0.0
                        state["processing_status"] = "idle"
                        state["status_message"] = f"Vidéo téléchargée : {safe_name}"
                except Exception as e:
                    with lock:
                        state["processing_status"] = "error"
                        state["status_message"] = f"Erreur téléchargement : {e}"

            threading.Thread(target=_download, daemon=True).start()
            return {"started": True}

        class ProcessReq(BaseModel):
            filename: str

        @self.settings_app.post("/process_video")
        def process_video(req: ProcessReq):
            if analyser_video is None or generer_mouvement is None or charger_mouvement is None:
                raise HTTPException(status_code=500, detail="Modules pipeline indisponibles")

            video_path = os.path.join(DATA_DIR, os.path.basename(req.filename))
            if not os.path.exists(video_path):
                raise HTTPException(status_code=404, detail="Vidéo introuvable")

            def _pipeline():
                try:
                    with lock:
                        state["processing_status"] = "extracting"
                        state["status_message"] = "Extraction des signaux..."
                    signaux_path = analyser_video(video_path)
                    if not signaux_path:
                        raise RuntimeError("Échec de l'extraction (aucun visage détecté ?)")

                    with lock:
                        state["processing_status"] = "mapping"
                        state["status_message"] = "Génération du mouvement..."
                    mvt_path = generer_mouvement(signaux_path)
                    if not mvt_path:
                        raise RuntimeError("Échec de la génération du mouvement")

                    frames, meta = charger_mouvement(mvt_path)
                    with lock:
                        state["movement_frames"] = frames
                        state["movement_duration"] = float(meta.get("duration_s", 0.0))
                        state["current_movement"] = mvt_path
                        state["processing_status"] = "ready"
                        state["status_message"] = (
                            f"Mouvement prêt ({len(frames)} frames, "
                            f"{state['movement_duration']:.1f}s)"
                        )
                except Exception as e:
                    with lock:
                        state["processing_status"] = "error"
                        state["status_message"] = f"Erreur : {e}"

            threading.Thread(target=_pipeline, daemon=True).start()
            return {"started": True}

        @self.settings_app.post("/play")
        def play():
            with lock:
                if not state["movement_frames"]:
                    raise HTTPException(status_code=400, detail="Aucun mouvement chargé")
                state["is_replaying"] = True
                state["replay_start_time"] = time.time()
                state["processing_status"] = "playing"
                state["status_message"] = "Rejeu en cours..."
            return {"started": True}

        @self.settings_app.post("/stop")
        def stop_play():
            with lock:
                state["is_replaying"] = False
                state["processing_status"] = "ready" if state["movement_frames"] else "idle"
                state["status_message"] = "Rejeu arrêté"
            _set_neutral()
            return {"stopped": True}

        @self.settings_app.get("/status")
        def get_status():
            with lock:
                return {
                    "processing_status": state["processing_status"],
                    "status_message": state["status_message"],
                    "current_video": state["current_video"],
                    "duration": state["movement_duration"],
                    "is_replaying": state["is_replaying"],
                    "frame_count": len(state["movement_frames"]),
                }

        @self.settings_app.get("/video/{name}")
        def get_video(name: str):
            safe = os.path.basename(name)
            path = os.path.join(DATA_DIR, safe)
            if not os.path.exists(path):
                raise HTTPException(status_code=404, detail="Vidéo introuvable")
            return FileResponse(path)

        # === Boucle de contrôle (100 Hz) ===

        period = 1.0 / ROBOT_FPS
        _set_neutral()

        while not stop_event.is_set():
            with lock:
                replaying = state["is_replaying"]
                frames = state["movement_frames"]
                t0 = state["replay_start_time"]

            if replaying and frames and t0 is not None:
                t = time.time() - t0
                idx = int(t * ROBOT_FPS)
                if idx >= len(frames):
                    with lock:
                        state["is_replaying"] = False
                        state["processing_status"] = "ready"
                        state["status_message"] = "Rejeu terminé"
                    _set_neutral()
                else:
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

            time.sleep(period)


def menu_principal():
    while True:
        print("\n" + "=" * 40)
        print("       PROJET COQUILLE - HUB PRINCIPAL")
        print("=" * 40)
        print("1. Lancer l'App Coquille (Web Interface + Robot)")
        print("2. Lancer le menu des POC (Vision, Audio, YouTube)")
        print("3. Lancer les programmes de test (Sinusoïdes, Cercles)")
        print("4. Analyse de vidéo - extraction de signaux (Jalon 2)")
        print("5. Générer un mouvement robot depuis les signaux (Jalon 3)")
        print("6. Rejouer un mouvement en simulation (Jalon 3)")
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
                    if json_path and visualiser_video:
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

        elif choix == 'q':
            print("Fermeture du hub. À bientôt !")
            break

        else:
            print("Option invalide. Réessayer.")


if __name__ == "__main__":
    app = Coquille()
    try:
        app.wrapped_run()
    except KeyboardInterrupt:
        app.stop()
