import os
import time
import argparse
import cv2
import mediapipe as mp
import winsound  # Bibliothèque intégrée à Windows pour lire du son
from moviepy import VideoFileClip

def poc_robot_complet(video_path):
    print(f"\n[ÉTAPE 1] Préparation de la vidéo : {video_path}")
    
    if not os.path.exists(video_path):
        print(f"Erreur : Le fichier vidéo '{video_path}' n'existe pas.")
        return

    audio_temp_path = "temp_audio.wav"

    # --- 1. EXTRACTION DE L'AUDIO ---
    try:
        video_clip = VideoFileClip(video_path)
        if video_clip.audio is not None:
            print("-> Extraction de la piste audio en cours...")
            # On extrait en .wav (format requis par winsound) sans polluer la console
            video_clip.audio.write_audiofile(audio_temp_path, logger=None)
        else:
            print("-> [AVERTISSEMENT] Aucune piste audio trouvée dans la vidéo.")
            audio_temp_path = None
        video_clip.close()
    except Exception as e:
        print(f"-> [ERREUR] Impossible d'extraire l'audio : {e}")
        audio_temp_path = None

    print("\n[ÉTAPE 2] Lancement du tracking et de l'audio synchronisés")
    
    # --- 2. INITIALISATION DU TRACKING ---
    mp_face_mesh = mp.solutions.face_mesh
    mp_drawing = mp.solutions.drawing_utils
    mp_drawing_styles = mp.solutions.drawing_styles

    cap = cv2.VideoCapture(video_path)
    
    if not cap.isOpened():
        print("Erreur : Impossible d'ouvrir le flux vidéo.")
        return

    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps == 0:  
        fps = 30.0
    
    target_frame_time_ms = 1000.0 / fps

    print(f"-> Vidéo détectée à {fps} FPS.")
    print("-> Lecture en cours. Appuyez sur la touche 'q' sur la fenêtre vidéo pour quitter.\n")

    # --- 3. LANCEMENT DU SON EN ARRIÈRE-PLAN ---
    if audio_temp_path and os.path.exists(audio_temp_path):
        # SND_ASYNC dit à Windows de jouer le son sans bloquer la suite du code Python
        winsound.PlaySound(audio_temp_path, winsound.SND_FILENAME | winsound.SND_ASYNC)

    # --- 4. BOUCLE VIDÉO ---
    with mp_face_mesh.FaceMesh(
        max_num_faces=1, 
        refine_landmarks=True,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5
    ) as face_mesh:
        
        frame_count = 0
        
        while cap.isOpened():
            start_time = time.time()
            success, frame = cap.read()
            
            if not success:
                break

            frame_count += 1
            
            image_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = face_mesh.process(image_rgb)

            if results.multi_face_landmarks:
                for face_landmarks in results.multi_face_landmarks:
                    nose_tip = face_landmarks.landmark[1]
                    
                    if frame_count % 10 == 0:
                        print(f"Frame {frame_count} -> Ordre Robot | Nez X:{nose_tip.x:.2f}, Y:{nose_tip.y:.2f}")

                    mp_drawing.draw_landmarks(
                        image=frame,
                        landmark_list=face_landmarks,
                        connections=mp_face_mesh.FACEMESH_TESSELATION,
                        landmark_drawing_spec=None,
                        connection_drawing_spec=mp_drawing_styles.get_default_face_mesh_tesselation_style()
                    )

            cv2.imshow('Simulation Vision Robot', frame)
            
            process_time_ms = (time.time() - start_time) * 1000
            wait_time = int(target_frame_time_ms - process_time_ms)
            wait_time = max(1, wait_time)
            
            if cv2.waitKey(wait_time) & 0xFF == ord('q'):
                print("Interruption par l'utilisateur.")
                break

    # --- 5. NETTOYAGE ---
    # On coupe la musique si elle tournait encore
    winsound.PlaySound(None, winsound.SND_PURGE)
    
    cap.release()
    cv2.destroyAllWindows()
    
    # On supprime le fichier audio temporaire pour garder le dossier propre
    if audio_temp_path and os.path.exists(audio_temp_path):
        os.remove(audio_temp_path)
        
    print("\nTest terminé avec succès. Nettoyage effectué.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PoC Complet (Audio + Tracking Vidéo)")
    parser.add_argument("--video", type=str, required=True, help="Chemin vers la vidéo à analyser.")
    
    args = parser.parse_args()
    poc_robot_complet(args.video)