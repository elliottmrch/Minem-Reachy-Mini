"""Extraction et lecture audio pour Reachy Mini.

L'audio est extrait de la vidéo source, sauvegardé en WAV,
puis envoyé par chunks au robot via push_audio_sample() lors du rejeu.

Pipeline audio complet :
  1. extraire_audio_video(video, wav) → extrait la piste avec moviepy
  2. charger_audio(wav)              → charge en NumPy float32 16kHz (N, 1)
  3. LecteurAudio.demarrer()         → lance un thread qui pousse les chunks au robot

La synchronisation avec le rejeu robot (robot_loop) est assurée par l'horodatage
absolu dans _jouer() : on calcule le moment exact du prochain chunk pour éviter
la dérive temporelle accumulée par des sleep() relatifs.
"""

import os
import threading
import time

import numpy as np
import librosa

# Taille d'un chunk audio envoyé au robot à chaque appel push_audio_sample().
# Plus grand = moins d'appels réseau et moins de risques de coupure,
# mais plus de latence si la lecture doit être arrêtée précipitamment.
CHUNK_SIZE = 8192

# Fréquence d'échantillonnage attendue par le SDK Reachy Mini.
# librosa rééchantillonne automatiquement si la source est en 44100 Hz ou autre.
SAMPLE_RATE = 16000  # Hz


def extraire_audio_video(video_path: str, output_path: str | None = None) -> str:
    """Extrait la piste audio d'un fichier vidéo et la sauvegarde en WAV 16kHz.

    Utilise moviepy pour lire la piste audio de la vidéo et la réencoder
    au format WAV mono 16kHz attendu par charger_audio() et le robot.

    Args:
        video_path  : chemin absolu vers la vidéo source.
        output_path : chemin de sortie du WAV. Si None, dérivé du nom de la vidéo
                      (<stem>_audio.wav dans le même répertoire).

    Returns:
        Chemin absolu du fichier WAV créé.

    Raises:
        ValueError  : si la vidéo n'a pas de piste audio.
        ImportError : si moviepy n'est pas installé.
    """
    try:
        from moviepy import VideoFileClip
    except ImportError:
        raise ImportError("moviepy est requis : pip install moviepy")

    # Chemin de sortie par défaut : même répertoire que la vidéo
    if output_path is None:
        stem = os.path.splitext(video_path)[0]
        output_path = stem + "_audio.wav"

    clip = VideoFileClip(video_path)
    if clip.audio is None:
        clip.close()
        raise ValueError(f"La vidéo '{os.path.basename(video_path)}' n'a pas de piste audio.")

    # Écriture du WAV à 16kHz mono, logger=None pour supprimer la barre de progression moviepy
    clip.audio.write_audiofile(output_path, fps=SAMPLE_RATE, logger=None)
    clip.close()
    print(f"[OK] Audio extrait -> {output_path}")
    return output_path


def charger_audio(chemin: str, sr: int = SAMPLE_RATE) -> np.ndarray:
    """Charge un fichier audio en tableau NumPy float32, shape (N, 1).

    librosa gère automatiquement le rééchantillonnage si nécessaire.
    Le reshape en (N, 1) est requis par push_audio_sample() du SDK.

    Args:
        chemin : chemin vers le fichier audio (WAV, MP3, etc.).
        sr     : fréquence d'échantillonnage cible (défaut 16kHz).

    Returns:
        Tableau NumPy float32 de shape (N, 1) représentant l'audio mono.
    """
    audio, _ = librosa.load(chemin, sr=sr, mono=True)
    return audio.reshape(-1, 1)  # (samples,) → (samples, 1) pour le SDK


class LecteurAudio:
    """Envoie l'audio par chunks au robot Reachy Mini dans un thread dédié.

    Gère le démarrage, la pause et l'arrêt de la lecture audio en parallèle
    du rejeu robot (robot_loop). Les deux sont synchronisés par replay_start_time
    dans l'AppContext.

    Le timing de livraison des chunks utilise un horodatage ABSOLU (perf_counter)
    pour éviter la dérive qui surviendrait avec des sleep() relatifs successifs.
    """

    def __init__(self, reachy_mini, audio: np.ndarray, chunk_size: int = CHUNK_SIZE):
        """
        Args:
            reachy_mini : instance du robot (pour media.push_audio_sample).
            audio       : tableau NumPy float32 (N, 1) à 16kHz.
            chunk_size  : nombre d'échantillons par appel push_audio_sample.
        """
        self.reachy_mini = reachy_mini
        self.audio = audio           # shape (N, 1), float32, 16kHz
        self.chunk_size = chunk_size
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()  # set() pour interrompre la lecture
        self._start_sample = 0                # index d'échantillon de départ (pour seek/resume)

    def demarrer(self):
        """Lance la lecture depuis le début (sample 0).

        Appelle start_playing() sur le backend audio du robot,
        puis démarre _jouer() dans un thread daemon.
        """
        self._start_sample = 0
        self._stop_event.clear()
        self.reachy_mini.media.start_playing()
        self._thread = threading.Thread(target=self._jouer, daemon=True)
        self._thread.start()

    def demarrer_depuis(self, offset_seconds: float):
        """Lance la lecture depuis un offset temporel (pour reprendre après pause/seek).

        Args:
            offset_seconds : position de départ en secondes dans l'audio.
        """
        self._start_sample = int(offset_seconds * SAMPLE_RATE)
        self._stop_event.clear()
        self.reachy_mini.media.start_playing()
        self._thread = threading.Thread(target=self._jouer, daemon=True)
        self._thread.start()

    def arreter(self):
        """Arrête la lecture en cours.

        Déclenche le stop_event (la boucle _jouer() s'arrêtera au prochain chunk),
        attend la fin du thread (timeout 2s), puis appelle stop_playing().
        """
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)  # attente max 2s pour que le thread se termine
        try:
            self.reachy_mini.media.stop_playing()
        except Exception:
            pass  # le robot peut déjà être déconnecté lors d'un arrêt brutal

    def _jouer(self):
        """Boucle interne de lecture : envoie les chunks au robot avec timing absolu.

        Interroge d'abord le robot pour sa fréquence d'échantillonnage réelle
        (peut différer de 16000 sur certains firmwares), puis découpe l'audio
        en chunks et les envoie au rythme exact pour éviter toute dérive.
        """
        # Récupération du sample rate réel du robot (peut différer de SAMPLE_RATE)
        sr = SAMPLE_RATE
        try:
            sr = self.reachy_mini.media.get_output_audio_samplerate()
        except Exception:
            pass  # en cas d'erreur, on utilise le sample rate par défaut

        # Découpage de l'audio depuis l'offset de départ en chunks
        audio_slice = self.audio[self._start_sample:]
        chunks = [
            audio_slice[i : i + self.chunk_size]
            for i in range(0, len(audio_slice), self.chunk_size)
        ]

        # Horodatage de départ absolu pour un timing précis
        t_start = time.perf_counter()

        for idx, chunk in enumerate(chunks):
            if self._stop_event.is_set():
                break  # arrêt demandé (stop ou pause)

            # Envoi du chunk au robot
            self.reachy_mini.media.push_audio_sample(chunk)

            # Timing absolu : on calcule l'instant exact où le prochain chunk doit partir.
            # Cela compense les variations de durée de push_audio_sample() et évite
            # la dérive cumulée qu'aurait un simple time.sleep(chunk_size/sr).
            t_next = t_start + (idx + 1) * self.chunk_size / sr
            sleep_time = t_next - time.perf_counter()
            if sleep_time > 0:
                time.sleep(sleep_time)
