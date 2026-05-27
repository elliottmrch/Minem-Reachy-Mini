"""
Routes FastAPI — Gestion des vidéos.

Ce module enregistre 5 routes de gestion de vidéos sur l'instance FastAPI :

    POST /upload_video      → upload d'un fichier vidéo depuis le navigateur
    POST /download_youtube  → téléchargement asynchrone via yt-dlp
    GET  /videos            → liste des vidéos déjà traitées (avec JSON mouvement)
    DELETE /videos/{name}   → suppression d'une vidéo et de tous ses fichiers associés
    POST /select_video      → sélection d'une vidéo déjà traitée (chargement en mémoire)

Toutes ces routes partagent le même state/lock via AppContext.
Les modifications de state se font toujours sous `with lock:`.
"""

import os
import threading

from fastapi import File, HTTPException, UploadFile
from pydantic import BaseModel

from app_context import ALLOWED_VIDEO_EXT, DATA_DIR, AppContext, get_processed_videos

# ── Imports optionnels (graceful degradation) ─────────────────────────────────
# Si rejoueur ou audio ne sont pas disponibles, les fonctionnalités dégradent
# proprement (erreur HTTP 500 au lieu d'un crash au démarrage).

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
    # yt-dlp est optionnel : la route /download_youtube renvoie 500 si absent
    _yt_dlp = None


# ── Modèles Pydantic ──────────────────────────────────────────────────────────
# Pydantic valide automatiquement le corps JSON des requêtes POST.

class DownloadReq(BaseModel):
    """Corps de la requête POST /download_youtube."""
    url: str  # URL YouTube à télécharger (doit contenir "youtube.com" ou "youtu.be")


class SelectReq(BaseModel):
    """Corps de la requête POST /select_video."""
    filename: str  # Nom du fichier vidéo déjà présent dans DATA_DIR


# ── Enregistrement des routes ─────────────────────────────────────────────────

def register(ctx: AppContext) -> None:
    """Enregistre toutes les routes de gestion vidéo sur settings_app.

    Les fonctions définies ici sont des closures capturant state, lock et settings_app
    depuis ctx. Elles sont directement décorées avec @settings_app.post/get/delete
    ce qui les injecte dans l'instance FastAPI à l'appel de register().

    Args:
        ctx : contexte partagé (state, lock, reachy_mini, settings_app).
    """
    state = ctx.state
    lock = ctx.lock
    settings_app = ctx.settings_app

    # ── POST /upload_video ────────────────────────────────────────────────────
    @settings_app.post("/upload_video")
    async def upload_video(file: UploadFile = File(...)):
        """Reçoit un fichier vidéo depuis le formulaire HTML et le sauvegarde dans DATA_DIR.

        Valide l'extension, écrit le fichier sur disque, met à jour state.
        Le pipeline (process_video) doit être lancé séparément.
        """
        # Validation de l'extension avant d'écrire quoi que ce soit sur disque
        if not file.filename or not file.filename.lower().endswith(ALLOWED_VIDEO_EXT):
            raise HTTPException(status_code=400, detail="Format non supporté")

        # Nettoyage du nom : os.path.basename retire tout chemin éventuel (sécurité)
        safe_name = os.path.basename(file.filename)
        os.makedirs(DATA_DIR, exist_ok=True)
        dest = os.path.join(DATA_DIR, safe_name)

        # Lecture asynchrone du contenu et écriture sur disque
        content = await file.read()
        with open(dest, "wb") as fp:
            fp.write(content)

        # Mise à jour de l'état : on réinitialise tout ce qui concerne le mouvement
        # car la vidéo vient d'être uploadée et n'a pas encore été traitée
        with lock:
            state["current_video"] = safe_name
            state["movement_frames"] = []
            state["current_movement"] = None
            state["movement_duration"] = 0.0
            state["processing_status"] = "idle"
            state["status_message"] = f"Vidéo chargée : {safe_name}"
        return {"filename": safe_name}

    # ── POST /download_youtube ────────────────────────────────────────────────
    @settings_app.post("/download_youtube")
    def download_youtube(req: DownloadReq):
        """Lance le téléchargement d'une vidéo YouTube en arrière-plan via yt-dlp.

        Le téléchargement est non-bloquant : un thread daemon est lancé et
        met à jour state à chaque progression. Le frontend poll /status pour suivre.
        """
        if _yt_dlp is None:
            raise HTTPException(status_code=500, detail="yt_dlp non installé")
        if not ("youtube.com" in req.url or "youtu.be" in req.url):
            raise HTTPException(status_code=400, detail="URL YouTube invalide")

        def _download():
            """Thread interne : télécharge la vidéo et met à jour state."""
            try:
                # Signalement immédiat du début du téléchargement dans l'UI
                with lock:
                    state["processing_status"] = "downloading"
                    state["status_message"] = "Téléchargement YouTube..."

                def _progress(d):
                    """Hook yt-dlp appelé périodiquement pour reporter la progression."""
                    if d["status"] == "downloading":
                        total = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
                        downloaded = d.get("downloaded_bytes", 0)
                        if total > 0:
                            pct = int(downloaded / total * 100)
                            with lock:
                                state["status_message"] = f"Téléchargement... {pct}%"

                os.makedirs(DATA_DIR, exist_ok=True)
                ydl_opts = {
                    "format": "best[ext=mp4]/best",  # préférence mp4 pour compatibilité navigateur
                    "outtmpl": os.path.join(DATA_DIR, "%(id)s.%(ext)s"),  # nom = ID YouTube
                    "noplaylist": True,   # ne télécharger qu'une seule vidéo, pas toute une playlist
                    "quiet": True,        # pas de sortie console yt-dlp
                    "progress_hooks": [_progress],
                }
                with _yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(req.url, download=True)

                safe_name = f"{info['id']}.{info.get('ext', 'mp4')}"
                final_path = os.path.join(DATA_DIR, safe_name)
                if not os.path.exists(final_path):
                    raise RuntimeError("Fichier téléchargé introuvable")

                # Succès : on met à jour l'état comme après un upload classique
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

        # Lancement non-bloquant dans un thread daemon (s'arrête si l'app s'arrête)
        threading.Thread(target=_download, daemon=True).start()
        return {"started": True}

    # ── GET /videos ───────────────────────────────────────────────────────────
    @settings_app.get("/videos")
    def list_videos():
        """Retourne la liste des vidéos déjà traitées (ayant un JSON de mouvement).

        Utilisé par le frontend pour peupler le menu déroulant "Vidéos déjà traitées".
        """
        return {"videos": get_processed_videos()}

    # ── DELETE /videos/{filename} ─────────────────────────────────────────────
    @settings_app.delete("/videos/{filename}")
    def delete_video(filename: str):
        """Supprime une vidéo et tous ses fichiers dérivés.

        Fichiers supprimés (si présents) :
          - <stem>.mp4           : vidéo source
          - <stem>_signaux.json  : signaux bruts extraits par extracteur
          - <stem>_signaux_mouvement.json : mouvement généré par mapper
          - <stem>_audio.wav     : piste audio extraite

        Si la vidéo supprimée est celle actuellement chargée en mémoire,
        l'état est entièrement réinitialisé.
        """
        # Nettoyage du nom pour éviter les traversées de répertoire (sécurité)
        safe = os.path.basename(filename)
        if not safe or not safe.lower().endswith(ALLOWED_VIDEO_EXT):
            raise HTTPException(status_code=400, detail="Nom de fichier invalide")
        video_path = os.path.join(DATA_DIR, safe)
        if not os.path.exists(video_path):
            raise HTTPException(status_code=404, detail="Vidéo introuvable")

        # Suppression de tous les fichiers associés à cette vidéo
        stem = os.path.splitext(safe)[0]
        for fname in [safe, f"{stem}_signaux.json", f"{stem}_signaux_mouvement.json", f"{stem}_audio.wav"]:
            fpath = os.path.join(DATA_DIR, fname)
            if os.path.exists(fpath):
                os.remove(fpath)

        # Si la vidéo supprimée était la vidéo active, on nettoie le state complet
        with lock:
            if state["current_video"] == safe:
                state["is_replaying"] = False
                # Arrêt de l'audio si une lecture est en cours
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

    # ── POST /select_video ────────────────────────────────────────────────────
    @settings_app.post("/select_video")
    def select_video(req: SelectReq):
        """Charge en mémoire une vidéo déjà présente dans DATA_DIR.

        Si un fichier de mouvement existe pour cette vidéo, il est chargé
        immédiatement (frames + durée + audio). Sinon, la vidéo est marquée
        comme "chargée mais non traitée" (il faudra lancer le pipeline).

        Returns:
            {"filename": str, "cached": bool}
            cached=True si le mouvement était déjà généré et a été chargé.
        """
        if charger_mouvement is None:
            raise HTTPException(status_code=500, detail="Module rejoueur indisponible")

        # Refus si un traitement est déjà en cours (on ne peut pas changer de vidéo en plein pipeline)
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
            # ── Vidéo déjà traitée : chargement du mouvement et de l'audio ──
            frames, meta = charger_mouvement(mvt_path)

            # Tentative de chargement de l'audio associé (peut ne pas exister)
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
            # ── Vidéo non encore traitée : chargement sans mouvement ──────────
            # L'UI devra proposer de lancer le pipeline (process_video)
            with lock:
                state["current_video"] = safe_name
                state["movement_frames"] = []
                state["current_movement"] = None
                state["movement_duration"] = 0.0
                state["processing_status"] = "idle"
                state["status_message"] = f"Vidéo chargée : {safe_name}"
            return {"filename": safe_name, "cached": False}
