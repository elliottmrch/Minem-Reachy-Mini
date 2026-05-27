import json
import os
import threading
import time

import numpy as np
from reachy_mini import ReachyMini, ReachyMiniApp
from reachy_mini.utils import create_head_pose

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "data"))


def charger_mouvement(json_path: str) -> tuple[list[dict], dict]:
    """Charge un fichier _mouvement.json et retourne (frames, metadata).

    Utilisable depuis l'app web (Coquille) sans ouvrir une nouvelle connexion robot.
    """
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["frames"], data.get("metadata", {})


class Rejoueur(ReachyMiniApp):
    custom_app_url: str | None = None
    request_media_backend: str | None = "no_media"

    movement_json: str = ""

    def run(self, reachy_mini: ReachyMini, stop_event: threading.Event):
        if not self.movement_json:
            print("[ERREUR] Aucun fichier de mouvement spécifié.")
            return

        if not os.path.exists(self.movement_json):
            print(f"[ERREUR] Fichier introuvable : {self.movement_json}")
            return

        with open(self.movement_json, "r", encoding="utf-8") as f:
            data = json.load(f)

        frames = data["frames"]
        metadata = data.get("metadata", {})
        duration = metadata.get("duration_s", "?")
        total = len(frames)

        print(f"\n[INFO] Fichier : {os.path.basename(self.movement_json)}")
        print(f"[INFO] Durée   : {duration}s | {total} frames")
        print(f"[INFO] Début du rejeu...\n")

        ALPHA = 0.18
        smoothed = {"yaw": 0.0, "pitch": 0.0, "roll": 0.0,
                    "x": 0.0, "y": 0.0, "z": 0.0,
                    "ant_l": 0.0, "ant_r": 0.0, "body_yaw": 0.0}

        for i, frame in enumerate(frames):
            if stop_event.is_set():
                print("\n[INFO] Rejeu interrompu.")
                break

            head_data = frame["head"]
            antennas = frame["antennas"]

            for k in ("yaw", "pitch", "roll", "x", "y", "z"):
                smoothed[k] = ALPHA * head_data[k] + (1 - ALPHA) * smoothed[k]
            smoothed["ant_l"] = ALPHA * antennas[0] + (1 - ALPHA) * smoothed["ant_l"]
            smoothed["ant_r"] = ALPHA * antennas[1] + (1 - ALPHA) * smoothed["ant_r"]
            smoothed["body_yaw"] = ALPHA * float(frame.get("body_yaw", 0.0)) + (1 - ALPHA) * smoothed["body_yaw"]

            head_pose = create_head_pose(
                yaw=smoothed["yaw"],
                pitch=smoothed["pitch"],
                roll=smoothed["roll"],
                x=smoothed["x"],
                y=smoothed["y"],
                z=smoothed["z"],
                degrees=True,
            )
            reachy_mini.set_target(
                head=head_pose,
                antennas=np.array([smoothed["ant_l"], smoothed["ant_r"]], dtype=float),
                body_yaw=smoothed["body_yaw"],
            )

            if i % 100 == 0:
                pct = int(i / total * 100)
                print(f"  [{pct:3d}%] t={frame['timestamp']:.2f}s", end="\r", flush=True)

            if i < total - 1:
                dt = frames[i + 1]["timestamp"] - frame["timestamp"]
                time.sleep(max(0.0, dt))

        print(f"\n[OK] Rejeu terminé. Retour à la position neutre.")
        head_neutre = create_head_pose(yaw=0.0, pitch=0.0, roll=0.0, degrees=True)
        reachy_mini.set_target(
            head=head_neutre,
            antennas=np.array([0.0, 0.0]),
        )

def lancer_rejeu(movement_json: str | None = None):
    if movement_json is None:
        fichiers = [f for f in os.listdir(DATA_DIR) if f.endswith("_mouvement.json")]
        if not fichiers:
            print(f"[ERREUR] Aucun fichier *_mouvement.json trouvé dans {DATA_DIR}")
            print("Lancez d'abord mapper.py pour générer un mouvement.")
            return

        print("\nFichiers de mouvement disponibles :")
        for i, f in enumerate(fichiers):
            print(f"  {i + 1}. {f}")

        choix = input("\nNuméro du fichier à rejouer : ").strip()
        try:
            movement_json = os.path.join(DATA_DIR, fichiers[int(choix) - 1])
        except (ValueError, IndexError):
            print("[ERREUR] Choix invalide.")
            return

    app = Rejoueur()
    app.movement_json = movement_json
    try:
        app.wrapped_run()
    except KeyboardInterrupt:
        app.stop()

if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) >= 2 else None
    lancer_rejeu(path)
