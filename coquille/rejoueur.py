import json
import os
import threading
import time

import numpy as np
from reachy_mini import ReachyMini, ReachyMiniApp
from reachy_mini.utils import create_head_pose

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR   = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "data"))


class Rejoueur(ReachyMiniApp):
    """
    Rejoue un fichier de mouvement JSON sur Reachy Mini (simulation ou robot réel).

    Utilisation :
        app = Rejoueur(movement_json="data/exemple_mouvement.json")
        app.wrapped_run()

    Le fichier JSON doit être au format généré par mapper.py :
        { "metadata": {...}, "frames": [{"timestamp", "antennas", "body_yaw", "head"}, ...] }
    """

    # Pas d'interface web pour le rejeu
    custom_app_url: str | None = None
    request_media_backend: str | None = "no_media"

    # Chemin vers le fichier de mouvement à rejouer
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

        frames   = data["frames"]
        metadata = data.get("metadata", {})
        duration = metadata.get("duration_s", "?")
        total    = len(frames)

        print(f"\n[INFO] Fichier : {os.path.basename(self.movement_json)}")
        print(f"[INFO] Durée   : {duration}s | {total} frames")
        print(f"[INFO] Début du rejeu...\n")

        for i, frame in enumerate(frames):
            if stop_event.is_set():
                print("\n[INFO] Rejeu interrompu.")
                break

            head_data = frame["head"]
            antennas  = frame["antennas"]

            # Envoi des consignes au robot
            head_pose = create_head_pose(
                yaw=head_data["yaw"],
                pitch=head_data["pitch"],
                roll=head_data["roll"],
                degrees=True,
            )
            reachy_mini.set_target(
                head=head_pose,
                antennas=np.array(antennas, dtype=float),
                body_yaw=float(frame.get("body_yaw", 0.0)),
            )

            # Affichage de la progression toutes les 100 frames
            if i % 100 == 0:
                pct = int(i / total * 100)
                print(f"  [{pct:3d}%] t={frame['timestamp']:.2f}s", end="\r", flush=True)

            # Attendre jusqu'à la prochaine frame
            if i < total - 1:
                dt = frames[i + 1]["timestamp"] - frame["timestamp"]
                time.sleep(max(0.0, dt))

        # Retour à la position neutre
        print(f"\n[OK] Rejeu terminé. Retour à la position neutre.")
        head_neutre = create_head_pose(yaw=0.0, pitch=0.0, roll=0.0, degrees=True)
        reachy_mini.set_target(
            head=head_neutre,
            antennas=np.array([0.0, 0.0]),
        )


# ─── Lancement direct ─────────────────────────────────────────────────────────

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
