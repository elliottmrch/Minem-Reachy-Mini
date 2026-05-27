"""
Routes FastAPI — Pipeline de traitement vidéo.

Ce module enregistre une seule route :

    POST /process_video → déclenche le pipeline complet en arrière-plan

Le pipeline enchaîne 3 étapes dans un thread daemon :
  1. Extraction des signaux faciaux (extracteur.analyser_video)
     → produit <stem>_signaux.json
  2. Génération du mouvement robot (mapper.generer_mouvement)
     → produit <stem>_signaux_mouvement.json (interpolé à 100 fps)
  3. Chargement de l'audio (moviepy → librosa)
     → produit <stem>_audio.wav

À chaque étape, processing_status est mis à jour dans state pour que
le frontend puisse suivre la progression via GET /status (polling).

Optimisation cache : si le JSON de mouvement existe déjà pour cette vidéo,
les étapes 1 et 2 sont ignorées et on recharge directement depuis le cache.
"""

import os
import threading

from fastapi import HTTPException
from pydantic import BaseModel

from app_context import DATA_DIR, AppContext

# ── Imports optionnels du pipeline ────────────────────────────────────────────
# Chaque module est optionnel pour permettre un démarrage partiel si une dépendance
# (mediapipe, mapper…) n'est pas installée. La route renvoie HTTP 500 si nécessaire.

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


# ── Modèle Pydantic ───────────────────────────────────────────────────────────

class ProcessReq(BaseModel):
    """Corps de la requête POST /process_video."""
    filename: str  # Nom de la vidéo dans DATA_DIR à traiter


# ── Enregistrement de la route ────────────────────────────────────────────────

def register(ctx: AppContext) -> None:
    """Enregistre la route /process_video sur settings_app.

    Args:
        ctx : contexte partagé (state, lock, reachy_mini, settings_app).
    """
    state = ctx.state
    lock = ctx.lock
    settings_app = ctx.settings_app

    # ── POST /process_video ───────────────────────────────────────────────────
    @settings_app.post("/process_video")
    def process_video(req: ProcessReq):
        """Lance le pipeline extraction → mapping → audio dans un thread daemon.

        Retourne immédiatement {"started": True} sans attendre la fin du traitement.
        Le frontend poll GET /status pour suivre processing_status :
          "extracting" (33%) → "mapping" (66%) → "ready" (100%) ou "error"
        """
        # Vérification que tous les modules nécessaires sont disponibles
        if analyser_video is None or generer_mouvement is None or charger_mouvement is None:
            raise HTTPException(status_code=500, detail="Modules pipeline indisponibles")

        video_path = os.path.join(DATA_DIR, os.path.basename(req.filename))
        if not os.path.exists(video_path):
            raise HTTPException(status_code=404, detail="Vidéo introuvable")

        def _pipeline():
            """Corps du pipeline — exécuté dans un thread daemon non-bloquant."""
            try:
                stem = os.path.splitext(os.path.basename(req.filename))[0]
                mvt_path = os.path.join(DATA_DIR, f"{stem}_signaux_mouvement.json")

                # ── Cas cache : le JSON de mouvement existe déjà ──────────────
                # On saute l'extraction et le mapping (longs) et on recharge directement.
                if os.path.exists(mvt_path):
                    frames, meta = charger_mouvement(mvt_path)

                    # Tentative de chargement audio depuis le WAV existant
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
                    return  # Pas besoin de refaire le pipeline

                # ── Étape 1 : Extraction des signaux faciaux ──────────────────
                # analyser_video() lit la vidéo frame par frame avec MediaPipe,
                # extrait yaw/pitch/roll + expressions faciales, et écrit un JSON.
                with lock:
                    state["processing_status"] = "extracting"
                    state["status_message"] = "Extraction des signaux..."
                signaux_path = analyser_video(video_path)
                if not signaux_path:
                    raise RuntimeError("Échec de l'extraction (aucun visage détecté ?)")

                # ── Étape 2 : Génération du mouvement robot ───────────────────
                # generer_mouvement() mappe les signaux faciaux sur les articulations
                # du robot (tête, antennes, torse), calibre, et interpole à 100 fps.
                with lock:
                    state["processing_status"] = "mapping"
                    state["status_message"] = "Génération du mouvement..."
                mvt_path = generer_mouvement(signaux_path)
                if not mvt_path:
                    raise RuntimeError("Échec de la génération du mouvement")

                # Chargement du mouvement généré en mémoire
                frames, meta = charger_mouvement(mvt_path)

                # ── Étape 3 : Extraction et chargement de l'audio ────────────
                # L'audio est extrait de la vidéo source (moviepy), puis chargé
                # en tableau NumPy (librosa) pour LecteurAudio.
                audio_data = None
                if extraire_audio_video is not None and charger_audio is not None:
                    audio_path = os.path.join(DATA_DIR, f"{stem}_audio.wav")
                    # Extraction seulement si le WAV n'existe pas déjà
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

                # ── Succès : tout est chargé en mémoire ───────────────────────
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
                # ValueError levée par analyser_video si aucun visage n'est détecté
                with lock:
                    state["processing_status"] = "error"
                    state["status_message"] = str(e)
            except Exception as e:
                # Toute autre erreur inattendue
                with lock:
                    state["processing_status"] = "error"
                    state["status_message"] = f"Erreur : {e}"

        # Lancement non-bloquant : la route répond immédiatement
        threading.Thread(target=_pipeline, daemon=True).start()
        return {"started": True}
