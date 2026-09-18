# -*- coding: utf-8 -*-
"""
importar_sala.py
=================

Script de Python de Unreal Engine 5.8 que importa la geometria de la sala de
domo (generada en Blender por otro agente) y arma el nivel /Game/Maps/DomoVR
listo para verse en VR.

Se ejecuta headless con:

    UnrealEditor-Cmd.exe <ruta al .uproject> -run=pythonscript -script=<ruta a este archivo>

MODELOS DE SALA (variable de entorno DOMO_FOV, ver 04_Docs/05_Modelos_de_sala.md):
    sin DOMO_FOV o DOMO_FOV=180   media esfera: 02_Export/sala_domo.fbx ->
                                  mallas en /Game/Sala, nivel /Game/Maps/DomoVR
                                  (comportamiento original, sin cambios).
    DOMO_FOV=45 / DOMO_FOV=90     SALAS FRONTALES (desde el 18 sep 2026): 45 =
                                  cine domo inclinado tipo Maloka con grada,
                                  90 = sala de pie con plataformas. Leen
                                  02_Export/sala_domo_45.json (mallas,
                                  materiales, ojo), vacian /Game/Sala/Domo_45,
                                  crean sus materiales en
                                  /Game/Sala/Domo_45/Materials y ponen
                                  PlayerStart + Camara_Ojo a altura de ojo.
                                  La cupula usa el MI_Domo compartido.
    otro DOMO_FOV (casquete)      02_Export/sala_domo_N.fbx ->
                                  mallas en /Game/Sala/Domo_90 (el importador
                                  las nombra sala_domo_90_SM_*), nivel
                                  /Game/Maps/DomoVR_90. Los materiales M_* /
                                  MI_Domo de /Game/Sala/Materials se REUTILIZAN
                                  (solo se crean los que falten); el FBX se
                                  importa sin materiales para no pisar los
                                  assets de la media esfera. No se toca
                                  /Game/Maps/DomoVR ni sala_domo_SM_*.
    importar_sala.ps1 -Fov 90 fija la variable y corre este script.

IMPORTANTE (operacion): si el editor grafico de DomoVR ya esta abierto, NO
correr este script por linea de comandos (dos procesos de Unreal sobre el
mismo .uproject se pelean por los mismos archivos). En ese caso se corre
desde dentro del editor abierto (ventana de Python / botonera), no headless.

Contrato de entrada (ver 04_Docs/Unreal_sala_domo.md):
    Archivo:     02_Export/sala_domo.fbx
    Texturas:    02_Export/texturas/*.png (color base, rugosidad, normal;
                 2048x2048) para M_Piso, M_Muro, M_Butaca, M_Tarima y
                 M_Puerta. M_Domo no lleva textura horneada.
    Objetos:     SM_Domo, SM_Muro, SM_Piso, SM_Tarima, SM_Control,
                 SM_Butacas_01 .. SM_Butacas_06, SM_Puerta_01 .. SM_Puerta_04
    Materiales:  M_Domo, M_Muro, M_Piso, M_Butaca, M_Tarima, M_Control,
                 M_Puerta
    Escala:      1 m Blender = 100 uu Unreal (el FBX ya viene en esa escala)
    Domo:        cilindro de 11.5 m de radio, piso plano (sin grada)
    Tarima:      cilindro central de 3 m de diametro x 1 m de alto, en el
                 origen
    Control:     sector de 5 m de ancho contra el muro (lado -X), sin
                 butacas, con consola y piso marcado (SM_Control), flanqueado
                 por dos de las cuatro puertas
    Butacas:     6 modulos en cuna radial x 60 butacas reclinables = 360
                 butacas totales, repartidas en unos 335 grados (no los 360
                 completos, por el sector de control), respaldo muy
                 reclinado, el espectador casi acostado mirando al cenit
    Puertas:     4, con hueco real en el muro cilindrico

IMPORTANTE: si sala_domo.fbx todavia no existe (el otro agente sigue
trabajando en 01_Blender/02_Export), este script NO falla: salta el paso de
importacion de malla, deja constancia clara en el log, y construye igual el
resto del nivel (materiales, iluminacion, post-proceso, punto de partida).
Eso permite verificar en Unreal todo lo que no depende del FBX antes de que
el archivo llegue. Lo mismo aplica a las texturas: si 02_Export/texturas/ no
existe o no trae el mapa que le toca a un material, ese material cae a un
color plano oscuro y mate en vez de fallar.

IDEMPOTENCIA: este script es la fuente de verdad de los assets que crea
(materiales, texturas, instancias de material) y del contenido del nivel.
Se puede correr las veces que haga falta: cada asset se borra y se vuelve a
crear si ya existia (no se reutiliza a medias), y el nivel se limpia de
actores antes de reconstruirlo. Ningun valor de retorno de create_asset /
load_asset / new_level se usa sin comprobar antes que no sea None/False: si
algo falla, el script para con una excepcion que dice que asset y que ruta
fallaron, en vez de seguir de largo y reventar mas abajo con un error
críptico.
"""

import os
import unreal


# ---------------------------------------------------------------------------
# Configuracion / contrato
# ---------------------------------------------------------------------------

# Ruta del proyecto = carpeta que contiene este script (03_Unreal).
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DOMO_ROOT_DIR = os.path.dirname(SCRIPT_DIR)  # Domo_VR_Unreal

def _leer_fov_domo():
    """FOV del modelo de sala desde DOMO_FOV (180 si no esta). Mismo criterio
    que 01_Blender/generar_sala_domo.py."""
    valor = os.environ.get("DOMO_FOV", "").strip()
    if not valor:
        return 180.0
    fov = float(valor)
    if not (10.0 <= fov <= 180.0):
        raise RuntimeError("[importar_sala] DOMO_FOV tiene que estar entre 10 y 180; llego {}".format(valor))
    return fov


FOV_DOMO = _leer_fov_domo()
ES_MEDIA_ESFERA = abs(FOV_DOMO - 180.0) < 1e-6
# Sufijo de archivos y assets del modelo: vacio para la media esfera (nombres
# originales), "_90" / "_45" para los casquetes. Igual que en Blender.
SUFIJO_MODELO = "" if ES_MEDIA_ESFERA else "_{:g}".format(FOV_DOMO)

FBX_PATH = os.path.join(DOMO_ROOT_DIR, "02_Export", "sala_domo{}.fbx".format(SUFIJO_MODELO))
TEXTURAS_DIR = os.path.join(DOMO_ROOT_DIR, "02_Export", "texturas")

# Salas frontales (DOMO_FOV = 45 o 90, desde el 18 sep 2026): el 45 es el cine
# domo inclinado tipo Maloka con grada y 314 butacas, el 90 la sala de pie con
# plataformas y barandas. Ya no son casquetes: el generador de Blender escribe
# junto al FBX un JSON (02_Export/sala_domo_45.json) con la lista de mallas,
# el material de cada una, los colores de trabajo y la posicion del ojo, y
# este script arma el nivel a partir de ese JSON. Sus materiales viven en
# /Game/Sala/Domo_45/Materials (propios del modelo, se recrean en cada
# corrida); la cupula sigue usando el MI_Domo compartido, que es el que
# alimenta Spout. Ver 04_Docs/05_Modelos_de_sala.md.
ES_SALA_FRONTAL = (not ES_MEDIA_ESFERA) and any(abs(FOV_DOMO - k) < 1e-6 for k in (45.0, 90.0))
DATOS_SALA_PATH = os.path.join(DOMO_ROOT_DIR, "02_Export", "sala_domo{}.json".format(SUFIJO_MODELO))
DATOS_SALA = None
if ES_SALA_FRONTAL:
    import json
    if not os.path.isfile(DATOS_SALA_PATH):
        raise RuntimeError("[importar_sala] Falta {}: correr antes generar_sala_domo.py -- --fov {:g}".format(
            DATOS_SALA_PATH, FOV_DOMO))
    with open(DATOS_SALA_PATH, "r", encoding="utf-8") as _fh:
        DATOS_SALA = json.load(_fh)

CONTENT_SALA = "/Game/Sala"
CONTENT_MATERIALS = "/Game/Sala/Materials"
CONTENT_TEXTURES = "/Game/Sala/Textures"
# Donde caen las mallas: la media esfera en /Game/Sala (como siempre); cada
# casquete en su subcarpeta, para que no se mezclen con las del 180 y se
# puedan borrar de un tajo.
CONTENT_MALLAS = CONTENT_SALA if ES_MEDIA_ESFERA else "{}/Domo{}".format(CONTENT_SALA, SUFIJO_MODELO)
CONTENT_MAPS = "/Game/Maps"
MAP_PACKAGE_PATH = "/Game/Maps/DomoVR{}".format(SUFIJO_MODELO)
# Materiales propios de una sala frontal (colores de trabajo del JSON).
CONTENT_MATERIALS_SALA = "{}/Materials".format(CONTENT_MALLAS)

PREFIJO_BUTACAS = "SM_Butacas"
PREFIJO_PUERTAS = "SM_Puerta"

# Nombres de malla esperados segun el contrato con el agente de Blender.
NOMBRES_MALLAS_ESPERADAS = (
    ["SM_Domo", "SM_Muro", "SM_Listones", "SM_Piso", "SM_Tarima", "SM_Control"]
    + ["{}_{:02d}".format(PREFIJO_BUTACAS, i) for i in range(1, 7)]
    + ["{}_{:02d}".format(PREFIJO_PUERTAS, i) for i in range(1, 5)]
)
if ES_SALA_FRONTAL:
    NOMBRES_MALLAS_ESPERADAS = list(DATOS_SALA["mallas"])
BUTACAS_POR_MODULO = 60
TOTAL_BUTACAS = 360

# Cada malla se resuelve al material que le corresponde. M_Domo se maneja
# aparte (es emisivo, no oscuro/mate). Los que no tienen textura horneada
# (M_Control) simplemente no encuentran archivo y quedan en color plano.
MATERIAL_POR_MALLA = {
    "SM_Muro": "M_Muro",
    "SM_Listones": "M_Madera",
    "SM_Piso": "M_Piso",
    "SM_Tarima": "M_Tarima",
    "SM_Control": "M_Control",
}

# Colores/rugosidad de respaldo cuando no hay textura horneada disponible
# (o hasta que 02_Export/texturas/ tenga el mapa correspondiente). Formato:
# nombre_material -> (color_rgb, roughness).
FALLBACK_MATERIALES = {
    "M_Muro": ((0.02, 0.02, 0.02), 0.95),
    "M_Piso": ((0.015, 0.015, 0.015), 0.95),
    "M_Butaca": ((0.05, 0.05, 0.055), 0.9),
    "M_Madera": ((0.30, 0.17, 0.08), 0.6),
    "M_Tarima": ((0.05, 0.05, 0.055), 0.6),
    "M_Control": ((0.04, 0.04, 0.045), 0.5),
    "M_Puerta": ((0.06, 0.045, 0.03), 0.55),
}

# Nanite: decision unica, valida para toda la sala (ver 04_Docs/Unreal_sala_domo.md,
# seccion "Nanite: encendido o apagado"). La escena de hoy son 43 294
# triangulos en total -- Nanite no aporta nada a ese conteo y solo suma
# costo (streaming, DDC, el propio indicador de uso que hay que mantener al
# dia en cada material). Se deja APAGADO para la geometria actual. El dia
# que entre el escaneo por fotogrametria del planetario real (RealityCapture,
# geometria de verdad pesada), esta es la UNICA linea que hay que voltear a
# True: build_nanite en la importacion y el indicador de uso en los
# materiales se derivan los dos de esta misma constante, para que no vuelvan
# a quedar desincronizados como paso la primera vez (materiales creados sin
# el indicador de uso, mientras las mallas si tenian Nanite activo).
USAR_NANITE = False

# Escala de la sala (planetario tipo Bogota). Todo en centimetros (uu de
# Unreal). La sala NO tiene ningun volumen exterior (el sector de control
# esta dentro del mismo cilindro): todo lo que dependa del tamano de la sala
# se cine al cilindro de 11.5 m de radio.
DOMO_RADIO_CM = 1150.0          # 11.5 m de radio
DOMO_DIAMETRO_CM = DOMO_RADIO_CM * 2.0
TARIMA_RADIO_CM = 150.0          # cilindro central, 3 m de diametro

# Punto de partida del jugador: el piso es plano (sin grada) y los
# respaldos de las butacas van muy reclinados, casi acostado mirando al
# cenit. La altura de ojo de alguien casi acostado es bastante mas baja que
# la de alguien sentado erguido (que rondaria 120 cm) o incluso que la de
# alguien apenas reclinado (~105 cm, la estimacion anterior de este mismo
# script cuando el respaldo era menos inclinado). Se usa 70 cm como
# aproximacion de trabajo; hay que ajustarla con la geometria real de las
# butacas apenas llegue.
PLAYER_EYE_HEIGHT_CM = 70.0

# El origen (0,0) esta ocupado por SM_Tarima (radio 150 cm): el PlayerStart
# no puede ir ahi. Sin las coordenadas reales de las butacas todavia, se
# coloca a un radio prudente mas alla de la tarima, hacia +X (lado opuesto
# al sector de control, que esta contra el muro en -X), como marcador de
# posicion razonable dentro de una de las 6 cunas de butacas. Ajustar en
# cuanto se conozcan las coordenadas reales de las filas.
PLAYER_START_RADIO_CM = 400.0

# Textura de marcador de posicion para el emisivo del domo: se usa una
# textura de grilla del propio motor (util ademas para verificar a ojo el
# mapeo UV azimut/elevacion del domo) hasta que TouchDesigner entregue el
# feed real por Spout. M_Domo NO usa ninguna textura horneada de
# 02_Export/texturas/: sigue siendo puramente emisivo/parametrico.
# DefaultTexture es sRGB: con la rejilla lineal T_Default_Material_Grid_M el
# nodo con sampler Color no compilaba y el domo se dibujaba negro.
TEXTURA_PLACEHOLDER_PATH = "/Engine/EngineResources/DefaultTexture"

# Nombre del parametro de textura expuesto en el material del domo, para que
# TouchDesigner/Spout lo pueda sobreescribir en runtime via Material Instance
# Dinamica.
PARAMETRO_TEXTURA_DOMO = "SpoutTexture"

# Nombre del parametro que multiplica la emision del domo, y su valor de
# arranque. El usuario quiere ver de verdad como la cupula ilumina la sala
# por Lumen (segundo objetivo explicito de este encargo): un valor de 1.0
# en Emissive Color es demasiado debil como fuente de luz en un cilindro de
# 11.5 m de radio. Se probaron 20, 300 y 50000 en vivo (MaterialInstanceTools
# por MCP) sin poder confirmar por captura visual cual se ve bien -- ver
# 04_Docs/Unreal_sala_domo.md, seccion sobre el intento de verificacion
# visual, para la explicacion completa de por que esa comprobacion quedo
# inconclusa (un modo de vista de depuracion del editor que no se pudo
# desactivar por las herramientas de MCP disponibles). 100.0 queda como
# punto de partida razonado, no confirmado a ojo; es un parametro de
# Material Instance, no una constante fija en el grafo, precisamente para
# que se pueda subir o bajar despues sin recompilar el material.
PARAMETRO_INTENSIDAD_DOMO = "EmissiveIntensity"
INTENSIDAD_DOMO_INICIAL = 1.0

# Sinonimos de nombre de archivo para reconocer cada tipo de mapa PBR sin
# depender de una convencion de nombres exacta (todavia no la conocemos:
# los mapas los esta horneando el otro agente en paralelo).
SINONIMOS_TIPO_MAPA = {
    "basecolor": ["basecolor", "base_color", "albedo", "diffuse", "color"],
    "roughness": ["roughness", "rough", "rugosidad"],
    "normal": ["normal", "nrm", "norm"],
}

resumen = {
    "mallas_importadas": [],
    "mallas_faltantes": [],
    "texturas_importadas": [],
    "materiales_creados": [],
    "materiales_reutilizados": [],
    "actores_colocados": [],
    "avisos": [],
}


def log(msg):
    # Se usa log_warning (no unreal.log) a proposito: en corridas headless
    # con -run=pythonscript se comprobo que los mensajes "Display" de la
    # categoria LogPython no siempre llegan a la consola/log, mientras que
    # los "Warning" si, siempre. El resumen que pide el encargo tiene que
    # verse si o si, y el prefijo "[importar_sala]" deja claro que no es un
    # problema real.
    unreal.log_warning("[importar_sala] {}".format(msg))


def aviso(msg):
    resumen["avisos"].append(msg)
    unreal.log_warning("[importar_sala] {}".format(msg))


def fallar(msg):
    """Falla ruidosamente en vez de dejar que un None/False se arrastre
    veinte lineas mas abajo como un AttributeError críptico."""
    raise RuntimeError("[importar_sala] {}".format(msg))


# ---------------------------------------------------------------------------
# Helpers de asset idempotentes
# ---------------------------------------------------------------------------

def _ruta_completa(package_path, nombre):
    return package_path.rstrip("/") + "/" + nombre


def _borrar_si_existe(ruta_completa):
    if unreal.EditorAssetLibrary.does_asset_exist(ruta_completa):
        ok = unreal.EditorAssetLibrary.delete_asset(ruta_completa)
        if not ok:
            fallar(
                "No se pudo borrar el asset existente en {} antes de "
                "recrearlo.".format(ruta_completa)
            )


def crear_asset(nombre, package_path, clase, factory):
    """Crea un asset desde cero en package_path/nombre. Si ya existia, lo
    borra primero (este script siempre reconstruye sus propios assets, no
    los reutiliza a medias). Nunca devuelve None: si create_asset falla,
    para con un mensaje claro."""
    ruta = _ruta_completa(package_path, nombre)
    _borrar_si_existe(ruta)
    asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
    asset = asset_tools.create_asset(nombre, package_path, clase, factory)
    if asset is None:
        fallar(
            "create_asset devolvio None para '{}' en '{}' (clase {}). No se "
            "puede continuar.".format(nombre, package_path, clase)
        )
    return asset


def cargar_asset_obligatorio(ruta):
    """load_asset que falla ruidosamente si el asset no existe, en vez de
    devolver None y dejar que reviente mas abajo."""
    asset = unreal.EditorAssetLibrary.load_asset(ruta)
    if asset is None:
        fallar("load_asset devolvio None para '{}'.".format(ruta))
    return asset


# ---------------------------------------------------------------------------
# Paso 1: importar el FBX como Static Meshes separados
# ---------------------------------------------------------------------------

def importar_fbx():
    """Importa sala_domo.fbx a /Game/Sala/ sin combinar mallas.

    Devuelve un dict {nombre_canonico_del_contrato: unreal.StaticMesh}. Si
    el archivo no existe todavia, devuelve un dict vacio y deja constancia
    en el resumen.
    """
    if not os.path.isfile(FBX_PATH):
        aviso(
            "No se encontro {} todavia (el otro agente sigue generando la "
            "geometria en Blender). Se omite la importacion de malla; el "
            "resto del nivel se construye igual.".format(FBX_PATH)
        )
        resumen["mallas_faltantes"] = list(NOMBRES_MALLAS_ESPERADAS)
        return {}

    log("Importando {} -> {}".format(FBX_PATH, CONTENT_MALLAS))

    if ES_SALA_FRONTAL and unreal.EditorAssetLibrary.does_directory_exist(CONTENT_MALLAS):
        # La sala frontal no tiene las mismas mallas que el casquete que habia
        # antes en esta carpeta (tarima, cunas, control...): se vacia la
        # carpeta del modelo para que no queden assets huerfanos. Solo esta
        # carpeta; /Game/Sala/Materials y las mallas del 180 no se tocan.
        viejos = unreal.EditorAssetLibrary.list_assets(CONTENT_MALLAS, True, False)
        if viejos:
            unreal.EditorAssetLibrary.delete_directory(CONTENT_MALLAS)
            log("Carpeta {} vaciada antes de importar ({} assets).".format(CONTENT_MALLAS, len(viejos)))

    options = unreal.FbxImportUI()
    options.import_mesh = True
    options.import_as_skeletal = False
    # La media esfera importa los materiales del FBX como siempre (quedan en
    # /Game/Sala como M_* sueltos, que el nivel no usa). Los casquetes NO:
    # traerian los mismos nombres y pisarian esos assets del 180; sus mallas
    # reciben los materiales de /Game/Sala/Materials en aplicar_materiales.
    options.import_materials = ES_MEDIA_ESFERA
    options.import_textures = False
    options.import_animations = False
    options.mesh_type_to_import = unreal.FBXImportType.FBXIT_STATIC_MESH
    options.automated_import_should_detect_type = False

    sm_data = options.static_mesh_import_data
    # "sin combinar mallas, conservando los nombres" -> combine_meshes=False.
    sm_data.set_editor_property("combine_meshes", False)
    # Sala frontal: sin colision convexa automatica (el casco convexo de la
    # cupula o de la grada envolveria al jugador); se usa la malla como
    # colision compleja, ver _colision_compleja.
    sm_data.set_editor_property("auto_generate_collision", not ES_SALA_FRONTAL)
    sm_data.set_editor_property("generate_lightmap_u_vs", False)
    # CRITICO, no se puede dejar en el valor por defecto del motor: el
    # constructor de UFbxAssetImportData (FbxAssetImportData.cpp) trae
    # bConvertSceneUnit=false de fabrica. Sin esto en True, el importador NO
    # convierte las unidades del FBX (metros, del lado de Blender) a
    # centimetros (las uu de Unreal): un objeto de 23 m de Blender entraba
    # como 23 uu = 23 CENTIMETROS, no 23 metros -- exactamente el factor 100
    # que faltaba. Se detecto midiendo con get_actor_bounds por MCP: Domo_Actor
    # daba +-11.5 uu en vez de +-1150 uu. bConvertSceneUnit=True (y no un
    # ImportUniformScale=100 a mano) es la correccion correcta: usa la unidad
    # que el propio FBX declara en vez de asumir un factor fijo, asi que sigue
    # funcionando igual si el otro agente ajusta la escala de export de
    # Blender el dia de manana. Se decidio arreglarlo aca, del lado de Unreal,
    # y no tocando el export de Blender, porque el mismo .fbx tambien produce
    # el .glb de 02_Export/ y cualquier otro consumidor futuro: cambiar la
    # escala de origen los afectaria a todos, mientras que esto solo cambia
    # como IMPORTA Unreal, sin tocar el archivo de origen.
    sm_data.set_editor_property("convert_scene_unit", True)
    # Ver USAR_NANITE mas arriba: hoy la escena entera son 43 294 triangulos
    # (no lo justifica), asi que queda apagado. Si algun dia entra geometria
    # pesada de verdad (fotogrametria), esta llamada y la de los materiales
    # (crear_materiales) se prenden juntas con esa misma constante.
    sm_data.set_editor_property("build_nanite", USAR_NANITE)

    task = unreal.AssetImportTask()
    task.set_editor_property("filename", FBX_PATH)
    task.set_editor_property("destination_path", CONTENT_MALLAS)
    task.set_editor_property("replace_existing", True)
    task.set_editor_property("replace_existing_settings", True)
    task.set_editor_property("automated", True)
    task.set_editor_property("save", True)
    task.set_editor_property("factory", unreal.FbxFactory())
    task.set_editor_property("options", options)

    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])

    imported = list(task.get_objects())
    mallas_crudas = {}
    for obj in imported:
        if isinstance(obj, unreal.StaticMesh):
            mallas_crudas[obj.get_name()] = obj

    if not mallas_crudas:
        fallar(
            "El FBX {} existe pero la importacion no devolvio ningun "
            "Static Mesh. Revisar el log de FBXImport de esta corrida; "
            "esto no es un caso de 'archivo faltante', es un fallo real de "
            "importacion.".format(FBX_PATH)
        )

    log("Nombres de asset reales despues de importar: {}".format(sorted(mallas_crudas.keys())))

    # El importador de FBX de Unreal antepone el nombre base del archivo al
    # nombre de cada malla cuando el nodo/objeto de origen no tiene un
    # nombre unico dentro de la escena (se observo con un FBX real de
    # prueba: "SM_Domo" llego como asset "sala_domo_SM_Domo", no como
    # "SM_Domo"). Para no depender de que Blender exporte los nombres
    # pelados, se resuelve por sufijo contra los nombres del contrato.
    mallas = {}
    nombres_no_reconocidos = []
    for nombre_real, obj in mallas_crudas.items():
        canonico = _nombre_canonico_de_malla(nombre_real)
        if canonico:
            mallas[canonico] = obj
        else:
            nombres_no_reconocidos.append(nombre_real)

    if nombres_no_reconocidos:
        aviso(
            "Estas mallas importadas no calzan (ni exacto ni por sufijo) con "
            "ningun nombre del contrato: {}. No se colocan automaticamente "
            "en el nivel.".format(nombres_no_reconocidos)
        )

    log("Mallas reconocidas por el contrato: {}".format(sorted(mallas.keys())))
    resumen["mallas_importadas"] = sorted(mallas.keys())
    if ES_SALA_FRONTAL:
        for mesh in mallas.values():
            _colision_compleja(mesh)

    faltantes = [n for n in NOMBRES_MALLAS_ESPERADAS if n not in mallas]
    if faltantes:
        aviso(
            "El FBX no trajo estas mallas esperadas por el contrato: {}. "
            "Se continua con lo que si llego.".format(faltantes)
        )
    resumen["mallas_faltantes"] = faltantes

    # Defensivo: si el FBX llega con mas variantes de butacas/puertas de las
    # nombradas por el contrato (p. ej. granularidad por asiento en vez de
    # por modulo), lo dejamos anotado para decidir instanciado real despues.
    extra_repetidas = [
        n for n in nombres_no_reconocidos
        if PREFIJO_BUTACAS in n or PREFIJO_PUERTAS in n
    ]
    if extra_repetidas:
        aviso(
            "Aparecieron mallas de butacas/puertas fuera del patron "
            "esperado: {}. Revisar si conviene Instanced Static Mesh en vez "
            "de colocarlas como actores sueltos.".format(extra_repetidas)
        )

    return mallas


def _colision_compleja(mesh):
    """Colision por poligono (Use Complex Collision As Simple): se puede
    caminar por las gradas y plataformas y el jugador no queda encerrado en
    un casco convexo."""
    try:
        body = mesh.get_editor_property("body_setup")
        if body is None:
            aviso("{}: sin body_setup; queda sin colision.".format(mesh.get_name()))
            return
        body.set_editor_property("collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
    except Exception as exc:  # noqa: BLE001
        aviso("{}: no se pudo poner colision compleja ({}).".format(mesh.get_name(), exc))


def _nombre_canonico_de_malla(nombre_real):
    """Resuelve un nombre de asset real contra los nombres del contrato,
    tolerando que el importador le haya antepuesto el nombre del archivo
    (ver comentario en importar_fbx)."""
    if nombre_real in NOMBRES_MALLAS_ESPERADAS:
        return nombre_real
    for esperado in NOMBRES_MALLAS_ESPERADAS:
        if nombre_real.endswith("_" + esperado):
            return esperado
    return None


# ---------------------------------------------------------------------------
# Paso 2: texturas PBR horneadas
# ---------------------------------------------------------------------------

def _buscar_textura(nombre_material, tipo):
    """Busca en TEXTURAS_DIR un archivo cuyo nombre calce con el material
    (sin el prefijo M_) y con algun sinonimo del tipo de mapa pedido.
    Devuelve la ruta completa o None si no hay match (todavia no sabemos la
    convencion de nombres exacta que va a usar el otro agente)."""
    if not os.path.isdir(TEXTURAS_DIR):
        return None

    token_material = nombre_material.replace("M_", "").lower()
    sinonimos = SINONIMOS_TIPO_MAPA[tipo]

    candidatos = []
    for nombre_archivo in os.listdir(TEXTURAS_DIR):
        base, ext = os.path.splitext(nombre_archivo)
        if ext.lower() not in (".png", ".tga", ".jpg", ".jpeg"):
            continue
        base_lower = base.lower()
        if token_material in base_lower and any(s in base_lower for s in sinonimos):
            candidatos.append(nombre_archivo)

    if not candidatos:
        return None
    if len(candidatos) > 1:
        aviso(
            "Mas de un archivo de textura calza con material={} tipo={}: "
            "{}. Se usa el primero.".format(nombre_material, tipo, sorted(candidatos))
        )
    return os.path.join(TEXTURAS_DIR, sorted(candidatos)[0])


def _importar_textura(ruta_archivo, nombre_asset, tipo):
    """Importa un PNG/TGA como Texture2D en CONTENT_TEXTURES, idempotente,
    y deja la textura configurada segun su tipo:
      - basecolor: color normal (sRGB encendido, compresion por defecto).
      - roughness: lineal, sin sRGB (TC_Masks) -- es un mapa de datos, no de
        color; usar sRGB aqui es el error clasico que arruina los valores.
      - normal: marcado como Normalmap (TC_Normalmap), tambien sin sRGB.
    """
    ruta_asset = _ruta_completa(CONTENT_TEXTURES, nombre_asset)
    _borrar_si_existe(ruta_asset)

    task = unreal.AssetImportTask()
    task.set_editor_property("filename", ruta_archivo)
    task.set_editor_property("destination_path", CONTENT_TEXTURES)
    task.set_editor_property("destination_name", nombre_asset)
    task.set_editor_property("replace_existing", True)
    task.set_editor_property("automated", True)
    task.set_editor_property("save", True)
    task.set_editor_property("factory", unreal.TextureFactory())

    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])

    objetos = [o for o in task.get_objects() if isinstance(o, unreal.Texture2D)]
    if not objetos:
        fallar(
            "La importacion de la textura {} ({}) no devolvio ningun "
            "Texture2D.".format(ruta_archivo, nombre_asset)
        )
    textura = objetos[0]

    if tipo == "normal":
        textura.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_NORMALMAP)
        textura.set_editor_property("srgb", False)
    elif tipo == "roughness":
        textura.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_MASKS)
        textura.set_editor_property("srgb", False)
    # basecolor se deja con los valores por defecto del importador (color,
    # con sRGB encendido): es una textura de color de verdad.

    unreal.EditorAssetLibrary.save_loaded_asset(textura)
    resumen["texturas_importadas"].append(nombre_asset)
    return textura


def _texturas_para_material(nombre_material):
    """Busca e importa (si existen) los 3 mapas de un material. Devuelve un
    dict {tipo: unreal.Texture2D} con solo los tipos que si se encontraron."""
    encontradas = {}
    for tipo in ("basecolor", "roughness", "normal"):
        ruta_archivo = _buscar_textura(nombre_material, tipo)
        if ruta_archivo is None:
            continue
        nombre_asset = "T_{}_{}".format(nombre_material.replace("M_", ""), tipo.capitalize())
        encontradas[tipo] = _importar_textura(ruta_archivo, nombre_asset, tipo)
    return encontradas


# ---------------------------------------------------------------------------
# Paso 3: materiales
# ---------------------------------------------------------------------------

def _material_pbr_o_plano(nombre_material):
    """Crea un material Default Lit para piso/muro/butaca/tarima/control/
    puerta. Si 02_Export/texturas/ trae los mapas de este material, los usa
    (color base + rugosidad lineal + normal); si no, cae a un color plano
    oscuro y mate (FALLBACK_MATERIALES)."""
    material = crear_asset(nombre_material, CONTENT_MATERIALS, unreal.Material, unreal.MaterialFactoryNew())
    mel = unreal.MaterialEditingLibrary

    color_fallback, roughness_fallback = FALLBACK_MATERIALES.get(
        nombre_material, ((0.03, 0.03, 0.03), 0.9)
    )

    texturas = _texturas_para_material(nombre_material)

    # --- Color base ---
    if "basecolor" in texturas:
        tex_expr = mel.create_material_expression(
            material, unreal.MaterialExpressionTextureSampleParameter2D, -500, -150
        )
        tex_expr.set_editor_property("parameter_name", "BaseColorTexture")
        tex_expr.set_editor_property("texture", texturas["basecolor"])
        tex_expr.set_editor_property("sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_COLOR)
        mel.connect_material_property(tex_expr, "RGB", unreal.MaterialProperty.MP_BASE_COLOR)
    else:
        color_expr = mel.create_material_expression(
            material, unreal.MaterialExpressionVectorParameter, -500, -150
        )
        color_expr.set_editor_property("parameter_name", "Color")
        color_expr.set_editor_property(
            "default_value",
            unreal.LinearColor(color_fallback[0], color_fallback[1], color_fallback[2], 1.0),
        )
        mel.connect_material_property(color_expr, "RGB", unreal.MaterialProperty.MP_BASE_COLOR)

    # --- Rugosidad ---
    if "roughness" in texturas:
        tex_expr = mel.create_material_expression(
            material, unreal.MaterialExpressionTextureSampleParameter2D, -500, 0
        )
        tex_expr.set_editor_property("parameter_name", "RoughnessTexture")
        tex_expr.set_editor_property("texture", texturas["roughness"])
        tex_expr.set_editor_property("sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_MASKS)
        mel.connect_material_property(tex_expr, "R", unreal.MaterialProperty.MP_ROUGHNESS)
    else:
        rough_expr = mel.create_material_expression(
            material, unreal.MaterialExpressionScalarParameter, -500, 0
        )
        rough_expr.set_editor_property("parameter_name", "Roughness")
        rough_expr.set_editor_property("default_value", roughness_fallback)
        mel.connect_material_property(rough_expr, "", unreal.MaterialProperty.MP_ROUGHNESS)

    # --- Metalico: siempre 0, no hay mapas metalicos en el contrato ---
    metal_expr = mel.create_material_expression(
        material, unreal.MaterialExpressionConstant, -500, 150
    )
    metal_expr.set_editor_property("r", 0.0)
    mel.connect_material_property(metal_expr, "", unreal.MaterialProperty.MP_METALLIC)

    # --- Normal ---
    if "normal" in texturas:
        tex_expr = mel.create_material_expression(
            material, unreal.MaterialExpressionTextureSampleParameter2D, -500, 300
        )
        tex_expr.set_editor_property("parameter_name", "NormalTexture")
        tex_expr.set_editor_property("texture", texturas["normal"])
        tex_expr.set_editor_property("sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL)
        mel.connect_material_property(tex_expr, "RGB", unreal.MaterialProperty.MP_NORMAL)

    errores = mel.recompile_material(material)
    if errores:
        aviso("Errores al compilar {}: {}".format(nombre_material, list(errores)))

    if not texturas:
        aviso(
            "{} no encontro texturas en {}: quedo con color plano de "
            "respaldo {}.".format(nombre_material, TEXTURAS_DIR, color_fallback)
        )

    marcar_uso_nanite(material, nombre_material)

    return material


def marcar_uso_nanite(material, nombre_material):
    """Pone (o quita) el indicador de uso Nanite del material, en linea con
    USAR_NANITE. Sin este indicador guardado en el asset, el editor renderiza
    bien igual (lo activa al vuelo) pero avisa "le faltaba el indicador de
    uso Nanite... puede no renderizarse correctamente fuera del editor" cada
    vez que se corre Map Check -- eso fue justamente lo que paso la primera
    vez que se activo Nanite en la importacion sin tocar los materiales.
    Nombre real de la API (UE 5.8, MaterialEditingLibrary.h):
    SetBaseMaterialUsage(Material, EMaterialUsage, bool); MATUSAGE_Nanite es
    el valor de EMaterialUsage para esto. No se uso SetMaterialUsage (existe
    pero esta deprecado a favor de SetBaseMaterialUsage)."""
    mel = unreal.MaterialEditingLibrary
    mel.set_base_material_usage(material, unreal.MaterialUsage.MATUSAGE_NANITE, USAR_NANITE)
    tiene_uso = mel.has_material_usage(material, unreal.MaterialUsage.MATUSAGE_NANITE)
    if tiene_uso != USAR_NANITE:
        aviso(
            "{}: se pidio set_base_material_usage(MATUSAGE_NANITE, {}) pero "
            "has_material_usage devolvio {} despues. Revisar a mano en el "
            "editor (Map Check).".format(nombre_material, USAR_NANITE, tiene_uso)
        )


def _material_domo_emisivo():
    """M_Domo: Unlit, con textura emisiva parametrizada para Spout. No usa
    ningun mapa horneado de 02_Export/texturas/."""
    material = crear_asset("M_Domo", CONTENT_MATERIALS, unreal.Material, unreal.MaterialFactoryNew())
    mel = unreal.MaterialEditingLibrary

    material.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    # Dos caras: se ve desde dentro de la sala sin depender de la orientacion de las normales.
    material.set_editor_property("two_sided", True)
    # "Is Sky": Lumen casi no toma la emision de una malla gigante y delgada
    # como la cupula. Marcada como cielo, un SkyLight con captura en tiempo
    # real la lee cada frame y la reparte como luz sobre sillas y muros.
    material.set_editor_property("is_sky", True)

    placeholder_tex = unreal.EditorAssetLibrary.load_asset(TEXTURA_PLACEHOLDER_PATH)
    if placeholder_tex is None:
        aviso(
            "No se pudo cargar la textura de marcador de posicion {}; "
            "M_Domo queda con el parametro de textura sin default.".format(
                TEXTURA_PLACEHOLDER_PATH
            )
        )

    tex_expr = mel.create_material_expression(
        material, unreal.MaterialExpressionTextureSampleParameter2D, -400, 0
    )
    tex_expr.set_editor_property("parameter_name", PARAMETRO_TEXTURA_DOMO)
    if placeholder_tex is not None:
        tex_expr.set_editor_property("texture", placeholder_tex)
        tex_expr.set_editor_property("sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_COLOR)

    intensidad_expr = mel.create_material_expression(
        material, unreal.MaterialExpressionScalarParameter, -250, 150
    )
    intensidad_expr.set_editor_property("parameter_name", PARAMETRO_INTENSIDAD_DOMO)
    intensidad_expr.set_editor_property("default_value", INTENSIDAD_DOMO_INICIAL)

    multiplicar_expr = mel.create_material_expression(
        material, unreal.MaterialExpressionMultiply, -120, 0
    )
    mel.connect_material_expressions(tex_expr, "RGB", multiplicar_expr, "A")
    mel.connect_material_expressions(intensidad_expr, "", multiplicar_expr, "B")
    mel.connect_material_property(multiplicar_expr, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)

    errores = mel.recompile_material(material)
    if errores:
        aviso("Errores al compilar M_Domo: {}".format(list(errores)))

    # Material Instance para que TouchDesigner/Spout sustituya la textura en
    # runtime sin tocar el material base. En runtime, la sustitucion en vivo
    # se hace creando una Dynamic Material Instance a partir de esta MI y
    # llamando Set Texture Parameter Value cada vez que llegue un frame
    # nuevo por Spout (ver 04_Docs/Unreal_sala_domo.md).
    #
    # UMaterialInstanceConstantFactoryNew.InitialParent es un UPROPERTY() sin
    # especificador Edit/BlueprintReadWrite: no es accesible por
    # set_editor_property desde Python (se probo y falla con "Failed to find
    # property"). El padre se asigna despues, con la funcion pensada para
    # eso, MaterialEditingLibrary.set_material_instance_parent.
    mi = crear_asset(
        "MI_Domo", CONTENT_MATERIALS, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew()
    )
    mel.set_material_instance_parent(mi, material)

    return material, mi


MATERIALES_PBR = ("M_Muro", "M_Madera", "M_Piso", "M_Butaca", "M_Tarima", "M_Control", "M_Puerta")


def crear_materiales():
    """Media esfera: recrea todos los materiales (fuente de verdad, como
    siempre). Casquetes: reutiliza los que ya existen en /Game/Sala/Materials
    y crea solo los que falten, para no reescribir los assets del 180 mientras
    el editor puede tenerlos abiertos."""
    materiales = {}
    creados = []

    if ES_SALA_FRONTAL:
        return _crear_materiales_frontales()

    if ES_MEDIA_ESFERA:
        m_domo, mi_domo = _material_domo_emisivo()
        materiales["M_Domo"] = m_domo
        materiales["MI_Domo"] = mi_domo
        creados += ["M_Domo", "MI_Domo"]
        for nombre_material in MATERIALES_PBR:
            materiales[nombre_material] = _material_pbr_o_plano(nombre_material)
            creados.append(nombre_material)
    else:
        ruta_m_domo = _ruta_completa(CONTENT_MATERIALS, "M_Domo")
        ruta_mi_domo = _ruta_completa(CONTENT_MATERIALS, "MI_Domo")
        if (unreal.EditorAssetLibrary.does_asset_exist(ruta_m_domo)
                and unreal.EditorAssetLibrary.does_asset_exist(ruta_mi_domo)):
            materiales["M_Domo"] = cargar_asset_obligatorio(ruta_m_domo)
            materiales["MI_Domo"] = cargar_asset_obligatorio(ruta_mi_domo)
        else:
            aviso("M_Domo/MI_Domo no existian en {}; se crean (normalmente los crea "
                  "la importacion de la media esfera).".format(CONTENT_MATERIALS))
            m_domo, mi_domo = _material_domo_emisivo()
            materiales["M_Domo"] = m_domo
            materiales["MI_Domo"] = mi_domo
            creados += ["M_Domo", "MI_Domo"]
        for nombre_material in MATERIALES_PBR:
            ruta = _ruta_completa(CONTENT_MATERIALS, nombre_material)
            if unreal.EditorAssetLibrary.does_asset_exist(ruta):
                materiales[nombre_material] = cargar_asset_obligatorio(ruta)
            else:
                aviso("{} no existia; se crea.".format(ruta))
                materiales[nombre_material] = _material_pbr_o_plano(nombre_material)
                creados.append(nombre_material)

    if creados:
        unreal.EditorAssetLibrary.save_directory(CONTENT_MATERIALS, False, True)
    if resumen["texturas_importadas"]:
        unreal.EditorAssetLibrary.save_directory(CONTENT_TEXTURES, False, True)

    reutilizados = sorted(set(materiales.keys()) - set(creados))
    log("Materiales creados: {}; reutilizados: {}".format(sorted(creados), reutilizados))
    resumen["materiales_creados"] = sorted(creados)
    resumen["materiales_reutilizados"] = reutilizados
    return materiales


def _material_color_frontal(nombre, datos):
    """Material Default Lit de color plano con parametros Color, Roughness y
    Metallic (y Emissive si el JSON trae emision, como el LED de paso). Los
    valores son los mismos que usa Blender para los renders."""
    material = crear_asset(nombre, CONTENT_MATERIALS_SALA, unreal.Material, unreal.MaterialFactoryNew())
    mel = unreal.MaterialEditingLibrary
    color = datos["color"]
    expr = mel.create_material_expression(material, unreal.MaterialExpressionVectorParameter, -500, -150)
    expr.set_editor_property("parameter_name", "Color")
    expr.set_editor_property("default_value", unreal.LinearColor(color[0], color[1], color[2], 1.0))
    mel.connect_material_property(expr, "RGB", unreal.MaterialProperty.MP_BASE_COLOR)
    for y, (param, valor, prop) in enumerate((
            ("Roughness", datos["rugosidad"], unreal.MaterialProperty.MP_ROUGHNESS),
            ("Metallic", datos["metalico"], unreal.MaterialProperty.MP_METALLIC))):
        e = mel.create_material_expression(material, unreal.MaterialExpressionScalarParameter, -500, y * 150)
        e.set_editor_property("parameter_name", param)
        e.set_editor_property("default_value", float(valor))
        mel.connect_material_property(e, "", prop)
    if datos.get("emision"):
        em = datos["emision"]
        fuerza = float(datos.get("fuerza_emision", 1.0))
        e = mel.create_material_expression(material, unreal.MaterialExpressionVectorParameter, -500, 300)
        e.set_editor_property("parameter_name", "Emissive")
        e.set_editor_property("default_value", unreal.LinearColor(em[0] * fuerza, em[1] * fuerza, em[2] * fuerza, 1.0))
        mel.connect_material_property(e, "RGB", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    errores = mel.recompile_material(material)
    if errores:
        aviso("Errores al compilar {}: {}".format(nombre, list(errores)))
    marcar_uso_nanite(material, nombre)
    return material


def _crear_materiales_frontales():
    """Sala frontal: MI_Domo compartido (el de Spout) para la cupula, mas los
    materiales propios del modelo en CONTENT_MATERIALS_SALA, recreados en cada
    corrida desde el JSON de Blender."""
    materiales, creados = {}, []
    ruta_m_domo = _ruta_completa(CONTENT_MATERIALS, "M_Domo")
    ruta_mi_domo = _ruta_completa(CONTENT_MATERIALS, "MI_Domo")
    if (unreal.EditorAssetLibrary.does_asset_exist(ruta_m_domo)
            and unreal.EditorAssetLibrary.does_asset_exist(ruta_mi_domo)):
        materiales["M_Domo"] = cargar_asset_obligatorio(ruta_m_domo)
        materiales["MI_Domo"] = cargar_asset_obligatorio(ruta_mi_domo)
    else:
        aviso("M_Domo/MI_Domo no existian en {}; se crean.".format(CONTENT_MATERIALS))
        materiales["M_Domo"], materiales["MI_Domo"] = _material_domo_emisivo()
        creados += ["M_Domo", "MI_Domo"]
        unreal.EditorAssetLibrary.save_directory(CONTENT_MATERIALS, False, True)
    if not unreal.EditorAssetLibrary.does_directory_exist(CONTENT_MATERIALS_SALA):
        unreal.EditorAssetLibrary.make_directory(CONTENT_MATERIALS_SALA)
    for nombre, datos in sorted(DATOS_SALA["materiales"].items()):
        materiales[nombre] = _material_color_frontal(nombre, datos)
        creados.append("{}/{}".format(CONTENT_MATERIALS_SALA, nombre))
    unreal.EditorAssetLibrary.save_directory(CONTENT_MATERIALS_SALA, False, True)
    reutilizados = ["MI_Domo"] if "MI_Domo" not in creados else []
    log("Materiales de la sala frontal creados: {}; reutilizados: {}".format(creados, reutilizados))
    resumen["materiales_creados"] = creados
    resumen["materiales_reutilizados"] = reutilizados
    return materiales


def asignar_material(mesh, material, slot_index=0):
    if mesh is None or material is None:
        return
    try:
        mesh.set_material(slot_index, material)
    except Exception as exc:  # noqa: BLE001 - queremos seguir aunque falle un slot
        aviso("No se pudo asignar material en {}: {}".format(mesh.get_name(), exc))


def aplicar_materiales(mallas, materiales):
    for nombre, mesh in mallas.items():
        if nombre == "SM_Domo":
            asignar_material(mesh, materiales.get("MI_Domo", materiales.get("M_Domo")))
        elif ES_SALA_FRONTAL:
            nombre_mat = DATOS_SALA["material_por_malla"].get(nombre)
            if nombre_mat not in materiales:
                aviso("{}: el JSON no le asigna un material conocido ({}).".format(nombre, nombre_mat))
                continue
            asignar_material(mesh, materiales[nombre_mat])
        elif nombre in MATERIAL_POR_MALLA:
            asignar_material(mesh, materiales.get(MATERIAL_POR_MALLA[nombre]))
        elif nombre.startswith(PREFIJO_BUTACAS):
            asignar_material(mesh, materiales.get("M_Butaca"))
        elif nombre.startswith(PREFIJO_PUERTAS):
            asignar_material(mesh, materiales.get("M_Puerta"))


# ---------------------------------------------------------------------------
# Paso 4: nivel
# ---------------------------------------------------------------------------

def crear_nivel():
    level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    if not unreal.EditorAssetLibrary.does_directory_exist(CONTENT_MAPS):
        unreal.EditorAssetLibrary.make_directory(CONTENT_MAPS)

    if unreal.EditorAssetLibrary.does_asset_exist(MAP_PACKAGE_PATH):
        # Idempotente: no se borra ni se recrea el .umap (mas delicado si el
        # editor lo tiene abierto); se carga y se limpia de actores antes de
        # reconstruirlo.
        ok = level_subsystem.load_level(MAP_PACKAGE_PATH)
        if not ok:
            fallar("No se pudo cargar el nivel existente {}".format(MAP_PACKAGE_PATH))
        log("Nivel existente {} cargado; se limpia antes de reconstruirlo.".format(MAP_PACKAGE_PATH))
        actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        actores_previos = actor_subsystem.get_all_level_actors()
        if actores_previos:
            actor_subsystem.destroy_actors(actores_previos)
            log("Se borraron {} actores previos del nivel.".format(len(actores_previos)))
    else:
        ok = level_subsystem.new_level(MAP_PACKAGE_PATH)
        if not ok:
            fallar("No se pudo crear el nivel {}".format(MAP_PACKAGE_PATH))
        log("Nivel creado: {}".format(MAP_PACKAGE_PATH))

    return level_subsystem


def limpiar_luces_de_cielo(actor_subsystem):
    """Quita SkyLight/niebla/atmosfera que puedan contaminar la lectura de
    la proyeccion sobre la cupula. La unica fuente de luz relevante debe
    ser la emision de M_Domo."""
    clases_a_quitar = (
        unreal.SkyLight,
        unreal.DirectionalLight,
        unreal.ExponentialHeightFog,
        unreal.SkyAtmosphere,
    )
    quitados = []
    for actor in actor_subsystem.get_all_level_actors():
        if isinstance(actor, clases_a_quitar):
            quitados.append(actor.get_actor_label())
            actor_subsystem.destroy_actor(actor)
    if quitados:
        log("Actores de iluminacion de cielo removidos: {}".format(quitados))


def colocar_geometria(actor_subsystem, mallas):
    """Coloca un AStaticMeshActor por cada malla reconocida.

    OJO: NO se usa spawn_actor_from_object(mesh, ...). Esa funcion (y su
    prima vieja, EditorLevelLibrary.spawn_actor_from_object -- llama a la
    misma subrutina interna) resuelve el actor a crear a traves del sistema
    de "asset placement" de la interfaz del editor
    (FLevelEditorViewportClient::TryPlacingActorFromObject ->
    TryPlacingAssetObject), que depende de un viewport de Level Editor vivo.
    Un commandlet lanzado con -run=pythonscript NO abre esa interfaz, asi
    que esa ruta devuelve un array vacio y la funcion de Python recibe None
    para cada malla, en silencio (se comprobo en una corrida real: 15
    mallas, 15 "None", 0 excepciones).

    spawn_actor_from_class SI funciono en esa misma corrida (asi se
    colocaron el PostProcessVolume y el PlayerStart): instanciar una clase
    de actor es un camino mas simple que no pasa por la resolucion de
    "que factory de colocacion le corresponde a este asset", y no depende
    del viewport. Por eso aqui se crea un AStaticMeshActor por spawn_actor_
    from_class (clase, no objeto) y despues se le asigna la malla a mano
    con StaticMeshComponent.set_static_mesh -- mismo resultado final, sin
    pasar por el sistema de colocacion interactivo.
    """
    fallidas = []
    for nombre in NOMBRES_MALLAS_ESPERADAS:
        mesh = mallas.get(nombre)
        if mesh is None:
            continue

        actor = actor_subsystem.spawn_actor_from_class(
            unreal.StaticMeshActor, unreal.Vector(0.0, 0.0, 0.0), unreal.Rotator(0.0, 0.0, 0.0)
        )
        if actor is None:
            aviso("spawn_actor_from_class devolvio None para {}.".format(nombre))
            fallidas.append(nombre)
            continue

        mesh_component = actor.static_mesh_component
        if mesh_component is None:
            aviso("{} no tiene static_mesh_component (no deberia pasar en un AStaticMeshActor).".format(nombre))
            fallidas.append(nombre)
            continue

        ok = mesh_component.set_static_mesh(mesh)
        if not ok:
            aviso("set_static_mesh devolvio False para {}.".format(nombre))
            fallidas.append(nombre)
            continue

        actor.set_actor_label(nombre.replace("SM_", "") + "_Actor")
        resumen["actores_colocados"].append(actor.get_actor_label())

    if fallidas:
        fallar(
            "No se pudo colocar en el nivel la geometria de: {}. Un import "
            "que no coloca (toda o parte de) la geometria no cuenta como "
            "exitoso, aunque el resto del script haya terminado sin "
            "excepciones.".format(fallidas)
        )


def crear_post_process(actor_subsystem):
    ppv = actor_subsystem.spawn_actor_from_class(
        unreal.PostProcessVolume, unreal.Vector(0.0, 0.0, 0.0), unreal.Rotator(0.0, 0.0, 0.0)
    )
    if ppv is None:
        fallar("spawn_actor_from_class devolvio None para PostProcessVolume.")
    ppv.set_actor_label("PPV_ExposicionFija")
    # Extension infinita: no depende del tamano de la sala (11.5 m de radio,
    # sin ningun volumen exterior ya que el sector de control quedo dentro
    # del mismo cilindro), asi que no hace falta dimensionar una caja.
    ppv.set_editor_property("unbound", True)

    settings = ppv.settings
    settings.set_editor_property("override_auto_exposure_method", True)
    settings.set_editor_property("auto_exposure_method", unreal.AutoExposureMethod.AEM_MANUAL)
    settings.set_editor_property("override_auto_exposure_bias", True)
    # Sin exposicion fisica de camara: con ella la emision del domo quedaba
    # hundida en negro. -1.5 evita que la cupula se queme.
    settings.set_editor_property("override_auto_exposure_apply_physical_camera_exposure", True)
    settings.set_editor_property("auto_exposure_apply_physical_camera_exposure", False)
    settings.set_editor_property("auto_exposure_bias", -0.5)
    # La luz de la sala viene solo del rebote de la cupula (Lumen). Se
    # refuerza el rebote y se baja el bloom para que la proyeccion no se lave.
    settings.set_editor_property("override_indirect_lighting_intensity", True)
    settings.set_editor_property("indirect_lighting_intensity", 8.0)
    settings.set_editor_property("override_lumen_scene_lighting_quality", True)
    settings.set_editor_property("lumen_scene_lighting_quality", 2.0)
    settings.set_editor_property("override_bloom_intensity", True)
    settings.set_editor_property("bloom_intensity", 0.15)
    settings.set_editor_property("override_auto_exposure_min_brightness", True)
    settings.set_editor_property("auto_exposure_min_brightness", 1.0)
    settings.set_editor_property("override_auto_exposure_max_brightness", True)
    settings.set_editor_property("auto_exposure_max_brightness", 1.0)
    ppv.set_editor_property("settings", settings)

    resumen["actores_colocados"].append(ppv.get_actor_label())
    log("Post Process Volume infinito con exposicion manual y fija creado.")
    return ppv


def crear_skylight_domo(actor_subsystem):
    """SkyLight con captura en tiempo real: toma la cupula (M_Domo marcado
    como cielo) cada frame y la usa como luz de la sala. Asi el contenido
    que llega por Spout tine sillas, piso y listones con sus colores."""
    sky = actor_subsystem.spawn_actor_from_class(
        unreal.SkyLight, unreal.Vector(0.0, 0.0, 400.0), unreal.Rotator(0.0, 0.0, 0.0)
    )
    if sky is None:
        fallar("spawn_actor_from_class devolvio None para SkyLight.")
    sky.set_actor_label("SkyLight_Domo")
    comp = sky.get_component_by_class(unreal.SkyLightComponent)
    comp.set_editor_property("mobility", unreal.ComponentMobility.MOVABLE)
    comp.set_editor_property("real_time_capture", True)
    # En las salas frontales la pantalla baja hasta el piso: la parte de la
    # cupula bajo el horizonte tambien alumbra.
    comp.set_editor_property("lower_hemisphere_is_black", not ES_SALA_FRONTAL)
    comp.set_editor_property("intensity", 2.0)
    resumen["actores_colocados"].append(sky.get_actor_label())
    log("SkyLight_Domo con captura en tiempo real creado (intensidad 2).")
    return sky


def _signo_y_blender_a_unreal(actor_subsystem):
    """El FBX de Blender entra a Unreal con el eje Y invertido (Unreal es de
    mano izquierda). En vez de suponerlo, se mide: SM_Puerta_01 esta en +Y en
    Blender (ver crear_puertas_frontales); se mira de que lado quedo."""
    for actor in actor_subsystem.get_all_level_actors():
        if actor.get_actor_label() == "Puerta_01_Actor":
            origen, _ = actor.get_actor_bounds(False)
            signo = 1.0 if origen.y > 0 else -1.0
            log("Puerta_01 (en +Y en Blender) quedo en y={:.0f} cm: signo de Y Blender->Unreal = {:+.0f}".format(
                origen.y, signo))
            return signo
    aviso("No se encontro Puerta_01_Actor para medir el eje Y; se supone invertido.")
    return -1.0


def crear_ojo_frontal(actor_subsystem):
    """PlayerStart y CameraActor en el ojo del espectador que calculo Blender
    (sentado en la fila 7 del modelo 45 a 1,2 m del piso de la grada; de pie
    en la plataforma 3 del modelo 90 a 1,6 m). Misma convencion que el 180:
    la ubicacion del PlayerStart ES la altura de ojo. La camara queda mirando
    al cuadro blanco del patron (frente, +X)."""
    ojo = DATOS_SALA["ojo"]
    sy = _signo_y_blender_a_unreal(actor_subsystem)
    x, y, z = ojo["posicion_m"]
    ubicacion = unreal.Vector(x * 100.0, sy * y * 100.0, z * 100.0)
    yaw = sy * ojo["yaw_deg"]
    rot_start = unreal.Rotator(roll=0.0, pitch=0.0, yaw=yaw)
    rot_cam = unreal.Rotator(roll=0.0, pitch=ojo["pitch_deg"], yaw=yaw)

    start = actor_subsystem.spawn_actor_from_class(unreal.PlayerStart, ubicacion, rot_start)
    if start is None:
        fallar("spawn_actor_from_class devolvio None para PlayerStart.")
    etiqueta = "PlayerStart_Butaca" if DATOS_SALA["sala"].get("filas") else "PlayerStart_DePie"
    start.set_actor_label(etiqueta)
    resumen["actores_colocados"].append(etiqueta)

    cam = actor_subsystem.spawn_actor_from_class(unreal.CameraActor, ubicacion, rot_cam)
    if cam is None:
        fallar("spawn_actor_from_class devolvio None para CameraActor.")
    cam.set_actor_label("Camara_Ojo")
    try:
        cam.camera_component.set_editor_property("field_of_view", 90.0)
    except Exception as exc:  # noqa: BLE001
        aviso("Camara_Ojo: no se pudo fijar el FOV ({}).".format(exc))
    resumen["actores_colocados"].append("Camara_Ojo")
    log("{} y Camara_Ojo en ({:.0f}, {:.0f}, {:.0f}) cm, ojo a {:.2f} m del piso, yaw {:.1f}, pitch camara {:.1f}.".format(
        etiqueta, ubicacion.x, ubicacion.y, ubicacion.z, ojo["altura_sobre_piso_m"], yaw, ojo["pitch_deg"]))
    return start


def crear_player_start(actor_subsystem):
    # Se aleja de la tarima central (radio 150 cm) y del lado -X (sector de
    # control): +X es un punto neutral dentro de una de las cunas de
    # butacas mientras no se tengan las coordenadas reales de las filas.
    ubicacion = unreal.Vector(PLAYER_START_RADIO_CM, 0.0, PLAYER_EYE_HEIGHT_CM)
    start = actor_subsystem.spawn_actor_from_class(
        unreal.PlayerStart, ubicacion, unreal.Rotator(0.0, 180.0, 0.0)
    )
    if start is None:
        fallar("spawn_actor_from_class devolvio None para PlayerStart.")
    start.set_actor_label("PlayerStart_Butaca")
    resumen["actores_colocados"].append(start.get_actor_label())
    log(
        "PlayerStart colocado a {:.0f} cm del centro (fuera de la tarima de "
        "{:.0f} cm de radio), a {:.0f} cm de altura (altura de ojo "
        "aproximada de un espectador casi acostado). Mirando hacia el "
        "centro de la sala.".format(
            PLAYER_START_RADIO_CM, TARIMA_RADIO_CM, PLAYER_EYE_HEIGHT_CM
        )
    )
    return start


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    log("=== Importacion de la sala de domo (DomoVR) ===")
    tipo = ("media esfera" if ES_MEDIA_ESFERA else
            "sala frontal: {}".format(DATOS_SALA["titulo"]) if ES_SALA_FRONTAL else "casquete")
    log("Modelo de sala: {:g} ({}) -> mallas en {}, nivel {}".format(
        FOV_DOMO, tipo, CONTENT_MALLAS, MAP_PACKAGE_PATH))
    log("FBX esperado en: {}".format(FBX_PATH))
    if ES_SALA_FRONTAL:
        pantalla = DATOS_SALA["pantalla"]
        log("Pantalla de 180 grados, radio {:.1f} m, inclinada {:.1f} grados; datos de {}".format(
            pantalla["radio_m"], pantalla["inclinacion_deg"], DATOS_SALA_PATH))
    else:
        log("Texturas esperadas en: {}".format(TEXTURAS_DIR))
        log(
            "Escala de sala: radio {:.1f} m (cilindro cerrado, sin volumen "
            "exterior), {} butacas en 6 cunas radiales.".format(
                DOMO_RADIO_CM / 100.0, TOTAL_BUTACAS
            )
        )

    mallas = importar_fbx()
    materiales = crear_materiales()

    if mallas:
        aplicar_materiales(mallas, materiales)

    actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    crear_nivel()
    limpiar_luces_de_cielo(actor_subsystem)

    if mallas:
        colocar_geometria(actor_subsystem, mallas)
    else:
        aviso("Nivel creado sin geometria: el FBX no estaba disponible todavia.")

    crear_post_process(actor_subsystem)
    crear_skylight_domo(actor_subsystem)
    if ES_SALA_FRONTAL:
        crear_ojo_frontal(actor_subsystem)
    else:
        crear_player_start(actor_subsystem)

    level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    ok = level_subsystem.save_current_level()
    if not ok:
        aviso("save_current_level devolvio False; revisar si el nivel quedo guardado.")
    # Media esfera: guarda todo /Game/Sala y todo /Game/Maps (como siempre).
    # Casquete: solo su carpeta de mallas y SU mapa. OJO: el commandlet
    # arranca con el mapa de inicio del proyecto (/Game/Maps/DomoVR) cargado,
    # y save_directory(CONTENT_MAPS, only_if_is_dirty=False) lo reescribia
    # aunque no se hubiera tocado (paso el 17 sep 2026 con el editor abierto
    # en ese mismo mapa; se restauro desde git). Por eso aqui el casquete
    # guarda el paquete del nivel nuevo por nombre y nada mas.
    unreal.EditorAssetLibrary.save_directory(CONTENT_MALLAS, False, True)
    if ES_MEDIA_ESFERA:
        unreal.EditorAssetLibrary.save_directory(CONTENT_MAPS, False, True)
    else:
        if not unreal.EditorAssetLibrary.save_asset(MAP_PACKAGE_PATH, False):
            aviso("save_asset devolvio False para {}; revisar si el nivel quedo guardado.".format(MAP_PACKAGE_PATH))

    log("=== Resumen ===")
    log("Mallas importadas ({}): {}".format(len(resumen["mallas_importadas"]), resumen["mallas_importadas"]))
    if resumen["mallas_faltantes"]:
        log("Mallas faltantes ({}): {}".format(len(resumen["mallas_faltantes"]), resumen["mallas_faltantes"]))
    log("Texturas importadas ({}): {}".format(len(resumen["texturas_importadas"]), resumen["texturas_importadas"]))
    log("Materiales creados ({}): {}".format(len(resumen["materiales_creados"]), resumen["materiales_creados"]))
    if resumen["materiales_reutilizados"]:
        log("Materiales reutilizados ({}): {}".format(len(resumen["materiales_reutilizados"]), resumen["materiales_reutilizados"]))
    log("Actores colocados ({}): {}".format(len(resumen["actores_colocados"]), resumen["actores_colocados"]))
    if resumen["avisos"]:
        log("Avisos ({}):".format(len(resumen["avisos"])))
        for a in resumen["avisos"]:
            log("  - {}".format(a))
    log("=== Fin importar_sala.py ===")


main()
