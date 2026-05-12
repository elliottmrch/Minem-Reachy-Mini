# Mapping humain > Reachy Mini

Proposition de table de correspondance entre les signaux observés sur un visage humain et les mouvements possibles du robot Reachy Mini.

---

## 1. Signaux humains extraits

L'extraction repose sur MediaPipe FaceMesh (468 landmarks 3D). Les signaux retenus sont les suivants :

| Signal | Méthode de calcul |
|--------|------------------|
| Yaw — rotation horizontale de la tête | Vecteur 3D œil-nez-menton |
| Pitch — inclinaison avant/arrière | Composante verticale du vecteur normal à la tête |
| Roll — inclinaison latérale | Angle entre les deux coins des yeux |
| Ouverture de la bouche | Distance verticale lèvres / hauteur du visage |
| Ouverture des yeux (gauche et droit) | Eye Aspect Ratio (EAR) |
| Indice de sourire | Largeur de la bouche / distance inter-oculaire |
| Haussement sourcil (gauche et droit) | Projection perpendiculaire du sourcil sur l'axe des yeux |
| Position du visage (cx, cy) | Centre de la bounding box normalisé [0, 1] |

---

## 2. Table de correspondance

### 2.1 Tête du robot

| Signal humain | Mouvement robot | Justification |
|--------------|----------------|---------------|
| Yaw tête | Yaw tête robot (×0.8) | Reprise directe, légèrement réduite pour rester dans les limites mécaniques |
| Pitch tête | Pitch tête robot (×0.8) | Reprise directe |
| Roll tête | Roll tête robot (×0.5) | Réduit car peu lisible sans visage |
| Ouverture bouche | Pitch vers le bas | Simule le poids naturel de la mâchoire lors de la parole |
| Ouverture des yeux | Recul léger de la tête (translation X) | Exprime la surprise — l'écarquillement provoque un mouvement de recul |
| Sourire | Élévation légère de la tête (translation Z) | Exprime la légèreté et l'attitude positive |

### 2.2 Antennes

| Signal humain | Mouvement robot | Justification |
|--------------|----------------|---------------|
| Haussement sourcil gauche | Antenne gauche vers le haut | Les antennes remplacent l'absence de sourcils |
| Haussement sourcil droit | Antenne droite vers le haut | Même logique, effet miroir dû à la convention d'axe |

Le facteur appliqué est volontairement élevé pour que même un haussement discret reste visible sur le robot.

### 2.3 Corps du robot

| Signal humain | Mouvement robot | Justification |
|--------------|----------------|---------------|
| Position horizontale du visage (cx) | Rotation du corps (yaw) | Le robot suit la personne si elle se déplace latéralement |

Une zone morte est appliquée autour du centre pour éviter les micro-oscillations quand le visage est centré.

---

## 3. Réponses aux questions du jalon

**Quels mouvements humains peuvent être repris directement par la tête du robot ?**
Le yaw et le pitch de la tête se mappent quasi-directement : ce sont des rotations que le robot peut reproduire dans les mêmes axes. Seul un facteur d'échelle est appliqué pour respecter les limites mécaniques. Le roll est repris mais atténué, car il est moins lisible sur un robot sans visage.

**Que pourrait devenir un sourire ?**
Le robot n'ayant pas de bouche, le sourire est traduit par une légère élévation de la tête (translation verticale). Ce mouvement est associé à une attitude ouverte et positive, ce qui constitue un équivalent fonctionnel du sourire.

**Comment les antennes pourraient-elles être utilisées comme élément expressif ?**
Les antennes remplacent les sourcils. Le haussement de sourcil est l'un des signaux émotionnels les plus lisibles chez l'humain (surprise, questionnement, attention). Mapper ce signal sur les antennes permet au robot de transmettre ces états sans avoir de visage articulé.

**Faut-il exagérer certains mouvements pour qu'ils restent lisibles ?**
Oui, partiellement. Les antennes utilisent un facteur d'amplification élevé car un haussement de quelques degrés serait imperceptible à distance. La translation verticale liée au sourire est également amplifiée pour la même raison. En revanche, les rotations de tête sont légèrement réduites pour rester naturelles et éviter les mouvements saccadés.
