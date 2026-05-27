"""Extraction et lecture audio pour Reachy Mini.
L'audio est extrait de la vidéo source et envoyé au robot
via push_audio_sample() lors du rejeu.
"""

import os
import threading
import time

import numpy as np
import librosa

CHUNK_SIZE = 2048   # Plus petit = moins d'impact par chunk tardif
SAMPLE_RATE = 16000  # Hz attendu par Reachy Mini


def extraire_audio_video(video_path: str, output_path: str | None = None) -> str:
    """Extrait la piste audio d'une vidéo et la sauvegarde en WAV.

    Raises:
        ValueError: Si la vidéo n'a pas de piste audio.
        ImportError: Si moviepy n'est pas installé.
    """
    try:
        from moviepy import VideoFileClip
    except ImportError:
        raise ImportError("moviepy est requis : pip install moviepy")

    if output_path is None:
        stem = os.path.splitext(video_path)[0]
        output_path = stem + "_audio.wav"

    clip = VideoFileClip(video_path)
    if clip.audio is None:
        clip.close()
        raise ValueError(f"La vidéo '{os.path.basename(video_path)}' n'a pas de piste audio.")

    clip.audio.write_audiofile(output_path, fps=SAMPLE_RATE, logger=None)
    clip.close()
    print(f"[OK] Audio extrait -> {output_path}")
    return output_path


def charger_audio(chemin: str, sr: int = SAMPLE_RATE) -> np.ndarray:
    """Charge un fichier audio en tableau NumPy float32, shape (N, 1) attendu par le SDK."""
    audio, _ = librosa.load(chemin, sr=sr, mono=True)
    return audio.reshape(-1, 1)  # (samples,) -> (samples, 1)


class LecteurAudio:
    """Envoie l'audio par chunks au robot Reachy Mini dans un thread dédié."""

    def __init__(self, reachy_mini, audio: np.ndarray, chunk_size: int = CHUNK_SIZE):
        self.reachy_mini = reachy_mini
        self.audio = audio          # shape (N, 1), float32, 16kHz
        self.chunk_size = chunk_size
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def demarrer(self):
        """Lance start_playing() puis démarre la lecture en arrière-plan."""
        self._stop_event.clear()
        self.reachy_mini.media.start_playing()
        self._thread = threading.Thread(target=self._jouer, daemon=True)
        self._thread.start()

    def arreter(self):
        """Arrête la lecture et appelle stop_playing()."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        try:
            self.reachy_mini.media.stop_playing()
        except Exception:
            pass

    def _jouer(self):
        """Boucle interne : envoie les chunks au robot avec timing absolu."""
        sr = SAMPLE_RATE
        try:
            sr = self.reachy_mini.media.get_output_audio_samplerate()
        except Exception:
            pass

        chunks = [
            self.audio[i : i + self.chunk_size]
            for i in range(0, len(self.audio), self.chunk_size)
        ]

        t_start = time.perf_counter()

        for idx, chunk in enumerate(chunks):
            if self._stop_event.is_set():
                break

            self.reachy_mini.media.push_audio_sample(chunk)

            # Timing absolu : on attend jusqu'au moment exact du prochain chunk
            t_next = t_start + (idx + 1) * self.chunk_size / sr
            sleep_time = t_next - time.perf_counter()
            if sleep_time > 0:
                time.sleep(sleep_time)
