import os
import threading

from fastapi import HTTPException
from pydantic import BaseModel

from app_context import DATA_DIR, AppContext

try:
    from extracteur import analyser_video
except ImportError as e:
    print(f"[INFO] Module extracteur indisponible : {e}")
    analyser_video = None

try:
    from mapper import generer_mouvement
except ImportError as e:
    print(f"[INFO] Module mapper indisponible : {e}")
    generer_mouvement = None

try:
    from rejoueur import charger_mouvement
except ImportError as e:
    print(f"[INFO] Module rejoueur indisponible : {e}")
    charger_mouvement = None

try:
    from audio_player import charger_audio, extraire_audio_video
except ImportError as e:
    print(f"[INFO] Module audio indisponible : {e}")
    charger_audio = None
    extraire_audio_video = None


class ProcessReq(BaseModel):
    filename: str


def register(ctx: AppContext) -> None:
    state = ctx.state
    lock = ctx.lock
    settings_app = ctx.settings_app

    @settings_app.post("/process_video")
    def process_video(req: ProcessReq):
        if analyser_video is None or generer_mouvement is None or charger_mouvement is None:
            raise HTTPException(status_code=500, detail="Modules pipeline indisponibles")

        video_path = os.path.join(DATA_DIR, os.path.basename(req.filename))
        if not os.path.exists(video_path):
            raise HTTPException(status_code=404, detail="Vidéo introuvable")

        def _pipeline():
            try:
                stem = os.path.splitext(os.path.basename(req.filename))[0]
                mvt_path = os.path.join(DATA_DIR, f"{stem}_signaux_mouvement.json")
                if os.path.exists(mvt_path):
                    frames, meta = charger_mouvement(mvt_path)
                    audio_data = None
                    if charger_audio is not None:
                        audio_path = os.path.join(DATA_DIR, f"{stem}_audio.wav")
                        if os.path.exists(audio_path):
                            try:
                                audio_data = charger_audio(audio_path)
                            except Exception as ae:
                                print(f"[WARN] Chargement audio échoué : {ae}")
                    with lock:
                        state["movement_frames"] = frames
                        state["movement_duration"] = float(meta.get("duration_s", 0.0))
                        state["current_movement"] = mvt_path
                        state["audio_data"] = audio_data
                        state["processing_status"] = "ready"
                        state["status_message"] = (
                            f"Mouvement prêt (cache) — {len(frames)} frames, "
                            f"{float(meta.get('duration_s', 0.0)):.1f}s"
                        )
                    return

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
                audio_data = None
                if extraire_audio_video is not None and charger_audio is not None:
                    audio_path = os.path.join(DATA_DIR, f"{stem}_audio.wav")
                    if not os.path.exists(audio_path):
                        try:
                            extraire_audio_video(video_path, audio_path)
                        except Exception as ae:
                            print(f"[WARN] Extraction audio échouée : {ae}")
                    if os.path.exists(audio_path):
                        try:
                            audio_data = charger_audio(audio_path)
                        except Exception as ae:
                            print(f"[WARN] Chargement audio échoué : {ae}")
                with lock:
                    state["movement_frames"] = frames
                    state["movement_duration"] = float(meta.get("duration_s", 0.0))
                    state["current_movement"] = mvt_path
                    state["audio_data"] = audio_data
                    state["processing_status"] = "ready"
                    state["status_message"] = (
                        f"Mouvement prêt ({len(frames)} frames, "
                        f"{state['movement_duration']:.1f}s)"
                    )
            except ValueError as e:
                with lock:
                    state["processing_status"] = "error"
                    state["status_message"] = str(e)
            except Exception as e:
                with lock:
                    state["processing_status"] = "error"
                    state["status_message"] = f"Erreur : {e}"

        threading.Thread(target=_pipeline, daemon=True).start()
        return {"started": True}
