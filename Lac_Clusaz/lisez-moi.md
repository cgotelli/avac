Un projet de vague d'impulsion doit respecter l'architecture des répertoires, à savoir un répertoire dit de projet (noté proj_dir) qui contient :
- le répertoire AVAC : il contient le code de calcul des avalanches
- le répertoire Topo : il contient l'ensemble des fichiers topographiques nécessaires au calcul
- le répertoire Vagues : il comprend l'ensemble des scripts nécessaires au calcul des vagues (le code s'appelle Wave)
Les fichiers de paramètres sont des fichiers yaml (configuration_AVAC.yaml, AVAC_parameters et impulse_configuration.yaml). Ces fichiers sont générés par les cahiers jupyter :
    1. `AVAC.ipynb`,
    2. `Waves_preprocess.ipynb` et 
    3. `Waves_postprocess.ipynb`.
Tout se dréoule à l'aide de ces cahiers jupyter. La seule exception est la création d'animations 3D avec pyvista qui, pour l'heure, se fait en ligne de commande.

# Prérequis :
- python > 3.0
- clawpack > 5.9
- AVAC > 4.3
Les codes clawpack et AVAC font appel à des bibliothèques à charger indépendamment.

Tous les paramètres sont passés à geoclaw sous forme de fichiers de configuration yaml qu'il faut remplir dans les cahiers jupyther (dictionnaires). Une fois que les fichiers de configuration ont été exportés à partir des cahiers jupyter, il est toujours possible de modifier directement `impulse_configuration.yaml` et `AVAC_configuration.yaml` dans un éditeur de texte sans repasser par les cahiers jupyter.

# Procédures de calcul :
1. Faire le calcul des avalanches dans le répertoire AVAC. Tout se gère à partir de AVAC.ipynb. Il faut impérativement placer un fichier de topographie de type raster et un shape fournissant les zones de départ dans le dossier /Topo. Puis remplir les dictionnaires de paramètres et aller de cellule en cellule pour générer les conditions initiales et le fichier topo compatible avec AVAC. Il est possible de faire une animation en exécutant le script `pyvista_postprocess.py` (voir infra).
2. Se placer dans le répertoire du projet et lancer Waves_preprocess.ipynb. Il faut en général un shapefile (polyline) qui renseigne sur le contour du lac. Cela est nécessaire pour l'initialisation de la hauteur d'eau dans la retenue. Les paramètres sont dans les différents dictionnaires topo_files, lake, computation, dict_gauges. Il faut notamment définir le domaine de calcul [xmin, xmax, ymin, ymax]. Ce cahier lit les simulations d'AVAC et les transforme en conditions aux limites pour le calcul de vagues. Ces conditions sont écrites dans le répertoire CL sous la forme de fichiers texte npy (un fichier par bord [est, ouest, nord, sud] du domaine de calcul et par unité de temps).
3. Se placer dans le répertoire Vagues et exécuter les cellules de Waves_postprocess.ipynb. Ce cahier lance l'exécution et lit les résultats, qui sont reportés sous forme de cartes, profils en long et animation Il est possible de faire une animation en exécutant le script `pyvista_postprocess.py`.


# Fonctionnement de pyvista_postprocess.py
Le script ouvre une fenêtre Qt et permet de visualiser en 3D le résultat d'une simulation. Il y a des paramètes par défaut, ce qui fait que l'exécution `python pyvista_postprocess.py` dans la commande de prompt (en se plaçant soit dans /Vagues soit dans /AVAC) doit être suffisante à créer la fenêtre Qt et visualiser la simulation. Pour faire défiler la simulation, il faut appuyer sur les flèches du clavier (droite/gauche) ou bien les touches (k et j). Les flèches haut/bas agrandit ou rapetisse la vue 3D. Avec la souris on peut modifier l'angle de perspective et zoomer. Pour créer une animation, il faut appuyer sur m (cela lance l'animation au temps affiché dans le fenêtre). On peut se reporter aux lignes 230 à 259 pour voir les options. Par exemple, pour changer la coloration (colormap), on exécute : 
    python pyvista_postprocess.py -m 'coolwarm' 'viridis' 
Pour imposer des hauteurs comprises dans la plage 0--5 m, avec un nom d'animation exportée 'avalanche.mp4', d'une coloration ["terrain", "gnuplot_r"] pour le terrain et la hauteur,une taille de fenêtre Qt [1600,1600] et une perspective d'azimuth 0 et d'altitude -60 m, on tape dans la fenêtre de prompt :
    python pyvista_postprocess.py --clim 0 5 -f "avalanche.mp4" --cmaps "terrain" "gnuplot_r" -ws 1600 1600 -az 0 -el -60

# Changements apportés en mai 2026
Le principal problème reste la sensibilité des résultats au choix du mode de transfert de quantité (*source* ou *bc*) et à la proximité du lac avec les frontières du domaine de calcul.

Plusieurs modifications ont été apportées.

## Avac
Afin de pouvoir garder plusieurs résultats de simulation, il y a une fonction *rename_output_directory* qui permet de renommer le réertoire de sortie /_output et de sauvegarder le nom dans le fichier de configuration. Il faut juste faire attention à quelle simulation on se réfère dans Wave.

## Waves preprocess
Il devient obligatoire d'utiliser un contour du lac (shapefile de type polyline) :
1. le contour sert à définir la condition initiale
2. il permet de calculer les fluides de masse et de quantité de mouvement dans le lac (on a besoin de la normale au contour et l'avantage d'un shapefile réalisé manuellement par rapport à un raster automatique est qu'on dimininue le bruit et les problèmes de définition de cette normale)

Le dictionnaire de configuration est enrichi d'un sous-dictionnaire 'scenario' qui permet de passer la valeur de la période de retour. Le sous-dictionnaire 'output' est enrichi de nouvelles clés pour gérer la cartographie de façon systématique.

Dans le sous-dictionnaire 'rheology', on peut employer un Strickler qui dépend de la tranche d'altitude. Il suffit alors de remplir un array et de renseigner la clé 'manning_break'. Par exemple rheology['Strickler'] = [10,30] et rheology['friction_break_elevation'] = 2000 implique que le coefficient de Stickler vaut 10 au-dessus de 2000 m et 30 au-dessous de 2000 m. On peut multiplier à l'envi la taille des arrays selon le besoin. L'idée est de prendre un frottement plus important pour la région concernée par l'avalanche. S'il n'y a qu'une seule valeur pour la clé Strickler, p. ex. rheology['Strickler'] = 30, alors un seul coefficient de frottement s'applique à tout le domaine. Si la longueur de l'array rheology['Strickler'] est n, alors la longueur de rheology['friction_break_elevation'] est n-1.

J'ai ajouté la fonction modify_spillway_elevation, qui modifie le modèle numérique de terrain pour intégrer un barrage ou un seuil. Il faut un shapefile (polyline) qui définit la position du barrage.

La fonction de calcul des conditions aux limites a été modifiée pour prendre en compte des avalanches qui seraient en fin de vie (donc avec une hauteur donnée et une vitesse nulle ou proche de zéro). Sans cela, un dépôt de neige est traité comme un volume d'eau, qui est mis en mouvement par Wave.

## Wave postprocess
Le calcul de l'énergie des vagues et de l'avalanche a été affiné. Plusieurs fonctions ont été introduites :
* *create_plot_lake_contour_meshing* : à partir du shapefile du contour, on énumère les segments, leurs longueurs, et leur normale orientée. Un maillage du contour est effectué avec un pas cohérent avec celui du MNT.
* *calculate_inflow* : calcul des énergies cinétique, potentielle, des flux de volume à partir d'AVAC et de Wave. Cela permet de calculer l'énergie fournie par l'avalanche.
* *calculate_overflow_rate* : calcule le volume d'eau qui passe par-dessus le contour (shapefile) du lac
 
 Un booléen Apply_mask a été introduit. A priori, il est considéré comme vrai, c'est-à-dire que les calculs ne s'appliquent qu'au domaine du lac (à l'intérieur du contour). Un masque est généré pour tous les arrays générés. On conserve des arrays non masqués pour suivre le mouvement de l'eau hors du lac.

 Un boucle itérative permet de faire une série de calcul pour voir l'effet de la densité de la neige ($\rho_a/\rho$) sur les caractéristiques des vagues.

 Un cahier supplémentaire Check_Wave-process permet de comparer les simulations AVAC et Wave afin de s'assurer de leur cohérence. Notamment les fonctions :
 * *plot_avalanche* : permet de tracer l'emprise d'AVAC à un temps donné tout en visualisant le contour du lac et ses caractéristiques
 * *init_plot_avalanche_side_by_side*, *draw_avalanche_side_by_side* : permet de tracer les hauteurs d'AVAC et de Wave, puis de faire défiler les résultats
 * *init_plot_avalanche*, *draw_avalanche* : fonction similaire à la précédente avec en sus un profil de hauteur et de quantité de mouvement à travers une polyligne.

## Modules
Le module `module_waves.py` a été amélioré et étendu.

Dernière mise à jour : 11 mai 2026




