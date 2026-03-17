import time
import numpy as np

from reachy_mini import ReachyMini
from reachy_mini.utils import create_head_pose

def sinusoides_une_dimension_a_la_fois():
    hz = 100
    dt = 1.0 / hz
    f_move = 0.5
    cycle = 3
    duree_totale_axe = cycle / f_move 

    amplitudes = {
        'roll': 20, 'pitch': 20, 'yaw': 30,
        'x': 20, 'y': 20, 'z': 12
    }
    dimensions = ['roll', 'pitch', 'yaw', 'x', 'y', 'z']
    
    print(f"\nBoucle de contrôle à {hz} Hz (dt={dt*1000} ms)")
    print(f"Chaque dimension : {cycle} cycles à {f_move} Hz = {duree_totale_axe}s\n")
    
    with ReachyMini(media_backend="no_media") as mini:
        for dim in dimensions:
            amp = amplitudes[dim]
            print(f" -> {dim} : ±{amp}")
            
            t_debut = time.time()
            
            while (time.time() - t_debut) < duree_totale_axe:
                t = time.time() - t_debut
                
                valeur = amp * np.sin(2 * np.pi * f_move * t)
                
                pose_head = {'roll': 0, 'pitch': 0, 'yaw': 0, 'x': 0, 'y': 0, 'z': 0}
                pose_head[dim] = valeur
                
                mini.goto_target(
                    head=create_head_pose(**pose_head, degrees=True, mm=True),
                    duration=0.1
                )
                
                time.sleep(dt)

        print("\n Retour position neutre...")
        mini.goto_target(head=create_head_pose(z=0, degrees=True, mm=True), duration=1.0)
        time.sleep(1)
        print("Terminé !")

def mouvements_combines():
    hz = 100
    dt = 1.0 / hz
    
    print(f"\nBoucle de contrôle à {hz} Hz (dt={dt*1000} ms)\n")
    
    # Paramètres Séquence A
    f_y = 0.4
    f_pitch = 1.6
    cycles_A = 3       
    duree_totale_A = cycles_A / f_y
    amp_y = 24
    amp_pitch = 16

    # Paramètres Séquence B
    f_cercle = 0.5
    cycles_B = 3       
    duree_totale_B = cycles_B / f_cercle  # Donne bien 6.0s
    rayon_cercle = 20
    z_constant = 5

    with ReachyMini(media_backend="no_media") as mini:
        print(f"Séquence A : {cycles_A} cycles")
        print(f" y : ±{amp_y}mm à {f_y}Hz")
        print(f" pitch : ±{amp_pitch}° à {f_pitch}Hz")
        print(f" Durée : {duree_totale_A}s\n")
        
        t_debut = time.time()
        while (time.time() - t_debut) < duree_totale_A:
            t = time.time() - t_debut
            
            val_y = amp_y * np.sin(2 * np.pi * f_y * t)
            val_pitch = amp_pitch * np.sin(2 * np.pi * f_pitch * t)
            
            pose_head = {'roll': 0, 'pitch': val_pitch, 'yaw': 0, 'x': 0, 'y': val_y, 'z': 0}
            
            mini.goto_target(
                head=create_head_pose(**pose_head, degrees=True, mm=True),
                duration=0.1
            )
            time.sleep(dt)

        print(" Transition...\n")
        
        print(f"Séquence B : {cycles_B} tours de cercle")
        print(f" Rayon : {rayon_cercle}mm, z constant : {z_constant}mm")
        print(f" Vitesse : {f_cercle}Hz")
        print(f" Durée : {duree_totale_B}s\n")
        
        t_debut = time.time()
        while (time.time() - t_debut) < duree_totale_B:
            t = time.time() - t_debut
            
            val_x = rayon_cercle * np.cos(2 * np.pi * f_cercle * t)
            val_y = rayon_cercle * np.sin(2 * np.pi * f_cercle * t)
            
            pose_head = {'roll': 0, 'pitch': 0, 'yaw': 0, 'x': val_x, 'y': val_y, 'z': z_constant}
            
            mini.goto_target(
                head=create_head_pose(**pose_head, degrees=True, mm=True),
                duration=0.1
            )
            time.sleep(dt)
            
        print(" Retour position neutre...")
        mini.goto_target(head=create_head_pose(z=0, degrees=True, mm=True), duration=1.0)
        time.sleep(1)
        print("Terminé !")
        
def select_program():
    print("1. sinusoides_une_dimension_a_la_fois")
    print("2. mouvements_combines")
    choix = input("Sélectionnez un programme : ")
    if choix == '1':
        sinusoides_une_dimension_a_la_fois()
    elif choix == '2':
        mouvements_combines()

if __name__ == "__main__":
    try:
        select_program()
    except KeyboardInterrupt:
        print("\nArrêt.")