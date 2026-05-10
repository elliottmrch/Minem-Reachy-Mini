# Second jalon à respecter : 24 avril

Pour cette date, chaque groupe doit avoir :

- Un code capable de charger une vidéo locale et d’en analyser automatiquement les images.
- Un premier système de détection du visage principal.
- Une recherche sur l’interprétation des émotions à partir des mouvements du visage et de la tête.
- Une première proposition de mapping entre les signaux humains observés et les mouvements possibles du robot.

Le niveau attendu ici est celui du prototype. Avoir plusieurs solutions concurrentes pour résoudre le même problème est bienvenu, avoir une première intégration complète aussi.

## 1. Chargement et analyse d’une vidéo

Votre programme doit être capable de :

- charger une vidéo locale simple (une seule personne, format mp4),
- la parcourir image par image,
- détecter un visage,
- extraire sur la durée plusieurs informations numériques exploitables.

Le traitement doit être automatique, sans réglages manuels image par image.

## 2. Extraction de signaux/landmarks

Vous devez extraire au minimum :

- la position du visage dans l’image,
- l’orientation de la tête ou une approximation exploitable de cette orientation,
- au moins trois autres signaux parmi les suivants :
  - ouverture de la bouche,
  - ouverture des yeux,
  - sourire ou indice approchant,
  - inclinaison de la tête,
  - tout autre indicateur pertinent que vous savez justifier.

Les signaux doivent être enregistrés dans un format facilement réutilisable par la suite, par exemple JSON, CSV ou équivalent. Chaque signal sera stocké avec son timestamp (le moment précis où il se produit, 0 étant le début de la vidéo).

## 3. Visualisation / vérification

Vous devez produire un moyen de vérifier visuellement que votre code fonctionne.

Par exemple :

- vidéo annotée,
- images annotées,
- tracés temporels,
- affichage des signaux/landmarks,
- affichage de la boîte englobante,
- reproduire les mouvements avec reachy.

Le but est de pouvoir juger rapidement si les mesures sont plausibles.

## 4. Recherche libre sur le thème “comment faire un robot expressif”

Vous devez réaliser une phase de recherche sur les différentes techniques pour exprimer des émotions au travers d’un robot. Le but ici et de chercher des idées qui pourraient être appliquées au projet.

Vous pouvez citer des papiers de recherche, des œuvres cinématographiques et tout autre support que vous jugerez pertinent.

Il est très commun, dans un travail exploratoire comme celui-ci, de se rendre compte en cours d’étude d’une approche que celle-ci n’est pas applicable à votre projet. Vous êtes encouragés à présenter ces approches également si vous les trouvez intéressantes.

Un rapport est demandé pour cette section, taille maximum 10 pages.

## 5. Proposition de mapping vers le robot

À partir des signaux extraits et de votre recherche, vous devez proposer une première table de correspondance entre :

- ce qui est observé sur l’humain,
- et ce qui pourrait être joué par Reachy Mini.

Exemples de questions à traiter :

- quels mouvements humains peuvent être repris assez directement par la tête du robot ?
- que pourrait devenir un sourire, sachant que le robot n’a pas de bouche ?
- comment les antennes pourraient-elles être utilisées comme élément expressif ?
- faut-il exagérer certains mouvements pour qu’ils restent lisibles sur le robot ?

À ce stade, une proposition argumentée suffit mais vous êtes vivement encouragés à illustrer votre proposition de petits codes qui font bouger Reachy en simulation.
