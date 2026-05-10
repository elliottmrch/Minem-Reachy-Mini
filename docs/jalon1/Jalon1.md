# Premier jalon à respecter : 27 mars

Pour cette date, chaque groupe doit avoir :

- Une app coquille qui peut être lancée en simulation (chaque membre du groupe doit en avoir une, et normalement c’est déjà fait).
- Un code qui fait bouger le robot en simulation : faire les programmes ci-dessous. J’ai mis sur Junia-Learning une vidéo des mouvements.
- La conception technique du projet (diagramme de classes envisagé, recherches sur les librairies que vous pourriez utiliser, …).
- Des mini POC sur les librairies choisies afin de vérifier qu’elles pourront fonctionner.

## Exercice : Boucle de contrôle et trajectoires continues

### Contexte

Si l’on voulait simplement déplacer la tête d’un point A à un point B, on utiliserait `goto`, on fixerait une durée, et ce serait terminé.

Mais dans une application réelle, on ne connaît pas toujours la position cible à l’avance. On doit souvent réajuster la consigne en permanence.

Cela revient à mettre en place une boucle de contrôle : une boucle dans laquelle on envoie très régulièrement de nouvelles consignes proches les unes des autres.

Les moteurs suivront ces requêtes du mieux possible.

Si les commandes sont physiquement cohérentes (vitesses et amplitudes raisonnables), le mouvement observé sera fluide.

L’objectif de cet exercice est donc de :

- Manipuler les 6 dimensions de mouvement.
- Comprendre l’effet d’une commande envoyée en continu.
- Observer l’impact de la fréquence d’envoi des consignes.
- Expérimenter les combinaisons de mouvements.

Travail en simulation.

## Livrables

Deux scripts Python indépendants

ou

Deux modes dans un même script

Les programmes doivent être exécutables en simulation.

Faire un commit & push de ces exercices sur le repo de votre app.

## Contraintes générales

- Utiliser une boucle de contrôle qui envoie des commandes régulièrement (100 fois par seconde, soit 100 Hz).
- Produire des mouvements physiquement suivables : amplitudes raisonnables, vitesse et accélération non extrêmes.
- Le robot doit enchaîner les séquences automatiquement, sans intervention utilisateur pendant l’exécution.

## Programme 1 : Sinusoïdes une dimension à la fois

### Objectif

Comprendre le mapping des 6 dimensions et valider votre boucle de contrôle.

### À réaliser

- Faire bouger la tête selon un sinus sur une seule dimension.
- Puis passer automatiquement à la dimension suivante.
- Pour chaque dimension : exactement 3 oscillations complètes.

### Dimensions à couvrir

Rotations :

- `roll`
- `pitch`
- `yaw`

Translations :

- `x`
- `y`
- `z`

### Paramètres à définir par vous

- amplitude pour chaque dimension
- fréquence

### Bonus optionnel

En parallèle, animer les antennes avec un petit mouvement sinusoïdal.

Fréquence et amplitude libres.

Pendant tout le programme.

## Programme 2 : Mouvements combinés

### Objectif

Combiner plusieurs dimensions pour créer des trajectoires plus riches.

### Séquence A : oscillation latérale + hochement

- Le robot oscille de gauche à droite selon un sinus lent sur la coordonnée `y`.
- En même temps, il hoche la tête “oui” via une oscillation sinusoïdale plus rapide sur l’angle `pitch`.
- Cette séquence dure exactement 3 périodes de l’oscillation gauche-droite, soit 3 oscillations complètes en `y`.

### Séquence B : cercle à z constant

Après les 3 périodes de la séquence A :

- Le robot dessine un cercle avec sa tête.
- Le cercle est dans le plan `x y`.
- La hauteur `z` reste constante pendant tout le cercle.
- Faire 3 tours complets puis terminer le programme.

## Expérimentation

Que se passe-t-il si vous envoyez les commandes moins fréquemment ?

Testez par exemple :

- 50 Hz
- 20 Hz
- 10 Hz
- 5 Hz
- 1 Hz
- 0.5 Hz

Observez la fluidité du mouvement et expliquez ce que vous constatez.
