from shapely.geometry import LineString

def check_configuration(config, topo_dir, damping_max= 0.4):
    """
    Vérifie la cohérence de la configuration avant lancement du calcul.

    Contrôles effectués :
      1. Présence dans topo_dir de tous les fichiers référencés dans topo_files et lake['topography'].
      2. Égalité entre la maille du masque (topo_files['mask_raster']) et celle du MNT (lake['topography']).
      3. Facteur d'amortissement computation['damping'] <= damping_max= 0.4 (par défaut)
      4. Mode de calcul computation['mode'] dans {'bc', 'src'}.

    Paramètres
    ----------
    config : dict
        Dictionnaire de configuration chargé depuis le fichier YAML.
    topo_dir : Path ou str
        Chemin vers le dossier contenant les fichiers de topographie.

    Retourne
    --------
    bool
        True si la configuration est valide, False sinon (les erreurs sont affichées).
    """
    from pathlib import Path
    try:
        from module_avac import reading_raster_file_features
    except ImportError:
        import sys
        sys.path.insert(0, str(Path(topo_dir).parent / "AVAC"))
        from module_avac import reading_raster_file_features

    topo_dir    = Path(topo_dir)
    topo_files  = config['topo_files']
    lake        = config['lake']
    computation = config['computation']

    errors = []

    # --- 1. Présence des fichiers de topographie ---
    file_entries = {k: v for k, v in topo_files.items() if isinstance(v, str)}
    for key, filename in file_entries.items():
        if not (topo_dir / filename).exists():
            errors.append(
                f"  [topo_files] Fichier manquant : topo_files['{key}'] = '{filename}' "
                f"introuvable dans {topo_dir}"
            )

    lake_topo_path = topo_dir / lake['topography']
    if not lake_topo_path.exists():
        errors.append(
            f"  [lake] Fichier manquant : lake['topography'] = '{lake['topography']}' "
            f"introuvable dans {topo_dir}"
        )

    # --- 2. Cohérence des mailles masque / MNT ---
    mask_path = topo_dir / topo_files.get('mask_raster', '')
    if mask_path.exists() and lake_topo_path.exists():
        try:
            _, _, _, _, _, _, cs_mask, _, _, _, _ = reading_raster_file_features(mask_path)
            _, _, _, _, _, _, cs_mnt,  _, _, _, _ = reading_raster_file_features(lake_topo_path)
            if abs(cs_mask - cs_mnt) > 1e-6:
                errors.append(
                    f"  [topo_files/lake] Incohérence de maille : "
                    f"masque '{topo_files['mask_raster']}' = {cs_mask} m  ≠  "
                    f"MNT '{lake['topography']}' = {cs_mnt} m"
                )
        except Exception as exc:
            errors.append(
                f"  [topo_files] Impossible de lire les mailles du masque ou du MNT : {exc}"
            )

    # --- 3. Facteur d'amortissement ---
    damping = computation.get('damping')
    if damping is not None and damping > damping_max:
        errors.append(
            f"  [computation] damping = {damping} > {damping_max}. "
            f"Le facteur d'amortissement doit être strictement inférieur à {damping_max} !"
        )

    # --- 4. Mode de calcul ---
    mode = computation.get('mode', '')
    MODES_VALIDES = ('bc', 'src')
    if mode not in MODES_VALIDES:
        errors.append(
            f"  [computation] mode = '{mode}' non reconnu. "
            f"Valeurs acceptées : {MODES_VALIDES}."
        )

    # --- Bilan ---
    if errors:
        print(f"La configuration comporte {len(errors)} erreur(s) :")
        for msg in errors:
            print(msg)
        return False

    print("Configuration valide.")
    return True



def check_output(Frames):
    """
    Fournit les caractéristiques du domaine de calcul et l'itervalle de temps afin de vérifier que cela correspond bien à ce qui était demandé
    Entrée :
        * Frames : liste de frames
    Sorties :
        * domain_extent : dictionnaire des caractéristiques du domaine de calcul
        * time_extent : dictionnaire de l'intervalle de temps
    """
    xlower = []
    xupper = []
    ylower = []
    yupper = []
    NbSim = len(Frames)
    t_0 = Frames[0].t
    t_f = Frames[NbSim-1].t
    dt  = (t_f-t_0)/(NbSim-1)
    
    for patch in Frames[0].domain.patches:
        xlower.append(patch.grid.x.lower)
        xupper.append(patch.grid.x.upper)
        ylower.append(patch.grid.y.lower)
        yupper.append(patch.grid.y.upper)
    xmin_o  = min(xlower)
    xmax_o  = max(xupper)
    ymin_o  = min(ylower)
    ymax_o  = max(yupper)
    delta   = Frames[0].patch.delta
    nombre_patches = len(Frames[0].domain.patches)
    print(f"* xmin =  {format_m(xmin_o)} et xmax =  {format_m(xmax_o)} ; delta_x = {delta[0]}.")
    print(f"* ymin =  {format_m(ymin_o)} et ymax = {format_m(ymax_o)} ; delta_y = {delta[1]}.")
    print(f"* Il y a {nombre_patches} patches au temps t = {t_0}.")
    print(f"* Temps initial t = {t_0} ; temps final t = {t_f} ; dt = {dt}.")

    print(f"* Nombre de simulations : {NbSim-1}.")
    domain_extent = {'xmin':xmin_o,'xmax':xmax_o,'ymin':ymin_o,'ymax':ymax_o, 'dx':delta[0],'dy':delta[1]}
    time_extent   = {'t_0':t_0,'t_f':t_f,'dt':dt}
    return domain_extent, time_extent

def check_domain_in_topo(lake, topo_xmin, topo_xmax, topo_ymin, topo_ymax):
    """
    Vérifie que le domaine lac est entièrement contenu dans l'étendue de la topo.
    Lève une ValueError détaillée si ce n'est pas le cas.
    Arguments :
    - lake : dictionnaire avec les indications sur les caractéristiques du lac
    - topo_xmin, topo_xmax, topo_ymin, topo_ymax : extension du domaine de calcul
    """
    topo = {'xmin': topo_xmin, 'xmax': topo_xmax, 'ymin': topo_ymin, 'ymax': topo_ymax}
    
    checks = {
        'xmin': lake['xmin'] >= topo['xmin'],
        'xmax': lake['xmax'] <= topo['xmax'],
        'ymin': lake['ymin'] >= topo['ymin'],
        'ymax': lake['ymax'] <= topo['ymax'],
    }
    
    errors = [
        f"  lake['{k}'] = {lake[k]:>10.1f}  hors de [{topo['xmin' if 'x' in k else 'ymin']:.1f}, {topo['xmax' if 'x' in k else 'ymax']:.1f}]"
        for k, ok in checks.items() if not ok
    ]
    
    if errors:
        raise ValueError(
            f"Domaine lac incompatible avec la topo ({lake['topography']}) :\n"
            + "\n".join(errors)
            + f"\n\nDomaine lac  : x=[{lake['xmin']}, {lake['xmax']}]  y=[{lake['ymin']}, {lake['ymax']}]"
            + f"\nEtendue topo : x=[{topo['xmin']}, {topo['xmax']}]  y=[{topo['ymin']}, {topo['ymax']}]"
        )
    
    print(f"Le domaine de calcul des vagues est entièrement contenu dans le fichier {lake['topography']}.")

def format_m(x, decimals=1):
    """espace fine insécable"""
    return f"{x:_.{decimals}f}".replace("_", "\u202f")   

def create_mask(proj_dir,topo_dir,topo_files,lake,erase=True,Language='French',mask_cell_size=None):
    """
    Create a mask by clipping the topo file
    Input:
        * proj_dir: string, name of the project directory
        * topo_dir: string, name of the topographic file directory
        * topo_files: dictionary, locates the topo files and gives the no-data code
        * lake: dictionary, provides all the info about the lake
        * mask_cell_size: float, optional. Cell size of the mask raster. If None, uses the topo
          file cell size. Must match the computation grid cell size so that GeoClaw's ForceDry
          mechanism can evaluate the mask correctly at each cell center (GeoClaw interpolates
          binary masks poorly when resolutions differ).
    Output:
        * a raster file with 0 for points inside the lake (wet) and 1 outside the lake (dry).
          This file can be read by geoclaw
    Note that if erase = False, then the dummy file 'masque.asc' is conserved and is compatible with Qgis
    """
    import subprocess
    from module_avac import reading_raster_file_features, reading_raster_file, export_claw_dem
    xmin, xmax, ymin, ymax, nbx, nby, cell_size, \
        dictionary_extent, failure, remarks, grid_type = reading_raster_file_features(topo_dir / lake['topography'])
    if mask_cell_size is not None:
        cell_size = mask_cell_size
    # adresses
    shp       = topo_dir / topo_files["mask_shp"]  # shapefile with the mask surrounding the lake
    out_tif   = proj_dir / "Topo" / "masque.tif"   # dummy file
    out_asc   = topo_dir / "masque_qgis.asc"       # dummy file that can be erased or saved (Qgis compatible)
    path_mask = topo_dir /'mask.asc'               # name of the mask, geoclaw compatible (not Qgis compatible)
    import subprocess
    # creating the mask raster file 'masque.tif'
    subprocess.run([
        "gdal_rasterize",
        "-burn", "0",    # intérieur du polygone → 0 (lac)
        "-init", "1",    # fond → 1 (zones sèches)
        "-at",           # ALL_TOUCHED : inclut les pixels sur le contour
        "-te", f"{xmin}", f"{ymin}", f"{xmax}", f"{ymax}",
        "-tr", str(cell_size), str(cell_size),
        "-ot", "Byte",
        "-of", "GTiff",
        str(shp),
        str(out_tif),
    ], check=True)
    # converting to ESRI raster file
    subprocess.run([
        "gdal_translate",
        "-of", "AAIGrid",
        str(out_tif),
        str(out_asc),
    ], check=True)

    # Export to geoclaw raster file that can be read by geoclaw
    mask_r = reading_raster_file(str(out_asc))
    export_claw_dem(mask_r.x.min(),mask_r.x.max(),mask_r.y.min(),mask_r.y.max(),mask_r.Z.shape[1],mask_r.Z.shape[0],
                    mask_r.Z,name_file =str(path_mask) ,boolean = True, Language = Language )
    # Erasing the dummy files
    if erase: 
        out_asc.unlink()
    else:
        if Language == 'French':
            print("J'ai gardé le fichier temporaire masque.asc (comptatible qgis).")
        else:
            print("I kept the temporary file (qgis compatible) file masque.asc")
    out_tif.unlink()
    if Language == 'French': 
        print(f"Masque créé : {path_mask}")
    else:
        print(f"Mask created: {path_mask}")

def reload_wave(dossier=None):
    """
    Reloads the module module_waves in a robust way... so if changes are made in this file, it is possible to reload the module.

    Input:
        * folder : str, optional. Path to the folder containing the module

    Output:
        * module or None. The reloaded module or None in case of error

    """
    import importlib
    import os
    import sys
    if dossier is not None:
        module_dir = str(dossier)
    elif 'module_waves' in sys.modules and hasattr(sys.modules['module_waves'], '__file__'):
        module_dir = os.path.dirname(os.path.abspath(sys.modules['module_waves'].__file__))
    else:
        module_dir = os.getcwd()
    
    module_path = os.path.join(module_dir, 'module_waves.py')
    
    # Vérification de l'existence du fichier
    if not os.path.exists(module_path):
        print(f"Error: {module_path} does not exist...")
        return None
    
    try:
        # Add folder to system path
        if module_dir not in sys.path:
            sys.path.insert(0, module_dir)
        
        # Méthode 1: if module has not been imported
        if 'module_waves' not in sys.modules:
            spec = importlib.util.spec_from_file_location("module_waves", module_path)
            module = importlib.util.module_from_spec(spec)
            sys.modules["module_waves"] = module
            spec.loader.exec_module(module)
            print("Module imported for the first time.")
        
        # Méthode 2: if module exists, reload it
        else:
            # Supprimer complètement le module du cache
            if 'module_waves' in sys.modules:
                del sys.modules['module_waves']
            
            # Nettoyer aussi les sous-modules si ils existent
            modules_to_remove = [name for name in sys.modules.keys() 
                               if name.startswith('module_waves.')]
            for module_name in modules_to_remove:
                del sys.modules[module_name]
            
            # Reimporter complètement
            spec = importlib.util.spec_from_file_location("module_waves", module_path)
            module = importlib.util.module_from_spec(spec)
            sys.modules["module_waves"] = module
            spec.loader.exec_module(module)
            print("Module reloaded successfully.")
        
        # Mettre à jour les globals() du notebook
        globals()['module_waves'] = sys.modules['module_waves']
        
        return sys.modules['module_waves']
        
    except Exception as e:
        print(f"ERROR when loading the module: {e}")
        return None
    
def create_boundary_conditions(proj_dir, lake, BC_dir, damping = 0.3, avac_out = '_output', n = 100):
    """
    Create the boundary condition files
    Input:
        * proj_dir: string, project directory
        * lake: dictionary providing the lake features
        * BC_dir: string, directory where the boundary condition files are recorded
        * damping: float, damping coefficient (by default: 0.3, i.e. snow density = 300 kg/m³)
        * n: integer, number of points for discretizing a boundary
    Output:
        * h_list : dictionary with the list of h values for each boundary
        * q_list : dictionary with the list of /q/ values for each boundary 
        * flux_list : dictionary with the list of hu.n values for each boundary 
        * times : list of times for each file
    Note that a file called 'summary_config.yaml' is generated for ensuring that all is ok
    """
    import yaml
    from yaml import safe_load
    import numpy as np
    from clawpack.visclaw import gridtools
    from clawpack.pyclaw.solution import Solution
    from pathlib import Path
    import datetime
    # get the current date and time
    now = datetime.datetime.now()
    proj_dir        = Path(proj_dir)
    # définition des dossiers
    
    avac_dir        = proj_dir / "AVAC"
    # chargement du fichier de configuration AVAC
    with open(avac_dir / "AVAC_configuration.yaml") as file:
        config = safe_load(file)
        avac_output = config["output"]
    if avac_out == '_output':
        avac_out = avac_output["output_directory"]
        print(f"Dossier AVAC lu depuis AVAC_configuration.yaml : {avac_out}")
    avac_output_dir = avac_dir / avac_out

    ntimes          = len(list(avac_output_dir.glob("fort.q*")))
    print(f"J'ai trouvé {ntimes} fichiers de simulation AVAC dans {avac_output_dir}")
    print(f"Format des données de simulations : {avac_output["output_format"]}")
    # extension du domaine
    xmin, xmax = lake['xmin'],  lake['xmax'] 
    ymin, ymax = lake['ymin'],  lake['ymax'] 

    # boundaries of the lake domain
    boundaries = ("bottom", "right", "top", "left")
    x = np.hstack((
        np.linspace(xmin, xmax, n, endpoint=True),  # South
        np.full(n, xmax),  # East
        np.linspace(xmax, xmin, n, endpoint=True),  # North
        np.full(n, xmin),  # West
    ))
    y = np.hstack((
        np.full(n, ymin),
        np.linspace(ymin, ymax, n),
        np.full(n, ymax),
        np.linspace(ymax, ymin, n)
    ))

    dist1 = x.max()-x.min()
    dist2 = dist1 + y.max()-y.min()
    dist3 = dist2 + dist1
    dist4 = dist3 + dist2 - dist1
    dist = np.cumsum(np.sqrt(np.diff(x)**2 + np.diff(y)**2))
    dist = np.hstack((0, dist, 2*dist[-1]-dist[-2]))

    def extract(i, outdir=avac_output_dir):
        frame_sol = Solution(i, path=outdir, file_format=avac_output["output_format"])
        q = gridtools.grid_output_2d(
            frame_sol,
            lambda q: q,
            x, y,
            levels = "all",
            return_ma=True
        )
        return q, frame_sol.t

    def write(outdir=BC_dir):
        Path(outdir).mkdir(exist_ok=True)
        for b in boundaries:
            for f in outdir.glob(f"{b}*.npy"):
                f.unlink()
        times  = []
        q_list = {'bottom':[], 'right':[], 'top':[], 'left':[]}
        h_list = {'bottom':[], 'right':[], 'top':[], 'left':[]}
        flux_list = {'bottom':[], 'right':[], 'top':[], 'left':[]}
        dy = (ymax-ymin)/(n-1)
        dx = (xmax-xmin)/(n-1)
        for ti in range(ntimes):
            print(f"Sauvegarde du fichier {ti+1:>{4}}/{ntimes}...", end="\r")
            q, t = extract(ti)
            times.append(t)
            h, hu, hv, eta = q
            d_ell_dict = {'bottom':dx, 'right':dy, 'top':dx, 'left':dy}
            normal_dict = {'bottom':[0,-1], 'right':[1,0], 'top':[0,1], 'left':[-1,0]}
            for bi, boundary in enumerate(boundaries):
                s = slice(bi*n, (bi+1)*n)
                h_s  = h[s].copy()
                hu_s = hu[s]
                hv_s = hv[s]
                # Si l'avalanche est proche de l'arrêt ou à l'arrêt, il faut annuler la hauteur afin d'éviter la création
                # d'un flux fictif das Wave
                epsilon = 1e-6  # seuil de détection d'un dépôt à l'arrêt
                h_s[(np.abs(hu_s) < epsilon) & (np.abs(hv_s) < epsilon)] = 0.0
                data = np.column_stack((x[s], y[s], h_s, hu_s, hv_s))
                path = outdir / f"{boundary}_{ti:0>{4}}.npy"
                np.savetxt(path, data, comments="")
                dl = d_ell_dict[boundary]
                normal = normal_dict[boundary]
                Q = ((data.T[3].data **2+data.T[4].data **2)**0.5).sum()*dl *damping
                Q_proj = ((data.T[3].data *normal[0]+data.T[4].data * normal[1]) ).sum()*dl *damping
                H = data.T[2]
                H = np.mean([h for h in H if ~np.isnan(h)])
                q_list[boundary].append(Q)
                h_list[boundary].append(H)
                flux_list[boundary].append(Q_proj)
        np.savetxt(outdir / "times.txt", times)
        print()
        return h_list,q_list, flux_list, times
    
    configuration_bc = {'date':now,
                        'directories':{'proj_dir':str(proj_dir),'avac_dir':str(avac_dir),'avac_output':str(avac_output_dir),'bc_dir':str(BC_dir)},
                        'nb_simul':ntimes, 'damping':damping,'period_return':config['release']['period_return']}
    
    file_name = BC_dir / 'summary_config.yaml'
    with open(file_name, 'w') as file:
        yaml.dump(configuration_bc, file)
        print(f"J'ai sauvé le fichier {file_name}.")
    
    h_list, q_list, flux_list, times = write()
    print(f"J'ai généré les conditions aux limites entre les temps  t = {times[0]} s et t = {times[-1]}.")
    return h_list, q_list, flux_list, times


def modify_spillway_elevation(topo_file, shapefile_path, half_width, new_altitude):
    """
    Rehausse localement le MNT dans une bande rectangulaire centrée sur une polyligne.

    Entrées :
        * topo_file      : objet Topography retourné par reading_raster_file
        * shapefile_path : chemin vers le shapefile de la polyligne (axe du seuil)
        * half_width     : demi-largeur de la zone de modification de part et d'autre de la polyligne (mètres)
        * new_altitude   : nouvelle altitude du seuil (mètres, même système de coordonnées que le MNT)
    Sortie :
        * un nouvel objet Topography avec le Z modifié localement.

    Note : le shapefile doit être dans le même CRS que le MNT.
    """
    from copy import deepcopy
    import geopandas as gp
    import shapely
    from clawpack.geoclaw import topotools as topo_module

    # Lecture du shapefile et union des tronçons
    line_gdf  = gp.read_file(shapefile_path)
    line_union = line_gdf.geometry.union_all()

    # Buffer rectangulaire (cap_style='flat' → pas d'arrondi aux extrémités)
    buffer_poly = line_union.buffer(half_width, cap_style='flat')

    # Test vectorisé : quelles cellules de la grille tombent dans la zone tampon
    mask = shapely.contains_xy(
        buffer_poly,
        topo_file.X.ravel(),
        topo_file.Y.ravel()
    ).reshape(topo_file.Z.shape)

    # Copie profonde puis modification locale
    new_topo   = deepcopy(topo_file)
    n_modified = int(mask.sum())
    new_topo.Z[mask] = new_altitude

    print(f"* Seuil mis à {new_altitude:.3f} m sur {n_modified} cellule(s) "
          f"(bande de ±{half_width:.1f} m autour de la polyligne).")
    return new_topo


# def valeurs_frontière(face, frame, xmin, xmax, ymin, ymax, nb_grille,
#                       fn_h, fn_hu, fn_hv, fn_eta, origine=True):

def boundary_values(face, frame, config,  origine = True):

    """
    Extrait les grandeurs hydrauliques le long d'une frontière du domaine de calcul.

    Entrées
        * face : {'sud', 'nord', 'est', 'ouest'}
        * frame : clawpack.pyclaw.solution.Solution (frame de simulation à l'instant voulu)
        * config : fichier de configuration
        * origine : bool 
            * Si True (défaut), les coordonnées retournées sont absolues.
            * Si False, elles sont relatives à l'angle inférieur gauche (xmin, ymin).
    Sortie :
        * tuple de dimension (5, nb_grille)
          nb_grille = nombre de points de l'interpolation de la grille (fourni par config)
          Le tuple contient 5 ndarrays :
          - 0 : coordonnées le long de la frontière (x pour sud/nord, y pour est/ouest), éventuellement en relatif
          - 1 : h hauteur d'eau.
          - 2 : composante de la vitesse normale à la frontière  
          - 3 : composante du débit normale à la frontière
          - 4 : eta, altitude de la surface libre.
    """
    import numpy as np
    from clawpack.visclaw import gridtools
    from pathlib import Path
    topo_dir = Path(config['directory']['project_directory'])
    try:
        from module_avac import reading_raster_file_features, fn_hv, fn_hu, fn_h, fn_eta
    except ImportError:
        import sys
        sys.path.insert(0, str(Path(topo_dir).parent / "AVAC"))
        from module_avac import reading_raster_file_features, fn_hv, fn_hu, fn_h, fn_eta

    topo_files  = config['topo_files']
    lake        = config['lake']
    computation = config['computation']
    xmin        = lake['xmin']
    xmax        = lake['xmax']
    ymin        = lake['ymin']
    ymax        = lake['ymax']
    nb_grille   = computation['nb_grid']
    config_dict = {
        'sud':   dict(coord=np.linspace(xmin, xmax, nb_grille), fixed=ymin, axis='x', fn_qn=fn_hv, origin=xmin),
        'nord':  dict(coord=np.linspace(xmin, xmax, nb_grille), fixed=ymax, axis='x', fn_qn=fn_hv, origin=xmin),
        'est':   dict(coord=np.linspace(ymin, ymax, nb_grille), fixed=xmax, axis='y', fn_qn=fn_hu, origin=ymin),
        'ouest': dict(coord=np.linspace(ymin, ymax, nb_grille), fixed=xmin, axis='y', fn_qn=fn_hu, origin=ymin),
    }
    if face not in config_dict:
        raise ValueError(f"face doit être 'sud', 'nord', 'est' ou 'ouest', or l'argument reçu est {face!r}")

    cfg      = config_dict[face]
    coord    = cfg['coord']
    fixed    = np.full_like(coord, cfg['fixed'])
    x_p, y_p = (coord, fixed) if cfg['axis'] == 'x' else (fixed, coord)

    kw        = dict(levels='all', return_ma=True)
    h         = gridtools.grid_output_2d(frame, fn_h,         x_p, y_p, **kw)
    q_normal  = gridtools.grid_output_2d(frame, cfg['fn_qn'], x_p, y_p, **kw)
    eta       = gridtools.grid_output_2d(frame, fn_eta,       x_p, y_p, **kw)
    v_normal  = np.zeros(coord.shape)
    np.divide(q_normal, h, out=v_normal, where = h != 0)

    if not origine:
        coord = coord - cfg['origin']

    return coord, h, v_normal, q_normal, eta


def Create_Animation(frames, x_profil, y_profil, config, temps_in, offset_min = 1,offset_max = 0,offset_text = 1.5):
    """ 
    Génère les fichiers pour l'animation
    Entrées :
        * frames   : ensemble des frames de type clawpack.pyclaw.solution.Solution 
        * x_profil : ndarray des x
        * y_profil : ndarray des y
        * config : dictionnaire de configuration
        * offset_min  : float, optionnel (par défaut 1), marge à retrancher pour la cote minimale du terrain
        * offset_max  : float, optionnel (par défaut 0), marge à ajouter pour la cote maximale du terrain
        * offset_text : float, optionnel (par défaut 1.5), marge à retrancher pour le texte affiché
    """
    import numpy as np
    import numpy.ma as ma
    import matplotlib.pyplot as plt
    from clawpack.visclaw import gridtools
    from pathlib import Path
    topo_dir = Path(config['directory']['project_directory'])
    try:
        from module_avac import reading_raster_file_features, fn_hv, fn_hu, fn_h, fn_eta, fn_ground
    except ImportError:
        import sys
        sys.path.insert(0, str(Path(topo_dir).parent / "AVAC"))
        from module_avac import reading_raster_file_features, fn_hv, fn_hu, fn_h, fn_eta, fn_ground
    x_début  = x_profil[0]
    y_début  = y_profil[0]
    distance = ((x_profil-x_début)**2+(y_profil-y_début)**2)**0.5
    x1       = distance[-1] 
    x0       = distance[0]
    computation = config['computation']
    NbSim       = computation['nb_simul']
    figs        = []
    L           = x1-x0
    ground_1d = gridtools.grid_output_2d(frames[0], fn_ground, x_profil, y_profil,
                                     levels='all', return_ma=True, method='linear')
    z_coupe_min = ground_1d.min()-offset_min
    z_coupe_max = ground_1d.max()-offset_max
    for i in range(0,NbSim):
        eta_i = gridtools.grid_output_2d(frames[i], fn_eta, x_profil, y_profil, 
                                 levels='all',return_ma=True,method='linear')
        sol_i = gridtools.grid_output_2d(frames[i], fn_ground, x_profil, y_profil, 
                                 levels='all',return_ma=True,method='linear')
        h_i = gridtools.grid_output_2d(frames[i], fn_h, x_profil, y_profil, 
                                 levels='all',return_ma=True,method='linear')
        fig  = plt.figure( figsize=(10,2))
        axes = plt.subplot(1, 1, 1)
        
        axes.set_xlabel(r'$x $',fontsize=14)
        axes.set_ylabel(r'$z $',fontsize=14)
        axes.set_xlim((0,L))
        axes.set_ylim(( z_coupe_min, z_coupe_max))

        text = axes.text(L/2, z_coupe_max-offset_text, '')
        tt = temps_in[i]
        val = f'{tt:.1f}'
        text.set_text(r'$ t = {} $ s '.format(val))

        axes.set_title(" ")
        axes.fill_between(distance, eta_i, sol_i, color='lightskyblue')
        axes.fill_between(distance, sol_i, z_coupe_min,  hatch='//', edgecolor='sienna',facecolor='white')

        axes.plot(distance, ma.masked_where(eta_i==sol_i, eta_i), color = 'deepskyblue')
        #axes.plot(distance, eta_i, 'b')
        figs.append(fig)
        plt.close(fig)
    return figs





def calculate_inflow_rate(contour_dict,config_total,verbosity = False, calculate_avac = False):
    """ 
    Calcule l'énergie cinétique du flux entrant d'énergie cinétique et potentielle. On lit
    les simulations d'AVAC et on calcule les flux le long du contour du lac
    Entrées :
        * contour_dict : dictionnaire donnant les caractéristiques du contour du lac avec
            - mesh_points = tuple (y,x)  
            - vectors     = 2d array (nx, ny) vecteur normal au segment
            - segment_length = array, longueur de chaque segment
            - segment_slice  = slice (indices) de chaque segment dans la liste des points
        * config_total : dictionnaire de configuration
        * verbosity: boolean, afficher les infos issues de clawpack
    Sorties :
        * frame_temps : array contenant les temps de chaque frame
        * flux_énergie_cinétique : array contenant le flux d'Ec par unité de temps
        * flux_énergie_potentielle : array contenant le flux d'Ep par unité de temps
    """
    from pathlib import Path
    from scipy.interpolate import RegularGridInterpolator
    import numpy as np
    from clawpack.geoclaw import fgout_tools
    from clawpack.visclaw import gridtools
    from tqdm import tqdm
    if not verbosity:
        import io, contextlib
    try:
        from module_avac import plot_topo, fn_h, reading_raster_file
    except ImportError:
        import sys
        sys.path.insert(0, str(Path(topo_dir).parent / "AVAC"))
        from module_avac import plot_topo, fn_h, reading_raster_file

    # répertoire
    topo_dir    = Path(config_total['répertoires']['topo_dir'])
    avac_dir    = Path(config_total['répertoires']['avac_dir'])
    waves_dir   = Path(config_total['répertoires']['waves_dir'])

    # avac config
    avac_config        = config_total['avac']
    claw_outdir_name   = avac_config['output']['output_directory']
    avac_fgno          = 1
    avac_output_dir    = avac_dir / claw_outdir_name
    avac_output_format = avac_config['output']['output_format']

    # waves config
    wave_fgno   = 1
    wave_config = config_total['waves']
    lake        = wave_config['lake']
    z_lac       = lake['water_level']
    wave_outdir_name   = wave_config['output']['output_directory']
    wave_output_dir    = waves_dir / wave_outdir_name
    wave_output_format = wave_config['output']['output_format']
    wave_cell_size     = wave_config['computation']['cell_size']

    # création des grilles fixes
    wave_fg_grid    = fgout_tools.FGoutGrid(wave_fgno, wave_output_dir, wave_output_format)
    # lecture des frames du modèle avac
    if verbosity:
        wave_fg_grid.read_fgout_grids_data()
    else:
        with contextlib.redirect_stdout(io.StringIO()):
                wave_fg_grid.read_fgout_grids_data()
                fg = wave_fg_grid.read_frame(1)
    
    # contour du lac
    pts_contour = contour_dict['mesh_points']
    vecteurs    = contour_dict['vectors']
    longueurs   = contour_dict['segment_length']
    seg_slices  = contour_dict['segment_slice']
    # paramètres
    # comme on applique le coefficient d'amortissement, la masse volumique est rho = 1000 !
    rho        = wave_config['rheology']['rho']  
    g          = wave_config['rheology']['gravity'] # gravity
    NbSim_wave = wave_config['computation']['nb_simul']+1
    NbSim_avac = avac_config['computation']['nb_simul']+1
    z_lac      = lake['water_level']

    # grille
    X_grille, Y_grille = fg.X, fg.Y
    dx_grille   = fg.x[1]-fg.x[0]
    dy_grille   = fg.y[1]-fg.y[0]
    pts_grille  = np.column_stack([Y_grille.ravel(), X_grille.ravel()])
    grid_shape  = X_grille.shape

    # masque du lac sur la grille de tout le domaine
    lake_mask_file          = reading_raster_file(topo_dir / wave_config['topo_files']['mask_raster'])
    interpolation_lake_mask = RegularGridInterpolator(
        (lake_mask_file.y, lake_mask_file.x), lake_mask_file.Z, method='nearest',
        bounds_error=False, fill_value=0
        )
    
    # masque interpolé sur la grille du lac
    masque_lac = ~interpolation_lake_mask( (Y_grille, X_grille) ).astype(bool)

    if calculate_avac:
        avac_fg_grid    = fgout_tools.FGoutGrid(avac_fgno, avac_output_dir, avac_output_format)
        if verbosity:
            avac_fg_grid.read_fgout_grids_data()
        else:
            with contextlib.redirect_stdout(io.StringIO()):
                avac_fg_grid.read_fgout_grids_data()
        # calcul par segment pour avac
        avac_flux_volume_liste = []
        avac_frame_temps_liste = []
        avac_volume_lac_liste  = []
        for fgframe in tqdm(range(NbSim_avac)):
            # lecture des frames du modèle avac
            if verbosity:
                avac_frame = avac_fg_grid.read_frame(fgframe+1)
            else:
                with contextlib.redirect_stdout(io.StringIO()):
                    avac_frame = avac_fg_grid.read_frame(fgframe)
            # interpolateur
            axes = (avac_frame.y, avac_frame.x)
            kw   = dict(method='linear', bounds_error=False, fill_value=0.0)
            interp_speed_norm = RegularGridInterpolator(axes, avac_frame.s.T, **kw)
            interp_hu         = RegularGridInterpolator(axes, avac_frame.hu.T, **kw)
            interp_hv         = RegularGridInterpolator(axes, avac_frame.hv.T, **kw)
            interp_h          = RegularGridInterpolator(axes, avac_frame.h.T, **kw)
            interp_B          = RegularGridInterpolator(axes, avac_frame.B.T, **kw)
            # interpolation
            hauteur_contour          = interp_h(pts_contour)
            altitude_contour         = interp_B(pts_contour)
            norme_vitesse_contour    = interp_speed_norm(pts_contour)
            vecteur_hu_contour       = np.array([[hu,hv] for hu, hv in zip(interp_hu(pts_contour), interp_hv(pts_contour))])
            
            hauteur_avalanche_domaine = interp_h(pts_grille).reshape(grid_shape)
            # intégration le long du contour du débit entrant
            # on ne considère que le flux entrant, donc on élimine les valeurs < 0
            flux_volume_seg   = np.array([max(0,-((vecteur_hu_contour[s]@vecteurs[n])).mean()*longueurs[n]) 
                                        for s, n in zip(seg_slices, range(len(vecteurs)))])
            # volume de neige dans le domaine
            volume_lac = hauteur_avalanche_domaine
            # volume de neige dans le lac
            volume_lac = np.where(masque_lac[np.newaxis], volume_lac, 0.0).sum()*dx_grille*dy_grille

            avac_flux_volume_liste.append(flux_volume_seg.sum())
            avac_volume_lac_liste.append(volume_lac)
            avac_frame_temps_liste.append(avac_frame.t)         
        avac_frame_temps = np.array(avac_frame_temps_liste)
        avac_volume_lac  = np.array(avac_volume_lac_liste)
        avac_flux_volume  = np.array(avac_flux_volume_liste)         

    # calcul par segment pour wave
    wave_flux_volume_eau_liste          = []
    wave_volume_eau_lac_liste           = []
    wave_flux_énergie_cinétique_liste   = []
    wave_flux_énergie_potentielle_liste = []
    wave_frame_temps_liste              = []
    for fgframe in tqdm(range(NbSim_wave)):
        # lecture des frames du modèle avac
        if verbosity:
            wave_frame = wave_fg_grid.read_frame(fgframe+1)
        else:
            with contextlib.redirect_stdout(io.StringIO()):
                wave_frame = wave_fg_grid.read_frame(fgframe+1)
        # interpolateur
        axes = (wave_frame.y, wave_frame.x)
        kw   = dict(method='linear', bounds_error=False, fill_value=0.0)
        interp_speed_norm = RegularGridInterpolator(axes, wave_frame.s.T, **kw)
        interp_hu         = RegularGridInterpolator(axes, wave_frame.hu.T, **kw)
        interp_hv         = RegularGridInterpolator(axes, wave_frame.hv.T, **kw)
        interp_h          = RegularGridInterpolator(axes, wave_frame.h.T, **kw)
        interp_B          = RegularGridInterpolator(axes, wave_frame.B.T, **kw)
        # interpolation
        hauteur_contour          = interp_h(pts_contour)
        altitude_contour         = interp_B(pts_contour)
        norme_vitesse_contour    = interp_speed_norm(pts_contour)
        # calcul des flux
        # on ne considère que le flux entrant, donc on élimine les valeurs < 0
        vecteur_hu_contour       = np.array([[hu,hv] for hu, hv in zip(interp_hu(pts_contour), interp_hv(pts_contour))])
        flux_énergie_cinétique_seg = np.array([max(0,-((vecteur_hu_contour[s]@vecteurs[n])*norme_vitesse_contour[s]**2).mean()*longueurs[n]) 
                                    for s, n in zip(seg_slices, range(len(vecteurs)))])
        flux_énergie_potentielle_seg = np.array([max(0,-((vecteur_hu_contour[s]@vecteurs[n])*
                                                        (hauteur_contour[s]+altitude_contour[s]-z_lac)).mean()*longueurs[n]) 
                                    for s, n in zip(seg_slices, range(len(vecteurs)))])
        flux_volume_seg   = np.array([max(0,-((vecteur_hu_contour[s]@vecteurs[n])).mean()*longueurs[n]) 
                                    for s, n in zip(seg_slices, range(len(vecteurs)))])
        # intégration par sommation des flux sur chaque segment
        flux_énergie_cinétique   = 0.5*rho*flux_énergie_cinétique_seg.sum()
        flux_énergie_potentielle = 0.5*rho*g*flux_énergie_potentielle_seg.sum()
        flux_volume              = flux_volume_seg.sum()
        # hauteur d'eau dans tout le domaine de calcul
        hauteur_eau_domaine = interp_h(pts_grille).reshape(grid_shape)
        # volume de neige dans le lac par application du masque
        volume_lac = np.where(masque_lac[np.newaxis], hauteur_eau_domaine, 0.0).sum()*dx_grille*dy_grille
        # ajout aux listes
        wave_flux_énergie_cinétique_liste.append(flux_énergie_cinétique)
        wave_flux_énergie_potentielle_liste.append(flux_énergie_potentielle)
        wave_flux_volume_eau_liste.append(flux_volume)
        wave_volume_eau_lac_liste.append(volume_lac)
        wave_frame_temps_liste.append(wave_frame.t)
    
    wave_flux_énergie_cinétique   = np.array(wave_flux_énergie_cinétique_liste)
    wave_flux_énergie_potentielle = np.array(wave_flux_énergie_potentielle_liste)
    wave_frame_temps              = np.array(wave_frame_temps_liste)
    wave_flux_volume              = np.array(wave_flux_volume_eau_liste)
    wave_volume_lac               = np.array(wave_volume_eau_lac_liste)
    
    if calculate_avac:
        return avac_frame_temps, wave_frame_temps, avac_flux_volume, avac_volume_lac, wave_flux_énergie_cinétique, \
            wave_flux_énergie_potentielle, wave_flux_volume, wave_volume_lac

    else:
        return wave_frame_temps, wave_flux_énergie_cinétique, wave_flux_énergie_potentielle, wave_flux_volume, wave_volume_lac


def calculate_inflow(contour_dict,config_total,verbosity = False):
    """ 
    Calcule l'énergie cinétique du flux entrant d'énergie cinétique et potentielle. On lit
    les simulations d'AVAC et on calcule les flux le long du contour du lac
    Entrées :
        * contour_dict : dictionnaire donnant les caractéristiques du contour du lac avec
            - mesh_points = tuple (y,x)  
            - vectors     = 2d array (nx, ny) vecteur normal au segment
            - segment_length = array, longueur de chaque segment
            - segment_slice  = slice (indices) de chaque segment dans la liste des points
        * config_total : dictionnaire de configuration
        * verbosity: boolean, afficher les infos issues de clawpack
    Sorties :
        * frame_temps : array contenant les temps de chaque frame
        * flux_énergie_cinétique : array contenant le flux d'Ec par unité de temps
        * flux_énergie_potentielle : array contenant le flux d'Ep par unité de temps
    """
    from pathlib import Path
    from scipy.interpolate import RegularGridInterpolator
    import numpy as np
    from clawpack.geoclaw import fgout_tools
    from clawpack.visclaw import gridtools
    from tqdm import tqdm
    if not verbosity:
        import io, contextlib
    try:
        from module_avac import plot_topo, fn_h, reading_raster_file
    except ImportError:
        import sys
        sys.path.insert(0, str(Path(topo_dir).parent / "AVAC"))
        from module_avac import plot_topo, fn_h, reading_raster_file

    # répertoire
    topo_dir    = Path(config_total['répertoires']['topo_dir'])
    avac_dir    = Path(config_total['répertoires']['avac_dir'])
    waves_dir   = Path(config_total['répertoires']['waves_dir'])

    # avac config
    avac_config        = config_total['avac']
    claw_outdir_name   = avac_config['output']['output_directory']
    avac_fgno          = 1
    avac_output_dir    = avac_dir / claw_outdir_name
    avac_output_format = avac_config['output']['output_format']

    # waves config
    wave_fgno   = 1
    wave_config = config_total['waves']
    lake        = wave_config['lake']
    #z_lac       = lake['water_level']
    wave_outdir_name   = wave_config['output']['output_directory']
    wave_output_dir    = waves_dir / wave_outdir_name
    wave_output_format = wave_config['output']['output_format']

    # création des grilles fixes
    wave_fg_grid    = fgout_tools.FGoutGrid(wave_fgno, wave_output_dir, wave_output_format)
    avac_fg_grid    = fgout_tools.FGoutGrid(avac_fgno, avac_output_dir, avac_output_format)
    if verbosity:
        avac_fg_grid.read_fgout_grids_data()
        wave_fg_grid.read_fgout_grids_data()
    else:
        with contextlib.redirect_stdout(io.StringIO()):
            avac_fg_grid.read_fgout_grids_data()
            wave_fg_grid.read_fgout_grids_data()
    
    # contour du lac
    pts_contour = contour_dict['mesh_points']
    vecteurs    = contour_dict['vectors']
    longueurs   = contour_dict['segment_length']
    seg_slices  = contour_dict['segment_slice']
    # paramètres
    # comme on applique le coefficient d'amortissement, la masse volumique est rho = 1000 !
    #rho        = 1000  
    #g          = 9.81 # gravity
    NbSim_wave = wave_config['computation']['nb_simul']
    NbSim_avac = avac_config['computation']['nb_simul']
    #z_lac      = lake['water_level']

    # extension du lac
    xmin, xmax = lake['xmin'], lake['xmax']
    ymin, ymax = lake['ymin'], lake['ymax']
    
    # grille d'interpolation du lac
    # nb_grille  = wave_config['computation']['nb_grid']
    # x_grille   = np.linspace(xmin,xmax,nb_grille)
    # y_grille   = np.linspace(ymin,ymax,nb_grille)
    # dx_grille  = (xmax-xmin)/(nb_grille-1)
    # dy_grille  = (ymax-ymin)/(nb_grille-1)
    # X_grille, Y_grille = np.meshgrid(x_grille,y_grille)
    # pts_grille  = np.column_stack([Y_grille.ravel(), X_grille.ravel()])
    # grid_shape  = X_grille.shape

    with contextlib.redirect_stdout(io.StringIO()):
                fg = wave_fg_grid.read_frame(1)
    x_grille = fg.x
    y_grille = fg.y
    dx_grille = fg.x[1]-fg.x[0]
    dy_grille = fg.y[1]-fg.y[0]
    X_grille, Y_grille = fg.X, fg.Y
    pts_grille  = np.column_stack([Y_grille.ravel(), X_grille.ravel()])
    grid_shape  = X_grille.shape
    

    # masque du lac sur la grille de tout le domaine
    lake_mask_file          = reading_raster_file(topo_dir / wave_config['topo_files']['mask_raster'])
    interpolation_lake_mask = RegularGridInterpolator(
        (lake_mask_file.y, lake_mask_file.x), lake_mask_file.Z, method='nearest',
        bounds_error=False, fill_value=0
        )
    
    # masque interpolé sur la grille du lac
    masque_lac = ~interpolation_lake_mask( (Y_grille, X_grille) ).astype(bool)

    # calcul par segment pour avac
    flux_volume           = []
    avac_frame_temps_list = []
    volume_lac_list       = []
    for fgframe in tqdm(range(NbSim_avac)):
        # lecture des frames du modèle avac
        if verbosity:
            avac_frame = avac_fg_grid.read_frame(fgframe+1)
        else:
            with contextlib.redirect_stdout(io.StringIO()):
                avac_frame = avac_fg_grid.read_frame(fgframe+1)
        # interpolateur
        axes = (avac_frame.y, avac_frame.x)
        kw   = dict(method='linear', bounds_error=False, fill_value=0.0)
        interp_speed_norm = RegularGridInterpolator(axes, avac_frame.s.T, **kw)
        interp_hu         = RegularGridInterpolator(axes, avac_frame.hu.T, **kw)
        interp_hv         = RegularGridInterpolator(axes, avac_frame.hv.T, **kw)
        interp_h          = RegularGridInterpolator(axes, avac_frame.h.T, **kw)
        interp_B          = RegularGridInterpolator(axes, avac_frame.B.T, **kw)
        # interpolation
        # hauteur_contour          = interp_h(pts_contour)
        # altitude_contour         = interp_B(pts_contour)
        # norme_vitesse_contour    = interp_speed_norm(pts_contour)
        vecteur_hu_contour       = np.array([[hu,hv] for hu, hv in zip(interp_hu(pts_contour), interp_hv(pts_contour))])
        
        hauteur_avalanche_domaine = interp_h(pts_grille).reshape(grid_shape)
        # intégration le long du contour du débit entrant
        # on ne considère que le flux entrant, donc on élimine les valeurs < 0
        flux_volume_seg   = np.array([max(0,-((vecteur_hu_contour[s]@vecteurs[n])).mean()*longueurs[n]) 
                                    for s, n in zip(seg_slices, range(len(vecteurs)))])
        # volume de neige dans le domaine
        volume_lac = hauteur_avalanche_domaine
        # volume de neige dans le lac
        volume_lac = np.where(masque_lac[np.newaxis], volume_lac, 0.0).sum()*dx_grille*dy_grille

        flux_volume.append(flux_volume_seg.sum())
        volume_lac_list.append(volume_lac)
        avac_frame_temps_list.append(avac_frame.t)

    # calcul par segment pour wave
    flux_volume_eau       = []
    volume_eau_lac        = []
    wave_frame_temps_list = []
    for fgframe in tqdm(range(NbSim_wave)):
        # lecture des frames du modèle avac
        if verbosity:
            wave_frame = wave_fg_grid.read_frame(fgframe+1)
        else:
            with contextlib.redirect_stdout(io.StringIO()):
                wave_frame = wave_fg_grid.read_frame(fgframe+1)
        # interpolateur
        axes = (wave_frame.y, wave_frame.x)
        kw   = dict(method='linear', bounds_error=False, fill_value=0.0)
        interp_speed_norm = RegularGridInterpolator(axes, wave_frame.s.T, **kw)
        interp_hu         = RegularGridInterpolator(axes, wave_frame.hu.T, **kw)
        interp_hv         = RegularGridInterpolator(axes, wave_frame.hv.T, **kw)
        interp_h          = RegularGridInterpolator(axes, wave_frame.h.T, **kw)
        interp_B          = RegularGridInterpolator(axes, wave_frame.B.T, **kw)
        # interpolation
        #hauteur_contour          = interp_h(pts_contour)
        #altitude_contour         = interp_B(pts_contour)
        #norme_vitesse_contour    = interp_speed_norm(pts_contour)
        vecteur_hu_contour       = np.array([[hu,hv] for hu, hv in zip(interp_hu(pts_contour), interp_hv(pts_contour))])
        
        hauteur_eau_domaine = interp_h(pts_grille).reshape(grid_shape)
        # intégration le long du contour du débit entrant
        # on ne considère que le flux entrant, donc on élimine les valeurs < 0
        flux_volume_seg   = np.array([max(0,-((vecteur_hu_contour[s]@vecteurs[n])).mean()*longueurs[n]) 
                                    for s, n in zip(seg_slices, range(len(vecteurs)))])
        # volume de neige dans le domaine
        volume_lac = hauteur_eau_domaine
        # volume de neige dans le lac
        volume_lac = np.where(masque_lac[np.newaxis], volume_lac, 0.0).sum()*dx_grille*dy_grille

        flux_volume_eau.append(flux_volume_seg.sum())
        volume_eau_lac.append(volume_lac)
        wave_frame_temps_list.append(wave_frame.t)
    
    avac_frame_temps = np.array(avac_frame_temps_list)
    wave_frame_temps = np.array(wave_frame_temps_list)
    flux_volume = np.array(flux_volume)
    flux_volume_eau = np.array(flux_volume_eau)
    volume_lac  = np.array(volume_lac_list)
    volume_lac_eau  = np.array(volume_eau_lac)
    return avac_frame_temps, wave_frame_temps, flux_volume, flux_volume_eau, volume_lac, volume_lac_eau, masque_lac

def create_lake_contour_mesh(config_total,dx_fgout):
    """
    Create the lake contour's meshin:
    Input:
        * config_total: dictionary
        * dx_fgout: float
    Output:
        * pts_all, 
        * longueurs, 
        * vecteurs, 
        * seg_slices
    """
    
    from pathlib import Path
    import geopandas as gp
    import numpy as np
    topo_dir   = Path(config_total['répertoires']['topo_dir'])
    topo_files = config_total['waves']['topo_files']
    # --- polyligne du rivage ---
    lake_mask_gdf  = gp.read_file(topo_dir / topo_files['mask_shp']) # importation du masque config['topo_files']['mask_shp']
    lake_poly      = lake_mask_gdf.geometry.iloc[0]
    xs_raw, ys_raw = np.array(lake_poly.exterior.coords.xy[0]), np.array(lake_poly.exterior.coords.xy[1])

    # Supprimer les po  ints redondants (distance < eps entre deux points consécutifs)
    eps         = 1e-6  # tolérance en mètres
    mask_unique = np.concatenate(([True], np.hypot(np.diff(xs_raw), np.diff(ys_raw)) > eps))
    xs          = xs_raw[mask_unique][:-1] # il faut enlever le dernier élément car lake_mask_gdf.geometry retourne un anneau fermé
    ys          = ys_raw[mask_unique][:-1]
    # définition des segments
    dx_seg = np.roll(xs, -1) - xs   # xs[1]-xs[0], ..., xs[0]-xs[-1]  (bouclage)
    dy_seg = np.roll(ys, -1) - ys
    dl_seg = np.hypot(dx_seg, dy_seg)
    nx_seg = -dy_seg / dl_seg       # normale au segment orientée de l'intérieur vers l'extérieur
    ny_seg =  dx_seg / dl_seg
    xm     = 0.5*(xs + np.roll(xs, -1))  # points milieux 
    ym     = 0.5*(ys + np.roll(ys, -1))
    pts_m  = (xm, ym) # milieux
    pts_s  = (xs, ys) # sommets
    # détermination du nombre de points par segment pour être cohérent avec la maille de la grille
    num_pts    = np.maximum(2, (dl_seg / dx_fgout).astype(int))  # ≥ 2 points par segment

    # Construction vectorisée avec segments de longueurs variables
    pts_list   = []  # maillage du contour
    seg_slices = []  # pour retrouver quels points appartiennent à quel segment
    idx        = 0   # indice pour suivre les points
    vecteurs   = []  # vecteurs normaux à chaque segment
    for i, n in enumerate(num_pts):
        t  = np.linspace(0, 1, n)
        xp = xs[i] + t * dx_seg[i]
        yp = ys[i] + t * dy_seg[i]
        pts_list.append(np.column_stack((yp, xp)))
        seg_slices.append(slice(idx, idx + n))
        idx += n
        vecteurs.append([nx_seg[i],ny_seg[i]])

    pts_all   = np.vstack(pts_list)
    longueurs = np.array([np.linalg.norm(np.diff(seg, axis=0), axis=1).sum() for seg in pts_list])
    vecteurs  = np.array(vecteurs)
    return pts_all, longueurs, vecteurs, seg_slices, pts_m, pts_s  


def create_plot_lake_contour_meshing(config_total,topo_file = None, frame_test = None, verbosity = False):
    """
    Détermine le maillage du cont race le contour et 
    Entrées :
        * config_total : dictionnaire de la configuration
        * topo_file : fichier topo, si le nom est renseigné la fonction trace la carte
        * frame_test : entier, numéro de la frame qui sert de test pour tracer l'emprise de l'avalanche
        * verbosity : afficher ou non les infos venues de clawpack
    Sortie :
        * dictionnaire des caractéristiques du contour :
            - 'vectors'         : vecteurs normaux aux segments,
            - 'mesh_points'     : points du maillage,
            - 'segment_length'  : longueurs des segments,
            - 'segment_slice'   : indices des segments,
            - 'segment_center'  : milieux des segments, 
            - 'contour_vertices': extrémités des segments}
    """
    from pathlib import Path
    import numpy as np
    import numpy.ma as ma
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap
    import geopandas as gp
    from clawpack.geoclaw import fgout_tools
    from clawpack.visclaw import gridtools
    from clawpack.pyclaw.solution import Solution
    from clawpack.pyclaw import solution as solution
    from clawpack.visclaw.plottools import pcolorcells
    if not verbosity:
        import io, contextlib
    try:
        from module_avac import plot_topo, fn_h
    except ImportError:
        import sys
        sys.path.insert(0, str(Path(topo_dir).parent / "AVAC"))
        from module_avac import plot_topo, fn_h
    
    topo_dir    = Path(config_total['répertoires']['topo_dir'])
    # avac config
    avac_dir    = Path(config_total['répertoires']['avac_dir'])
    avac_config = config_total['avac']
    # waves config
    lake               = config_total['waves']['lake']
    waves_outdir_names = config_total['waves']['output']['output_directory']
    waves_dir          = Path(config_total['répertoires']['waves_dir'])
    waves_output_dir   = waves_dir / waves_outdir_names
    topo_files         = config_total['waves']['topo_files']
    # On va lire les fichiers fgout générées par AVAC
    claw_outdir_name = config_total['avac']['output']['output_directory']
    fgno             = 1
    outdir           = avac_dir / claw_outdir_name
    output_format = avac_config['output']['output_format']
    fgout_grid    = fgout_tools.FGoutGrid(fgno, outdir, output_format)
    if verbosity:
        fgout_grid.read_fgout_grids_data()
    else:
        with contextlib.redirect_stdout(io.StringIO()):
            fgout_grid.read_fgout_grids_data()

    if frame_test == None:
        NbSim   = config_total['waves']['computation']['nb_simul']+1
        fgframe = int(NbSim/2)
    else:
        fgframe = frame_test
    if verbosity:
            fgout = fgout_grid.read_frame(fgframe)
    else:
            # si on ne veut pas afficher les messages de clawpack
            # redirect_stdout redirige les print() vers un buffer mémoire qui est simplement abandonné
            with contextlib.redirect_stdout(io.StringIO()):
                fgout = fgout_grid.read_frame(fgframe)
    
    dx_fgout  = fgout.x[1] - fgout.x[0]          # résolution fgout
    
    pts_all, longueurs, vecteurs, seg_slices, pts_m, pts_s = create_lake_contour_mesh(config_total,dx_fgout)
    
    contour_dict = {'vectors':vecteurs,'mesh_points':pts_all,
                    'segment_length':longueurs,'segment_slice':seg_slices,'segment_center':pts_m, 'contour_vertices':pts_s}

    ##########################################
    # Tracé de la carte si cela est souhaité #
    ##########################################
    if topo_file is None:
        if verbosity:
            print("pas de tracé de la carte")
    else:
        # lecture état initial du lac
        output_format      = config_total['waves']['output']['output_format']
        sol = solution.Solution(0, path = waves_output_dir, file_format = output_format)
        
        # extension du domaine
        xmin, xmax = lake['xmin'], lake['xmax']
        ymin, ymax = lake['ymin'], lake['ymax']
        print(f"Visualisation du domaine de calcul et du contour du lac avec emprise de l'avalanche au temps {fgout.t:.2f} s.")

        xs, ys     = pts_s
        xm, ym     = pts_m
        nx_seg, ny_seg = vecteurs[:,0], vecteurs[:,1]
        # grille
        nb_grille = config_total['waves']['computation']['nb_grid']
        x         = np.linspace(xmin,xmax,nb_grille)
        y         = np.linspace(ymin,ymax,nb_grille)
        X_grille, Y_grille = np.meshgrid(x,y)
        hauteur_0 = gridtools.grid_output_2d(sol, fn_h, X_grille, Y_grille, 
                                                levels='all',return_ma=True)
        dx = (xmax-xmin)/nb_grille
        dy = (ymax-ymin)/nb_grille
        # paramètre de la carte
        minor_step = config_total['waves']['output']['carto_layout']['minor_label_step']
        margin     = config_total['waves']['output']['carto_layout']['margin']  # mètres
        fig, ax, x0, y0 = plot_topo(topo_file, step = minor_step)
        # limites du domaine comme rectangle rouge
        ax.add_patch(plt.Rectangle((xmin-x0, ymin-y0),
                                    width  = xmax-xmin,
                                    height = ymax-ymin,
                                    ls="-", lw=1, ec="red", fc="none"))

        # Zoom sur le lac avec une marge
        ax.set_xlim(xmin - x0 - margin, lake['xmax'] - x0 + margin)
        ax.set_ylim(ymin - y0 - margin, ymax - y0 + margin)
        ε = config_total['waves']['computation']['dry_limit']

        eta_masque = ma.masked_where(hauteur_0 < ε, hauteur_0)
        cmap_flat = ListedColormap([
                                    (0,   0,   0,   0  ), # transparent
                                    (0.2, 0.4, 1.0, 0.95) ]) # bleu])   
        ax.imshow((hauteur_0 >= ε).astype(float), origin='lower',
                extent=[xmin-x0, xmax-x0, ymin-y0, ymax-y0],
                cmap=cmap_flat, vmin=0, vmax=1)

        # tracé du masque
        lake_mask_gdf  = gp.read_file(topo_dir / topo_files['mask_shp'])
        lake_mask_gdf.geometry.translate(-x0, -y0).plot(
            ax=ax, facecolor='none', edgecolor='blue', linewidth=1.5 
        )
        ax.scatter(pts_all[:,1]-x0,pts_all[:,0]-y0,color = 'green', marker = '*',alpha = .5)
        ax.scatter(xm-x0,ym-y0)
        ax.scatter(xs-x0,ys-y0,color = 'red', marker = '+')
        scale_arrow = 20
        for i in range(len(xm)):
            ax.arrow(xm[i]-x0,ym[i]-y0,scale_arrow*nx_seg[i],scale_arrow*ny_seg[i],width = 1)
            ax.text(xm[i]+1.2*scale_arrow*nx_seg[i]-x0,ym[i]+1.2*scale_arrow*ny_seg[i]-y0,str(i))
        pc1 = pcolorcells(fgout.X-x0, fgout.Y-y0, ma.masked_where(fgout.h == 0, fgout.s), cmap='coolwarm', ax=ax,alpha=0.5)
        cb1 = plt.colorbar(pc1, extend='max', shrink=0.7)

    # retourne le dictionnaire du contour
    return contour_dict



def calculate_overflow_rate(config_total,verbosity = False):
    """ 
    Calcule l'hydrogramme de surverse. On lit
    les simulations de Waves et on calcule les flux de volume (débit) le long du contour du lac
    Entrées :

        * config_total : dictionnaire de configuration
        * verbosity : afficher ou non les infos venues de clawpack
    Sorties :
        * frame_temps : array contenant les temps de chaque frame
        * flux_volume : array contenant le flux de volume par unité de temps
    """
    from pathlib import Path
    from scipy.interpolate import RegularGridInterpolator
    import numpy as np
    from clawpack.geoclaw import fgout_tools
    from clawpack.visclaw import gridtools
    if not verbosity:
        import io, contextlib
    try:
        from module_avac import plot_topo, fn_h
    except ImportError:
        import sys
        sys.path.insert(0, str(Path(topo_dir).parent / "AVAC"))
        from module_avac import plot_topo, fn_h
    
    topo_dir    = Path(config_total['répertoires']['topo_dir'])
    # information sur le contour
    contour_dict = create_plot_lake_contour_meshing(config_total,topo_file = None, verbosity = verbosity)
    # On va lire les fichiers fgout générées par Waves
    fgno          = 1
    outdir        = config_total['waves']['output']['output_directory']
    output_format = config_total['waves']['output']['output_format']
    fgout_grid    = fgout_tools.FGoutGrid(fgno, outdir, output_format)
    if verbosity:
        fgout_grid.read_fgout_grids_data()
    else:
        with contextlib.redirect_stdout(io.StringIO()):
            fgout_grid.read_fgout_grids_data()
    # contour du lac
    # contour_dict : dictionnaire donnant les caractéristiques du contour du lac avec
    #        - mesh_points = tuple (y,x)  
    #        - vectors     = 2d array (nx, ny) vecteur normal au segment
    #        - segment_length = array, longueur de chaque segment
    #        - segment_slice  = slice (indices) de chaque segment dans la liste des points
    pts_all    = contour_dict['mesh_points']
    vecteurs   = contour_dict['vectors']
    longueurs  = contour_dict['segment_length']
    seg_slices = contour_dict['segment_slice']
    # paramètres
    # rho        = config_total['waves']['rheology']['rho']
    NbSim      = config_total['waves']['computation']['nb_simul']+1
    # z_lac      = config_total['waves']['lake']['water_level']
    # calcul par segment
    débit_list       = []
    frame_temps_list = []
    for fgframe in range(1,NbSim):
        if verbosity:
            fgout = fgout_grid.read_frame(fgframe)
        else:
            with contextlib.redirect_stdout(io.StringIO()):
                fgout = fgout_grid.read_frame(fgframe)
        
        interp_hu = RegularGridInterpolator(
            (fgout.y, fgout.x), fgout.hu.T, method='linear', bounds_error=False, fill_value=np.nan
        )
        interp_hv = RegularGridInterpolator(
            (fgout.y, fgout.x), fgout.hv.T, method='linear', bounds_error=False, fill_value=np.nan
        )

        vecteur_hu_profil = np.array([[hu,hv] for hu,hv in zip(interp_hu(pts_all), interp_hv(pts_all))])
        
        # intégration le long du contour du lac
        # signe - car la normale est orientée
        flux_volume_seg   = np.array([-((vecteur_hu_profil[s]@vecteurs[n])).mean()*longueurs[n]
                                    for s, n in zip(seg_slices, range(len(vecteurs)))])
        
        débit_list.append(flux_volume_seg.sum())
        frame_temps_list.append(fgout.t)
    frame_temps = np.array(frame_temps_list)
    flux_volume= np.array(débit_list)

    return frame_temps, flux_volume



def plot_four_gauge_profiles(config_total, xcenter, ycenter, bound  = 60):
    """ 
    Trace les profils de terrain (bathyémtrie)
    Entrées :
        * config : dictionnaire des paramètres
        *  xcenter, ycenter point de départ
        * bound : float, on cherche trace des lignes entre les jauges et le centre (xcenter, ycenter) avec une étendue de +/- bound
    """
    #from shapely import LineString, intersection
    import matplotlib.pyplot as plt
    from pathlib import Path
    import numpy as np
    from clawpack.geoclaw import fgout_tools
    from clawpack.visclaw import gridtools
    from clawpack.pyclaw.solution import Solution
    from clawpack.pyclaw import solution as solution
    try:
        from module_avac import fn_ground
    except ImportError:
        import sys
        sys.path.insert(0, str(Path(topo_dir).parent / "AVAC"))
        from module_avac import fn_ground

    def Enlever_masque(fd):
        fdd = []
        for m in range(len(fd)):
            if type(fd[m][1]) != np.ma.core.MaskedConstant:
                fdd.append(fd[m])
        return fdd

    def triangle(axes,x_t, z, taille, rapport):
        cote = taille/np.tan(60/180*np.pi)*rapport
        dh   = taille /3
        lw   = 0.5
        axes.plot([x_t, x_t+cote ], [z, z+taille], color='b', linestyle='-', linewidth=lw)
        axes.plot([x_t, x_t-cote ], [z, z+taille], color='b', linestyle='-', linewidth=lw)
        axes.plot([x_t+cote, x_t-cote], [z+taille, z+taille], color='b', linestyle='-', linewidth=lw)
        axes.plot([x_t+cote, x_t-cote], [z-dh, z-dh], color='b', linestyle='-', linewidth=lw)
        axes.plot([x_t+cote/2, x_t-cote/2], [z-2*dh, z-2*dh], color='b', linestyle='-', linewidth=lw)

    lake   = config_total['waves']['lake']
    gauges = config_total['waves']['gauges']
    z_lac  = lake['water_level']
    waves_outdir_names = config_total['waves']['output']['output_directory']
    waves_dir          = Path(config_total['répertoires']['waves_dir'])
    waves_output_dir   = waves_dir / waves_outdir_names
    output_format      = config_total['waves']['output']['output_format']

    # position des jauges
    if not gauges['gauge_recording']:
        print("Pas de jauges !")
    
    else:
        positions_jauges = []
        print(f"Il y a {len(gauges)-1} jauges.")
        for k in range(len(gauges)-1):
                    gaugeno = str(k)
                    x = gauges[gaugeno]['x']
                    y = gauges[gaugeno]['y']
                    print(f"x = {x} y = {y}")
                    positions_jauges.append([x,y])
        positions_jauges = np.array(positions_jauges)    
        
        # extension du domaine
        xmin, xmax = lake['xmin'], lake['xmax']
        ymin, ymax = lake['ymin'], lake['ymax']
        
        # grille
        nb_grille = config_total['waves']['computation']['nb_grid']
        x         = np.linspace(xmin,xmax,nb_grille)
        y         = np.linspace(ymin,ymax,nb_grille)
        X_grille, Y_grille = np.meshgrid(x,y)
        
        # surface libre
        #surface_libre_simple = LineString([(-bound, z_lac), (bound, z_lac)])
        L_p                  = bound # longueur profil

        
        #étiquette = ['(a)','(b)','(c)','(d)']
        étiquette = ['(1)','(2)','(3)','(4)']

        # état initial du lac
        sol = solution.Solution(0, path = waves_output_dir, file_format = output_format)

        
    def dessiner_profil(k, ax):
        xj = positions_jauges[k][0]
        yj = positions_jauges[k][1]
        vec_directeur = [xj-xcenter, yj-ycenter]
        vec_directeur = vec_directeur / np.linalg.norm(vec_directeur)

        
        x_0 = xj+vec_directeur[0]*L_p
        x_1 = xj-vec_directeur[0]*L_p
        y_0 = yj+vec_directeur[1]*L_p
        y_1 = yj-vec_directeur[1]*L_p

        nb_points = 40
        x_profil = np.linspace(x_0, x_1, nb_points)
        y_profil = np.linspace(y_0, y_1, nb_points)
        distance = np.array([np.dot([x_profil[i]-xj, y_profil[i]-yj], vec_directeur) for i in range(nb_points)])
        z_profil = gridtools.grid_output_2d(sol, fn_ground, x_profil, y_profil, levels='all', return_ma=True)

        # Segment mouille le plus bas (= lac) parmi tous les segments sous z_lac
        z_arr = np.ma.filled(z_profil, z_lac + 1)   # valeurs masquees -> sec
        wet = z_arr <= z_lac
        segments, i = [], 0
        while i < len(wet):
            if wet[i]:
                j = i
                while j < len(wet) and wet[j]:
                    j += 1
                segments.append((i, j - 1))
                i = j
            else:
                i += 1
        if not segments:
            return
        i0, i1 = min(segments, key=lambda s: z_arr[s[0]:s[1]+1].min())

        # Rives exactes par interpolation lineaire
        x_right = (distance[i0-1] + (z_lac - z_arr[i0-1]) / (z_arr[i0] - z_arr[i0-1])
                * (distance[i0] - distance[i0-1])) if i0 > 0 else distance[i0]
        x_left  = (distance[i1+1] + (z_lac - z_arr[i1+1]) / (z_arr[i1] - z_arr[i1+1])
                * (distance[i1] - distance[i1+1])) if i1 < len(wet)-1 else distance[i1]

        mask = np.zeros(len(distance), dtype=bool)
        mask[i0:i1+1] = True

        x_t = -0.8*bound # position du triangle

        ax.text(0.9, 0.1, étiquette[k],
                backgroundcolor = 'white',
            horizontalalignment='center',
            verticalalignment='center',
            transform=ax.transAxes)
        ax.plot(distance, z_profil, color='sienna')
        ax.fill_between(distance, z_lac, z_profil,
                        where=mask, color='lightskyblue', interpolate=True)
        ax.plot([x_left, x_right], [z_lac, z_lac], color='blue', linestyle='-', linewidth=1)
        triangle(ax, x_t, z_lac, 0.8, 4)
        ax.fill_between(distance, z_profil, z_profil.min(), hatch='OO', edgecolor='peachpuff', facecolor='white')

    # Figure récapitulative
    fig, ((ax1, ax2 ),(ax3, ax4 )) = plt.subplots(2,2)
    fig.set_figheight(6)
    fig.set_figwidth(12)
    axes = (ax1, ax2, ax3, ax4 )
    for i, ax in zip (range(4),axes):
        dessiner_profil(i,ax)
    return fig, (ax1, ax2, ax3, ax4 )

# fonction de vérification

def plot_avalanche(target_time,config_total,topo_file, verbosity = False, cmap = 'gist_rainbow'):
    """
    Détermine le maillage du cont race le contour et 
    Entrées :
        * config_total : dictionnaire de la configuration
        * topo_file : fichier topo, si le nom est renseigné la fonction trace la carte
        * frame_test : entier, numéro de la frame qui sert de test pour tracer l'emprise de l'avalanche
        * verbosity : afficher ou non les infos venues de clawpack
    Sortie :
        * fig
    """
    # Importation des paquets
    from pathlib import Path
    import numpy as np
    import numpy.ma as ma
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap
    import geopandas as gp
    from tqdm import tqdm  
    from scipy.interpolate import RegularGridInterpolator
    from clawpack.geoclaw import fgout_tools
    from clawpack.visclaw import gridtools
    from clawpack.pyclaw.solution import Solution
    from clawpack.pyclaw import solution as solution
    from clawpack.visclaw.plottools import pcolorcells
    if not verbosity:
        import io, contextlib
    try:
        from module_avac import plot_topo, fn_h, reading_raster_file
    except ImportError:
        import sys
        sys.path.insert(0, str(Path(topo_dir).parent / "AVAC"))
        from module_avac import plot_topo, fn_h, reading_raster_file
    from module_waves import create_lake_contour_mesh


    # répertoire
    topo_dir    = Path(config_total['répertoires']['topo_dir'])
    avac_dir    = Path(config_total['répertoires']['avac_dir'])
    waves_dir   = Path(config_total['répertoires']['waves_dir'])

    # avac config
    avac_config        = config_total['avac']
    claw_outdir_name   = avac_config['output']['output_directory']
    avac_fgno          = 1
    avac_output_dir    = avac_dir / claw_outdir_name
    avac_output_format = avac_config['output']['output_format']

    # waves config
    wave_fgno   = 1
    wave_config = config_total['waves']
    lake        = wave_config['lake']
    z_lac       = lake['water_level']
    wave_outdir_name   = wave_config['output']['output_directory']
    wave_output_dir    = waves_dir / wave_outdir_name
    wave_output_format = wave_config['output']['output_format']

    # création des grilles fixes
    wave_fg_grid    = fgout_tools.FGoutGrid(wave_fgno, wave_output_dir, wave_output_format)
    avac_fg_grid    = fgout_tools.FGoutGrid(avac_fgno, avac_output_dir, avac_output_format)
    if verbosity:
        avac_fg_grid.read_fgout_grids_data()
        wave_fg_grid.read_fgout_grids_data()
    else:
        with contextlib.redirect_stdout(io.StringIO()):
            avac_fg_grid.read_fgout_grids_data()
            wave_fg_grid.read_fgout_grids_data()
    
    # contour du lac
    dx         = wave_config['computation']['cell_size']
    pts_all, longueurs, vecteurs, seg_slices, pts_m, pts_s = create_lake_contour_mesh(config_total,dx)
    
    contour_dict = {'vectors':vecteurs,'mesh_points':pts_all,
                    'segment_length':longueurs,'segment_slice':seg_slices,'segment_center':pts_m, 'contour_vertices':pts_s}
    pts_contour = contour_dict['mesh_points']
    vecteurs    = contour_dict['vectors']
    longueurs   = contour_dict['segment_length']
    seg_slices  = contour_dict['segment_slice']
    # paramètres
    # comme on applique le coefficient d'amortissement, la masse volumique est rho = 1000 !
    rho        = 1000  
    g          = 9.81 # gravity
    NbSim_wave = wave_config['computation']['nb_simul']+1
    NbSim_avac = avac_config['computation']['nb_simul']+1
    z_lac      = lake['water_level']

    # extension du lac
    xmin, xmax = lake['xmin'], lake['xmax']
    ymin, ymax = lake['ymin'], lake['ymax']
    
    
    # grille d'interpolation du lac
    nb_grille  = wave_config['computation']['nb_grid']
    x_grille = np.linspace(xmin,xmax,nb_grille)
    y_grille = np.linspace(ymin,ymax,nb_grille)
    X_grille, Y_grille = np.meshgrid(x_grille,y_grille)
    dx_grille   = (xmax-xmin)/nb_grille
    dy_grille   = (ymax-ymin)/nb_grille
    pts_grille  = np.column_stack([Y_grille.ravel(), X_grille.ravel()])
    grid_shape  = X_grille.shape

    # masque du lac sur la grille de tout le domaine
    lake_mask_file          = reading_raster_file(topo_dir / wave_config['topo_files']['mask_raster'])
    interpolation_lake_mask = RegularGridInterpolator(
        (lake_mask_file.y, lake_mask_file.x), lake_mask_file.Z, method='nearest',
        bounds_error=False, fill_value=0
        )
    
    # masque interpolé sur la grille du lac
    masque_lac = ~interpolation_lake_mask( (Y_grille, X_grille) ).astype(bool)
    
    wave_frame_temps_list = []
    for fgframe in tqdm(range(1,NbSim_wave)):
        # lecture des frames du modèle wave
        if verbosity:
            wave_frame = wave_fg_grid.read_frame(fgframe)
        else:
            with contextlib.redirect_stdout(io.StringIO()):
                wave_frame = wave_fg_grid.read_frame(fgframe)
        wave_frame_temps_list.append(wave_frame.t)
    
    avac_frame_temps_list = []
    for fgframe in tqdm(range(1,NbSim_avac)):
        # lecture des frames du modèle avac
        if verbosity:
            avac_frame = avac_fg_grid.read_frame(fgframe)
        else:
            with contextlib.redirect_stdout(io.StringIO()):
                avac_frame = avac_fg_grid.read_frame(fgframe)
        avac_frame_temps_list.append(avac_frame.t)

    # position de la valeur correspondant au temps cible
    idx_wave = int(np.argmin(np.abs(np.array(wave_frame_temps_list) - target_time)))
    idx_avac = int(np.argmin(np.abs(np.array(avac_frame_temps_list) - target_time)))
    # résultat
    print(f"avac i = {idx_avac}/{NbSim_avac} et wave i = {idx_wave}/{NbSim_wave}")

    # lecture des deux frames au temps t = target_time
    wave_frame = wave_fg_grid.read_frame(idx_wave)
    avac_frame = avac_fg_grid.read_frame(idx_avac)
    wave_axes = (wave_frame.y, wave_frame.x)
    avac_axes = (avac_frame.y, avac_frame.x)
    kw   = dict(method='linear', bounds_error=False, fill_value=0.0)
    interp_h_wave          = RegularGridInterpolator(wave_axes, wave_frame.h.T, **kw)
    interp_h_avac          = RegularGridInterpolator(avac_axes, avac_frame.h.T, **kw)
    wave_hauteur = interp_h_wave(pts_grille).reshape(grid_shape)
    avac_hauteur = interp_h_avac(pts_grille).reshape(grid_shape)

    minor_step = wave_config['output']['carto_layout']['minor_label_step']

    
    dx = float(topo_file.x[-1] - topo_file.x[0])
    dy = float(topo_file.y[-1] - topo_file.y[0])

    w = 5  # largeur par panneau (inches)
    h = w * dy / dx  # hauteur respectant le rapport d'aspect
    margin = wave_config['output']['carto_layout']['margin']
    fig, (ax_wave, ax_avac) = plt.subplots(1, 2, figsize=(2*w, h), layout='constrained')

    fig_tmp, ax_wave, x0, y0 = plot_topo(topo_file, ax=ax_wave, step = minor_step*2)
    fig_tmp, ax_avac, x0, y0 = plot_topo(topo_file, ax=ax_avac, step = minor_step*2)
    ax_wave.add_patch(plt.Rectangle((xmin-x0, ymin-y0),
                                width  = xmax-xmin,
                                height = ymax-ymin,
                                ls="-", lw=1, ec="red", fc="none"))
    pc1 = pcolorcells(wave_frame.X-x0, wave_frame.Y-y0, ma.masked_where(wave_frame.h == 0, 
                                                                             wave_frame.h), cmap=cmap, ax=ax_wave,alpha=0.5)
    pc2 = pcolorcells(avac_frame.X-x0, avac_frame.Y-y0, ma.masked_where(avac_frame.h == 0, 
                                                                        avac_frame.h), cmap=cmap, ax=ax_avac,alpha=0.5)
    ax_avac.set_xlim(xmin - x0 - margin, lake['xmax'] - x0 + margin)
    ax_avac.set_ylim(ymin - y0 - margin, ymax - y0 + margin)
    ax_avac.add_patch(plt.Rectangle((xmin-x0, ymin-y0),
                                width  = xmax-xmin,
                                height = ymax-ymin,
                                ls="-", lw=1, ec="red", fc="none"))

    return fig 

###############################
# comparaison carte avalanche #
###############################
def init_plot_avalanche_side_by_side(config_total, topo_file, margin=50, figsize_width=5,cmap = 'gist_rainbow'):
    """
    Initialisation de la figure 
    Entrées
        * config total : dictionnaire
        * topo_file : clawpack topo object
        * margine : marge tout autour de la carte
        * figsize_width : largeur de l'image (5' par défaut)
        * cmap : color mao
    """
      # --- colorbar partagée (initialisée avec un mappable neutre) ---
    import matplotlib.cm as cm
    import matplotlib.colors as mcolors
    import numpy as np
    from pathlib import Path 
    from clawpack.geoclaw import fgout_tools
    import io, contextlib
    import matplotlib.pyplot as plt
    try:
        from module_avac import plot_topo, fn_h, reading_raster_file
    except ImportError:
        import sys
        sys.path.insert(0, str(Path(topo_dir).parent / "AVAC"))
        from module_avac import plot_topo, fn_h, reading_raster_file
    
    topo_dir  = Path(config_total['répertoires']['topo_dir'])
    avac_dir  = Path(config_total['répertoires']['avac_dir'])
    waves_dir = Path(config_total['répertoires']['waves_dir'])
    wave_cfg  = config_total['waves']
    avac_cfg  = config_total['avac']
    lake      = wave_cfg['lake']
    damping   = wave_cfg['computation']['damping']
    
    # lecture grilles fgout  
    wave_fg = fgout_tools.FGoutGrid(1, waves_dir / wave_cfg['output']['output_directory'],
                                        wave_cfg['output']['output_format'])
    avac_fg = fgout_tools.FGoutGrid(1, avac_dir  / avac_cfg['output']['output_directory'],
                                        avac_cfg['output']['output_format'])
    with contextlib.redirect_stdout(io.StringIO()):
        wave_fg.read_fgout_grids_data()
        avac_fg.read_fgout_grids_data()

    # état initial (frame 1, lac au repos) 
    with contextlib.redirect_stdout(io.StringIO()):
        h0_wave = wave_fg.read_frame(1).h   # (nx, ny) sur la grille fgout wave
        h0_avac = avac_fg.read_frame(1).h*damping   # idem pour avac

    # listes de temps (direct depuis config, sans lire toutes les frames)  
    n_wave = wave_cfg['computation']['nb_simul']   # 120
    n_avac = avac_cfg['computation']['nb_simul']   # 150
    wave_times = np.linspace(wave_cfg['computation']['t_0'],
                            wave_cfg['computation']['t_max'], n_wave + 1)[1:]
    avac_times = np.linspace(0, avac_cfg['computation']['t_max'], n_avac + 1)[1:]

    # figure  
    xmin, xmax = lake['xmin'], lake['xmax']
    ymin, ymax = lake['ymin'], lake['ymax']
    step = wave_cfg['output']['carto_layout']['minor_label_step'] * 2
    dx_t = float(topo_file.x[-1] - topo_file.x[0])
    dy_t = float(topo_file.y[-1] - topo_file.y[0])
    w, h = figsize_width, figsize_width * dy_t / dx_t
    fig, (ax_w, ax_a) = plt.subplots(1, 2, figsize=(2*w, h), layout='constrained')

    _, ax_w, x0, y0 = plot_topo(topo_file, ax=ax_w, step=step)
    _, ax_a, x0, y0 = plot_topo(topo_file, ax=ax_a, step=step)

    for ax in (ax_w, ax_a):
        ax.add_patch(plt.Rectangle((xmin-x0, ymin-y0), xmax-xmin, ymax-ymin,
                                                ls='-', lw=1, ec='red', fc='none'))
        ax.set_xlim(xmin - x0 - margin, xmax - x0 + margin)
        ax.set_ylim(ymin - y0 - margin, ymax - y0 + margin)

    ax_w.set_title('Vagues')
    ax_a.set_title('Avalanche')


    sm = plt.cm.ScalarMappable(cmap=cmap, norm=mcolors.Normalize(vmin=-1, vmax=1))
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=[ax_w, ax_a], shrink=0.7, label=r'$h(t)-h_0$ (m)')

    return dict(fig=fig, ax_wave=ax_w, ax_avac=ax_a, x0=x0, y0=y0,
                wave_fg=wave_fg, avac_fg=avac_fg,
                wave_times=wave_times, avac_times=avac_times,
                h0_wave=h0_wave, h0_avac=h0_avac,
                cbar=cbar, sm=sm,
                _artists=[],damping = damping, cmap = cmap)



def draw_avalanche_side_by_side(target_time, ctx):
    """
    Trace l'avalanche calculée par Avac et l'avalanche "équivalente en eau liquide" obtenue à partir des CL
    Entrées :
        * target_time : temps auquel on trace les cartes
        * ctx : dictionnaire fourni par le script d'initialisaiton
    """
    import matplotlib.colors as mcolors
    import contextlib, io
    from clawpack.visclaw.plottools import pcolorcells
    import numpy as np
    import numpy.ma as ma

    for art in ctx['_artists']:
        art.remove()
    ctx['_artists'].clear()
    cmap = ctx['cmap']
    damping = ctx['damping']
    idx_w = int(np.argmin(np.abs(ctx['wave_times'] - target_time)))
    idx_a = int(np.argmin(np.abs(ctx['avac_times'] - target_time)))

    with contextlib.redirect_stdout(io.StringIO()):
        wf = ctx['wave_fg'].read_frame(idx_w + 1)
        af = ctx['avac_fg'].read_frame(idx_a + 1)

    x0, y0 = ctx['x0'], ctx['y0']

    # perturbations par rapport à l'état initial
    dh_wave = wf.s*wf.h - ctx['h0_wave']*0
    dh_avac = af.s*af.h*damping - ctx['h0_avac']*0
    dh_wave_masked = ma.masked_where((wf.h == 0) | (dh_wave == 0), dh_wave)
    dh_avac_masked = ma.masked_where((af.h == 0) | (dh_avac == 0), dh_avac)

    # plage de couleurs commune et symétrique
    vmax = max(np.abs(dh_wave).max(), np.abs(dh_avac).max())
    vmax = vmax if vmax > 0 else 1.0

    
    norm = mcolors.Normalize(vmin=-vmax, vmax=vmax)

    pc1 = pcolorcells(wf.X-x0, wf.Y-y0, ma.masked_where(wf.h==0, dh_wave_masked),
                      cmap=cmap, norm=norm, ax=ctx['ax_wave'], alpha=0.8)
    pc2 = pcolorcells(af.X-x0, af.Y-y0, ma.masked_where(af.h==0, dh_avac),
                      cmap=cmap, norm=norm, ax=ctx['ax_avac'], alpha=0.8)

    ctx['ax_wave'].set_title(f'Vagues — t = {wf.t:.1f} s')
    ctx['ax_avac'].set_title(f'Avalanche — t = {af.t:.1f} s')

    # mise à jour de la colorbar partagée
    ctx['sm'].norm = norm
    ctx['cbar'].update_normal(ctx['sm'])

    ctx['_artists'] = [pc1, pc2]
    ctx['fig'].canvas.draw_idle()

######################################
# comparaison carte avalanche + flux #
#####################################
def linestring_to_arrays(line: LineString, n_pts: int = 200):
    """transform un objet de type LineString en tableau"""
    from shapely.geometry import LineString
    import numpy as np
    distances = np.linspace(0, line.length, n_pts)
    coords    = np.array([[line.interpolate(d).x, line.interpolate(d).y] for d in distances])
    return coords[:, 0], coords[:, 1], distances  # x, y, dist

def linestring_to_arrays_with_normals(line: LineString, n_pts: int = 200):
    """
    Échantillonne la polyligne en n_pts points et retourne la normale
    (orientée à gauche) en chacun d'eux.
    
    Retourne : x, y, distance, nx, ny  — tous de shape (n_pts,)
    """
    import numpy as np
    import matplotlib.pyplot as plt
    from pathlib import Path
    from clawpack.geoclaw import fgout_tools
    from clawpack.visclaw.plottools import pcolorcells
    from module_avac import plot_topo
    from scipy.interpolate import RegularGridInterpolator
    import numpy.ma as ma
    coords    = np.array(line.coords)            # (n_segments+1, 2)
    dx_seg    = np.diff(coords[:, 0])
    dy_seg    = np.diff(coords[:, 1])
    L_seg     = np.hypot(dx_seg, dy_seg)         # longueur de chaque segment
    d_noeuds  = np.concatenate([[0], np.cumsum(L_seg)])  # distances aux nœuds

    # normales unitaires à gauche de chaque segment
    nx_seg = -dy_seg / L_seg
    ny_seg =  dx_seg / L_seg

    # points échantillonnés
    distances = np.linspace(0, line.length, n_pts)
    coords_pts = np.array([[line.interpolate(d).x, line.interpolate(d).y]
                            for d in distances])

    # affecter la normale du segment à chaque point
    # np.searchsorted : d_noeuds[i] <= dist < d_noeuds[i+1] → segment i
    seg_idx = np.searchsorted(d_noeuds[1:], distances, side='left')
    seg_idx = np.clip(seg_idx, 0, len(L_seg) - 1)

    nx = nx_seg[seg_idx]
    ny = ny_seg[seg_idx]

    return coords_pts[:, 0], coords_pts[:, 1], distances, nx, ny



# ─────────────────────────────────────────────────────────
def init_plot_avalanche(config_total, topo_file, polyligne:LineString, margin=50, figsize_width=3,cmap = 'gist_rainbow', plot_h = True):
    """
    Initialisation de la celle 
    Entrées
        * config total : dictionnaire
        * topo_file : clawpack topo object
        * margine : marge tout autour de la carte
        * figsize_width : largeur de l'image (5' par défaut)
        * cmap : color mao
    """
    import contextlib, io
    from clawpack.geoclaw import fgout_tools
    from pathlib import Path
    import numpy as np
    import matplotlib.pyplot as plt
    import ipywidgets as widgets
    try:
        from module_avac import plot_topo, fn_h
    except ImportError:
        import sys
        sys.path.insert(0, str(Path(topo_dir).parent / "AVAC"))
        from module_avac import plot_topo, fn_h

    topo_dir  = Path(config_total['répertoires']['topo_dir'])
    avac_dir  = Path(config_total['répertoires']['avac_dir'])
    waves_dir = Path(config_total['répertoires']['waves_dir'])
    wave_cfg  = config_total['waves']
    avac_cfg  = config_total['avac']
    lake      = wave_cfg['lake']
    damping   = wave_cfg['computation']['damping']
    # --- grilles fgout ---
    wave_fg = fgout_tools.FGoutGrid(1, waves_dir / wave_cfg['output']['output_directory'],
                                        wave_cfg['output']['output_format'])
    avac_fg = fgout_tools.FGoutGrid(1, avac_dir  / avac_cfg['output']['output_directory'],
                                        avac_cfg['output']['output_format'])
    with contextlib.redirect_stdout(io.StringIO()):
        wave_fg.read_fgout_grids_data()
        avac_fg.read_fgout_grids_data()

    # --- listes de temps (direct depuis config, sans lire toutes les frames) ---
    n_wave = wave_cfg['computation']['nb_simul']   # 120
    n_avac = avac_cfg['computation']['nb_simul']   # 150
    wave_times = np.linspace(wave_cfg['computation']['t_0'],
                             wave_cfg['computation']['t_max'], n_wave + 1)[1:]
    avac_times = np.linspace(0, avac_cfg['computation']['t_max'], n_avac + 1)[1:]

    x, y, dist, nx, ny = linestring_to_arrays_with_normals(polyligne)
    # --- figure ---
    xmin, xmax = lake['xmin'], lake['xmax']
    ymin, ymax = lake['ymin'], lake['ymax']
    step = wave_cfg['output']['carto_layout']['minor_label_step'] * 2
    dx_t = float(topo_file.x[-1] - topo_file.x[0])
    dy_t = float(topo_file.y[-1] - topo_file.y[0])
    w, h = figsize_width, figsize_width * dy_t / dx_t
    fig, ((ax_w, ax_a),(ax_p_w,ax_p_a)) = plt.subplots(2, 2, figsize=(2*w, 2*h), layout='constrained')

    fig.canvas.header_visible = False

    _, ax_w, x0, y0 = plot_topo(topo_file, ax=ax_w, step=step)
    _, ax_a, x0, y0 = plot_topo(topo_file, ax=ax_a, step=step)

    for ax in (ax_w, ax_a):
        ax.add_patch(plt.Rectangle((xmin-x0, ymin-y0), xmax-xmin, ymax-ymin,
                                   ls='-', lw=1, ec='red', fc='none'))
        ax.set_xlim(xmin - x0 - margin, xmax - x0 + margin)
        ax.set_ylim(ymin - y0 - margin, ymax - y0 + margin)

    ax_w.set_title('Vagues')
    ax_a.set_title('Avalanche')

    # tracé de la polyligne
    ax_w.plot(np.array(polyligne.coords.xy[0])-x0,np.array(polyligne.coords.xy[1])-y0,color='blue',lw=1.5)
    ax_a.plot(np.array(polyligne.coords.xy[0])-x0,np.array(polyligne.coords.xy[1])-y0,color='blue',lw=1.5)

    ax_p_w.set_ylabel(r'$hu$ (m²/s)')
    ax_p_w.set_xlabel(r'distance (m)')
    ax_p_w.grid()
    if plot_h:
        ax_p_a.set_ylabel(r'$h$ (m)')
    else:
        ax_p_a.set_ylabel(r'$hu|s|$ (m²/s)')
    ax_p_a.set_xlabel(r'distance (m)')
    ax_p_a.grid()

    info = widgets.HTML(value="")

    return dict(fig=fig, ax_wave=ax_w, ax_avac=ax_a, ax_profil_avac = ax_p_a, ax_profil_wave = ax_p_w,
                x0=x0, y0=y0,
                wave_fg=wave_fg, avac_fg=avac_fg,
                wave_times=wave_times, avac_times=avac_times,damping=damping,
                _artists=[],polyline=dict(x=x,y=y,distance=dist,n_x=nx,n_y=ny),cmap=cmap, info = info, plot_h = plot_h)


# ─────────────────────────────────────────────────────────
def draw_avalanche(target_time, ctx):
    """
    Mise à jour rapide pour un temps donné.
    """
    import contextlib, io
    import numpy as np
    from clawpack.visclaw.plottools import pcolorcells
    import numpy.ma as ma
    from scipy.interpolate import RegularGridInterpolator
    import ipywidgets as widgets
    for art in ctx['_artists']:
        art.remove()
    ctx['_artists'].clear()
    plot_h   = ctx['plot_h']
    cmap     = ctx['cmap']
    damping  = ctx['damping']
    idx_w    = int(np.argmin(np.abs(ctx['wave_times'] - target_time)))
    idx_a    = int(np.argmin(np.abs(ctx['avac_times'] - target_time)))

    with contextlib.redirect_stdout(io.StringIO()):
        wf = ctx['wave_fg'].read_frame(idx_w + 1)
        af = ctx['avac_fg'].read_frame(idx_a + 1)

      # interpolation de la polyligne
    x    = ctx['polyline']['x']
    y    = ctx['polyline']['y']
    dist = ctx['polyline']['distance']
    n_x  = ctx['polyline']['n_x']
    n_y  = ctx['polyline']['n_y']
    kw   = dict(method='linear', bounds_error=False, fill_value=0.0)
    pts = np.column_stack([y, x])   # (y, x)     pour RegularGridInterpolator
    wave_hu  = RegularGridInterpolator((wf.y, wf.x), wf.hu.T, **kw)(pts)
    avac_hu  = RegularGridInterpolator((af.y, af.x), af.hu.T, **kw)(pts)
    wave_hv  = RegularGridInterpolator((wf.y, wf.x), wf.hv.T, **kw)(pts)
    avac_hv  = RegularGridInterpolator((af.y, af.x), af.hv.T, **kw)(pts)
    avac_s   = RegularGridInterpolator((af.y, af.x), af.s.T, **kw)(pts)
    wave_s   = RegularGridInterpolator((wf.y, wf.x), wf.s.T, **kw)(pts)
    avac_h   = RegularGridInterpolator((af.y, af.x), af.h.T, **kw)(pts)*damping
    wave_h   = RegularGridInterpolator((wf.y, wf.x), wf.h.T, **kw)(pts)

    wave_flux = -(wave_hu*n_x+wave_hv*n_y)                   # on multiplie par -1 pour avoir une valeur > 0 quand le flux est entrant
    avac_flux = -(avac_hu*n_x+avac_hv*n_y)*damping
    wave_qdm = -(wave_hu*n_x+wave_hv*n_y)*wave_s
    avac_qdm = -(avac_hu*n_x+avac_hv*n_y)*avac_s*damping
    # intégration pour avoir le débit
    Q_avac = np.trapz(avac_flux, dist)
    Q_wave = np.trapz(wave_flux, dist)

    x0, y0 = ctx['x0'], ctx['y0']
    pc1 = pcolorcells(wf.X-x0, wf.Y-y0, ma.masked_where(wf.h==0, wf.h),
                      cmap=cmap, ax=ctx['ax_wave'], alpha=0.5)
    pc2 = pcolorcells(af.X-x0, af.Y-y0, ma.masked_where(af.h==0, af.h),
                      cmap= cmap  , ax=ctx['ax_avac'], alpha=0.5)
    ctx['ax_wave'].set_title(f'Vagues — t = {wf.t:.1f} s')
    ctx['ax_avac'].set_title(f'Avalanche — t = {af.t:.1f} s')
    
    ax3 = ctx['ax_profil_wave']
    ax4 = ctx['ax_profil_avac']
    plot3 = ax3.plot(dist,wave_flux,'-r',label="modèle wave")
    plot4 = ax3.plot(dist,avac_flux,'--k',label="modèle avac")
    if plot_h:
        plot5 = ax4.plot(dist,wave_h,'-r')
        plot6 = ax4.plot(dist,avac_h,'--k')
    else:
        plot5 = ax4.plot(dist,wave_qdm,'-r')
        plot6 = ax4.plot(dist,avac_qdm,'--k')
    info = widgets.HTML(value="")   # créer une fois dans init, stocker dans ctx

    # dans draw_avalanche, mettre à jour le widget :
    ctx['info'].value = (
    f"<b>Q<sub>avac</sub></b> = {Q_avac:.0f} m³/s &nbsp;|&nbsp; "
    f"<b>Q<sub>wave</sub></b> = {Q_wave:.0f} m³/s"
    )

    ax3.legend()
    #ax4.legend()
    ctx['_artists'] = [pc1, pc2, plot3[0], plot4[0], plot5[0], plot6[0]]   

    ctx['fig'].canvas.draw_idle()


#####
def afficher_config(cfg):
    """ 
    Affiche la configuration dans une table
    Entrée :
        * cfg : dictionnaire de paramètres
    """
    from tabulate import tabulate
    rows = []
    def walk(d, path):
        for k, v in d.items():
            p = path + [str(k)]
            if isinstance(v, dict):
                walk(v, p)
            else:
                rows.append((p, str(v)))
    walk(cfg, [])

    depth = max(len(p) for p, _ in rows)
    prev = [''] * depth
    table = []
    for path, val in rows:
        padded = path + [''] * (depth - len(path))
        display = [padded[i] if padded[:i+1] != prev[:i+1] else '' for i in range(depth)]
        table.append(display + [val])
        prev = padded

    noms = {1: ['Paramètre'], 2: ['Section', 'Paramètre'],
            3: ['Section', 'Sous-section', 'Paramètre']}
    headers = noms.get(depth, [f'Niveau {i+1}' for i in range(depth)]) + ['Valeur']
    print(tabulate(table, headers=headers, tablefmt='simple'))


#######
 



def compare_dicts(d1, d2, path=""):
    """
    Compare deux dictionnaires et affiche les différences.
    Entrées :
        * d1 : dictionnaire ou adresse du dictionnaire
        * d2 : dictionnaire ou adresse du dictionnaire
        * path : chemin du sous-dictionnaire
    Sortie :
        * diffs: différence
    """
    import pathlib
    from yaml import safe_load
    def _load(arg):
        if isinstance(arg, (str, pathlib.Path)):
            with open(arg) as f:
                return safe_load(f)
        return arg  # déjà un dict

    if not path:  # chargement uniquement au niveau racine
        d1 = _load(d1)
        d2 = _load(d2)

    diffs = []
    all_keys = set(d1) | set(d2)
    for key in sorted(all_keys):
        full_key = f"{path}.{key}" if path else str(key)
        if key not in d1:
            diffs.append(f"  {full_key}: absent de d1, présent dans d2 = {d2[key]!r}")
        elif key not in d2:
            diffs.append(f"  {full_key}: présent dans d1 = {d1[key]!r}, absent de d2")
        elif isinstance(d1[key], dict) and isinstance(d2[key], dict):
            diffs.extend(compare_dicts(d1[key], d2[key], path=full_key))
        elif d1[key] != d2[key]:
            diffs.append(f"  {full_key}: d1={d1[key]!r}  !=  d2={d2[key]!r}")

    if not path:
        if diffs:
            print(f"{len(diffs)} différence(s) trouvée(s) :")
            print("\n".join(diffs))
        else:
            print(f"Les deux dictionnaires sont identiques.")

    return diffs


def calculate_wave_energy(config,masque_lac = None):
    """
    Calcule l'énergie des vagues
    Entrées :
        * configuration : dictionnaire de paramètres
        * masque_lac : array du lac (booléen), optionnel. Si le masque n'est pas fourni, le calcul concerne tout le lac.
          S'il est fourni, on fait un calcul sur tout le domaine et on applique le masque pour ne retenir que le lac
    Sortie :
        * énergie_dic : dictionnaire. Il comprend :
             - potentielle_lac : série de valeurs donnant l'énergie potentielle des vagues
             - cinétique_lac   : série de valeurs donnant l'énergie cinétique des vagues
             - énergie_tot_lac : série de valeurs donnant l'énergie totale des vagues
             - les sous-dictionnaires :
                    * frames_lac : donne accès à tous les frames à chaque temps pour le lac
                        - potentielle : énergie potentielle
                        - cinétique : énergie_cinétique
                        - vague : vague
                        - hauteur : hauteur
                    * frames_domain : donne accès à tous les frames à chaque temps pour tout le domaine
                        - potentielle :énergie potentielle non masquée 
                        - cinétique : énergie cinétique non masquée 
                        - vague : vague non masquée 
                        - hauteur : hauteur non masquée 
    """
    import numpy as np
    import io, contextlib
    from copy import copy
    from clawpack.geoclaw import fgout_tools
    NbSim       = config['computation']['nb_simul'] + 1
    fgout_waves = fgout_tools.FGoutGrid(1, config['computation']['output_directory'], config['output']['output_format'])
    ρ           = config['rheology']['rho']
    g           = config['rheology']['gravity']
    if masque_lac is None:
        Apply_mask = False
    else:
        Apply_mask = True
    with contextlib.redirect_stdout(io.StringIO()):
        fgout_waves.read_fgout_grids_data()
        fg = fgout_waves.read_frame(1)
    hauteur_0 = fg.h.T
    dx = fg.x[1]-fg.x[0]
    dy = fg.y[1]-fg.y[0]
    # Calcul des énergies et des hauteurs de vague
    énergie_potentielle = np.zeros((NbSim,)+hauteur_0.shape)
    vague               = np.zeros((NbSim,)+hauteur_0.shape)
    énergie_cinétique   = np.zeros((NbSim,)+hauteur_0.shape)
    hauteur             = np.zeros((NbSim,)+hauteur_0.shape)
    temps = []
    for i in range(NbSim):
        with contextlib.redirect_stdout(io.StringIO()):
                fg = fgout_waves.read_frame(i+1)
        hauteur[i]             = fg.h.T
        vague[i]               = fg.h.T - hauteur_0
        énergie_potentielle[i] = 0.5 * ρ * g * vague[i]**2
        ec                     = 0.5 * ρ * (fg.hu.T**2 +fg.hv.T**2)
        np.divide(ec, hauteur[i], out = ec, where = (hauteur[i] != 0) )
        énergie_cinétique[i]   = ec
        temps.append(fg.t)
    if Apply_mask:
        énergie_cinétique_non_masquée   = copy(énergie_cinétique)
        énergie_potentielle_non_masquée = copy(énergie_potentielle)
        hauteur_non_masquée             = copy(hauteur)
        vague_non_masquée               = copy(vague)
        énergie_potentielle = np.where(masque_lac[np.newaxis], énergie_potentielle, 0.0)
        énergie_cinétique   = np.where(masque_lac[np.newaxis], énergie_cinétique,   0.0)
        vague               = np.where(masque_lac[np.newaxis], vague,               0.0)
        hauteur             = np.where(masque_lac[np.newaxis], hauteur,             0.0)
    énergie_pot_lac = np.array([énergie_potentielle[i].sum()*dx*dy for i in range(NbSim)]) # en J
    énergie_cin_lac = np.array([énergie_cinétique[i].sum()*dx*dy for i in range(NbSim)])   # en J
    énergie_tot_lac = énergie_cin_lac + énergie_pot_lac 
    temps           = np.array(temps)
    if Apply_mask:
         énergie_dic = {'potentielle_lac':énergie_pot_lac,'cinétique_lac':énergie_cin_lac,'totale_lac':énergie_tot_lac,
                        'frames_lac':{'potentielle':énergie_potentielle,'cinétique':énergie_cinétique,'vague':vague,'hauteur':hauteur},
                        'frames_domain':{'potentielle':énergie_potentielle_non_masquée ,
                                         'cinétique':énergie_cinétique_non_masquée ,'vague':vague_non_masquée ,'hauteur':hauteur_non_masquée }}
    else:
         énergie_dic = {'potentielle_lac':énergie_pot_lac,'cinétique_lac':énergie_cin_lac,'totale_lac':énergie_tot_lac,
                        'frames_lac':{'potentielle':None,'cinétique':None,'vague':None,'hauteur':None},
                        'frames_domain':{'potentielle':énergie_potentielle_non_masquée ,
                                         'cinétique':énergie_cinétique_non_masquée ,'vague':vague_non_masquée ,'hauteur':hauteur_non_masquée }}
    return énergie_dic, temps
