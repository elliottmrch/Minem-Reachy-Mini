import os
import threading

from fastapi import File, HTTPException, UploadFile
from pydantic import BaseModel

from app_context import ALLOWED_VIDEO_EXT, DATA_DIR, AppContext, get_processed_videos

try:
    from rejoueur import charger_mouvement
except ImportError as e:
    print(f"[INFO] Module rejoueur indisponible : {e}")
    charger_mouvement = None

try:
    from audio_player import charger_audio
except ImportError as e:
    print(f"[INFO] Module audio indisponible : {e}")
    charger_audio = None

try:
    import yt_dlp as _yt_dlp
except ImportError:
    _yt_dlp = None


class DownloadReq(BaseModel):
    url: str


class SelectReq(BaseModel):
    filename: str


def register(ctx: AppContext) -> None:
    state = ctx.state
    lock = ctx.lock
    settings_app = ctx.settings_app

    @settings_app.post("/upload_video")
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

    @settings_app.post("/download_youtube")
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

    @settings_app.get("/videos")
    def list_videos():
        return {"videos": get_processed_videos()}

    @settings_app.delete("/videos/{filename}")
    def delete_video(filename: str):
        safe = os.path.basename(filename)
        if not safe or not safe.lower().endswith(ALLOWED_VIDEO_EXT):
            raise HTTPException(status_code=400, detail="Nom de fichier invalide")
        video_path = os.path.join(DATA_DIR, safe)
        if not os.path.exists(video_path):
            raise HTTPException(status_code=404, detail="Vidéo introuvable")
        stem = os.path.splitext(safe)[0]
        for fname in [safe, f"{stem}_signaux.json", f"{stem}_signaux_mouvement.json", f"{stem}_audio.wav"]:
            fpath = os.path.join(DATA_DIR, fname)
            if os.path.exists(fpath):
                os.remove(fpath)
        with lock:
            if state["current_video"] == safe:
                state["is_replaying"] = False
                if state["audio_lecteur"] is not None:
                    state["audio_lecteur"].arreter()
                    state["audio_lecteur"] = None
                state["current_video"] = None
                state["movement_frames"] = []
                state["current_movement"] = None
                state["movement_duration"] = 0.0
                state["audio_data"] = None
                state["processing_status"] = "idle"
                state["status_message"] = "Prêt"
        return {"deleted": safe}

    @settings_app.post("/select_video")
    def select_video(req: SelectReq):
        if charger_mouvement is None:
            raise HTTPException(status_code=500, detail="Module rejoueur indisponible")
        with lock:
            if state["processing_status"] in ("extracting", "mapping", "downloading"):
                raise HTTPException(status_code=409, detail="Un traitement est déjà en cours")
        safe_name = os.path.basename(req.filename)
        video_path = os.path.join(DATA_DIR, safe_name)
        if not os.path.exists(video_path):
            raise HTTPException(status_code=404, detail="Vidéo introuvable")
        stem = os.path.splitext(safe_name)[0]
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
                state["current_video"] = safe_name
                state["movement_frames"] = frames
                state["movement_duration"] = float(meta.get("duration_s", 0.0))
                state["current_movement"] = mvt_path
                state["audio_data"] = audio_data
                state["processing_status"] = "ready"
                state["status_message"] = (
                    f"Mouvement prêt ({len(frames)} frames, "
                    f"{float(meta.get('duration_s', 0.0)):.1f}s)"
                )
            return {"filename": safe_name, "cached": True}
        else:
            with lock:
                state["current_video"] = safe_name
                state["movement_frames"] = []
                state["current_movement"] = None
                state["movement_duration"] = 0.0
                state["processing_status"] = "idle"
                state["status_message"] = f"Vidéo chargée : {safe_name}"
            return {"filename": safe_name, "cached": False}
