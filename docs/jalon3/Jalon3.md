# Troisième jalon à respecter : 11 mai

Pour cette date, chaque groupe doit avoir :

- Un code capable de transformer les signaux extraits d’une vidéo en informations exploitables par le robot.
- Un premier système de génération de mouvement rejouable pour Reachy Mini.
- Une structure de données permettant de stocker un mouvement complet avec son timestamp.
- Un rejeu fonctionnel du mouvement en simulation.
- Une analyse critique des choix de mapping retenus et de leurs limites.

Le niveau attendu ici est celui du prototype. Avoir plusieurs solutions concurrentes pour résoudre le même problème est bienvenu, avoir une première intégration complète aussi.

## 1. Définition du mapping humain -> robot

À partir des signaux extraits au jalon précédent, vous devez définir une première correspondance entre :

- les signaux observés sur l’humain,
- et les mouvements possibles de Reachy Mini.

Cette correspondance doit être explicitée et justifiée.

Exemples de questions à traiter :

- quels signaux humains peuvent être repris directement par la tête du robot ?
- quels signaux doivent être simplifiés, transformés ou exagérés ?
- comment exploiter les antennes comme élément expressif ?
- quels signaux ne sont finalement pas retenus, et pourquoi ?

À ce stade, il n’est pas demandé d’avoir un mapping parfait, mais un mapping cohérent, argumenté et testable.

## 2. Génération d’un mouvement robot

Votre programme doit être capable de :

- charger les signaux extraits au jalon précédent,
- les convertir en consignes robot au cours du temps,
- produire un mouvement complet pour Reachy Mini,
- sauvegarder ce mouvement dans un format facilement réutilisable par la suite.

Le mouvement généré devra contenir au minimum :

- les valeurs des degrés de liberté pilotés,
- leur timestamp,
- éventuellement toute information complémentaire que vous jugerez utile.

Format de sauvegarde : JSON. Cf. exemple donné.

Ne sauvegardez pas les position des moteurs mais celles des antennes, du corps et de la tête (champs `antennas`, `body_yaw`, `head`).

## 3. Rejeu en simulation

Vous devez produire un moyen de rejouer automatiquement le mouvement généré sur Reachy Mini en simulation.

Le rejeu doit permettre de vérifier visuellement :

- que le fichier de mouvement est exploitable,
- que les consignes produites sont cohérentes,
- que le comportement obtenu est stable,
- et que le mouvement semble globalement plausible.

À ce stade, le rejeu en simulation est obligatoire.

## 4. Analyse critique du résultat

Vous devez fournir une première analyse critique du mouvement obtenu.

Cette analyse devra notamment aborder :

- les signaux humains retenus,
- la manière dont ils ont été traduits en mouvement robot,
- ce qui fonctionne bien,
- ce qui semble artificiel ou peu lisible,
- les limites liées au robot,
- les limites liées aux signaux extraits,
- les pistes d’amélioration envisagées.

Un rapport est demandé pour cette section et la section 1, taille maximum 10 pages.

## Bonus optionnel

- comparer plusieurs mappings concurrents
- comparer plusieurs traitements temporels
- exagérer volontairement certains mouvements pour améliorer la lisibilité
- synchroniser le mouvement avec l’audio
