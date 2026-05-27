"""
Interface en ligne de commande (CLI) — Hub principal du projet Coquille.

Ce module propose un menu interactif qui centralise toutes les façons de
lancer les différentes parties du projet, utile pour le développement et
les démonstrations hors app web.

Options disponibles :
  1. Lancer l'app web (Coquille) → démarre FastAPI + boucle robot
  2. Menu POC (Vision, Audio, YouTube) → expériences de preuve de concept
  3. Programmes de test (sinusoïdes, cercles) → tests matériel/simulation
  4. Analyse vidéo - extraction des signaux faciaux (Jalon 2)
  5. Générer un mouvement robot depuis les signaux (Jalon 3, mapper.py)
  6. Rejouer un mouvement en simulation (Jalon 3, rejoueur.py)

Pour lancer : python -m coquille.cli
"""

import os
import sys

# Ajout du dossier courant au sys.path pour permettre les imports absolus
# (même fonctionnement que main.py)
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

# Chemin vers le dossier data/ (utilisé pour l'option 4)
from app_context import DATA_DIR
# Classe principale de l'app web (option 1)
from main import Coquille

# ── Imports optionnels (un module absent ne bloque pas les autres options) ──

# Option 2 : menu POC (expériences préliminaires du projet)
try:
    from experiments.poc.poc import main as run_poc_menu
    from experiments.programmes_test import select_program as run_tests
except ImportError as e:
    print(f"[INFO] Impossible d'importer certains modules : {e}")
    run_poc_menu = None
    run_tests = None

# Option 4 : extraction des signaux faciaux avec MediaPipe
try:
    from extracteur import analyser_video
    from tools.visualiseur import visualiser_video
except ImportError as e:
    print(f"[INFO] Impossible d'importer les modules Jalon 2 : {e}")
    analyser_video = None
    visualiser_video = None

# Options 5 et 6 : mapping et rejeu (Jalon 3)
try:
    from mapper import lancer_mapping
    from rejoueur import lancer_rejeu
except ImportError as e:
    print(f"[INFO] Impossible d'importer les modules Jalon 3 : {e}")
    lancer_mapping = None
    lancer_rejeu = None


def menu_principal():
    """Affiche et gère le menu interactif principal du projet Coquille.

    Boucle infinie jusqu'au choix 'q' (quitter).
    Chaque option appelle le sous-module correspondant si disponible,
    ou affiche un message d'erreur en cas de dépendance manquante.
    """
    while True:
        # Affichage du menu à chaque itération pour rappel des options
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
            # Lance l'application web complète (FastAPI + boucle robot 100 Hz)
            # Bloquant jusqu'au Ctrl+C
            print("\nLancement de l'application Reachy Mini...")
            app = Coquille()
            try:
                app.wrapped_run()
            except KeyboardInterrupt:
                app.stop()

        elif choix == '2':
            # Menu des Proof-of-Concept (vision, audio, YouTube) — expériences du Jalon 1
            if run_poc_menu:
                print("\nOuverture du menu POC...")
                run_poc_menu()
            else:
                print("\n[ERREUR] Le module POC n'a pas pu être chargé. Vérifier les dossiers.")

        elif choix == '3':
            # Programmes de test hardware : sinusoïdes, cercles, mouvements prédéfinis
            if run_tests:
                print("\nOuverture des programmes de test...")
                run_tests()
            else:
                print("\n[ERREUR] Le module de test n'a pas pu être chargé. Vérifier les dossiers.")

        elif choix == '4':
            # Extraction des signaux faciaux depuis une vidéo (Jalon 2)
            # Lance analyser_video() qui produit <stem>_signaux.json dans data/
            if not analyser_video:
                print("\n[ERREUR] Les modules Jalon 2 n'ont pas pu être chargés.")
            else:
                filename = input("\nNom du fichier vidéo dans data/ (ex: haine.mp4) : ").strip()
                video_path = os.path.join(DATA_DIR, filename)
                if not os.path.exists(video_path):
                    print(f"[ERREUR] '{video_path}' introuvable.")
                else:
                    # analyser_video retourne le chemin du JSON de signaux produit
                    json_path = analyser_video(video_path)
                    # Visualisation optionnelle des signaux extraits sur la vidéo
                    if json_path and visualiser_video:
                        visualiser_video(video_path, json_path)

        elif choix == '5':
            # Génération du mouvement robot depuis un fichier *_signaux.json (Jalon 3)
            # Produit <stem>_signaux_mouvement.json interpolé à 100 fps
            if lancer_mapping:
                lancer_mapping()
            else:
                print("\n[ERREUR] Le module mapper n'a pas pu être chargé.")

        elif choix == '6':
            # Rejeu d'un fichier *_mouvement.json sur le robot physique (Jalon 3)
            # Ouvre une nouvelle connexion robot (via ReachyMiniApp)
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
    # Lancement direct : python -m coquille.cli
    menu_principal()
