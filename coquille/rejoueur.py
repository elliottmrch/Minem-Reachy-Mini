"""
Rejeu d'un mouvement enregistré sur le robot Reachy Mini.

Ce module propose deux usages :

1. charger_mouvement(json_path) : charge un fichier *_signaux_mouvement.json
   et retourne (frames, metadata) — utilisé par l'app web pour charger en mémoire
   sans ouvrir une nouvelle connexion robot.

2. Classe Rejoueur (ReachyMiniApp) : rejoue un fichier JSON directement sur le robot
   avec un lissage exponentiel (alpha=0.18) pour adoucir les transitions.
   Synchronisation temporelle précise via les timestamps du fichier JSON.

3. lancer_rejeu() : menu CLI interactif pour choisir un fichier et lancer le rejeu.

Format JSON attendu (*_signaux_mouvement.json, produit par mapper.py) :
    {
        "metadata": {"duration_s": float, "fps_robot": 100, "total_frames": int, ...},
        "frames": [
            {
                "timestamp": float,
                "head": {"yaw": float, "pitch": float, "roll": float, "x": float, "y": float, "z": float},
                "antennas": [float, float],
                "body_yaw": float
            },
            ...
        ]
    }
"""

import json
import os
import threading
import time

import numpy as np
from reachy_mini import ReachyMini, ReachyMiniApp
from reachy_mini.utils import create_head_pose

# Répertoire du script et dossier data/ par défaut
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "data"))


def charger_mouvement(json_path: str) -> tuple[list[dict], dict]:
    """Charge un fichier JSON de mouvement et retourne (frames, metadata).

    Cette fonction est utilisée par l'app web (routes_video, routes_processing)
    pour charger le mouvement en mémoire sans instancier de ReachyMiniApp.
    Les frames sont ensuite stockées dans state["movement_frames"] et parcourues
    par robot_loop.run() à 100 Hz.

    Args:
        json_path : chemin vers le fichier *_signaux_mouvement.json.

    Returns:
        frames   : liste de dicts [{timestamp, head, antennas, body_yaw}, ...]
        metadata : dict {"duration_s", "fps_robot", "total_frames", "source_file"}
    """
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["frames"], data.get("metadata", {})


class Rejoueur(ReachyMiniApp):
    """Application de rejeu direct sur le robot (usage CLI, Jalon 3).

    Hérite de ReachyMiniApp pour bénéficier de la connexion robot et du cycle de vie
    (wrapped_run → initialisation → run → arrêt propre).

    Contrairement à l'app web qui utilise robot_loop.run() à 100 Hz via AppContext,
    Rejoueur applique un lissage exponentiel (EMA) sur toutes les valeurs avant
    d'envoyer au robot, ce qui réduit les saccades visibles à bas fps.

    Attributs :
        movement_json : chemin vers le fichier JSON à rejouer (à définir avant wrapped_run()).
    """

    custom_app_url: str | None = None          # pas d'interface web pour le rejeu CLI
    request_media_backend: str | None = "no_media"  # pas d'audio dans le rejeu CLI

    movement_json: str = ""  # doit être renseigné avant l'appel à wrapped_run()

    def run(self, reachy_mini: ReachyMini, stop_event: threading.Event):
        """Rejoue le fichier JSON de mouvement sur le robot avec lissage EMA.

        Args:
            reachy_mini : connexion robot injectée par le SDK.
            stop_event  : déclenché par app.stop() ou Ctrl+C.
        """
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

        # ── Lissage exponentiel (EMA) ─────────────────────────────────────────
        # ALPHA = 0.18 : faible = mouvement très lissé/lent, élevé = mouvement plus proche de l'original.
        # Formule : smoothed[t] = ALPHA * target[t] + (1-ALPHA) * smoothed[t-1]
        ALPHA = 0.18
        smoothed = {
            "yaw": 0.0, "pitch": 0.0, "roll": 0.0,
            "x": 0.0, "y": 0.0, "z": 0.0,
            "ant_l": 0.0, "ant_r": 0.0, "body_yaw": 0.0
        }

        for i, frame in enumerate(frames):
            if stop_event.is_set():
                print("\n[INFO] Rejeu interrompu.")
                break

            head_data = frame["head"]
            antennas = frame["antennas"]

            # Application du filtre EMA sur chaque degré de liberté
            for k in ("yaw", "pitch", "roll", "x", "y", "z"):
                smoothed[k] = ALPHA * head_data[k] + (1 - ALPHA) * smoothed[k]
            smoothed["ant_l"]    = ALPHA * antennas[0]                    + (1 - ALPHA) * smoothed["ant_l"]
            smoothed["ant_r"]    = ALPHA * antennas[1]                    + (1 - ALPHA) * smoothed["ant_r"]
            smoothed["body_yaw"] = ALPHA * float(frame.get("body_yaw", 0.0)) + (1 - ALPHA) * smoothed["body_yaw"]

            # Envoi de la pose lissée au robot
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

            # Affichage de la progression tous les 100 frames (overwrite de ligne)
            if i % 100 == 0:
                pct = int(i / total * 100)
                print(f"  [{pct:3d}%] t={frame['timestamp']:.2f}s", end="\r", flush=True)

            # Attente jusqu'à la prochaine frame : on utilise le delta de timestamps
            # (plus précis qu'un sleep fixe car les timestamps viennent de la vidéo source)
            if i < total - 1:
                dt = frames[i + 1]["timestamp"] - frame["timestamp"]
                time.sleep(max(0.0, dt))

        print(f"\n[OK] Rejeu terminé. Retour à la position neutre.")
        # Position neutre finale : tête droite, antennes à 0
        head_neutre = create_head_pose(yaw=0.0, pitch=0.0, roll=0.0, degrees=True)
        reachy_mini.set_target(
            head=head_neutre,
            antennas=np.array([0.0, 0.0]),
        )


def lancer_rejeu(movement_json: str | None = None):
    """Lance le rejeu via menu CLI interactif ou directement depuis un chemin.

    Si movement_json est None, liste les fichiers *_mouvement.json dans DATA_DIR
    et propose à l'utilisateur d'en choisir un.

    Args:
        movement_json : chemin vers le fichier JSON (None = sélection interactive).
    """
    if movement_json is None:
        # Recherche des fichiers de mouvement disponibles dans data/
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

    # Instanciation et lancement de la ReachyMiniApp de rejeu
    app = Rejoueur()
    app.movement_json = movement_json
    try:
        app.wrapped_run()
    except KeyboardInterrupt:
        app.stop()


if __name__ == "__main__":
    # Lancement direct : python rejoueur.py [chemin_fichier.json]
    import sys
    path = sys.argv[1] if len(sys.argv) >= 2 else None
    lancer_rejeu(path)
