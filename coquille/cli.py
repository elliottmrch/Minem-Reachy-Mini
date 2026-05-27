import os
import sys

current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

from app_context import DATA_DIR
from main import Coquille

try:
    from experiments.poc.poc import main as run_poc_menu
    from experiments.programmes_test import select_program as run_tests
except ImportError as e:
    print(f"[INFO] Impossible d'importer certains modules : {e}")
    run_poc_menu = None
    run_tests = None

try:
    from extracteur import analyser_video
    from tools.visualiseur import visualiser_video
except ImportError as e:
    print(f"[INFO] Impossible d'importer les modules Jalon 2 : {e}")
    analyser_video = None
    visualiser_video = None

try:
    from mapper import lancer_mapping
    from rejoueur import lancer_rejeu
except ImportError as e:
    print(f"[INFO] Impossible d'importer les modules Jalon 3 : {e}")
    lancer_mapping = None
    lancer_rejeu = None


def menu_principal():
    while True:
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
            print("\nLancement de l'application Reachy Mini...")
            app = Coquille()
            try:
                app.wrapped_run()
            except KeyboardInterrupt:
                app.stop()

        elif choix == '2':
            if run_poc_menu:
                print("\nOuverture du menu POC...")
                run_poc_menu()
            else:
                print("\n[ERREUR] Le module POC n'a pas pu être chargé. Vérifier les dossiers.")

        elif choix == '3':
            if run_tests:
                print("\nOuverture des programmes de test...")
                run_tests()
            else:
                print("\n[ERREUR] Le module de test n'a pas pu être chargé. Vérifier les dossiers.")

        elif choix == '4':
            if not analyser_video:
                print("\n[ERREUR] Les modules Jalon 2 n'ont pas pu être chargés.")
            else:
                filename = input("\nNom du fichier vidéo dans data/ (ex: haine.mp4) : ").strip()
                video_path = os.path.join(DATA_DIR, filename)
                if not os.path.exists(video_path):
                    print(f"[ERREUR] '{video_path}' introuvable.")
                else:
                    json_path = analyser_video(video_path)
                    if json_path and visualiser_video:
                        visualiser_video(video_path, json_path)

        elif choix == '5':
            if lancer_mapping:
                lancer_mapping()
            else:
                print("\n[ERREUR] Le module mapper n'a pas pu être chargé.")

        elif choix == '6':
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
    menu_principal()
