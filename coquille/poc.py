from moviepy import VideoFileClip
import os

def poc_extract_audio(video_path, output_audio_path):
    print(f"Ouverture de la vidéo : {video_path}")
    try:
        video = VideoFileClip(video_path)
        if video.audio is not None:
            # Extraction du son de la vidéo quand il existe
            video.audio.write_audiofile(output_audio_path, logger=None)
            print(f"Succès ! Audio extrait vers : {output_audio_path}")
        else:
            print("Aucune piste audio trouvée dans cette vidéo.")
    except Exception as e:
        print(f"Erreur lors du traitement: {e}")

# poc_extract_audio("test_video.mp4", "extracted_audio.wav")

# ------------------------------------------

import cv2
import mediapipe as mp

def poc_face_landmarks(image_path):
    # Initialisation de MediaPipe Face Mesh
    mp_face_mesh = mp.solutions.face_mesh
    face_mesh = mp_face_mesh.FaceMesh(
        static_image_mode=True, 
        max_num_faces=1, # Détection d'un visage principal
        refine_landmarks=True,
        min_detection_confidence=0.5
    )

    # Lecture de l'image avec OpenCV
    image = cv2.imread(image_path)
    if image is None:
        print("Erreur: Image introuvable.")
        return

    # Conversion BGR (OpenCV) vers RGB (MediaPipe)
    results = face_mesh.process(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))

    if results.multi_face_landmarks:
        print("Visage détecté avec succès !")
        for face_landmarks in results.multi_face_landmarks:
            # Exemple : Récupérer les coordonnées du bout du nez (landmark 1)
            nose_tip = face_landmarks.landmark[1]
            print(f"Position du nez (Normalisée) : X={nose_tip.x:.2f}, Y={nose_tip.y:.2f}, Z={nose_tip.z:.2f}")
            
            # Note pour le mapping futur : on utilisera des calculs géométriques
            # sur ces points pour obtenir l'orientation (pitch, yaw, roll) 
            # et la taille de l'ouverture de la bouche (sourire).
    else:
        print("Aucun visage n'a été détecté.")

# poc_face_landmarks("test_face.jpg")