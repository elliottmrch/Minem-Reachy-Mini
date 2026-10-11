# MINEM — Reachy Mini

**Transférez vos expressions faciales sur le robot Reachy Mini, en temps réel par webcam ou depuis une vidéo.**

Projet de fin d'année réalisé en équipe en CIR2 (2025-2026) à JUNIA ISEN Bordeaux.

🔗 **Projet original et démo :** [huggingface.co/spaces/Reachy-NEM/coquille](https://huggingface.co/spaces/Reachy-NEM/coquille)

> Ce dépôt est une copie du Space Hugging Face, avec l'historique complet des commits. « Coquille » est le nom de code initial du projet.

---

## Fonctionnalités

- 🎬 **Import vidéo** : upload local (MP4/MOV) ou téléchargement YouTube automatique via `yt-dlp`
- 🧠 **Analyse faciale** : 478 landmarks MediaPipe FaceMesh (orientation de la tête, bouche, sourcils, ouverture des yeux / EAR)
- 🤖 **Rejeu sur robot** : pipeline signal → mapper → frames JSON, rejoué à 100 Hz
- 🎥 **Mode live** : contrôle en temps réel par webcam, calibration automatique en 30 frames, stream MJPEG
- 🔊 **Audio synchronisé** : lecture sur le haut-parleur du robot, synchronisée frame par frame
- 🌐 **API REST** : FastAPI complète (upload, traitement, play / pause / stop / seek, live, statut)

## Fonctionnement

```
Vidéo / Webcam ──► Extraction (MediaPipe FaceMesh) ──► Mapping (yaw, pitch, roll, antennes) ──► Boucle robot 100 Hz
                                                                                                  └─► Audio synchronisé
```

## Stack technique

Python · FastAPI · Uvicorn · MediaPipe · NumPy · librosa · MoviePy · yt-dlp · SDK Reachy Mini

## Architecture

| Fichier | Rôle |
|---|---|
| `main.py` | Point d'entrée, hérite de `ReachyMiniApp` et enregistre les routes |
| `app_context.py` | État partagé entre les routes (dataclass + verrou) |
| `robot_loop.py` | Boucle 100 Hz qui envoie les commandes au robot |
| `extracteur.py` | Analyse MediaPipe FaceMesh image par image |
| `mapper.py` | Conversion des signaux faciaux en commandes moteur |
| `live.py` | Capture webcam et traitement temps réel |
| `audio_player.py` | Lecture audio synchronisée |
| `routes_*.py` | Routes FastAPI : vidéo, traitement, lecture, live, divers |

## Installation

1. Ouvrir le tableau de bord du Reachy Mini : `http://reachy-mini:8000`
2. Section **Apps** → chercher **MINEM** → **Install**
3. L'app est accessible sur `http://reachy-mini:8042`

**Prérequis :** un Reachy Mini sur le réseau local, et une webcam pour le mode live.

## Utilisation

**Mode vidéo :**
1. Importer une vidéo ou coller une URL YouTube.
2. Cliquer sur *Analyser*.
3. Cliquer sur *Play* : le robot rejoue les expressions avec le son.

**Mode live :**
1. Se placer face à la webcam.
2. Cliquer sur *Démarrer le live*.
3. Le robot imite vos expressions en temps réel.

## Équipe

- **Elliott Amrouche** ([@elliottmrch](https://github.com/elliottmrch))
- **Noah Normand**
- **Martin Hurvois**
