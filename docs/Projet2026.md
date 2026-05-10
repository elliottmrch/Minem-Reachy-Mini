# Transfert d'expressivité faciale humaine vers un robot

## 1. Contexte

La communication non verbale joue un rôle central dans les interactions humaines. Reproduire cette expressivité sur un robot est un enjeu clé de l'interaction Homme-Robot (HRI), car elle permet de rendre le robot plus engageant, compréhensible et attachant.

Reachy Mini est un robot expressif conçu par Pollen Robotics. Il dispose de 9 degrés de liberté : une tête orientable (3 axes de rotation et 3 axes de translation), deux antennes mobiles et un corps rotatif. Ces actionneurs permettent des mouvements très expressifs, mais ne correspondent pas directement à ceux d'un visage humain. Le robot n'a ni bouche, ni nez, ni yeux, ni sourcils, ni peau articulée. En revanche, il peut bouger ses antennes et dispose d'une mobilité de tête supérieure (discutable) à celle d'un humain. Il faut donc faire preuve de créativité pour traduire l'expressivité humaine en mouvements du robot.

Vous devez concevoir une application complète (backend + interface web) qui prend en entrée une vidéo contenant un visage humain, en extrait automatiquement des informations de mouvement par vision par ordinateur, puis les traduit en commandes pour Reachy Mini avec synchronisation audio. L'objectif est de permettre à quiconque, sans compétence en robotique, de "donner vie" au robot à partir d'une simple vidéo.

## 2. Pipeline de traitement

Le traitement se décompose en deux grandes étapes :

### Étape 1 — De la vidéo aux caractéristiques faciales

Il s'agit d'analyser la vidéo image par image pour en extraire des informations exploitables : position et orientation de la tête, expressions du visage, direction du regard, etc. Plusieurs bibliothèques de vision par ordinateur permettent de détecter des points de repère faciaux (landmarks) à partir desquels ces caractéristiques peuvent être calculées.

### Étape 2 — Des caractéristiques faciales aux commandes robot

Les caractéristiques extraites doivent ensuite être traduites en commandes pour les actionneurs du robot. Ce mapping n'est pas évident car les degrés de liberté du robot ne correspondent pas à ceux du visage humain. Par exemple :

- La position et l'orientation de la tête humaine peuvent se mapper assez directement sur la tête du robot.
- Le sourire d'une personne pourrait être détecté et traduit en un mouvement des antennes du robot.
- La direction du regard pourrait influencer légèrement l'orientation de la tête.

## 3. Objectif

Réaliser une application complète (backend + interface web) permettant de :

1. Importer une vidéo (locale ou avec URL YouTube),
2. Traiter automatiquement la vidéo pour en extraire une trajectoire de mouvement,
3. Sauvegarder ce mouvement,
4. Rejouer le mouvement sur le robot/simulateur.

## 4. Fonctionnalités attendues

1. Import de vidéos (formats usuels).
2. Traitement vidéo hors-ligne.
3. Détection d'un visage principal et extraction de signaux de mouvement.
4. Génération d'un fichier de mouvement rejouable.
5. Extraction du son de la vidéo quand il existe.
6. Lecture synchronisée mouvement + audio.
7. Interface web simple et utilisable.

## 5. Contraintes du sujet

1. L'application doit fonctionner sans intervention manuelle pendant le traitement.
2. Les erreurs doivent être gérées proprement (fichier invalide, absence de visage, échec de lecture, etc.).
3. Les données produites doivent être persistées localement.
4. Le système doit rester utilisable même sans robot physique (mode simulation).

## 6. Livrables

1. Code source complet et exécutable.
2. App publiée, téléchargeable et fonctionnelle depuis n'importe quel PC (sous votre OS).
3. README d'installation et d'utilisation.
4. Rapport technique : architecture, choix, limites, pistes d'amélioration.
5. Présentation (soutenance) technique.

## 7. Évaluation

1. Fonctionnalités conformes au sujet : 25%.
2. Respect des jalons : 10%.
3. Qualité logicielle (structure, lisibilité, robustesse, tests) : 25%.
4. Qualité de l'interface et expérience utilisateur : 10%.
5. Présentation/démonstration et qualité du rapport : 20%.
6. Innovation : 10%.

## 8. Innovations possibles

1. Plusieurs profils de "style" de mouvement.
2. Visualisation vidéo annotée du suivi facial.
3. Mesures de performance et optimisation.
4. Autre : n'hésitez pas à me soumettre des idées de fonctionnalités.

## Liens utiles

- https://huggingface.co/docs/reachy_mini/index
- https://huggingface.co/docs/reachy_mini/SDK/readme
- https://huggingface.co/docs/reachy_mini/examples/minimal_demo
- https://huggingface.co/docs/reachy_mini/platforms/simulation/get_started
- https://huggingface.co/docs/reachy_mini/API/reachymini
