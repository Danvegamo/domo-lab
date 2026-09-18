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

MODELOS DE SALA (ver 04_Docs/05_Modelos_de_sala.md):

    --fov 180  media esfera (planetario clasico, butacas concentricas). Salida
               sin sufijo (sala_domo.fbx, sala_domo.blend, vista_*.png) para
               no romper nada de lo que ya consume esos nombres.
    --fov 45   SALA FRONTAL tipo Cine Domo de Maloka / IMAX Dome: pantalla de
               180 grados de 22 m inclinada 27 grados hacia el frente, grada
               tipo estadio con 314 butacas reclinadas mirando a +X.
    --fov 90   SALA FRONTAL de pie tipo museo / parque: pantalla de 180 grados
               de 20 m inclinada 45 grados, plataformas escalonadas con
               barandas, publico de pie mirando a +X.
               Los numeros 45 y 90 son claves del modelo (heredadas de los
               casquetes que generaba antes), no el FOV: ver SALAS_FRONTALES
               y main_frontal(). Salida con sufijo: sala_domo_45.fbx,
               sala_domo_90.blend, 02_Export/sala_domo_90.json (datos que lee
               importar_sala.py), vista_planta_cenital_90.png, etc.
    otro N     casquete horizontal que cubre de 90 - N/2 grados al cenit (el
               comportamiento que tenian el 45 y el 90 hasta el 18 sep 2026).

Todo lo que sigue sobre casquetes, muro cilindrico, cunas, puertas en el
cilindro y horneado vale para el 180 y para los casquetes de otro N; las
salas frontales tienen su propia seccion (SALAS FRONTALES, casi al final).

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

def uv_equirectangular(co, eps, radio=None):
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
    en los tres modelos (el domo 90 muestra solo V de 0,75 a 1).

    Las salas frontales (modelos 45 y 90, ver SALAS_FRONTALES) llaman esta
    misma funcion con su propio radio y ANTES de inclinar la cupula: la UV
    queda en el marco propio de la pantalla (su arranque es el horizonte de
    la UV), que es lo que espera un domemaster de 180 grados."""
    if radio is None:
        radio = RADIO_ESFERA
    radio_xy = math.hypot(co.x, co.y)
    es_polo = radio_xy < eps
    azimut = math.atan2(co.y, co.x)
    u = (azimut / (2.0 * math.pi) + 0.5) % 1.0
    elevacion = math.asin(max(-1.0, min(1.0, co.z / radio)))
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
    bm = construir_bmesh_cupula(RADIO_ESFERA, _ELEV_MIN_RAD)
    obj = nuevo_objeto_desde_bmesh(bm, "SM_Domo")
    obj.location = (0, 0, Z_CENTRO_ESFERA)
    _material_domo_checker(obj)
    return obj


def _material_domo_checker(obj):
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


def construir_bmesh_cupula(radio_esfera, elev_min_rad):
    """Malla de la cupula centrada en el origen de su esfera, polo en +Z,
    frente (U = 0,5) en +X, normales hacia adentro y una sola capa UV
    ("UVMap", canal 0) segun uv_equirectangular. Devuelve el bmesh sin
    convertir a objeto, para que las salas frontales lo puedan inclinar."""
    bm = bmesh.new()
    anillos = []
    for j in range(SEGMENTOS_ELEVACION):
        elev = elev_min_rad + (math.pi / 2.0 - elev_min_rad) * j / SEGMENTOS_ELEVACION
        r_xy = radio_esfera * math.cos(elev)
        z = radio_esfera * math.sin(elev)
        anillo = []
        for i in range(SEGMENTOS_AZIMUT):
            ang = 2.0 * math.pi * i / SEGMENTOS_AZIMUT
            anillo.append(bm.verts.new((r_xy * math.cos(ang), r_xy * math.sin(ang), z)))
        anillos.append(anillo)
    polo = bm.verts.new((0.0, 0.0, radio_esfera))
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

    eps = radio_esfera * 1e-4
    uv_layer = bm.loops.layers.uv.new("UVMap")
    for f in bm.faces:
        us_crudos, vs, es_polo = [], [], []
        for loop in f.loops:
            u, v, p = uv_equirectangular(loop.vert.co, eps, radio_esfera)
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

    return bm


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


def agregar_butaca(bm, matriz_mundo, reclinacion_deg=None, inclinacion_asiento_deg=None,
                   altura_respaldo=None):
    """Butaca reclinada de domo, piso plano (sin grada): base, asiento
    inclinado hacia atras, respaldo MUY echado (63 grados desde la
    vertical por defecto, editable arriba), reposacabezas al final del
    respaldo, y dos apoyabrazos. Todo cajas: 6 x 12 = 72 triangulos por
    butaca, muy por debajo del limite de ~200. Los tres parametros
    opcionales los usa la sala 45 (butaca tipo IMAX Dome, menos echada);
    sin ellos la butaca es la de siempre."""
    ANGULO_RECLINACION_RESPALDO = reclinacion_deg if reclinacion_deg is not None else globals()["ANGULO_RECLINACION_RESPALDO"]
    ANGULO_INCLINACION_ASIENTO = (inclinacion_asiento_deg if inclinacion_asiento_deg is not None
                                  else globals()["ANGULO_INCLINACION_ASIENTO"])
    ALTURA_RESPALDO = altura_respaldo if altura_respaldo is not None else globals()["ALTURA_RESPALDO"]
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
    return crear_puerta_en(indice, matriz_mundo, mat_puerta)


def crear_puerta_en(indice, matriz_mundo, mat_puerta):
    """Marco + hoja de una puerta; +X local es la normal del muro."""
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
# SALAS FRONTALES: modelo 45 (cine domo inclinado tipo Maloka / IMAX Dome) y
# modelo 90 (domo frontal de pie, tipo museo o parque tematico)
# ---------------------------------------------------------------------------
#
# Desde el 18 sep 2026 "--fov 45" y "--fov 90" ya no generan casquetes
# horizontales: generan dos salas FRONTALES, donde todo el publico mira hacia
# +X. Los numeros 45 y 90 se conservan como claves del modelo (nombres de
# archivo, niveles DomoVR_45 / DomoVR_90, carpetas /Game/Sala/Domo_45|90), no
# describen el FOV. Cualquier otro --fov (distinto de 180, 45 y 90) sigue
# generando el casquete horizontal de antes.
#
# Geometria comun:
#   - La pantalla es una media esfera (180 grados) de radio "radio", construida
#     con construir_bmesh_cupula en su marco propio (polo +Z, frente +X, UV
#     V = 0,5 + elev/180, U = az/360 + 0,5, una sola capa) y DESPUES inclinada
#     "inclinacion" grados alrededor de Y, de modo que el polo se echa hacia el
#     frente (+X) y el borde delantero baja hasta el piso. La UV viaja con la
#     malla: el horizonte de la UV (V = 0,5) es el arranque de la pantalla, el
#     frente (U = 0,5) sigue en +X y el cuadro blanco del patron cae delante
#     del publico. Es lo mismo que recibe un domo inclinado real: un
#     domemaster de 180 grados con el cenit en el polo de la pantalla.
#   - El centro de la esfera queda en (0, 0, z_centro) con
#     z_centro = z_borde_frente + radio * sin(inclinacion): el punto mas bajo
#     del borde (el del frente) queda a z_borde_frente del piso.
#   - La planta de la sala es la proyeccion del borde de la pantalla: una
#     elipse de semiejes radio*cos(inclinacion) en X y radio en Y. Un muro
#     vertical (SM_Muro) baja de cada punto del borde hasta el piso: en el
#     frente mide casi cero, atras es la pared alta de la cabina.
#   - Graderias y plataformas son franjas en arco con centro de curvatura
#     delante de la pantalla (x = centro_curvatura_x), recortadas contra la
#     elipse, asi que las filas son curvas y miran al frente.

SALAS_FRONTALES = {
    45: {
        "titulo": "Cine domo inclinado tipo Maloka (IMAX Dome)",
        "tipo": "butacas",
        "radio": 11.0,                 # 22 m de diametro (Maloka)
        "altura_pantalla": 16.0,       # 16 m de alto (Maloka); de aqui sale la inclinacion
        "z_borde_frente": 0.0,
        "centro_curvatura_x": 16.0,    # filas en arco con centro 16 m delante del centro del domo
        "x_primera_fila": 3.2,
        "paso_fila": 1.05,             # butaca reclinada: 1,05 m de fila a fila
        "contrahuella": 0.42,          # grada tipo estadio
        "total_butacas": 314,          # aforo de Maloka (reapertura 2024)
        "paso_butaca": 0.60,
        "pasillo_central": 1.20,
        "margen_lateral": 1.00,        # pasillo contra el muro a cada lado
        "reclinacion_deg": 30.0,       # respaldo tipo IMAX Dome (no acostado como el planetario)
        "inclinacion_asiento_deg": 8.0,
        "altura_respaldo": 0.85,
        "fila_ojo": 6,                 # fila de la camara (0 = primera)
        "altura_ojo": 1.20,            # sentado, sobre el piso de la grada
        "x_puerta": 4.5,
    },
    90: {
        "titulo": "Domo frontal de pie (museo / parque tematico)",
        "tipo": "de_pie",
        "radio": 10.0,                 # 20 m de diametro
        "inclinacion_deg": 45.0,       # pantalla muy echada hacia el frente: se mira de frente
        "z_borde_frente": 0.0,
        "centro_curvatura_x": 14.0,
        "x_primera_plataforma": 2.5,
        "profundidad_plataforma": 1.5, # dos filas de gente de pie
        "num_plataformas": 5,
        "z_primera_plataforma": 0.20,
        "contrahuella": 0.45,
        "pasillo_central": 1.20,
        "margen_lateral": 0.0,
        "altura_baranda": 1.05,
        "altura_riel_medio": 0.55,
        "paso_postes": 1.5,
        "plataforma_ojo": 2,
        "altura_ojo": 1.60,            # de pie
        "x_puerta": 3.6,
    },
}

ES_SALA_FRONTAL = (not ES_MEDIA_ESFERA) and any(abs(FOV_DOMO - k) < 1e-6 for k in SALAS_FRONTALES)

# Colores de trabajo (lineales) de cada material de las salas frontales. Se
# eligieron para que cada pieza se distinga en Unreal aunque la unica luz sea
# la de la cupula: piso oscuro azulado, grada gris medio, baranda metal claro,
# butacas rojo tela, muro casi negro (pantalla de domo real), LED de paso
# ambar emisivo. importar_sala.py los lee del JSON de la sala.
MATERIALES_FRONTALES = {
    "M_Piso":       {"color": (0.035, 0.040, 0.060), "rugosidad": 0.95, "metalico": 0.0},
    "M_Grada":      {"color": (0.140, 0.140, 0.150), "rugosidad": 0.85, "metalico": 0.0},
    "M_Muro":       {"color": (0.025, 0.025, 0.030), "rugosidad": 0.95, "metalico": 0.0},
    "M_Baranda":    {"color": (0.620, 0.620, 0.650), "rugosidad": 0.35, "metalico": 0.6},
    "M_Butaca":     {"color": (0.300, 0.025, 0.030), "rugosidad": 0.90, "metalico": 0.0},
    "M_Puerta":     {"color": (0.250, 0.250, 0.270), "rugosidad": 0.40, "metalico": 0.5},
    "M_LedPaso":    {"color": (1.000, 0.550, 0.150), "rugosidad": 0.50, "metalico": 0.0,
                     "emision": (1.000, 0.550, 0.150), "fuerza_emision": 4.0},
    "M_Referencia": {"color": (0.550, 0.550, 0.520), "rugosidad": 0.70, "metalico": 0.0},
}

# Maniquies de escala (1,75 m): solo para los renders de verificacion, no se
# exportan al FBX.
ALTURA_PERSONA = 1.75


class GeometriaFrontal:
    """Constantes derivadas de un preset de SALAS_FRONTALES."""

    def __init__(self, preset):
        self.p = preset
        self.radio = preset["radio"]
        if "inclinacion_deg" in preset:
            self.inclinacion = math.radians(preset["inclinacion_deg"])
        else:
            # Maloka: la pantalla mide altura_pantalla desde el borde delantero
            # hasta lo mas alto, y eso es radio * (1 + sin(inclinacion)).
            s = (preset["altura_pantalla"] - self.radio) / self.radio
            self.inclinacion = math.asin(max(0.0, min(1.0, s)))
        self.z_centro = preset["z_borde_frente"] + self.radio * math.sin(self.inclinacion)
        self.centro = Vector((0.0, 0.0, self.z_centro))
        self.semieje_x = self.radio * math.cos(self.inclinacion)
        self.semieje_y = self.radio
        self.xf = preset["centro_curvatura_x"]
        self.rotacion = Matrix.Rotation(self.inclinacion, 4, 'Y')

    def punto_pantalla(self, az_deg, elev_deg):
        """Punto de la pantalla en coordenadas de mundo a partir de su
        azimut/elevacion PROPIOS (los de la UV)."""
        az, el = math.radians(az_deg), math.radians(elev_deg)
        local = Vector((math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el))) * self.radio
        return self.centro + (self.rotacion.to_3x3() @ local)

    def z_borde(self, t):
        """Altura del borde de la pantalla en el azimut propio t (radianes);
        su proyeccion en planta es (semieje_x cos t, semieje_y sin t)."""
        return self.z_centro - self.radio * math.cos(t) * math.sin(self.inclinacion)

    def punto_arco(self, rho, phi, z=0.0):
        return Vector((self.xf - rho * math.cos(phi), rho * math.sin(phi), z))

    def cortes_elipse(self, phi, margen=0.02):
        """Distancias (entrada, salida) a lo largo del rayo que sale del
        centro de curvatura con angulo phi, contra la elipse de la planta
        reducida en 'margen'. None si el rayo no la cruza."""
        a, b = self.semieje_x - margen, self.semieje_y - margen
        c, s = math.cos(phi), math.sin(phi)
        qa = c * c / (a * a) + s * s / (b * b)
        qb = -2.0 * self.xf * c / (a * a)
        qc = self.xf * self.xf / (a * a) - 1.0
        disc = qb * qb - 4.0 * qa * qc
        if disc <= 0.0:
            return None
        r = math.sqrt(disc)
        return ((-qb - r) / (2.0 * qa), (-qb + r) / (2.0 * qa))

    def dentro(self, x, y, margen=0.0):
        a, b = self.semieje_x - margen, self.semieje_y - margen
        return (x / a) ** 2 + (y / b) ** 2 <= 1.0


def agregar_prisma_arco(bm, g, rho_in, rho_out, z_top, z_base=0.0, paso_m=0.35):
    """Franja en arco (grada o plataforma) de z_base a z_top, recortada contra
    la elipse de la planta. rho_in es el borde delantero (hacia la pantalla).
    Devuelve (phi_max, lista de (phi, rho_in_recortado)) para colocar luces y
    barandas sobre el borde delantero, o None si no cabe."""
    validos = []
    n_busqueda = 720
    for k in range(n_busqueda + 1):
        phi = (math.pi / 2.0) * k / n_busqueda
        cortes = g.cortes_elipse(phi)
        if cortes is None:
            break
        ri, ro = max(rho_in, cortes[0]), min(rho_out, cortes[1])
        if ri >= ro - 0.05:
            break
        validos.append(phi)
    if len(validos) < 2:
        return None
    phi_max = validos[-1]
    arco_medio = phi_max * (rho_in + min(rho_out, rho_in + 6.0)) / 2.0
    n = max(8, int(2.0 * arco_medio / paso_m))
    anillos = []
    borde = []
    for k in range(n + 1):
        phi = -phi_max + 2.0 * phi_max * k / n
        cortes = g.cortes_elipse(abs(phi))
        ri, ro = max(rho_in, cortes[0]), min(rho_out, cortes[1])
        borde.append((phi, ri))
        anillos.append((
            bm.verts.new(g.punto_arco(ri, phi, z_base)),
            bm.verts.new(g.punto_arco(ri, phi, z_top)),
            bm.verts.new(g.punto_arco(ro, phi, z_top)),
            bm.verts.new(g.punto_arco(ro, phi, z_base)),
        ))
    caras = []
    for k in range(n):
        a0, a1 = anillos[k], anillos[k + 1]
        for m in range(4):
            mm = (m + 1) % 4
            caras.append(bm.faces.new((a0[m], a1[m], a1[mm], a0[mm])))
    caras.append(bm.faces.new(anillos[0]))
    caras.append(bm.faces.new(tuple(reversed(anillos[-1]))))
    bmesh.ops.recalc_face_normals(bm, faces=caras)
    return phi_max, borde


def agregar_barra(bm, p0, p1, grosor):
    """Caja de seccion cuadrada 'grosor' de p0 a p1 (tubo de baranda o poste)."""
    d = p1 - p0
    largo = d.length
    if largo < 1e-4:
        return
    ret = bmesh.ops.create_cube(bm, size=1.0)
    verts = ret["verts"]
    bmesh.ops.scale(bm, vec=(largo, grosor, grosor), verts=verts)
    arriba = 'Z' if abs(d.normalized().z) < 0.99 else 'Y'
    rot = d.normalized().to_track_quat('X', arriba).to_matrix().to_4x4()
    bmesh.ops.transform(bm, matrix=Matrix.Translation((p0 + p1) / 2.0) @ rot, verts=verts)


def agregar_baranda_arco(bm, g, rho, phi_ini, phi_fin, z_piso, altura, riel_medio, paso_postes, grosor=0.05):
    """Baranda sobre un arco: postes cada ~paso_postes, pasamanos a 'altura'
    y riel medio a 'riel_medio' sobre z_piso."""
    largo = abs(phi_fin - phi_ini) * rho
    if largo < 0.3:
        return
    n_postes = max(2, int(math.ceil(largo / paso_postes)) + 1)
    n_tramos = max(2, int(math.ceil(largo / 0.5)))
    for k in range(n_postes):
        phi = phi_ini + (phi_fin - phi_ini) * k / (n_postes - 1)
        base = g.punto_arco(rho, phi, z_piso)
        agregar_barra(bm, base, base + Vector((0, 0, altura + grosor / 2.0)), grosor)
    for h in (altura, riel_medio):
        if h is None:
            continue
        for k in range(n_tramos):
            f0 = phi_ini + (phi_fin - phi_ini) * k / n_tramos
            f1 = phi_ini + (phi_fin - phi_ini) * (k + 1) / n_tramos
            agregar_barra(bm, g.punto_arco(rho, f0, z_piso + h), g.punto_arco(rho, f1, z_piso + h),
                          grosor if h == altura else grosor * 0.7)


def agregar_led_arco(bm, g, borde, z, alto=0.03, fondo=0.04, excluir_centro=0.0):
    """Tira LED sobre el borde delantero de una grada (lista (phi, rho))."""
    for (f0, r0), (f1, r1) in zip(borde[:-1], borde[1:]):
        if excluir_centro and abs((f0 + f1) / 2.0) * r0 < excluir_centro / 2.0:
            continue
        # Sobre la cara de la contrahuella, justo bajo la nariz del escalon.
        p0 = g.punto_arco(r0 - fondo / 4.0, f0, z - alto)
        p1 = g.punto_arco(r1 - fondo / 4.0, f1, z - alto)
        agregar_barra(bm, p0, p1, alto)


def agregar_persona(bm, pos, yaw):
    """Maniqui de escala de ALTURA_PERSONA (cuerpo + cabeza)."""
    m = Matrix.Translation(pos) @ Matrix.Rotation(yaw, 4, 'Z')
    alto_cuerpo = ALTURA_PERSONA - 0.24
    agregar_caja(bm, (0.26, 0.46, alto_cuerpo), (0.0, 0.0, 0.0), 0.0, m)
    agregar_caja(bm, (0.22, 0.19, 0.24), (0.0, 0.0, alto_cuerpo), 0.0, m)


def material_frontal(nombre):
    d = MATERIALES_FRONTALES[nombre]
    mat = crear_material(nombre, d["color"], emision_color=d.get("emision"),
                         emision_fuerza=d.get("fuerza_emision", 0.0),
                         rugosidad=d["rugosidad"], metalico=d["metalico"])
    return mat


def objeto_frontal(bm, nombre, material):
    obj = nuevo_objeto_desde_bmesh(bm, nombre)
    obj.data.materials.append(material)
    return obj


def crear_pantalla_frontal(g):
    bm = construir_bmesh_cupula(g.radio, 0.0)
    bmesh.ops.transform(bm, matrix=Matrix.Translation(g.centro) @ g.rotacion, verts=bm.verts)
    obj = nuevo_objeto_desde_bmesh(bm, "SM_Domo")
    _material_domo_checker(obj)
    return obj


def crear_muro_y_piso_frontal(g, mat_muro, mat_piso):
    """Muro vertical bajo el borde de la pantalla y piso con la forma de su
    proyeccion. Mismos SEGMENTOS_AZIMUT que la cupula, asi el borde superior
    del muro coincide vertice a vertice con el borde de la pantalla."""
    bm = bmesh.new()
    arriba, abajo = [], []
    for i in range(SEGMENTOS_AZIMUT):
        t = 2.0 * math.pi * i / SEGMENTOS_AZIMUT
        x, y = g.semieje_x * math.cos(t), g.semieje_y * math.sin(t)
        z = g.z_borde(t)
        va = bm.verts.new((x, y, z))
        vb = va if z < 0.005 else bm.verts.new((x, y, 0.0))
        arriba.append(va)
        abajo.append(vb)
    caras = []
    for i in range(SEGMENTOS_AZIMUT):
        j = (i + 1) % SEGMENTOS_AZIMUT
        unicos = []
        for v in (abajo[i], abajo[j], arriba[j], arriba[i]):
            if v not in unicos:
                unicos.append(v)
        if len(unicos) >= 3:
            caras.append(bm.faces.new(unicos))
    bm.normal_update()
    for f in caras:
        c = f.calc_center_median()
        if f.normal.dot(Vector((c.x, c.y, 0.0))) > 0:
            f.normal_flip()
    muro = objeto_frontal(bm, "SM_Muro", mat_muro)

    bm = bmesh.new()
    vs = [bm.verts.new((g.semieje_x * math.cos(2.0 * math.pi * i / SEGMENTOS_AZIMUT),
                        g.semieje_y * math.sin(2.0 * math.pi * i / SEGMENTOS_AZIMUT), 0.0))
          for i in range(SEGMENTOS_AZIMUT)]
    f = bm.faces.new(vs)
    bm.normal_update()
    if f.normal.z < 0:
        f.normal_flip()
    piso = objeto_frontal(bm, "SM_Piso", mat_piso)
    return muro, piso


def crear_puertas_frontales(g, x_puerta, mat_puerta):
    """Dos puertas en el muro, una a cada lado, a la altura del pasillo
    delantero (piso a nivel 0)."""
    t = math.acos(max(-1.0, min(1.0, x_puerta / g.semieje_x)))
    alto_libre = g.z_borde(t)
    assert alto_libre > ALTURA_PUERTA + GROSOR_MARCO, \
        "El borde de la pantalla queda a {:.2f} m sobre la puerta; no cabe.".format(alto_libre)
    objetos = []
    for indice, signo in enumerate((+1.0, -1.0)):
        tt = signo * t
        p = Vector((g.semieje_x * math.cos(tt), g.semieje_y * math.sin(tt), 0.0))
        n = Vector((math.cos(tt) / g.semieje_x, math.sin(tt) / g.semieje_y, 0.0)).normalized()
        m = Matrix.Translation(p - n * 0.06) @ Matrix.Rotation(math.atan2(n.y, n.x), 4, 'Z')
        objetos.append(crear_puerta_en(indice, m, mat_puerta))
    return objetos


def seccion_de_filas_45(g):
    """Filas de la grada del modelo 45: se agregan filas hacia atras hasta
    llegar EXACTO a total_butacas; la ultima se recorta a lo que falte."""
    p = g.p
    filas = []
    total = 0
    r = 0
    while total < p["total_butacas"]:
        x = p["x_primera_fila"] - r * p["paso_fila"]
        rho = g.xf - x
        z = r * p["contrahuella"]
        n_lado = 0
        while True:
            d = p["pasillo_central"] / 2.0 + p["paso_butaca"] / 2.0 + n_lado * p["paso_butaca"]
            q = g.punto_arco(rho, d / rho)
            if not g.dentro(q.x, q.y, p["margen_lateral"] + p["paso_butaca"] / 2.0):
                break
            n_lado += 1
        if n_lado == 0:
            raise SystemExit("La grada llego al muro sin completar {} butacas (van {}).".format(
                p["total_butacas"], total))
        n = 2 * n_lado
        restante = p["total_butacas"] - total
        filas.append({"indice": r, "x": x, "rho": rho, "z": z, "por_lado": [n_lado, n_lado]})
        if n > restante:
            filas[-1]["por_lado"] = [restante - restante // 2, restante // 2]
            n = restante
        total += n
        r += 1
    return filas


def construir_sala_45(g, mats):
    p = g.p
    filas = seccion_de_filas_45(g)
    paso = p["paso_fila"]
    bm_grada, bm_baranda, bm_led = bmesh.new(), bmesh.new(), bmesh.new()
    bm_butacas = [bmesh.new(), bmesh.new()]   # SM_Butacas_01 = +Y, SM_Butacas_02 = -Y
    asientos = []
    n_filas = len(filas)
    for f in filas:
        rho_in = f["rho"] - paso / 2.0
        rho_out = f["rho"] + paso / 2.0 if f["indice"] < n_filas - 1 else 1e3
        if f["z"] > 0.0:
            res = agregar_prisma_arco(bm_grada, g, rho_in, rho_out, f["z"])
            if res:
                agregar_led_arco(bm_led, g, res[1], f["z"], excluir_centro=p["pasillo_central"])
        rho_asiento = f["rho"] + 0.05
        for lado, signo in enumerate((+1.0, -1.0)):
            for k in range(f["por_lado"][lado]):
                d = p["pasillo_central"] / 2.0 + p["paso_butaca"] / 2.0 + k * p["paso_butaca"]
                phi = signo * d / rho_asiento
                q = g.punto_arco(rho_asiento, phi, f["z"])
                yaw = math.atan2(-q.y, g.xf - q.x)
                m = Matrix.Translation(q) @ Matrix.Rotation(yaw, 4, 'Z')
                agregar_butaca(bm_butacas[lado], m, p["reclinacion_deg"], p["inclinacion_asiento_deg"],
                               p["altura_respaldo"])
                asientos.append((f["indice"], lado, k, q, yaw))

    # Pasillo central: medio escalon en la mitad trasera de cada fila, para
    # subir de una grada a la siguiente en dos pasos.
    for f in filas[:-1]:
        x0 = g.xf - (f["rho"] + paso / 2.0)
        agregar_caja(bm_grada, (paso / 2.0, p["pasillo_central"], p["contrahuella"] / 2.0),
                     (x0 + paso / 4.0, 0.0, f["z"]), 0.0, Matrix.Identity(4))

    # Pasamanos del pasillo central, a los dos lados, siguiendo la pendiente:
    # un poste por fila a 0,90 m del piso de su grada.
    alto_pasamanos = 0.90
    for signo in (+1.0, -1.0):
        y = signo * (p["pasillo_central"] / 2.0 - 0.04)
        tops = []
        for f in filas[1:]:
            base = Vector((g.xf - f["rho"], y, f["z"]))
            top = base + Vector((0, 0, alto_pasamanos))
            agregar_barra(bm_baranda, base, top + Vector((0, 0, 0.025)), 0.05)
            tops.append(top)
        for a, b in zip(tops[:-1], tops[1:]):
            agregar_barra(bm_baranda, a, b, 0.05)

    # Baranda frontal: separa el pasillo delantero (nivel 0) de la pantalla,
    # a 1,5 m delante de la primera fila.
    rho_frente = filas[0]["rho"] - paso / 2.0 - 1.5
    cortes = [ph for ph in (math.radians(a / 10.0) for a in range(0, 900))
              if g.cortes_elipse(ph) and g.cortes_elipse(ph)[0] < rho_frente]
    if cortes:
        ph = cortes[-1] - 1.2 / rho_frente   # deja 1,2 m libres contra el muro (acceso desde las puertas)
        agregar_baranda_arco(bm_baranda, g, rho_frente, -ph, ph, 0.0, 1.05, 0.55, 1.5)

    objetos = [
        objeto_frontal(bm_grada, "SM_Graderia", mats["M_Grada"]),
        objeto_frontal(bm_butacas[0], "SM_Butacas_01", mats["M_Butaca"]),
        objeto_frontal(bm_butacas[1], "SM_Butacas_02", mats["M_Butaca"]),
        objeto_frontal(bm_baranda, "SM_Barandas", mats["M_Baranda"]),
        objeto_frontal(bm_led, "SM_LucesPaso", mats["M_LedPaso"]),
    ]

    # Ojo: primera butaca a la derecha del pasillo (+Y en Blender) de la fila
    # fila_ojo, 0,5 m detras del centro del asiento (la cabeza contra el
    # reposacabezas del respaldo reclinado), a altura_ojo del piso de la grada.
    fila_ojo = min(p["fila_ojo"], n_filas - 1)
    _, _, _, q, yaw = next(a for a in asientos if a[0] == fila_ojo and a[1] == 0 and a[2] == 0)
    adelante = Vector((math.cos(yaw), math.sin(yaw), 0.0))
    ojo = q - adelante * 0.5 + Vector((0.0, 0.0, p["altura_ojo"]))

    # Maniquies de escala: dos de pie en el pasillo delantero.
    bm_ref = bmesh.new()
    x_ref = g.xf - filas[0]["rho"] + paso / 2.0 + 0.7
    agregar_persona(bm_ref, Vector((x_ref, 3.0, 0.0)), math.pi)
    agregar_persona(bm_ref, Vector((x_ref + 0.4, -4.5, 0.0)), math.pi * 0.8)
    referencia = objeto_frontal(bm_ref, "REF_Personas", mats["M_Referencia"])

    datos = {
        "filas": [{"fila": f["indice"] + 1, "x_m": round(f["x"], 3), "z_piso_m": round(f["z"], 3),
                   "butacas": sum(f["por_lado"])} for f in filas],
        "butacas": len(asientos),
    }
    print("\n--- Grada del modelo 45 ---")
    print(f"{'fila':>4} {'x(m)':>7} {'z piso(m)':>9} {'butacas':>8}")
    for f in datos["filas"]:
        print(f"{f['fila']:>4} {f['x_m']:>7.2f} {f['z_piso_m']:>9.2f} {f['butacas']:>8d}")
    print(f"Total de butacas: {len(asientos)} (esperado {p['total_butacas']})")
    assert len(asientos) == p["total_butacas"]
    return objetos, referencia, ojo, datos


def construir_sala_90(g, mats):
    p = g.p
    bm_grada, bm_baranda, bm_led, bm_ref = bmesh.new(), bmesh.new(), bmesh.new(), bmesh.new()
    prof = p["profundidad_plataforma"]
    plataformas = []
    for k in range(p["num_plataformas"]):
        x_frente = p["x_primera_plataforma"] - k * prof
        rho_in = g.xf - x_frente
        rho_out = rho_in + prof if k < p["num_plataformas"] - 1 else 1e3
        z = p["z_primera_plataforma"] + k * p["contrahuella"]
        res = agregar_prisma_arco(bm_grada, g, rho_in, rho_out, z)
        if res is None:
            raise SystemExit("La plataforma {} no cabe en la planta.".format(k + 1))
        phi_max, borde = res
        plataformas.append({"indice": k, "x_frente": x_frente, "rho_in": rho_in, "z": z, "phi_max": phi_max,
                            "ancho_m": 2.0 * phi_max * rho_in})
        agregar_led_arco(bm_led, g, borde, z, excluir_centro=p["pasillo_central"])

        # Baranda en el borde delantero de cada plataforma (el publico se
        # apoya en ella): dos tramos, con la abertura del pasillo central y
        # 0,9 m libres contra cada muro para las escaleras laterales.
        a_centro = (p["pasillo_central"] / 2.0) / rho_in
        a_fin = phi_max - 0.9 / rho_in
        rho_b = rho_in + 0.08
        for signo in (+1.0, -1.0):
            agregar_baranda_arco(bm_baranda, g, rho_b, signo * a_centro, signo * a_fin, z,
                                 p["altura_baranda"], p["altura_riel_medio"], p["paso_postes"])

        # Escalon intermedio en el pasillo central y en los dos extremos (mitad
        # de la contrahuella), sobre la plataforma de abajo.
        if k > 0:
            z_abajo = z - p["contrahuella"]
            x_esc = x_frente + 0.30 / 2.0
            agregar_caja(bm_grada, (0.30, p["pasillo_central"], p["contrahuella"] / 2.0),
                         (x_esc, 0.0, z_abajo), 0.0, Matrix.Identity(4))
            for signo in (+1.0, -1.0):
                phi_e = signo * (phi_max - 0.45 / rho_in)
                q = g.punto_arco(rho_in - 0.15, phi_e, z_abajo)
                yaw = math.atan2(-q.y, g.xf - q.x)
                agregar_caja(bm_grada, (0.30, 0.9, p["contrahuella"] / 2.0), (0.0, 0.0, 0.0), 0.0,
                             Matrix.Translation(q) @ Matrix.Rotation(yaw, 4, 'Z'))

    # Maniquies de escala: gente de pie apoyada en las barandas.
    for pl in plataformas[:4]:
        for y in (-3.2, 3.0, 5.6):
            phi = y / pl["rho_in"]
            if abs(phi) > pl["phi_max"] - 0.1:
                continue
            q = g.punto_arco(pl["rho_in"] + 0.45, phi, pl["z"])
            agregar_persona(bm_ref, q, math.atan2(-q.y, g.xf - q.x))

    objetos = [
        objeto_frontal(bm_grada, "SM_Plataformas", mats["M_Grada"]),
        objeto_frontal(bm_baranda, "SM_Barandas", mats["M_Baranda"]),
        objeto_frontal(bm_led, "SM_LucesPaso", mats["M_LedPaso"]),
    ]
    referencia = objeto_frontal(bm_ref, "REF_Personas", mats["M_Referencia"])

    pl = plataformas[min(p["plataforma_ojo"], len(plataformas) - 1)]
    phi = 1.4 / pl["rho_in"]
    q = g.punto_arco(pl["rho_in"] + 0.5, phi, pl["z"])
    ojo = q + Vector((0.0, 0.0, p["altura_ojo"]))

    area = 0.0
    for a, b in zip(plataformas, plataformas[1:] + [None]):
        prof_real = prof if b else (g.semieje_x + a["x_frente"])
        area += a["ancho_m"] * prof_real
    aforo = int(area / 0.5)   # 0,5 m2 por persona de pie, holgado
    print("\n--- Plataformas del modelo 90 ---")
    for pl_ in plataformas:
        print("plataforma {}: borde delantero x={:.2f} m, piso z={:.2f} m, ancho del borde {:.1f} m".format(
            pl_["indice"] + 1, pl_["x_frente"], pl_["z"], pl_["ancho_m"]))
    print("Aforo de pie estimado: {} personas (0,5 m2 por persona)".format(aforo))
    datos = {
        "plataformas": [{"plataforma": pl_["indice"] + 1, "x_borde_m": round(pl_["x_frente"], 3),
                         "z_piso_m": round(pl_["z"], 3), "ancho_borde_m": round(pl_["ancho_m"], 2)}
                        for pl_ in plataformas],
        "aforo_de_pie_estimado": aforo,
    }
    return objetos, referencia, ojo, datos


def imagen_patron(nombre="T_Patron_Prueba", ancho=2048, alto=1024):
    """Reproduce 00_TouchDesigner/shaders/patron.frag en una imagen (v = 0
    abajo, igual que la UV de Blender): rojo / amarillo / verde / cian por
    bandas de v, meridianos negros cada 0,125 en u (el de u = 0 grueso),
    cuadro blanco en (0,5, 0,75) y marca magenta en (0,5, 0,97)."""
    img = bpy.data.images.new(nombre, ancho, alto, alpha=False)
    pix = [0.0] * (ancho * alto * 4)
    for j in range(alto):
        v = (j + 0.5) / alto
        if v < 0.25:
            base = (1.0, 0.0, 0.0)
        elif v < 0.5:
            base = (1.0, 1.0, 0.0)
        elif v < 0.75:
            base = (0.0, 1.0, 0.0)
        else:
            base = (0.0, 1.0, 1.0)
        fila = j * ancho * 4
        for i in range(ancho):
            u = (i + 0.5) / ancho
            c = base
            if (u % 0.125) < 0.003 or u < 0.012:
                c = (0.0, 0.0, 0.0)
            if abs(u - 0.5) < 0.03 and abs(v - 0.75) < 0.06:
                c = (1.0, 1.0, 1.0)
            if abs(u - 0.5) < 0.015 and abs(v - 0.97) < 0.03:
                c = (1.0, 0.0, 1.0)
            o = fila + i * 4
            pix[o] = c[0]; pix[o + 1] = c[1]; pix[o + 2] = c[2]; pix[o + 3] = 1.0
    img.pixels.foreach_set(pix)
    img.pack()
    return img


def poner_patron_en_cupula(domo_obj):
    """Solo para los renders: la cupula se ve con el patron de prueba de
    TouchDesigner (emisivo puro) leyendo la capa UV del canal 0. Se hace
    despues de exportar, asi el FBX no arrastra la imagen."""
    mat = domo_obj.data.materials[0]
    nodos, enlaces = mat.node_tree.nodes, mat.node_tree.links
    for n in list(nodos):
        nodos.remove(n)
    salida = nodos.new("ShaderNodeOutputMaterial")
    emision = nodos.new("ShaderNodeEmission")
    emision.inputs["Strength"].default_value = 1.0
    tex = nodos.new("ShaderNodeTexImage")
    tex.image = imagen_patron()
    tex.interpolation = 'Closest'
    uv = nodos.new("ShaderNodeUVMap")
    uv.uv_map = domo_obj.data.uv_layers[0].name
    enlaces.new(uv.outputs["UV"], tex.inputs["Vector"])
    enlaces.new(tex.outputs["Color"], emision.inputs["Color"])
    enlaces.new(emision.outputs["Emission"], salida.inputs["Surface"])


def _orientacion_mirando(origen, objetivo):
    d = (objetivo - origen).normalized()
    yaw = math.degrees(math.atan2(d.y, d.x))
    pitch = math.degrees(math.asin(max(-1.0, min(1.0, d.z))))
    return yaw, pitch


def renderizar_vistas_frontales(g, domo_obj, ojo, referencia):
    escena = bpy.context.scene
    escena.render.engine = 'BLENDER_EEVEE'
    escena.render.resolution_x = RES_X
    escena.render.resolution_y = RES_Y
    escena.render.image_settings.file_format = 'PNG'
    escena.view_settings.view_transform = 'Standard'
    try:
        escena.eevee.taa_render_samples = 32
    except AttributeError:
        pass
    mundo = bpy.data.worlds.new("Mundo_Preview")
    mundo.use_nodes = True
    mundo.node_tree.nodes["Background"].inputs["Color"].default_value = (0.02, 0.02, 0.025, 1.0)
    escena.world = mundo

    # Luz de trabajo suave desde arriba (la cupula emisiva sola deja la sala
    # muy oscura en EEVEE): solo para leer la geometria en los renders.
    luz = bpy.data.lights.new("Luz_Trabajo", type='AREA')
    luz.energy = 2500.0
    luz.size = g.radio * 1.2
    obj_luz = bpy.data.objects.new("Luz_Trabajo", luz)
    obj_luz.location = (-1.0, 0.0, g.z_centro + g.radio * 0.55)
    bpy.context.collection.objects.link(obj_luz)

    cam_data = bpy.data.cameras.new("Camara_Preview")
    cam_data.clip_start = 0.05
    cam_data.clip_end = 200.0
    cam = bpy.data.objects.new("Camara_Preview", cam_data)
    bpy.context.collection.objects.link(cam)
    escena.camera = cam

    cuadro_blanco = g.punto_pantalla(0.0, 45.0)
    polo = g.punto_pantalla(0.0, 90.0)

    # 1) Planta cenital, sin la pantalla, en cuadro cuadrado (+X a la derecha).
    domo_obj.hide_render = True
    escena.render.resolution_x = RES_Y
    escena.render.resolution_y = RES_Y
    cam_data.type = 'ORTHO'
    cam_data.ortho_scale = g.radio * 2.15
    cam.location = (0.0, 0.0, g.z_centro + g.radio + 5.0)
    apuntar_camara(cam, Vector((0.0, 0.0, 0.0)))
    escena.render.filepath = ruta_preview("vista_planta_cenital")
    bpy.ops.render.render(write_still=True)
    escena.render.resolution_x = RES_X
    domo_obj.hide_render = False

    # 2) Vista general desde la esquina trasera alta, hacia la pantalla.
    cam_data.type = 'PERSP'
    cam_data.lens = 12.0
    cam.location = (-g.semieje_x * 0.72, -g.semieje_y * 0.33, g.z_centro + 2.0)
    apuntar_camara(cam, Vector((cuadro_blanco.x * 0.8, 1.0, (cuadro_blanco.z + polo.z) / 2.0 - 2.5)))
    escena.render.filepath = ruta_preview("vista_general_perspectiva")
    bpy.ops.render.render(write_still=True)

    # 3) Desde el ojo del espectador (sentado en 45, de pie en 90), mirando
    # al cuadro blanco del frente: con el lente de 12 mm entran las filas o
    # barandas de adelante y la pantalla hasta cerca del polo.
    referencia.hide_render = False
    cam_data.lens = 12.0
    cam.location = ojo
    objetivo = cuadro_blanco
    if g.p["tipo"] == "de_pie":
        # De pie se mira casi horizontal: entran la baranda propia y las de
        # adelante, y el cuadro blanco queda en el tercio superior.
        objetivo = Vector((cuadro_blanco.x, cuadro_blanco.y, ojo.z + (cuadro_blanco.z - ojo.z) * 0.25))
    apuntar_camara(cam, objetivo)
    nombre = "vista_desde_butaca" if g.p["tipo"] == "butacas" else "vista_de_pie"
    escena.render.filepath = ruta_preview(nombre)
    bpy.ops.render.render(write_still=True)
    return _orientacion_mirando(ojo, objetivo)


def verificar_export_frontal(g):
    """Lee el FBX de vuelta y comprueba la cupula: una sola capa UV, V de 0,5
    a 1, el frente (U = 0,5) en +X, el cuadro blanco (U 0,5, V 0,75) delante
    y por encima del borde, y el borde delantero a z_borde_frente."""
    escena_verificacion = bpy.data.scenes.new("Verificacion_FBX")
    escena_anterior = bpy.context.window.scene
    bpy.context.window.scene = escena_verificacion
    antes = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=RUTA_FBX)
    importados = [o for o in bpy.data.objects if o not in antes]
    print("\n--- Verificacion leyendo el FBX exportado de vuelta ---")
    print("objetos en el FBX: {}".format(sorted(o.name for o in importados)))
    domo = next((o for o in importados if o.name.startswith("SM_Domo")), None)
    resultado = {}
    if domo is None:
        print("SM_Domo: NO SE ENCONTRO EN EL FBX IMPORTADO")
    else:
        mw = domo.matrix_world
        malla = domo.data
        capas = [l.name for l in malla.uv_layers]
        uvs = malla.uv_layers[0].data
        frente_rim, cuadro, vs = [], [], []
        for poly in malla.polygons:
            for li in poly.loop_indices:
                u, v = uvs[li].uv
                co = mw @ malla.vertices[malla.loops[li].vertex_index].co
                vs.append(v)
                if abs(u - 0.5) < 0.01 and abs(v - 0.5) < 0.005:
                    frente_rim.append(co)
                if abs(u - 0.5) < 0.01 and abs(v - 0.75) < 0.01:
                    cuadro.append(co)
        pts = [mw @ Vector(c) for c in domo.bound_box]
        dx = max(p.x for p in pts) - min(p.x for p in pts)
        dy = max(p.y for p in pts) - min(p.y for p in pts)
        zmin = min(p.z for p in pts)
        zmax = max(p.z for p in pts)
        c_rim = sum(frente_rim, Vector()) / max(1, len(frente_rim))
        c_cuadro = sum(cuadro, Vector()) / max(1, len(cuadro))
        ok_capas = len(capas) == 1
        ok_v = abs(min(vs) - 0.5) < 1e-3 and abs(max(vs) - 1.0) < 1e-3
        ok_frente = c_cuadro.x > 0.0 and c_rim.x > 0.0 and abs(c_cuadro.y) < 0.2
        ok_borde = abs(c_rim.z - g.p["z_borde_frente"]) < 0.05
        print("SM_Domo: X={:.2f} m  Y={:.2f} m  z de {:.2f} a {:.2f} m".format(dx, dy, zmin, zmax))
        print("  capas UV: {} -> {}".format(capas, "OK" if ok_capas else "MAL (debe ser una)"))
        print("  V del canal 0 de {:.3f} a {:.3f} -> {}".format(min(vs), max(vs), "OK" if ok_v else "MAL"))
        print("  borde delantero (U 0,5 V 0,5) en ({:.2f}, {:.2f}, {:.2f}) -> {}".format(
            c_rim.x, c_rim.y, c_rim.z, "OK" if ok_borde else "MAL"))
        print("  cuadro blanco (U 0,5 V 0,75) en ({:.2f}, {:.2f}, {:.2f}) -> {}".format(
            c_cuadro.x, c_cuadro.y, c_cuadro.z, "OK, al frente (+X)" if ok_frente else "MAL"))
        resultado = {"capas_uv": capas, "v_min": round(min(vs), 4), "v_max": round(max(vs), 4),
                     "borde_frente": [round(c, 3) for c in c_rim],
                     "cuadro_blanco": [round(c, 3) for c in c_cuadro],
                     "ok": ok_capas and ok_v and ok_frente and ok_borde}
    for obj in importados:
        bpy.data.objects.remove(obj, do_unlink=True)
    bpy.context.window.scene = escena_anterior
    bpy.data.scenes.remove(escena_verificacion)
    return resultado


def main_frontal():
    import json
    clave = int(round(FOV_DOMO))
    preset = SALAS_FRONTALES[clave]
    g = GeometriaFrontal(preset)
    limpiar_escena()
    print("\n=== Sala frontal {}: {} ===".format(clave, preset["titulo"]))
    print("pantalla media esfera de radio {:.2f} m (diametro {:.1f} m), inclinada {:.1f} grados hacia +X".format(
        g.radio, 2 * g.radio, math.degrees(g.inclinacion)))
    print("centro de la esfera en z={:.2f} m | borde delantero a z={:.2f} m | lo mas alto a z={:.2f} m | "
          "borde trasero a z={:.2f} m | planta elipse {:.2f} x {:.2f} m".format(
              g.z_centro, preset["z_borde_frente"], g.z_centro + g.radio, g.z_borde(math.pi),
              2 * g.semieje_x, 2 * g.semieje_y))

    mats = {n: material_frontal(n) for n in MATERIALES_FRONTALES}
    domo = crear_pantalla_frontal(g)
    muro, piso = crear_muro_y_piso_frontal(g, mats["M_Muro"], mats["M_Piso"])
    puertas = crear_puertas_frontales(g, preset["x_puerta"], mats["M_Puerta"])
    if preset["tipo"] == "butacas":
        piezas, referencia, ojo, datos_sala = construir_sala_45(g, mats)
    else:
        piezas, referencia, ojo, datos_sala = construir_sala_90(g, mats)

    exportables = [piso, muro, domo] + piezas + puertas
    reportar_poligonos(exportables)
    for obj in exportables:
        if obj is not domo:
            desenvolver_uv_cube(obj)
    aplicar_transformaciones(exportables + [referencia])
    exportar_fbx(exportables)
    exportar_glb(exportables)

    poner_patron_en_cupula(domo)
    yaw, pitch = renderizar_vistas_frontales(g, domo, ojo, referencia)
    bpy.ops.wm.save_as_mainfile(filepath=RUTA_BLEND)
    verificacion = verificar_export_frontal(g)

    datos = {
        "modelo": clave,
        "titulo": preset["titulo"],
        "generado_por": "01_Blender/generar_sala_domo.py",
        "nota_coordenadas": "metros, ejes de Blender (+X frente, +Z arriba). Unreal: x*100, -y*100, z*100; yaw_unreal = -yaw.",
        "pantalla": {
            "fov_deg": 180.0,
            "radio_m": g.radio,
            "inclinacion_deg": round(math.degrees(g.inclinacion), 3),
            "centro_esfera_m": [0.0, 0.0, round(g.z_centro, 4)],
            "z_borde_frente_m": preset["z_borde_frente"],
            "z_maxima_m": round(g.z_centro + g.radio, 4),
            "z_borde_trasero_m": round(g.z_borde(math.pi), 4),
            "planta_elipse_m": [round(2 * g.semieje_x, 3), round(2 * g.semieje_y, 3)],
        },
        "mallas": [o.name for o in exportables],
        "material_por_malla": {o.name: o.data.materials[0].name for o in exportables if o is not domo},
        "materiales": {n: {k: (list(v) if isinstance(v, tuple) else v) for k, v in d.items()}
                       for n, d in MATERIALES_FRONTALES.items() if n != "M_Referencia"},
        "ojo": {"posicion_m": [round(c, 4) for c in ojo], "yaw_deg": round(yaw, 3), "pitch_deg": round(pitch, 3),
                "altura_sobre_piso_m": preset["altura_ojo"]},
        "sala": datos_sala,
        "verificacion_fbx": verificacion,
    }
    ruta_json = os.path.join(CARPETA_BASE, "02_Export", NOMBRE_SALIDA + ".json")
    with open(ruta_json, "w", encoding="utf-8") as fh:
        json.dump(datos, fh, ensure_ascii=False, indent=2)
    print("\nListo: {0}.blend, {0}.fbx, {0}.glb, {0}.json y 3 PNG de previsualizacion.".format(NOMBRE_SALIDA))
    if not verificacion.get("ok"):
        raise SystemExit("La verificacion del FBX fallo; revisar el bloque de arriba.")


# ---------------------------------------------------------------------------
# PROGRAMA PRINCIPAL
# ---------------------------------------------------------------------------

def main():
    if ES_SALA_FRONTAL:
        main_frontal()
        return
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
