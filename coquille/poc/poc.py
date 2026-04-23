import os
import json
import time
import cv2
import mediapipe as mp
from moviepy import VideoFileClip
import yt_dlp


# MEDIAPIPE 
# 468 points 3D
# Optimisé pour CPU, évite le besoin d'un GPU lourd.
# Coordonnées entre 0 et 1 facilitant le mapping vers le robot.
# Dlib = trop lourd à compiler/installer et seulement 68 points.
# OpenCV Haar Cascades = trop basique et pas de maillage fin du visage.

# MOVIEPY
# Extraction audio en une ligne de code.
# Gestion propre des ressources (.close()) pour éviter les fuites mémoire.
# PyAV = trop bas niveau, gestion des codecs complexe.
# Subprocess + FFmpeg = risqué pour la gestion des erreurs et des flux.

# YT-DLP
# Version la plus maintenue face aux mises à jour fréquentes de YouTube.
# Contourne le bridage de bande passante imposé par YouTube.
# Permet de forcer le MP4 pour garantir la compatibilité MediaPipe/MoviePy.
# Pytube = instable, casse souvent lors des changements d'algorithme YouTube.
# Youtube-dl = obsolète, vitesse de téléchargement bridée.

# Initialisation MediaPipe
mp_face_mesh = mp.solutions.face_mesh
mp_drawing = mp.solutions.drawing_utils
mp_drawing_styles = mp.solutions.drawing_styles

# POC 1 : MediaPipe en direct via webcam
def poc_1():
    cap = cv2.VideoCapture(0)
    
    with mp_face_mesh.FaceMesh(refine_landmarks=True) as face_mesh:
        while cap.isOpened():
            success, image = cap.read()
            if not success: 
                print("[ERREUR] Impossible d'accéder à la webcam.")
                break
            
            image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            results = face_mesh.process(image_rgb)
            
            if results.multi_face_landmarks:
                for face_landmarks in results.multi_face_landmarks:
                    mp_drawing.draw_landmarks(
                        image=image,
                        landmark_list=face_landmarks,
                        connections=mp_face_mesh.FACEMESH_TESSELATION,
                        connection_drawing_spec=mp_drawing_styles.get_default_face_mesh_tesselation_style())
            
            cv2.imshow('POC 1', image)
            if cv2.waitKey(5) & 0xFF == 27: break
            
    cap.release()
    cv2.destroyAllWindows()

# POC 2 : MediaPipe sur vidéo locale du nez vers JSON
def poc_2(video_path):
    if not os.path.exists(video_path):
        print(f"[ERREUR] Fichier '{video_path}' non trouvé.")
        return

    cap = cv2.VideoCapture(video_path)
    donnees = []
    fps_video = cap.get(cv2.CAP_PROP_FPS)
    print(f"[INFO] FPS détectés : {fps_video}")

    with mp_face_mesh.FaceMesh(refine_landmarks=True) as face_mesh:
        frame_count = 0
        while cap.isOpened():
            success, frame = cap.read()
            if not success: break
            
            results = face_mesh.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            if results.multi_face_landmarks:
                # 1 = Bout du nez 
                nez = results.multi_face_landmarks[0].landmark[1]
                donnees.append({
                    "timestamp": round(frame_count / fps_video, 3),
                    "x": round(nez.x, 4),
                    "y": round(nez.y, 4),
                    "z": round(nez.z, 4)
                })
            frame_count += 1
        
    with open("mouvement.json", "w") as f:
        json.dump(donnees, f, indent=4)
    
    cap.release()
    print(f"[SUCCES] {len(donnees)} points sauvegardés dans 'mouvement.json'.")

# POC 3 : MoviePy pour extraire l'audio d'une vidéo locale
def poc_3(video_path):
    if not os.path.exists(video_path):
        print(f"[ERREUR] Fichier '{video_path}' non trouvé.")
        return
    try:
        video = VideoFileClip(video_path)
        video.audio.write_audiofile("audio_extrait.mp3", logger=None)
        video.close()
        print("[SUCCES] Fichier 'audio_extrait.mp3' créé.")
    except Exception as e:
        print(f"[ERREUR] Echec de l'extraction audio : {e}")

# POC 4 : yt_dlp pour télécharger une vidéo ytb avec url
def poc_4(url):
    ydl_opts = {
        'format': 'best[ext=mp4]/best', 
        'outtmpl': 'video_ytb.mp4',
        'noplaylist': True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        print("[SUCCES] Vidéo enregistrée sous 'video_ytb.mp4'.")
    except Exception as e:
        print(f"[ERREUR] Echec du téléchargement : {e}")

# MENU
def main():
    while True:
        print("\n" + "="*30)
        print("         MENU POCs")
        print("="*30)
        print("1. POC 1 : Webcam Full Face Mediapipe")
        print("2. POC 2 : Extraction du mouvement du nez vers JSON")
        print("3. POC 3 : Extraction de l'audio d'une vidéo locale")
        print("4. POC 4 : Téléchargement d'une vidéo YouTube via URL")
        print("0. Quitter")
        
        choix = input("\nVotre choix : ").lower()

        if choix == '1':
            poc_1()
        elif choix == '2':
            f = input("Nom du fichier vidéo : ")
            poc_2(f)
        elif choix == '3':
            f = input("Nom du fichier vidéo : ")
            poc_3(f)
        elif choix == '4':
            u = input("URL YouTube : ")
            poc_4(u)
        elif choix == '0':
            print("Fin du programme.")
            break
        else:
            print("Option invalide.")

if __name__ == "__main__":
    main()