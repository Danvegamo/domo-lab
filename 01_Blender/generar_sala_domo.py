"""
Genera por completo, de forma idempotente y en headless, la geometria de una
sala tipo planetario (domo hemisferico + muro cilindrico con 4 puertas +
piso + tarima central + sector de control + 6 cunas de butacas reclinadas),
la guarda como .blend, hornea sus texturas PBR a PNG, la exporta a FBX y
glTF para Unreal Engine 5.8, y renderiza 4 vistas de previsualizacion con
EEVEE leyendo el FBX exportado de vuelta para verificar dimensiones.

Se ejecuta asi (headless, sin abrir la interfaz):
    blender.exe --background --python generar_sala_domo.py
    blender.exe --background --python generar_sala_domo.py -- --fov 90
    set DOMO_FOV=45 && blender.exe --background --python generar_sala_domo.py

MODELOS DE SALA (FOV_DOMO): el mismo script genera tres salas que solo se
diferencian en la cupula y en la altura del muro (ver 04_Docs/05_Modelos_de_sala.md):

    FOV 180  media esfera (planetario clasico). Salida sin sufijo
             (sala_domo.fbx, sala_domo.blend, vista_*.png) para no romper
             nada de lo que ya consume esos nombres.
    FOV 90   casquete esferico que cubre de 45 grados de elevacion al cenit.
    FOV 45   casquete que cubre de 67,5 grados de elevacion al cenit.
             Salida con sufijo: sala_domo_90.fbx, sala_domo_45.blend,
             vista_planta_cenital_90.png, etc.

El FOV se lee de la variable de entorno DOMO_FOV o del argumento --fov que
va despues de "--" (el argumento manda si estan los dos). La geometria del
casquete se deriva de FOV_DOMO en las constantes de abajo: el borde del
casquete siempre tiene el radio del muro (RADIO_DOMO) y la cupula siempre
llega a la misma altura de cenit que la media esfera (ALTURA_CENIT), asi que
la esfera de la que se recorta el casquete es mas grande y el muro sube hasta
donde arranca el casquete. Con FOV distinto de 180 no se hornean texturas
(son las mismas de la media esfera y Unreal reutiliza los materiales M_*);
--hornear las fuerza.

Cada corrida borra la escena entera (bpy.ops.wm.read_factory_settings con
use_empty=True) y la reconstruye desde las constantes de abajo, asi que
correr el script dos veces seguidas da exactamente el mismo resultado.

SUPUESTOS tomados sobre partes ambiguas del encargo (documentados aqui a
proposito porque son las que mas pueden cambiar despues):

- "LADO_CONTROL": el usuario dijo "al lado izquierdo, 5 metros", y luego
  aclaro que NO es un anexo exterior sino un SECTOR RESERVADO dentro de la
  misma sala, contra el muro, en el lado -X ("izquierda" vista en planta
  desde arriba, con +X hacia el frente). ANCHO_CONTROL=5.0 se toma como
  metros de ARCO sobre el muro (no como profundidad radial): con
  RADIO_DOMO=11.5, eso da un sector de unos 25 grados
  (ANCHO_CONTROL/RADIO_DOMO en radianes), calculado por programa en
  calcular_layout_sala(), nunca escrito a mano en grados.
- El sector de control NO tiene piso ni muro propios (ya esta dentro de la
  sala, sobre el mismo piso y bajo el mismo domo): SM_Control es solo el
  mobiliario (consola + panel de monitores) mas una marca en el piso
  (un parche con material propio) que delimita visualmente el sector.
- Los 6 cunas de butacas se reparten el arco que SOBRA (360 grados menos el
  sector de control, unos 335 grados), asi que cada cuna es un poco mas
  angosta que 60 grados; el reparto de filas/butacas por cuna ya se
  calcula a partir del arco disponible (funcion calcular_filas), asi que
  el total sigue dando exactamente 360 sin tocarlo a mano.
- De las 4 puertas: 2 flanquean el sector de control (una a cada lado,
  justo en sus dos bordes) y las otras 2 se reparten en el resto del muro,
  elegidas simetricas respecto del lado opuesto al control (ver
  calcular_layout_sala, comentario junto a PUERTAS_INDICES_FRONTERA).
- Las texturas PBR (base color / roughness / normal) se generan con nodos
  procedurales de Blender y se hornean con Cycles (el motor de horneado
  disponible en esta version; EEVEE se usa solo para los renders finales
  de previsualizacion). Se hornea una sola vez por material compartido
  (una butaca representativa, una puerta representativa) porque las 6
  cunas y las 4 puertas son geometria repetida con UV propio por objeto:
  el resultado es un patron homogeneo tipo tela/metal, no le hace falta
  que el UV coincida pixel a pixel entre copias.
"""

import bpy
import bmesh
import math
import os
import sys
from mathutils import Matrix, Vector

# ---------------------------------------------------------------------------
# CONSTANTES EDITABLES
# ---------------------------------------------------------------------------

# Escala de la sala (a escala del Planetario de Bogota).
RADIO_DOMO = 11.5          # metros, radio de la cupula y del muro
ALTURA_ARRANQUE = 3.0      # metros, altura del ecuador de la cupula (media esfera) sobre el piso

# Teselado de la cupula.
SEGMENTOS_AZIMUT = 128     # divisiones en la vuelta completa (U)
SEGMENTOS_ELEVACION = 64   # divisiones del borde de la cupula al cenit (V)
SEGMENTOS_MURO = SEGMENTOS_AZIMUT   # el muro comparte resolucion acimutal con la cupula


# ---------------------------------------------------------------------------
# MODELO DE SALA: FOV de la cupula y geometria derivada
# ---------------------------------------------------------------------------

def _argumentos_propios():
    """Argumentos que vienen despues de '--' en la linea de Blender (Blender
    se queda con los de antes)."""
    if "--" not in sys.argv:
        return []
    return sys.argv[sys.argv.index("--") + 1:]


def _leer_fov_domo():
    """FOV_DOMO: argumento '--fov N' (o '--fov=N') tras '--', si no la
    variable de entorno DOMO_FOV, si no 180 (media esfera)."""
    valor = os.environ.get("DOMO_FOV")
    extra = _argumentos_propios()
    for i, arg in enumerate(extra):
        if arg == "--fov" and i + 1 < len(extra):
            valor = extra[i + 1]
        elif arg.startswith("--fov="):
            valor = arg.split("=", 1)[1]
    if valor is None or valor.strip() == "":
        return 180.0
    fov = float(valor)
    if not (10.0 <= fov <= 180.0):
        raise SystemExit("DOMO_FOV / --fov tiene que estar entre 10 y 180 grados; llego {}".format(valor))
    return fov


FOV_DOMO = _leer_fov_domo()
ES_MEDIA_ESFERA = abs(FOV_DOMO - 180.0) < 1e-6

# Sufijo de los archivos de salida: la media esfera no lleva sufijo (es el
# modelo original y varios scripts/docs ya usan sala_domo.fbx); los demas
# modelos llevan el FOV (sala_domo_90.fbx, sala_domo_45.fbx).
SUFIJO_MODELO = "" if ES_MEDIA_ESFERA else "_{:g}".format(FOV_DOMO)

# Geometria del casquete. Convencion: la elevacion se mide desde el centro
# de la esfera de la cupula (el mismo punto desde el que se define la UV),
# no desde el ojo del espectador.
#   - ELEVACION_MIN_DEG: borde del casquete. 0 en la media esfera, 45 en el
#     domo 90, 67,5 en el domo 45.
#   - El borde del casquete tiene siempre el radio del muro (RADIO_DOMO), para
#     que el muro cilindrico suba hasta el y cierre la sala sin anillo plano.
#     Por eso la esfera de la que se recorta el casquete crece:
#     RADIO_ESFERA = RADIO_DOMO / cos(elev_min).
#   - La altura del cenit se mantiene igual en todos los modelos
#     (ALTURA_CENIT = ALTURA_ARRANQUE + RADIO_DOMO = 14,5 m): la sala no cambia
#     de envolvente, solo cambia cuanto de esa altura es muro y cuanto cupula.
#     SAGITA_DOMO es la altura del casquete y ALTURA_PARED lo que queda para
#     el muro. En la media esfera todo esto se reduce a los valores originales
#     (RADIO_ESFERA = 11,5, SAGITA = 11,5, ALTURA_PARED = 3).
#   - Z_CENTRO_ESFERA queda por debajo del piso en los casquetes (-1,76 m en
#     el domo 90, -15,55 m en el domo 45): es un punto virtual, no una cota
#     construible. Eso quiere decir que desde el centro del piso el borde del
#     casquete se ve algo mas bajo que el FOV nominal (unos 40 grados en el
#     domo 90 y 47 en el domo 45). Documentado en 05_Modelos_de_sala.md como
#     limitacion conocida.
ELEVACION_MIN_DEG = 90.0 - FOV_DOMO / 2.0
_ELEV_MIN_RAD = math.radians(ELEVACION_MIN_DEG)
ALTURA_CENIT = ALTURA_ARRANQUE + RADIO_DOMO
RADIO_ESFERA = RADIO_DOMO / math.cos(_ELEV_MIN_RAD)
SAGITA_DOMO = RADIO_ESFERA * (1.0 - math.sin(_ELEV_MIN_RAD))
ALTURA_PARED = ALTURA_CENIT - SAGITA_DOMO
Z_CENTRO_ESFERA = ALTURA_CENIT - RADIO_ESFERA

# Horneado de texturas PBR: solo en la media esfera (o con --hornear). Las
# texturas son por material y no dependen del modelo de sala; el importador
# de Unreal reutiliza los M_* que ya existen para los casquetes. Asi generar
# un casquete tarda un minuto en vez de diez y no reescribe las texturas de
# la media esfera.
HORNEAR_TEXTURAS = ES_MEDIA_ESFERA or ("--hornear" in _argumentos_propios())

# Tarima central.
RADIO_TARIMA = 1.5         # metros (3 m de diametro)
ALTURA_TARIMA = 1.0        # metros

# Sector de control (dentro de la sala, contra el muro, lado -X). Ver
# supuestos documentados arriba del archivo.
ANCHO_CONTROL = 7.0        # metros de ARCO sobre el muro (no radial)
RADIO_INICIO_CONTROL = 6.5 # metros: el control ocupa solo la parte de atras, contra el muro
LADO_CONTROL = "IZQUIERDA"          # documental: lado -X de la sala
ANGULO_CENTRO_CONTROL_DEG = 180.0   # -X = "izquierda" en planta, +X al frente

# Puertas en el muro.
ANCHO_PUERTA = 1.4
ALTURA_PUERTA = 2.3
GROSOR_MARCO = 0.10
GROSOR_HOJA = 0.05
# de las 4 fronteras "libres" entre cunas (fuera de las 2 que ya flanquean
# el control), se eligen la 2a y la 4a contando desde el borde de control:
# quedan simetricas respecto del punto exactamente opuesto al sector de
# control, que es justo lo que pide el encargo ("preferiblemente hacia el
# lado opuesto"). Se explica tambien en calcular_layout_sala().
INDICES_FRONTERAS_PUERTAS_EXTRA = (2, 4)

# Butacas: 6 cunas, 60 butacas por cuna, 360 en total. Las cunas se reparten
# el arco que sobra despues de descontar el sector de control.
NUM_MODULOS = 6
BUTACAS_POR_MODULO = 60
TOTAL_BUTACAS = NUM_MODULOS * BUTACAS_POR_MODULO

# Filas concentricas dentro de cada cuna. El numero de filas y de butacas
# por fila NO se escribe a mano: se calcula en calcular_filas() a partir de
# estos parametros y del angulo util real de la cuna (que depende del
# sector de control).
RADIO_INTERIOR_BUTACAS = 3.2     # metros, radio de la primera fila (deja 1.4 m libres alrededor de la tarima)
PASO_BUTACA = 0.60                # metros, paso real entre butacas de una fila (no se estira)
PASO_FILA_RADIAL = 1.20           # metros: el respaldo reclinado invade hacia atras, hace falta este paso
ANGULO_PASILLO_DEG = 3.0          # grados de pasillo libre a cada lado de la cuna

# Butaca reclinada de domo: el espectador queda casi acostado mirando al
# cenit (no es una butaca de teatro). Piso plano: todas las filas quedan al
# mismo nivel, sin grada.
ANCHO_ASIENTO = 0.56
PROFUNDIDAD_ASIENTO = 0.55
ALTO_BASE = 0.38                 # de piso a la superficie del asiento
GROSOR_PANEL = 0.06
ALTURA_RESPALDO = 0.80
ALTURA_REPOSACABEZAS = 0.25
ANGULO_RECLINACION_RESPALDO = 40.0   # grados desde la vertical, echado hacia ATRAS (hacia el muro)
ANGULO_INCLINACION_ASIENTO = 12.0    # grados: la punta del asiento sube, la cola baja
ANCHO_APOYABRAZOS = 0.09
ALTO_APOYABRAZOS = 0.16
LARGO_APOYABRAZOS = PROFUNDIDAD_ASIENTO * 0.75

# Texturas PBR horneadas.
RESOLUCION_TEXTURA = 2048
MUESTRAS_HORNEADO = 24

# Render de previsualizacion.
RES_X = 1280
RES_Y = 720

# Rutas de salida (ya existen las carpetas segun el encargo).
CARPETA_BASE = r"C:\Users\Danvegamo\Documents\Domo_VR_Unreal"
NOMBRE_SALIDA = "sala_domo" + SUFIJO_MODELO
RUTA_BLEND = os.path.join(CARPETA_BASE, "01_Blender", NOMBRE_SALIDA + ".blend")
RUTA_FBX = os.path.join(CARPETA_BASE, "02_Export", NOMBRE_SALIDA + ".fbx")
RUTA_GLB = os.path.join(CARPETA_BASE, "02_Export", NOMBRE_SALIDA + ".glb")
CARPETA_TEXTURAS = os.path.join(CARPETA_BASE, "02_Export", "texturas")
RUTA_PREVIEW = os.path.join(CARPETA_BASE, "05_Preview")


def ruta_preview(nombre_base):
    """vista_x.png para la media esfera, vista_x_90.png para el domo 90."""
    return os.path.join(RUTA_PREVIEW, "{}{}.png".format(nombre_base, SUFIJO_MODELO))


# ---------------------------------------------------------------------------
# UTILIDADES GENERALES
# ---------------------------------------------------------------------------

def limpiar_escena():
    """Deja Blender en un estado de fabrica y vacio. Esto es lo que hace
    idempotente al script: cada ejecucion parte de cero."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.unit_settings.system = 'METRIC'
    bpy.context.scene.unit_settings.scale_length = 1.0


def crear_material(nombre, color_base, emision_color=None, emision_fuerza=0.0, rugosidad=0.6, metalico=0.0):
    if nombre in bpy.data.materials:
        bpy.data.materials.remove(bpy.data.materials[nombre])
    mat = bpy.data.materials.new(nombre)
    mat.use_nodes = True
    principled = mat.node_tree.nodes.get("Principled BSDF")
    principled.inputs["Base Color"].default_value = (*color_base, 1.0)
    principled.inputs["Roughness"].default_value = rugosidad
    principled.inputs["Metallic"].default_value = metalico
    if emision_color is not None:
        principled.inputs["Emission Color"].default_value = (*emision_color, 1.0)
        principled.inputs["Emission Strength"].default_value = emision_fuerza
    return mat


def construir_variacion_procedural(mat, color_a, color_b, escala_ruido, rugosidad_base, rugosidad_amplitud, metalico, fuerza_bump):
    """Utilidad generica de material PBR procedural: mezcla dos colores con
    ruido (base color), varia la rugosidad con otro ruido a mayor escala, y
    agrega una leve protuberancia (bump) para que el normal horneado no
    salga completamente plano. Cada material que la usa le pasa sus
    propios colores/escala/rugosidad/metalico para que el resultado se
    lea distinto (concreto, panel acustico, tela, madera/metal, metal)."""
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    principled = nodes.get("Principled BSDF")
    coord = nodes.new("ShaderNodeTexCoord")

    ruido_color = nodes.new("ShaderNodeTexNoise")
    ruido_color.inputs["Scale"].default_value = escala_ruido
    rampa = nodes.new("ShaderNodeValToRGB")
    rampa.color_ramp.elements[0].color = (*color_a, 1.0)
    rampa.color_ramp.elements[1].color = (*color_b, 1.0)
    links.new(coord.outputs["Object"], ruido_color.inputs["Vector"])
    links.new(ruido_color.outputs["Fac"], rampa.inputs["Fac"])
    links.new(rampa.outputs["Color"], principled.inputs["Base Color"])

    ruido_rug = nodes.new("ShaderNodeTexNoise")
    ruido_rug.inputs["Scale"].default_value = escala_ruido * 1.7
    rango_rug = nodes.new("ShaderNodeMapRange")
    rango_rug.inputs["To Min"].default_value = max(0.0, rugosidad_base - rugosidad_amplitud)
    rango_rug.inputs["To Max"].default_value = min(1.0, rugosidad_base + rugosidad_amplitud)
    links.new(coord.outputs["Object"], ruido_rug.inputs["Vector"])
    links.new(ruido_rug.outputs["Fac"], rango_rug.inputs["Value"])
    links.new(rango_rug.outputs["Result"], principled.inputs["Roughness"])

    principled.inputs["Metallic"].default_value = metalico

    ruido_bump = nodes.new("ShaderNodeTexNoise")
    ruido_bump.inputs["Scale"].default_value = escala_ruido * 3.0
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = fuerza_bump
    links.new(coord.outputs["Object"], ruido_bump.inputs["Vector"])
    links.new(ruido_bump.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], principled.inputs["Normal"])
    return mat


def nuevo_objeto_desde_bmesh(bm, nombre):
    malla = bpy.data.meshes.new(nombre)
    bm.to_mesh(malla)
    bm.free()
    malla.update()
    obj = bpy.data.objects.new(nombre, malla)
    bpy.context.collection.objects.link(obj)
    return obj


def voltear_normales(bm):
    for f in bm.faces:
        f.normal_flip()
    bm.normal_update()


def desenvolver_uv_cube(obj, tam_cubo=1.0):
    """Desenvuelve la malla con proyeccion de cubo (bpy.ops.uv.cube_project),
    suficiente para que el horneado de texturas tenga un UV valido en
    piezas hechas de cajas (piso, muro, butacas, tarima, puertas)."""
    for o in bpy.context.selected_objects:
        o.select_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.cube_project(cube_size=tam_cubo, correct_aspect=True, clip_to_bounds=False, scale_to_bounds=False)
    bpy.ops.object.mode_set(mode='OBJECT')


# ---------------------------------------------------------------------------
# LAYOUT DE LA SALA: sector de control, cunas y puertas (todo por programa)
# ---------------------------------------------------------------------------

def calcular_layout_sala():
    """Calcula, a partir de ANCHO_CONTROL y RADIO_DOMO, el arco (en grados)
    que ocupa el sector de control, y reparte el arco restante entre las 6
    cunas de butacas. Tambien decide en que 4 fronteras entre bloques van
    las puertas. Nada de esto se escribe en grados a mano."""
    angulo_control_rad = ANCHO_CONTROL / RADIO_DOMO
    angulo_control_deg = math.degrees(angulo_control_rad)
    angulo_control_ini_deg = (ANGULO_CENTRO_CONTROL_DEG - angulo_control_deg / 2.0) % 360.0
    angulo_control_fin_deg = (ANGULO_CENTRO_CONTROL_DEG + angulo_control_deg / 2.0) % 360.0

    angulo_libre_deg = 360.0 - angulo_control_deg
    angulo_modulo_efectivo_deg = angulo_libre_deg / NUM_MODULOS

    # Fronteras entre cunas, arrancando justo despues del sector de control
    # y dando la vuelta hasta llegar de nuevo a el. boundaries[0] y
    # boundaries[-1] son exactamente los dos bordes del sector de control.
    inicio = ANGULO_CENTRO_CONTROL_DEG + angulo_control_deg / 2.0
    boundaries_deg = [(inicio + k * angulo_modulo_efectivo_deg) % 360.0 for k in range(NUM_MODULOS + 1)]
    centros_cunas_deg = [(inicio + (k + 0.5) * angulo_modulo_efectivo_deg) % 360.0 for k in range(NUM_MODULOS)]

    # Puertas: las 2 que flanquean el control son las fronteras 0 y NUM_MODULOS
    # (los bordes mismos del sector). Las otras 2 son las fronteras interiores
    # elegidas en INDICES_FRONTERAS_PUERTAS_EXTRA (por defecto la 2a y la 4a
    # frontera libre), que quedan simetricas respecto del punto opuesto al
    # sector de control.
    puertas_deg = [
        angulo_control_ini_deg,
        angulo_control_fin_deg,
        boundaries_deg[INDICES_FRONTERAS_PUERTAS_EXTRA[0]],
        boundaries_deg[INDICES_FRONTERAS_PUERTAS_EXTRA[1]],
    ]

    return {
        "angulo_control_deg": angulo_control_deg,
        "angulo_control_ini_deg": angulo_control_ini_deg,
        "angulo_control_fin_deg": angulo_control_fin_deg,
        "angulo_modulo_efectivo_deg": angulo_modulo_efectivo_deg,
        "boundaries_deg": boundaries_deg,
        "centros_cunas_deg": centros_cunas_deg,
        "puertas_deg": puertas_deg,
    }


# ---------------------------------------------------------------------------
# PISO
# ---------------------------------------------------------------------------

def crear_piso():
    bm = bmesh.new()
    bmesh.ops.create_circle(
        bm, cap_ends=True, cap_tris=False,
        segments=SEGMENTOS_MURO, radius=RADIO_DOMO,
        matrix=Matrix.Identity(4),
    )
    bm.faces.ensure_lookup_table()
    bm.normal_update()
    if bm.faces and bm.faces[0].normal.z < 0:
        voltear_normales(bm)
    obj = nuevo_objeto_desde_bmesh(bm, "SM_Piso")
    obj.data.materials.append(crear_material("M_Piso", (0.05, 0.05, 0.06), rugosidad=0.8))
    return obj


# ---------------------------------------------------------------------------
# MURO CILINDRICO CON 4 PUERTAS
# ---------------------------------------------------------------------------

def crear_muro(puertas_deg):
    """Construye el muro a mano (no con primitive_cone) para poder dejar
    huecos reales donde van las puertas: dos anillos bajos (0 y
    ALTURA_PUERTA) que se saltan en el tramo de cada puerta, y un tercer
    anillo hasta ALTURA_PARED que siempre se rellena (hace de dintel).
    ALTURA_PARED es donde arranca la cupula: 3 m en la media esfera, mas en
    los casquetes (ver la seccion MODELO DE SALA arriba)."""
    bm = bmesh.new()
    alturas = [0.0, ALTURA_PUERTA, ALTURA_PARED]
    anillos = []
    for z in alturas:
        anillo = []
        for i in range(SEGMENTOS_MURO):
            ang = 2.0 * math.pi * i / SEGMENTOS_MURO
            anillo.append(bm.verts.new((RADIO_DOMO * math.cos(ang), RADIO_DOMO * math.sin(ang), z)))
        anillos.append(anillo)
    bm.verts.ensure_lookup_table()

    medio_ancho_puerta_rad = (ANCHO_PUERTA / 2.0) / RADIO_DOMO
    puertas_rad = [math.radians(p) for p in puertas_deg]

    def cae_en_puerta(ang):
        for pr in puertas_rad:
            diff = ((ang - pr + math.pi) % (2.0 * math.pi)) - math.pi
            if abs(diff) <= medio_ancho_puerta_rad:
                return True
        return False

    for i in range(SEGMENTOS_MURO):
        j = (i + 1) % SEGMENTOS_MURO
        ang_centro = 2.0 * math.pi * (i + 0.5) / SEGMENTOS_MURO
        if not cae_en_puerta(ang_centro):
            bm.faces.new((anillos[0][i], anillos[0][j], anillos[1][j], anillos[1][i]))
        bm.faces.new((anillos[1][i], anillos[1][j], anillos[2][j], anillos[2][i]))

    bm.faces.ensure_lookup_table()
    bm.normal_update()
    if bm.faces:
        f0 = bm.faces[0]
        c = f0.calc_center_median()
        radial = Vector((c.x, c.y, 0.0)).normalized()
        if f0.normal.dot(radial) > 0:
            voltear_normales(bm)

    obj = nuevo_objeto_desde_bmesh(bm, "SM_Muro")
    obj.data.materials.append(crear_material("M_Muro", (0.05, 0.05, 0.06), rugosidad=0.85))
    return obj


# ---------------------------------------------------------------------------
# LISTONES VERTICALES DE MADERA SOBRE EL MURO
# ---------------------------------------------------------------------------

ANCHO_LISTON = 0.07     # metros, frente de cada liston
FONDO_LISTON = 0.035    # metros, cuanto sobresale del muro
PASO_LISTON = 0.14      # metros entre centros (deja 7 cm de sombra entre listones)


def crear_listones(puertas_deg):
    """Revestimiento de madera tipo riel: listones verticales del piso al
    arranque de la cupula, separados del muro negro, sin tapar las puertas
    (se deja libre el vano mas el marco)."""
    radio_liston = RADIO_DOMO - FONDO_LISTON / 2.0 - 0.005
    n = int(2.0 * math.pi * radio_liston / PASO_LISTON)
    margen_puerta = (ANCHO_PUERTA / 2.0 + GROSOR_MARCO * 2.0) / RADIO_DOMO
    puertas_rad = [math.radians(p) for p in puertas_deg]
    bm = bmesh.new()
    for i in range(n):
        ang = 2.0 * math.pi * i / n
        if any(abs(((ang - pr + math.pi) % (2.0 * math.pi)) - math.pi) <= margen_puerta for pr in puertas_rad):
            continue
        centro = Vector((radio_liston * math.cos(ang), radio_liston * math.sin(ang), 0.0))
        m = Matrix.Translation(centro) @ Matrix.Rotation(ang, 4, 'Z')
        agregar_caja(bm, (FONDO_LISTON, ANCHO_LISTON, ALTURA_PARED), (0.0, 0.0, 0.0), 0.0, m)
    obj = nuevo_objeto_desde_bmesh(bm, "SM_Listones")
    obj.data.materials.append(crear_material("M_Madera", (0.30, 0.17, 0.08), rugosidad=0.55))
    return obj


def construir_madera(mat):
    """Madera de veta vertical: ruido estirado en Z (vetas largas) mezclado
    entre dos tonos de roble, con bump suave de la misma veta."""
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    principled = nodes.get("Principled BSDF")
    coord = nodes.new("ShaderNodeTexCoord")
    mapeo = nodes.new("ShaderNodeMapping")
    mapeo.inputs["Scale"].default_value = (60.0, 60.0, 1.2)
    links.new(coord.outputs["Object"], mapeo.inputs["Vector"])
    veta = nodes.new("ShaderNodeTexNoise")
    veta.inputs["Scale"].default_value = 3.0
    veta.inputs["Detail"].default_value = 8.0
    links.new(mapeo.outputs["Vector"], veta.inputs["Vector"])
    rampa = nodes.new("ShaderNodeValToRGB")
    rampa.color_ramp.elements[0].color = (0.16, 0.08, 0.035, 1.0)
    rampa.color_ramp.elements[1].color = (0.42, 0.25, 0.12, 1.0)
    links.new(veta.outputs["Fac"], rampa.inputs["Fac"])
    links.new(rampa.outputs["Color"], principled.inputs["Base Color"])
    principled.inputs["Roughness"].default_value = 0.55
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.15
    links.new(veta.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], principled.inputs["Normal"])
    return mat


# ---------------------------------------------------------------------------
# CUPULA (media esfera o casquete) con UV equirectangular explicita
# ---------------------------------------------------------------------------

def uv_equirectangular(co, eps):
    """UV de un punto de la cupula en coordenadas locales (esfera centrada en
    el origen, radio RADIO_ESFERA). Es la convencion que lee Unreal y que
    espera el lienzo equirectangular 2:1 que manda TouchDesigner por Spout
    (04_Docs/04_Senal_TouchDesigner.md, seccion 3):

        U = azimut/360 + 0,5     U = 0,5 en +X (el frente de la sala), la
                                 costura U = 0/1 en -X (detras, zona de control)
        V = 0,5 + elevacion/180  V = 0,5 en el horizonte, 1 en el cenit: la
                                 cupula lee la MITAD SUPERIOR del lienzo

    Por que esta formula y no V = elevacion/90: la version anterior de este
    script escribia V = elevacion/90 en una capa nueva, pero
    primitive_uv_sphere_add ya traia una capa "UVMap" propia, asi que la
    nueva quedaba como "UVMap.001" (canal 1). Unreal muestrea el canal 0, o
    sea la UV por defecto de la esfera de Blender, que es exactamente esta
    (U con la costura en -X, V de 0 a 1 sobre la esfera COMPLETA, y por
    tanto 0,5..1 en la mitad superior). Medido el 17 sep 2026 leyendo el FBX
    exportado de vuelta (canal 0: U = 0,5 en +X, V = 0,75 a 45 grados) y
    en Unreal con el patron de bandas. Ahora la cupula se construye a mano y
    esta es la UNICA capa, con la formula que siempre se leyo en la practica.
    Para los casquetes NO se normaliza al casquete: V sigue siendo la
    elevacion absoluta, asi el mismo lienzo cae en el mismo sitio del cielo
    en los tres modelos (el domo 90 muestra solo V de 0,75 a 1)."""
    radio_xy = math.hypot(co.x, co.y)
    es_polo = radio_xy < eps
    azimut = math.atan2(co.y, co.x)
    u = (azimut / (2.0 * math.pi) + 0.5) % 1.0
    elevacion = math.asin(max(-1.0, min(1.0, co.z / RADIO_ESFERA)))
    v = 0.5 + elevacion / math.pi
    return u, max(0.5, min(1.0, v)), es_polo


def crear_domo():
    """Construye la cupula a mano con bmesh: SEGMENTOS_ELEVACION anillos de
    SEGMENTOS_AZIMUT vertices desde ELEVACION_MIN_DEG (0 en la media esfera,
    45 en el domo 90, 67,5 en el domo 45) hasta el cenit, mas el vertice de
    polo. Con FOV 180 los vertices coinciden con los de la media esfera de
    primitive_uv_sphere_add que usaba la version anterior (misma malla, mismo
    conteo de triangulos). Normales hacia adentro. UV segun uv_equirectangular,
    con correccion de costura en U=0/1 y promedio de U en el polo."""
    bm = bmesh.new()
    anillos = []
    for j in range(SEGMENTOS_ELEVACION):
        elev = _ELEV_MIN_RAD + (math.pi / 2.0 - _ELEV_MIN_RAD) * j / SEGMENTOS_ELEVACION
        r_xy = RADIO_ESFERA * math.cos(elev)
        z = RADIO_ESFERA * math.sin(elev)
        anillo = []
        for i in range(SEGMENTOS_AZIMUT):
            ang = 2.0 * math.pi * i / SEGMENTOS_AZIMUT
            anillo.append(bm.verts.new((r_xy * math.cos(ang), r_xy * math.sin(ang), z)))
        anillos.append(anillo)
    polo = bm.verts.new((0.0, 0.0, RADIO_ESFERA))
    bm.verts.ensure_lookup_table()

    for j in range(SEGMENTOS_ELEVACION - 1):
        for i in range(SEGMENTOS_AZIMUT):
            k = (i + 1) % SEGMENTOS_AZIMUT
            bm.faces.new((anillos[j][i], anillos[j][k], anillos[j + 1][k], anillos[j + 1][i]))
    for i in range(SEGMENTOS_AZIMUT):
        k = (i + 1) % SEGMENTOS_AZIMUT
        bm.faces.new((anillos[-1][i], anillos[-1][k], polo))

    bm.faces.ensure_lookup_table()
    bm.normal_update()
    # La sala se ve desde adentro: normales hacia el centro de la esfera.
    f0 = bm.faces[0]
    if f0.normal.dot(f0.calc_center_median()) > 0:
        voltear_normales(bm)

    eps = RADIO_ESFERA * 1e-4
    uv_layer = bm.loops.layers.uv.new("UVMap")
    for f in bm.faces:
        us_crudos, vs, es_polo = [], [], []
        for loop in f.loops:
            u, v, p = uv_equirectangular(loop.vert.co, eps)
            us_crudos.append(u)
            vs.append(v)
            es_polo.append(p)

        us_validos = [u for u, p in zip(us_crudos, es_polo) if not p]
        us_corregidos = list(us_crudos)
        if us_validos and (max(us_validos) - min(us_validos) > 0.5):
            for i, (u, p) in enumerate(zip(us_crudos, es_polo)):
                if not p and u < 0.5:
                    us_corregidos[i] = u + 1.0

        no_polo_corregidos = [u for u, p in zip(us_corregidos, es_polo) if not p]
        promedio = sum(no_polo_corregidos) / len(no_polo_corregidos) if no_polo_corregidos else 0.0

        for loop, u, v, p in zip(f.loops, us_corregidos, vs, es_polo):
            loop[uv_layer].uv = (promedio if p else u, v)

    obj = nuevo_objeto_desde_bmesh(bm, "SM_Domo")
    obj.location = (0, 0, Z_CENTRO_ESFERA)

    obj.data.materials.append(
        crear_material("M_Domo", (0.6, 0.6, 0.65), emision_color=(0.5, 0.55, 0.65), emision_fuerza=1.2)
    )
    mat = obj.data.materials[0]
    nodos = mat.node_tree.nodes
    enlaces = mat.node_tree.links
    nodo_uv = nodos.new("ShaderNodeUVMap")
    nodo_uv.uv_map = "UVMap"
    nodo_checker = nodos.new("ShaderNodeTexChecker")
    nodo_checker.inputs["Scale"].default_value = 24.0
    principled = nodos.get("Principled BSDF")
    enlaces.new(nodo_uv.outputs["UV"], nodo_checker.inputs["Vector"])
    enlaces.new(nodo_checker.outputs["Color"], principled.inputs["Base Color"])
    enlaces.new(nodo_checker.outputs["Color"], principled.inputs["Emission Color"])

    return obj


# ---------------------------------------------------------------------------
# TARIMA CENTRAL
# ---------------------------------------------------------------------------

def crear_tarima():
    bpy.ops.mesh.primitive_cylinder_add(
        radius=RADIO_TARIMA, depth=ALTURA_TARIMA, vertices=64,
        location=(0, 0, ALTURA_TARIMA / 2.0),
    )
    obj = bpy.context.active_object
    obj.name = "SM_Tarima"
    obj.data.materials.append(crear_material("M_Tarima", (0.08, 0.08, 0.09), rugosidad=0.4, metalico=0.7))
    return obj


# ---------------------------------------------------------------------------
# BUTACAS
# ---------------------------------------------------------------------------

def calcular_filas(angulo_util_rad):
    """Igual que antes: sin numeros de fila escritos a mano. El arco
    disponible en cada radio (angulo_util_rad, que ahora depende del arco
    que le toco a la cuna despues de descontar el sector de control) se
    divide entre PASO_BUTACA. Se van sumando filas hasta llegar EXACTO a
    BUTACAS_POR_MODULO; la ultima se recorta a lo que falte."""
    filas = []
    radio = RADIO_INTERIOR_BUTACAS
    total = 0
    while total < BUTACAS_POR_MODULO:
        arco_disponible = angulo_util_rad * radio
        n = max(1, math.floor(arco_disponible / PASO_BUTACA))
        restante = BUTACAS_POR_MODULO - total
        if n >= restante:
            n = restante
        filas.append({"radio": radio, "n": n})
        total += n
        radio += PASO_FILA_RADIAL
    return filas


def agregar_caja(bm, dimensiones, posicion_local, rotacion_local_grados, matriz_mundo):
    dx, dy, dz = dimensiones
    ret = bmesh.ops.create_cube(bm, size=1.0)
    verts = ret["verts"]
    bmesh.ops.scale(bm, vec=(dx, dy, dz), verts=verts)
    bmesh.ops.translate(bm, vec=(0, 0, dz / 2.0), verts=verts)
    if rotacion_local_grados:
        mat_rot = Matrix.Rotation(math.radians(rotacion_local_grados), 4, 'Y')
        bmesh.ops.transform(bm, matrix=mat_rot, verts=verts)
    bmesh.ops.translate(bm, vec=posicion_local, verts=verts)
    bmesh.ops.transform(bm, matrix=matriz_mundo, verts=verts)
    return verts


def agregar_butaca(bm, matriz_mundo):
    """Butaca reclinada de domo, piso plano (sin grada): base, asiento
    inclinado hacia atras, respaldo MUY echado (63 grados desde la
    vertical por defecto, editable arriba), reposacabezas al final del
    respaldo, y dos apoyabrazos. Todo cajas: 6 x 12 = 72 triangulos por
    butaca, muy por debajo del limite de ~200."""
    alto_asiento_z = ALTO_BASE
    # Convencion: +X local es el frente (hacia la tarima). En agregar_caja
    # un angulo positivo en Y inclina la pieza hacia +X; por eso el asiento
    # y el respaldo usan angulos NEGATIVOS, para caer hacia atras.

    agregar_caja(
        bm, (PROFUNDIDAD_ASIENTO * 0.75, ANCHO_ASIENTO * 0.75, ALTO_BASE - GROSOR_PANEL),
        (0.0, 0.0, 0.0), 0.0, matriz_mundo,
    )
    agregar_caja(
        bm, (PROFUNDIDAD_ASIENTO, ANCHO_ASIENTO, GROSOR_PANEL),
        (0.0, 0.0, alto_asiento_z), -ANGULO_INCLINACION_ASIENTO, matriz_mundo,
    )

    borde_trasero_x = -PROFUNDIDAD_ASIENTO / 2.0
    agregar_caja(
        bm, (GROSOR_PANEL, ANCHO_ASIENTO, ALTURA_RESPALDO),
        (borde_trasero_x, 0.0, alto_asiento_z), -ANGULO_RECLINACION_RESPALDO, matriz_mundo,
    )

    angulo_rad = math.radians(ANGULO_RECLINACION_RESPALDO)
    punta_respaldo_x = borde_trasero_x - ALTURA_RESPALDO * math.sin(angulo_rad)
    punta_respaldo_z = alto_asiento_z + ALTURA_RESPALDO * math.cos(angulo_rad)
    agregar_caja(
        bm, (GROSOR_PANEL * 1.4, ANCHO_ASIENTO * 0.55, ALTURA_REPOSACABEZAS),
        (punta_respaldo_x, 0.0, punta_respaldo_z), -ANGULO_RECLINACION_RESPALDO, matriz_mundo,
    )

    for signo in (+1.0, -1.0):
        y = signo * (ANCHO_ASIENTO / 2.0 - ANCHO_APOYABRAZOS / 2.0)
        agregar_caja(
            bm, (LARGO_APOYABRAZOS, ANCHO_APOYABRAZOS, ALTO_APOYABRAZOS),
            (0.0, y, alto_asiento_z), 0.0, matriz_mundo,
        )


def crear_modulo_butacas(indice_modulo, filas, angulo_util_rad, angulo_centro_deg, mat_butaca):
    """Coloca las butacas de una cuna. El paso lateral usa PASO_BUTACA real
    (metros) convertido a radianes segun el radio de cada fila, en vez de
    repartir angulo_util_rad en partes iguales: asi la separacion entre
    butacas es fisicamente constante en todas las filas (no se estira en
    las filas de adentro), y el limite izquierdo/derecho de cada fila cae
    siempre muy cerca de +-angulo_util_rad/2, dando cuadros con los dos
    costados rectos y radiales (una cuna real, no bandas concentricas)."""
    angulo_centro = math.radians(angulo_centro_deg)
    bm = bmesh.new()
    contador = 0
    for fila in filas:
        radio = fila["radio"]
        n = fila["n"]
        if n == 1:
            offsets = [0.0]
        else:
            paso_angular = PASO_BUTACA / radio
            offsets = [(i - (n - 1) / 2.0) * paso_angular for i in range(n)]

        for offset in offsets:
            angulo_asiento = angulo_centro + offset
            centro = Vector((radio * math.cos(angulo_asiento), radio * math.sin(angulo_asiento), 0.0))
            matriz_mundo = Matrix.Translation(centro) @ Matrix.Rotation(angulo_asiento + math.pi, 4, 'Z')
            agregar_butaca(bm, matriz_mundo)
            contador += 1

    nombre = f"SM_Butacas_{indice_modulo + 1:02d}"
    obj = nuevo_objeto_desde_bmesh(bm, nombre)
    obj.data.materials.append(mat_butaca)
    return obj, contador


def crear_todas_las_butacas(layout, mat_butaca):
    angulo_util_rad = math.radians(layout["angulo_modulo_efectivo_deg"] - 2.0 * ANGULO_PASILLO_DEG)
    filas = calcular_filas(angulo_util_rad)

    print("\n--- Reparto de filas por cuna (igual en las 6 cunas; piso plano, sin grada) ---")
    print(f"ancho efectivo de cuna: {layout['angulo_modulo_efectivo_deg']:.2f} grados "
          f"(arco libre 360 - {layout['angulo_control_deg']:.2f} de control, entre 6)")
    print(f"{'fila':>4} {'radio(m)':>9} {'butacas':>8}")
    total_modulo = 0
    for i, f in enumerate(filas):
        print(f"{i + 1:>4} {f['radio']:>9.2f} {f['n']:>8d}")
        total_modulo += f["n"]
    print(f"Total por cuna: {total_modulo}  (esperado {BUTACAS_POR_MODULO})")

    objetos = []
    total_general = 0
    for m in range(NUM_MODULOS):
        obj, n = crear_modulo_butacas(m, filas, angulo_util_rad, layout["centros_cunas_deg"][m], mat_butaca)
        objetos.append(obj)
        total_general += n

    print(f"Total general de butacas (6 cunas): {total_general}  (esperado {TOTAL_BUTACAS})")
    assert total_general == TOTAL_BUTACAS, "El reparto de filas no dio el total esperado."
    return objetos


# ---------------------------------------------------------------------------
# SECTOR DE CONTROL (dentro de la sala, contra el muro en -X)
# ---------------------------------------------------------------------------

def crear_zona_control(layout, mat_control):
    """SM_Control = mobiliario (consola + cuerpo + panel de monitores) mas
    un parche de piso que marca el sector, todo dentro de la sala (ver
    supuesto documentado arriba del archivo: ya no es un anexo exterior)."""
    ang_ini = math.radians(layout["angulo_control_ini_deg"])
    ang_fin = ang_ini + math.radians(layout["angulo_control_deg"])
    ang_centro = math.radians(ANGULO_CENTRO_CONTROL_DEG)

    bm = bmesh.new()

    # Parche de piso que marca el sector (un poco por encima del piso
    # general para que no compita en z-fighting).
    r_in, r_out = RADIO_INICIO_CONTROL, RADIO_DOMO - 0.4
    n_sub = 16
    anillo_in, anillo_out = [], []
    for i in range(n_sub + 1):
        t = ang_ini + (ang_fin - ang_ini) * i / n_sub
        anillo_in.append(bm.verts.new((r_in * math.cos(t), r_in * math.sin(t), 0.01)))
        anillo_out.append(bm.verts.new((r_out * math.cos(t), r_out * math.sin(t), 0.01)))
    bm.verts.ensure_lookup_table()
    for i in range(n_sub):
        bm.faces.new((anillo_in[i], anillo_out[i], anillo_out[i + 1], anillo_in[i + 1]))
    bm.faces.ensure_lookup_table()
    bm.normal_update()
    if bm.faces[0].normal.z < 0:
        voltear_normales(bm)

    # Consola de operacion, mirando hacia el centro de la sala (igual
    # convencion que las butacas).
    radio_consola = RADIO_DOMO - 2.3
    centro_consola = Vector((radio_consola * math.cos(ang_centro), radio_consola * math.sin(ang_centro), 0.0))
    matriz_consola = Matrix.Translation(centro_consola) @ Matrix.Rotation(ang_centro + math.pi, 4, 'Z')

    ancho_mueble = ANCHO_CONTROL * 0.7
    agregar_caja(bm, (0.80, ancho_mueble, 0.05), (0.0, 0.0, 0.75), 0.0, matriz_consola)        # tablero
    agregar_caja(bm, (0.60, ancho_mueble * 0.95, 0.70), (-0.10, 0.0, 0.0), 0.0, matriz_consola)  # cuerpo bajo mesa
    agregar_caja(bm, (0.10, ancho_mueble * 0.9, 0.50), (-0.30, 0.0, 0.80), 0.0, matriz_consola)  # fila de monitores
    # Rack de equipos contra el muro, detras del operador.
    agregar_caja(bm, (0.60, ancho_mueble * 0.5, 1.90), (-1.55, 0.0, 0.0), 0.0, matriz_consola)

    # Antepecho curvo (1 m de alto) que separa el control de las butacas.
    n_ant = 14
    for i in range(n_ant):
        t0 = ang_ini + (ang_fin - ang_ini) * i / n_ant
        t1 = ang_ini + (ang_fin - ang_ini) * (i + 1) / n_ant
        tm = (t0 + t1) / 2.0
        largo = 2.0 * r_in * math.sin((t1 - t0) / 2.0)
        centro = Vector((r_in * math.cos(tm), r_in * math.sin(tm), 0.0))
        m = Matrix.Translation(centro) @ Matrix.Rotation(tm, 4, 'Z')
        agregar_caja(bm, (0.08, largo, 1.0), (0.0, 0.0, 0.0), 0.0, m)

    obj = nuevo_objeto_desde_bmesh(bm, "SM_Control")
    obj.data.materials.append(mat_control)
    return obj


# ---------------------------------------------------------------------------
# PUERTAS
# ---------------------------------------------------------------------------

def crear_puerta(indice, angulo_deg, mat_puerta):
    ang = math.radians(angulo_deg)
    centro_pared = Vector((RADIO_DOMO * math.cos(ang), RADIO_DOMO * math.sin(ang), 0.0))
    matriz_mundo = Matrix.Translation(centro_pared) @ Matrix.Rotation(ang, 4, 'Z')

    bm = bmesh.new()
    for signo in (+1.0, -1.0):
        y = signo * (ANCHO_PUERTA / 2.0 + GROSOR_MARCO / 2.0)
        agregar_caja(bm, (GROSOR_MARCO * 1.5, GROSOR_MARCO, ALTURA_PUERTA + GROSOR_MARCO),
                     (0.0, y, 0.0), 0.0, matriz_mundo)
    agregar_caja(bm, (GROSOR_MARCO * 1.5, ANCHO_PUERTA + GROSOR_MARCO * 2.0, GROSOR_MARCO),
                 (0.0, 0.0, ALTURA_PUERTA), 0.0, matriz_mundo)
    agregar_caja(bm, (GROSOR_HOJA, ANCHO_PUERTA * 0.94, ALTURA_PUERTA * 0.96),
                 (0.0, 0.0, 0.0), 0.0, matriz_mundo)

    nombre = f"SM_Puerta_{indice + 1:02d}"
    obj = nuevo_objeto_desde_bmesh(bm, nombre)
    obj.data.materials.append(mat_puerta)
    return obj


def crear_todas_las_puertas(layout, mat_puerta):
    objetos = [crear_puerta(i, ang, mat_puerta) for i, ang in enumerate(layout["puertas_deg"])]
    print(f"\nPuertas colocadas en (grados): {[round(a, 1) for a in layout['puertas_deg']]}"
          f" -> las 2 primeras flanquean el sector de control, las otras 2 en el resto del muro.")
    return objetos


# ---------------------------------------------------------------------------
# HORNEADO DE TEXTURAS PBR
# ---------------------------------------------------------------------------

def hornear_material_pbr(obj, material, nombre_archivo):
    """Hornea Base Color / Roughness / Normal del material a PNG de
    RESOLUCION_TEXTURA x RESOLUCION_TEXTURA usando Cycles (motor de
    horneado disponible en esta version), y reconecta el material para
    que el Principled BSDF quede leyendo esas texturas horneadas en vez
    del grafo procedural: asi el FBX/glTF exportado sale con archivos de
    imagen reales, no con nodos procedurales que Unreal no puede leer."""
    os.makedirs(CARPETA_TEXTURAS, exist_ok=True)
    desenvolver_uv_cube(obj)

    motor_anterior = bpy.context.scene.render.engine
    bpy.context.scene.render.engine = 'CYCLES'
    bpy.context.scene.cycles.samples = MUESTRAS_HORNEADO
    for o in bpy.context.selected_objects:
        o.select_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj

    nodes = material.node_tree.nodes
    especificaciones = [
        ("BaseColor", 'DIFFUSE', {'COLOR'}, False),
        ("Roughness", 'ROUGHNESS', None, True),
        ("Normal", 'NORMAL', None, True),
    ]
    resultados = {}
    for sufijo, tipo_bake, pass_filter, sin_color in especificaciones:
        img = bpy.data.images.new(f"{nombre_archivo}_{sufijo}", RESOLUCION_TEXTURA, RESOLUCION_TEXTURA, alpha=False)
        img.colorspace_settings.name = 'Non-Color' if sin_color else 'sRGB'
        nodo_img = nodes.new("ShaderNodeTexImage")
        nodo_img.image = img
        for n in nodes:
            n.select = False
        nodo_img.select = True
        nodes.active = nodo_img
        if pass_filter:
            bpy.ops.object.bake(type=tipo_bake, pass_filter=pass_filter, margin=6)
        else:
            bpy.ops.object.bake(type=tipo_bake, margin=6)
        ruta = os.path.join(CARPETA_TEXTURAS, f"{nombre_archivo}_{sufijo}.png")
        img.filepath_raw = ruta
        img.file_format = 'PNG'
        img.save()
        resultados[sufijo] = (img, nodo_img)

    principled = nodes.get("Principled BSDF")
    links = material.node_tree.links
    nodo_uv = nodes.new("ShaderNodeUVMap")
    for _, nodo_img in resultados.values():
        links.new(nodo_uv.outputs["UV"], nodo_img.inputs["Vector"])
    links.new(resultados["BaseColor"][1].outputs["Color"], principled.inputs["Base Color"])
    links.new(resultados["Roughness"][1].outputs["Color"], principled.inputs["Roughness"])
    nodo_normal_map = nodes.new("ShaderNodeNormalMap")
    links.new(resultados["Normal"][1].outputs["Color"], nodo_normal_map.inputs["Color"])
    links.new(nodo_normal_map.outputs["Normal"], principled.inputs["Normal"])

    bpy.context.scene.render.engine = motor_anterior
    print(f"Texturas horneadas: {material.name} -> {CARPETA_TEXTURAS}\\{nombre_archivo}_[BaseColor|Roughness|Normal].png")


def hornear_todas_las_texturas(piso, muro, butaca_rep, tarima, puerta_rep, listones):
    """Con HORNEAR_TEXTURAS apagado (casquetes) solo se desenvuelve el UV de
    las mismas piezas, para que el FBX salga con UV valido igual que en la
    media esfera; las texturas PNG ya existen de la corrida del 180."""
    piezas = [
        (piso, "M_Piso"), (muro, "M_Muro"), (butaca_rep, "M_Butaca"),
        (tarima, "M_Tarima"), (puerta_rep, "M_Puerta"), (listones, "M_Madera"),
    ]
    for obj, nombre in piezas:
        if HORNEAR_TEXTURAS:
            hornear_material_pbr(obj, obj.data.materials[0], nombre)
        else:
            desenvolver_uv_cube(obj)
    if not HORNEAR_TEXTURAS:
        print("Horneado de texturas omitido (FOV {:g}); se reutilizan las PNG de {}".format(
            FOV_DOMO, CARPETA_TEXTURAS))


# ---------------------------------------------------------------------------
# TRANSFORMACIONES, EXPORT Y VERIFICACION
# ---------------------------------------------------------------------------

def aplicar_transformaciones(objetos):
    bpy.ops.object.select_all(action='DESELECT')
    for obj in objetos:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objetos[0]
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)


def exportar_fbx(objetos):
    bpy.ops.object.select_all(action='DESELECT')
    for obj in objetos:
        obj.select_set(True)
    bpy.ops.export_scene.fbx(
        filepath=RUTA_FBX, use_selection=True, object_types={'MESH'},
        global_scale=1.0, apply_unit_scale=True, apply_scale_options='FBX_SCALE_ALL',
        bake_space_transform=True, axis_forward='-Z', axis_up='Y',
        mesh_smooth_type='FACE', use_mesh_modifiers=True, use_triangles=False,
        path_mode='COPY', embed_textures=False,
    )


def exportar_glb(objetos):
    bpy.ops.object.select_all(action='DESELECT')
    for obj in objetos:
        obj.select_set(True)
    bpy.ops.export_scene.gltf(
        filepath=RUTA_GLB, export_format='GLB', use_selection=True,
        export_cameras=False, export_lights=False, export_apply=True, export_yup=True,
    )


def verificar_export():
    escena_verificacion = bpy.data.scenes.new("Verificacion_FBX")
    escena_anterior = bpy.context.window.scene
    bpy.context.window.scene = escena_verificacion

    antes = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=RUTA_FBX)
    importados = [o for o in bpy.data.objects if o not in antes]

    def dimensiones(obj):
        pts = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
        xs = [p.x for p in pts]; ys = [p.y for p in pts]; zs = [p.z for p in pts]
        return (max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))

    print("\n--- Verificacion leyendo el FBX exportado de vuelta ---")
    for nombre in ("SM_Domo", "SM_Muro", "SM_Butacas_01", "SM_Tarima"):
        obj = bpy.data.objects.get(nombre)
        if obj is None:
            print(f"{nombre}: NO SE ENCONTRO EN EL FBX IMPORTADO")
            continue
        dx, dy, dz = dimensiones(obj)
        print(f"{nombre}: X={dx:.3f} m  Y={dy:.3f} m  Z={dz:.3f} m")
        if nombre == "SM_Domo":
            diametro_esperado = RADIO_DOMO * 2.0
            ok = abs(dx - diametro_esperado) < 0.05 and abs(dy - diametro_esperado) < 0.05
            print(f"  diametro esperado {diametro_esperado:.2f} m -> {'OK' if ok else 'DESAJUSTADO'}")
            ok_z = abs(dz - SAGITA_DOMO) < 0.05
            print(f"  altura de cupula (sagita) esperada {SAGITA_DOMO:.2f} m -> {'OK' if ok_z else 'DESAJUSTADO'}")
            capas = [l.name for l in obj.data.uv_layers]
            vs = [d.uv.y for d in obj.data.uv_layers[0].data]
            print(f"  capas UV: {capas} (Unreal lee la primera); V del canal 0 de {min(vs):.3f} a {max(vs):.3f}"
                  f" (esperado {0.5 + ELEVACION_MIN_DEG / 180.0:.3f} a 1.000)")
        if nombre == "SM_Muro":
            ok = abs(dz - ALTURA_PARED) < 0.05
            print(f"  altura de muro esperada {ALTURA_PARED:.2f} m -> {'OK' if ok else 'DESAJUSTADO'}")

    for obj in importados:
        bpy.data.objects.remove(obj, do_unlink=True)
    bpy.context.window.scene = escena_anterior
    bpy.data.scenes.remove(escena_verificacion)


# ---------------------------------------------------------------------------
# PREVISUALIZACION CON EEVEE
# ---------------------------------------------------------------------------

def apuntar_camara(cam_obj, objetivo):
    direccion = (objetivo - cam_obj.location)
    cam_obj.rotation_euler = direccion.to_track_quat('-Z', 'Y').to_euler()


def preparar_render():
    escena = bpy.context.scene
    escena.render.engine = 'BLENDER_EEVEE'
    escena.render.resolution_x = RES_X
    escena.render.resolution_y = RES_Y
    escena.render.image_settings.file_format = 'PNG'
    escena.view_settings.view_transform = 'Standard'

    sol = bpy.data.lights.new("Sol_Preview", type='SUN')
    sol.energy = 2.5
    obj_sol = bpy.data.objects.new("Sol_Preview", sol)
    obj_sol.rotation_euler = (math.radians(55), 0, math.radians(35))
    bpy.context.collection.objects.link(obj_sol)

    relleno = bpy.data.lights.new("Relleno_Preview", type='AREA')
    relleno.energy = 400.0
    relleno.size = RADIO_DOMO
    obj_relleno = bpy.data.objects.new("Relleno_Preview", relleno)
    obj_relleno.location = (0, 0, ALTURA_PARED + SAGITA_DOMO * 0.6)
    bpy.context.collection.objects.link(obj_relleno)

    cam_data = bpy.data.cameras.new("Camara_Preview")
    cam_obj = bpy.data.objects.new("Camara_Preview", cam_data)
    bpy.context.collection.objects.link(cam_obj)
    escena.camera = cam_obj
    return cam_obj


def renderizar_vistas(cam_obj, domo_obj, layout):
    escena = bpy.context.scene

    # 1) Planta cenital: se oculta la cupula (es opaca y taparia todo desde
    # arriba) para poder ver piso, tarima, cunas, sector de control y
    # puertas en planta.
    domo_obj.hide_render = True
    cam_obj.data.type = 'ORTHO'
    cam_obj.data.ortho_scale = RADIO_DOMO * 2.2
    cam_obj.location = (0, 0, ALTURA_CENIT + 4.0)
    apuntar_camara(cam_obj, Vector((0, 0, 0)))
    escena.render.filepath = ruta_preview("vista_planta_cenital")
    bpy.ops.render.render(write_still=True)
    domo_obj.hide_render = False

    # 2) Vista desde una butaca mirando hacia el cenit: ojo calculado a lo
    # largo del respaldo reclinado (no a la altura del asiento, ahi
    # quedaria pegado al apoyabrazos vecino).
    filas_ref = calcular_filas(math.radians(layout["angulo_modulo_efectivo_deg"] - 2 * ANGULO_PASILLO_DEG))
    fila_ref = filas_ref[len(filas_ref) // 2]
    angulo_rad = math.radians(ANGULO_RECLINACION_RESPALDO)
    borde_trasero_x = -PROFUNDIDAD_ASIENTO / 2.0
    d_ojo, avance_ojo = 0.55, 0.18
    ojo_local_x = borde_trasero_x - math.sin(angulo_rad) * d_ojo + avance_ojo
    ojo_local_z = ALTO_BASE + math.cos(angulo_rad) * d_ojo
    cam_obj.data.type = 'PERSP'
    cam_obj.data.lens = 20.0
    cam_obj.location = (fila_ref["radio"] - ojo_local_x, 0.0, ojo_local_z)
    apuntar_camara(cam_obj, Vector((0.0, 0.0, ALTURA_CENIT - RADIO_DOMO * 0.2)))
    cam_obj.rotation_euler.x -= math.radians(12)
    escena.render.filepath = ruta_preview("vista_desde_butaca")
    bpy.ops.render.render(write_still=True)

    # 3) Vista general en perspectiva, desde dentro de la sala.
    cam_obj.data.lens = 16.0
    cam_obj.location = (1.0, -1.0, ALTURA_ARRANQUE + 2.2)
    apuntar_camara(cam_obj, Vector((RADIO_DOMO * 0.75, RADIO_DOMO * 0.75, 0.5)))
    escena.render.filepath = ruta_preview("vista_general_perspectiva")
    bpy.ops.render.render(write_still=True)

    # 4) Vista hacia el sector de control, desde el lado opuesto de la
    # sala, para que entren en cuadro las dos puertas que lo flanquean.
    cam_obj.data.lens = 20.0
    cam_obj.location = (6.5, 0.0, 1.6)
    ang_centro_control = math.radians(ANGULO_CENTRO_CONTROL_DEG)
    objetivo_control = Vector((8.5 * math.cos(ang_centro_control), 8.5 * math.sin(ang_centro_control), 1.4))
    apuntar_camara(cam_obj, objetivo_control)
    escena.render.filepath = ruta_preview("vista_zona_control")
    bpy.ops.render.render(write_still=True)


# ---------------------------------------------------------------------------
# REPORTE DE POLIGONOS
# ---------------------------------------------------------------------------

def contar_triangulos(obj):
    malla = obj.data
    malla.calc_loop_triangles()
    return len(malla.loop_triangles)


def reportar_poligonos(objetos_relevantes):
    print("\n--- Conteo de triangulos ---")
    total = 0
    for obj in objetos_relevantes:
        n = contar_triangulos(obj)
        total += n
        etiqueta = ""
        if obj.name.startswith("SM_Butacas_"):
            etiqueta = f"  ({n / BUTACAS_POR_MODULO:.0f} tris/butaca)"
        print(f"{obj.name}: {n} triangulos{etiqueta}")
    print(f"TOTAL escena: {total} triangulos")


# ---------------------------------------------------------------------------
# PROGRAMA PRINCIPAL
# ---------------------------------------------------------------------------

def main():
    limpiar_escena()

    print("\n=== Modelo de sala: FOV {:g} ({}) ===".format(
        FOV_DOMO, "media esfera" if ES_MEDIA_ESFERA else "casquete esferico"))
    print("radio del muro {:.2f} m | borde de cupula a {:.1f} grados de elevacion | "
          "radio de esfera {:.2f} m | muro de {:.2f} m | cupula de {:.2f} m de alto | "
          "cenit a {:.2f} m | centro de esfera en z={:.2f} m".format(
              RADIO_DOMO, ELEVACION_MIN_DEG, RADIO_ESFERA, ALTURA_PARED, SAGITA_DOMO,
              ALTURA_CENIT, Z_CENTRO_ESFERA))
    print("salida: {}.fbx / .glb / .blend, previews con sufijo '{}'".format(NOMBRE_SALIDA, SUFIJO_MODELO))

    layout = calcular_layout_sala()
    print(f"Sector de control: {layout['angulo_control_deg']:.2f} grados de arco "
          f"({layout['angulo_control_ini_deg']:.1f} a {layout['angulo_control_fin_deg']:.1f})")

    mat_butaca = crear_material("M_Butaca", (0.06, 0.06, 0.065), rugosidad=0.9)
    mat_puerta = crear_material("M_Puerta", (0.5, 0.5, 0.52), rugosidad=0.35, metalico=0.85)
    mat_control = crear_material("M_Control", (0.08, 0.09, 0.12), rugosidad=0.4, metalico=0.2)

    construir_variacion_procedural(mat_butaca, (0.04, 0.04, 0.045), (0.085, 0.085, 0.09), 40.0, 0.90, 0.05, 0.0, 0.08)
    construir_variacion_procedural(mat_puerta, (0.35, 0.35, 0.37), (0.55, 0.55, 0.58), 5.0, 0.30, 0.15, 0.9, 0.06)

    piso = crear_piso()
    construir_variacion_procedural(piso.data.materials[0], (0.02, 0.02, 0.02), (0.09, 0.085, 0.08), 6.0, 0.85, 0.1, 0.0, 0.12)

    muro = crear_muro(layout["puertas_deg"])
    construir_variacion_procedural(muro.data.materials[0], (0.015, 0.015, 0.018), (0.05, 0.05, 0.055), 10.0, 0.82, 0.08, 0.0, 0.25)
    listones = crear_listones(layout["puertas_deg"])
    construir_madera(listones.data.materials[0])

    domo = crear_domo()
    tarima = crear_tarima()
    construir_variacion_procedural(tarima.data.materials[0], (0.05, 0.05, 0.06), (0.12, 0.12, 0.14), 8.0, 0.35, 0.15, 0.85, 0.10)

    modulos_butacas = crear_todas_las_butacas(layout, mat_butaca)
    zona_control = crear_zona_control(layout, mat_control)
    puertas = crear_todas_las_puertas(layout, mat_puerta)

    todos_los_objetos = [piso, muro, listones, domo, tarima, zona_control] + modulos_butacas + puertas
    reportar_poligonos(todos_los_objetos)

    print(f"\nConteo de objetos en la escena: {len(todos_los_objetos)}")
    print(f"Conteo de butacas totales: {TOTAL_BUTACAS} (en {NUM_MODULOS} cunas de {BUTACAS_POR_MODULO})")

    # Horneado de texturas PBR (una sola vez por material compartido; solo
    # en la media esfera, ver HORNEAR_TEXTURAS).
    hornear_todas_las_texturas(piso, muro, modulos_butacas[0], tarima, puertas[0], listones)

    aplicar_transformaciones(todos_los_objetos)

    exportar_fbx(todos_los_objetos)
    exportar_glb(todos_los_objetos)

    cam_obj = preparar_render()
    renderizar_vistas(cam_obj, domo, layout)

    bpy.ops.wm.save_as_mainfile(filepath=RUTA_BLEND)

    verificar_export()

    print("\nListo: {0}.blend, {0}.fbx, {0}.glb{1} y 4 PNG de previsualizacion generados.".format(
        NOMBRE_SALIDA, ", texturas PBR" if HORNEAR_TEXTURAS else ""))


if __name__ == "__main__":
    main()
