# ==========================================================================
# VIDEO_DOME  ·  video 16:9 -> domemaster fulldome, con N pantallas ubicables
# TouchDesigner 2025 · copia del sistema de domo, sin camaras NDI
#
# Uso: pegar en un Text DAT dentro de /project1 -> click derecho -> Run Script
# Resultado: /project1/VIDEO_DOME/out_dome = domemaster cuadrado (Res x Res)
#
# Dos ideas sostienen todo esto:
#
# 1. El mapeo va al reves que un render. El shader dome_map.frag recorre los
#    pixeles del domemaster, calcula la direccion de cada uno en la cupula y
#    pregunta que pantalla la cubre. Sin geometria, sin camara, sin teselado.
#
# 2. Las pantallas no estan cableadas: viven en la tabla `screens`, una fila
#    cada una, convertida a CHOP y leida por el shader como arrays. Agregar,
#    mover, recortar o borrar una pantalla es editar una fila. Los templates y
#    las versiones guardan esa tabla, asi que un montaje se puede volver a
#    poner tal cual estaba.
#
# El build CONSERVA lo que ya estaba ajustado (pars y tabla). Para volver a los
# valores de fabrica: definir RESET_DEFAULTS = True antes de correr el script.
# ==========================================================================
import os

PARENT_PATH = globals().get('TEMPLATE_TARGET') or '/project1'
COMP_NAME = 'VIDEO_DOME'

# ruta por defecto del video (se cambia en vivo con el par Moviefile). Vacia:
# cada maquina pone la suya. build_domo.py la puede pasar en VIDEO_DOME_VIDEO.
VIDEO = globals().get('VIDEO_DOME_VIDEO') or ''

# 2048 alcanza para proyectar y para grabar; 4096 x 16 bit, multiplicado por
# las capas (pantallas, fondo, rejilla, simulador, editor), llena la memoria de
# video de la 3090 y TouchDesigner se cae. El par Res lo sube cuando haga falta.
RES = 2048          # lado del domemaster
DOME_FOV = 180.0    # angulo total del domo
FPS = 24            # el video es de 24 fps; la timeline se ajusta a eso
MAXSCREENS = 16     # tiene que coincidir con el #define del shader

# Donde viven los shaders, el modulo de pantallas y las versiones. Dentro del
# repo domo-lab es 00_TouchDesigner/video_dome; build_domo.py lo pasa en
# VIDEO_DOME_DIR. Solo se usa project.folder como ultimo recurso.
BASE_DIR = globals().get('VIDEO_DOME_DIR') or os.path.join(project.folder, '00_TouchDesigner', 'video_dome')
FRAG_PATH = os.path.join(BASE_DIR, 'dome_map.frag')
GUIDE_PATH = os.path.join(BASE_DIR, 'dome_guides.frag')
SCREENS_MOD_PATH = os.path.join(BASE_DIR, 'screens_module.py')
VERSIONS_DIR = os.path.join(BASE_DIR, 'versiones')
# El simulador de domo (theinfranet/TouchDesigner-Fulldome-Simulator) es
# opcional y no viene en el repo: si el .tox no esta, la red se construye sin
# el visor preview_dome.
SIM_TOX = globals().get('VIDEO_DOME_SIM_TOX') or os.path.join(
    project.folder, '01_Fulldome_Simulator', 'repo', 'FulldomeSimulator.tox')

# lente: distorsion de barril, vinieteo y opacidad global. El borde suave de
# cada pantalla ya no vive aca: es por pantalla, adentro de dome_map.frag.
LENS_FRAG = r'''// GLSL TOP - lente sobre el video plano, antes de mapearlo al domo
// uniform vector 0:  x = k1 (barrel<0 / pincushion>0)
//                    y = sin uso (el feather es por pantalla)
//                    z = vinieteo (0..1)
//                    w = opacidad global (0..1)
uniform vec4 uParams;

out vec4 fragColor;

void main()
{
    vec2 uv = vUV.st;
    vec2 nc = uv * 2.0 - 1.0;

    float k1  = uParams.x;
    float vig = uParams.z;
    float opa = uParams.w;

    float r2 = dot(nc, nc);
    vec2 d = nc * (1.0 + k1 * r2);

    vec4 col = vec4(0.0);
    if (abs(d.x) <= 1.0 && abs(d.y) <= 1.0) {
        col = texture(sTD2DInputs[0], d * 0.5 + 0.5);
    }

    float a = opa * (1.0 - vig * r2);
    fragColor = TDOutputSwizzle(vec4(col.rgb, col.a * a));
}
'''


def leer(ruta):
    if not os.path.isfile(ruta):
        raise RuntimeError('Falta el archivo: ' + ruta)
    with open(ruta, 'r', encoding='utf-8') as fh:
        return fh.read()


DOME_FRAG = leer(FRAG_PATH)
GUIDE_FRAG = leer(GUIDE_PATH)
SCREENS_MOD = leer(SCREENS_MOD_PATH)

# el modulo de pantallas tambien se usa aca, en el build, para escribir la
# tabla inicial: se ejecuta en un espacio propio para no ensuciar estos globals
SCR = {}
exec(compile(SCREENS_MOD, SCREENS_MOD_PATH, 'exec'), SCR)

root = op(PARENT_PATH)
if root is None:
    raise RuntimeError('No existe ' + PARENT_PATH)


# ==========================================================================
# 0. Guardar lo que habia antes de reconstruir
# ==========================================================================
KEEP = not globals().get('RESET_DEFAULTS', False)

pars_previos = {}
tabla_previa = None
momentos_previos = None
base = root.op(COMP_NAME)
if base is not None:
    if KEEP:
        for p in base.customPars:
            if p.isPulse or p.isMomentary:
                continue
            try:
                if p.mode == ParMode.EXPRESSION:
                    pars_previos[p.name] = ('expr', p.expr)
                else:
                    pars_previos[p.name] = ('val', p.eval())
            except Exception:
                pass
        vieja = base.op('screens')
        if vieja is not None and vieja.numRows > 1:
            tabla_previa = vieja.text
        vieja_m = base.op('moments')
        if vieja_m is not None and vieja_m.numRows > 1:
            momentos_previos = vieja_m.text
    base.destroy()

base = root.create(baseCOMP, COMP_NAME)
base.nodeX, base.nodeY = 0, 400
base.color = (0.55, 0.35, 0.65)


def setpar(o, names, value):
    """Asigna el primer parametro que exista de la lista (los nombres internos
    varian entre builds de TouchDesigner)."""
    for n in names:
        p = getattr(o.par, n, None)
        if p is not None:
            try:
                p.val = value
                return n
            except Exception:
                pass
    return None


def setpar_any(o, names, values, label=''):
    """Como setpar, pero probando varios valores posibles de un menu y avisando
    si ninguno entro, en vez de dejar el operador mal en silencio."""
    for n in names:
        p = getattr(o.par, n, None)
        if p is None:
            continue
        for v in values:
            try:
                p.val = v
                if str(p.eval()).lower().replace(' ', '') == str(v).lower().replace(' ', ''):
                    return n, v
            except Exception:
                continue
    print('[VIDEO_DOME] AJUSTAR A MANO: %s -> %s = %s' % (o.path, label or names[0], values[0]))
    return None, None


def expr(o, name, e):
    p = getattr(o.par, name, None)
    if p is not None:
        try:
            p.expr = e
            return True
        except Exception:
            print('[VIDEO_DOME] no se pudo poner la expresion en %s.%s' % (o.path, name))
    return False


def vec_slots(glsl_top, n):
    """El GLSL TOP trae 2 slots de vector; el par 'vec' es el largo de la
    secuencia y hay que subirlo antes de poder escribir vec2name en adelante."""
    setpar(glsl_top, ['vec'], n)


def array_slots(glsl_top, n):
    setpar(glsl_top, ['array'], n)


def write_shader(glsl_top, code):
    """Escribe el codigo real en el DAT del pixel shader. Sin esto TD deja el
    shader de ejemplo, que es literalmente vec4(1) = blanco puro."""
    p = getattr(glsl_top.par, 'pixeldat', None)
    if p is None:
        return False
    dat = p.eval()
    if dat is None:
        return False
    dat.text = code
    return True


# ==========================================================================
# 1. Parametros
# ==========================================================================
page_v = base.appendCustomPage('Video')
page_v.appendFile('Moviefile', label='Archivo de video')[0].val = VIDEO
p = page_v.appendMenu('Fuente', label='Fuente del video plano')[0]
p.menuNames = ['archivo', 'ndi', 'spout']
p.menuLabels = ['Archivo de video', 'NDI (red)', 'Spout (esta maquina)']
p.val = 'archivo'
page_v.appendStr('Ndinombre', label='Fuente NDI (nombre)')[0].val = ''
page_v.appendStr('Spoutnombre', label='Sender Spout (nombre)')[0].val = ''
page_v.appendToggle('Play', label='Reproducir')[0].val = True
page_v.appendPulse('Cue', label='Volver al inicio')
p = page_v.appendFloat('Speed', label='Velocidad')[0]
p.normMin, p.normMax, p.val = 0.0, 2.0, 1.0
page_v.appendToggle('Loopvideo', label='Loop')[0].val = True
page_v.appendToggle('Audio', label='Audio')[0].val = True
p = page_v.appendFloat('Volume', label='Volumen')[0]
p.normMin, p.normMax, p.val = 0.0, 1.0, 0.8

page_t = base.appendCustomPage('Montaje')
# OJO: appendMenu nace con name1/name2, hay que escribir los nombres siempre
p = page_t.appendMenu('Template', label='Template de pantallas')[0]
nombres_tpl = list(SCR['TEMPLATES'].keys())
p.menuNames = nombres_tpl
p.menuLabels = nombres_tpl
p.val = 'cine'
page_t.appendPulse('Applytemplate', label='Aplicar template (pisa la tabla)')
p = page_t.appendFloat('Yawglobal', label='Girar todo el montaje (grados)')[0]
p.normMin, p.normMax, p.val = -180.0, 180.0, 0.0
p = page_t.appendFloat('Domefov', label='FOV del domo (grados)')[0]
p.normMin, p.normMax, p.val = 180.0, 240.0, DOME_FOV
p = page_t.appendInt('Res', label='Lado del domemaster')[0]
p.normMin, p.normMax, p.val = 1024, 4096, RES
page_t.appendToggle('Flipx', label='Espejo horizontal de la salida')[0].val = False

page_s = base.appendCustomPage('Pantalla')
# Estos pars editan LA FILA seleccionada de la tabla. La tabla manda: si se
# edita a mano, con Leerfila los pars se ponen al dia.
p = page_s.appendInt('Screen', label='Pantalla (fila)')[0]
p.normMin, p.normMax, p.val = 1, MAXSCREENS, 1
page_s.appendStr('Sname', label='Nombre')[0].val = 'cine'
page_s.appendToggle('Son', label='Encendida')[0].val = True
p = page_s.appendMenu('Smode', label='Forma')[0]
p.menuNames = ['plana', 'curva', 'banda', 'tunel', 'cilindro']
p.menuLabels = ['Plana (rectas rectas, hasta ~100 grados)',
                'Curva (angulos iguales, para muy anchas)',
                'Banda (rectangulo en azimut/elevacion, puede dar la vuelta)',
                'Tunel (polar: el video se enrosca hacia el centro)',
                'Cilindro (pared alrededor del publico, con fuga al cenit)']
p.val = 'plana'
p = page_s.appendFloat('Syaw', label='Azimut (grados)')[0]
p.normMin, p.normMax, p.val = -180.0, 180.0, 0.0
p = page_s.appendFloat('Spitch', label='Elevacion (grados)')[0]
p.normMin, p.normMax, p.val = -20.0, 90.0, 45.0
p = page_s.appendFloat('Sroll', label='Rotacion (grados)')[0]
p.normMin, p.normMax, p.val = -180.0, 180.0, 0.0
p = page_s.appendFloat('Shfov', label='Ancho angular (grados)')[0]
p.normMin, p.normMax, p.val = 10.0, 360.0, 70.0
p = page_s.appendFloat('Svfov', label='Alto angular (grados)')[0]
p.normMin, p.normMax, p.val = 5.0, 180.0, 39.0
page_s.appendToggle('Sautovfov', label='Alto automatico (aspecto del video)')[0].val = True
p = page_s.appendMenu('Smirror', label='Espejo')[0]
p.menuNames = ['no', 'horizontal', 'vertical', 'ambos']
p.menuLabels = ['Sin espejo', 'Horizontal', 'Vertical', 'Los dos']
p.val = 'no'
p = page_s.appendFloat('Sopacity', label='Opacidad')[0]
p.normMin, p.normMax, p.val = 0.0, 1.0, 1.0
p = page_s.appendFloat('Sfeather', label='Borde suave')[0]
p.normMin, p.normMax, p.val = 0.0, 0.4, 0.04
p = page_s.appendFloat('Stile', label='Repeticiones adentro')[0]
p.normMin, p.normMax, p.val = 1.0, 8.0, 1.0
p = page_s.appendFloat('Scropx', label='Recorte X')[0]
p.normMin, p.normMax, p.val = 0.0, 1.0, 0.0
p = page_s.appendFloat('Scropy', label='Recorte Y')[0]
p.normMin, p.normMax, p.val = 0.0, 1.0, 0.0
p = page_s.appendFloat('Scropw', label='Recorte ancho')[0]
p.normMin, p.normMax, p.val = 0.05, 1.0, 1.0
p = page_s.appendFloat('Scroph', label='Recorte alto')[0]
p.normMin, p.normMax, p.val = 0.05, 1.0, 1.0
# Costura: los grados que se encima una copia con la siguiente. El shader
# reparte el pixel del solape entre las dos, asi el anillo deja de leerse como
# pantallas pegadas una al lado de la otra.
p = page_s.appendFloat('Sblend', label='Costura entre copias (grados)')[0]
p.normMin, p.normMax, p.val = 0.0, 30.0, 0.0
p = page_s.appendMenu('Sedges', label='Bordes que se degradan')[0]
p.menuNames = ['todos', 'lados', 'arribabajo']
p.menuLabels = ['Los cuatro lados',
                'Solo los costados (para anillos y bandas)',
                'Solo arriba y abajo (para cilindros)']
p.val = 'todos'
p = page_s.appendFloat('Stravel', label='Se lleva con la animacion')[0]
p.normMin, p.normMax, p.val = -2.0, 2.0, 0.0
p = page_s.appendFloat('Sspin', label='Gira con la animacion')[0]
p.normMin, p.normMax, p.val = -2.0, 2.0, 0.0

# Repeticion en anillo: la MISMA pantalla enfrente de cada sector del publico.
# Un domo lleno no tiene un frente; con rep = 4 o 6 nadie se queda mirando el
# fondo, y sigue siendo una sola fila que se mueve entera.
p = page_s.appendInt('Srep', label='Copias en anillo')[0]
p.normMin, p.normMax, p.val = 1, 12, 1
p = page_s.appendFloat('Srepspan', label='Arco que ocupan (grados)')[0]
p.normMin, p.normMax, p.val = 30.0, 360.0, 360.0
page_s.appendToggle('Srepmir', label='Espejar copias alternas')[0].val = False
p = page_s.appendFloat('Srepofs', label='Corrimiento del recorte por copia')[0]
p.normMin, p.normMax, p.val = 0.0, 1.0, 0.0
page_s.appendPulse('Addscreen', label='Agregar pantalla')
page_s.appendPulse('Dupscreen', label='Duplicar esta pantalla')
page_s.appendPulse('Delscreen', label='Borrar esta pantalla')
page_s.appendPulse('Readscreen', label='Leer la fila (si editaste la tabla)')

page_e = base.appendCustomPage('Espacio')
# Domo tipo planetario: elevado, se mira hacia arriba, y la vista da la vuelta.
# El circulo blanco de la rejilla marca cuanto abarca una mirada desde el
# asiento; lo de afuera existe pero hay que girar la cabeza para verlo.
p = page_e.appendFloat('Viewfov', label='Campo de una mirada (grados)')[0]
p.normMin, p.normMax, p.val = 60.0, 180.0, 120.0
p = page_e.appendFloat('Viewpitch', label='Elevacion de la mirada (grados)')[0]
p.normMin, p.normMax, p.val = 0.0, 90.0, 45.0
p = page_e.appendFloat('Viewyaw', label='Azimut de la mirada (grados)')[0]
p.normMin, p.normMax, p.val = -180.0, 180.0, 0.0
# cuantos puntos de vista dibuja la rejilla, repartidos en la vuelta. Con 4 o 6
# se ve de una si el montaje deja algun sector de la sala sin nada enfrente.
p = page_e.appendInt('Views', label='Puntos de vista del publico')[0]
p.normMin, p.normMax, p.val = 1, 8, 4
# El reloj de la animacion. Cada fila decide cuanto le afecta con Stravel y
# Sspin, asi que un mismo reloj puede llevarse el cilindro hacia arriba y girar
# el anillo en sentido contrario.
p = page_e.appendFloat('Animtravel', label='Velocidad de desplazamiento')[0]
p.normMin, p.normMax, p.val = -0.5, 0.5, 0.05
p = page_e.appendFloat('Animspin', label='Velocidad de giro (grados/seg)')[0]
p.normMin, p.normMax, p.val = -30.0, 30.0, 0.0

page_ed = base.appendCustomPage('Editor')
# El editor es un panel con el domemaster de fondo: se hace click adentro y la
# pantalla seleccionada se va ahi. Escribir azimut y elevacion a mano funciona,
# pero no deja "componer": hay que ver el domo mientras se mueve.
page_ed.appendPulse('Openeditor', label='Abrir el editor en una ventana')
page_ed.appendToggle('Edit', label='Mover con el mouse')[0].val = False
p = page_ed.appendMenu('Editwhat', label='El arrastre cambia')[0]
p.menuNames = ['mover', 'tamano', 'girar']
p.menuLabels = ['Ubicacion (azimut y elevacion)',
                'Tamano (ancho angular)',
                'Rotacion (roll)']
p.val = 'mover'
page_ed.appendToggle('Editsnap', label='Pegar a la rejilla')[0].val = False
p = page_ed.appendFloat('Editstep', label='Paso de la rejilla (grados)')[0]
p.normMin, p.normMax, p.val = 1.0, 45.0, 5.0

page_b = base.appendCustomPage('Fondo')
p = page_b.appendMenu('Bg', label='Fondo')[0]
p.menuNames = ['off', 'wash', 'wrap', 'custom']
p.menuLabels = ['Sin fondo (negro)',
                'Lavado: copia agrandada del cuadro',
                'Envolvente: el cuadro da la vuelta',
                'TOP externo (POPs, otro video...)']
p.val = 'wrap'
page_b.appendTOP('Bgtop', label='TOP externo')
p = page_b.appendFloat('Bgblur', label='Desenfoque')[0]
p.normMin, p.normMax, p.val = 0.0, 200.0, 60.0
p = page_b.appendFloat('Bgbright', label='Brillo')[0]
p.normMin, p.normMax, p.val = 0.0, 2.0, 0.35
p = page_b.appendFloat('Bgsat', label='Saturacion')[0]
p.normMin, p.normMax, p.val = 0.0, 2.0, 0.7
# el zoom del lavado tiene que ser >= al aspecto del video (1.78 en 16:9) o
# aparecen bandas rectas de borde estirado contra el circulo
p = page_b.appendFloat('Bgzoom', label='Zoom del lavado')[0]
p.normMin, p.normMax, p.val = 1.0, 4.0, 1.8
p = page_b.appendFloat('Bgtile', label='Repeticiones del envolvente')[0]
p.normMin, p.normMax, p.val = 1.0, 8.0, 2.0
p = page_b.appendFloat('Bgyaw', label='Girar el fondo (grados)')[0]
p.normMin, p.normMax, p.val = -180.0, 180.0, 0.0
# con esto el fondo acompana al montaje: si se gira todo, la costura del
# envolvente no se queda atras y el fondo deja de "perderse"
page_b.appendToggle('Bgfollow', label='El fondo sigue el giro global')[0].val = True

page_l = base.appendCustomPage('Look')
p = page_l.appendFloat('Opacity', label='Opacidad global')[0]
p.normMin, p.normMax, p.val = 0.0, 1.0, 1.0
p = page_l.appendFloat('Vignette', label='Vinieteo')[0]
p.normMin, p.normMax, p.val = 0.0, 1.0, 0.0
p = page_l.appendFloat('K1', label='Distorsion de lente')[0]
p.normMin, p.normMax, p.val = -0.5, 0.5, 0.0

page_g = base.appendCustomPage('Guias')
page_g.appendToggle('Guides', label='Rejilla de referencia')[0].val = False
p = page_g.appendFloat('Guidealpha', label='Opacidad de la rejilla')[0]
p.normMin, p.normMax, p.val = 0.0, 1.0, 0.6
p = page_g.appendFloat('Guidewidth', label='Grosor de linea')[0]
p.normMin, p.normMax, p.val = 0.5, 4.0, 1.2
p = page_g.appendFloat('Guidering', label='Anillos cada (grados)')[0]
p.normMin, p.normMax, p.val = 5.0, 45.0, 15.0
p = page_g.appendFloat('Guideray', label='Radios cada (grados)')[0]
p.normMin, p.normMax, p.val = 15.0, 90.0, 30.0
page_g.appendToggle('Preview', label='Simulador de domo (mirar desde adentro)')[0].val = True

page_ver = base.appendCustomPage('Versiones')
# Una version guarda TODOS los pars + la tabla de pantallas. El .toe y git
# llevan el historial del proyecto; esto guarda montajes para volver a ellos.
p = page_ver.appendStr('Versionname', label='Nombre de la version')[0]
p.val = 'v1'
page_ver.appendPulse('Saveversion', label='Guardar version')
p = page_ver.appendMenu('Version', label='Version guardada')[0]
_vers = []
if os.path.isdir(VERSIONS_DIR):
    _vers = sorted(f[:-5] for f in os.listdir(VERSIONS_DIR) if f.endswith('.json'))
p.menuNames = _vers or ['ninguna']
p.menuLabels = _vers or ['(no hay versiones guardadas)']
page_ver.appendPulse('Loadversion', label='Cargar version')
page_ver.appendPulse('Refreshversions', label='Refrescar lista')

page_m = base.appendCustomPage('Momentos')
# Un momento = un minuto de la pelicula + el montaje que le toca. La tabla
# `moments` los guarda ordenados por tiempo; el motor los va aplicando y funde
# de uno al siguiente. Asi un fragmento puede ser tunel, el que sigue duplicado
# y el otro en espejo, sin tocar nada mientras corre.
page_m.appendToggle('Moments', label='Seguir los momentos')[0].val = False
p = page_m.appendStr('Momentname', label='Nombre del momento')[0]
p.val = 'momento'
p = page_m.appendFloat('Momentfade', label='Fusion por defecto (segundos)')[0]
p.normMin, p.normMax, p.val = 0.0, 10.0, 1.5
page_m.appendPulse('Addmoment', label='Marcar aca el montaje de ahora')
p = page_m.appendMenu('Moment', label='Momento')[0]
p.menuNames = ['ninguno']
p.menuLabels = ['(no hay momentos)']
page_m.appendPulse('Gotomoment', label='Ir a ese momento')
page_m.appendPulse('Delmoment', label='Borrar ese momento')
page_m.appendPulse('Refreshmoments', label='Refrescar la lista')
# lo escribe el motor durante una fusion: 0 = montaje nuevo, 1 = el anterior
p = page_m.appendFloat('Fade', label='Fusion en curso')[0]
p.normMin, p.normMax, p.val = 0.0, 1.0, 0.0

page_r = base.appendCustomPage('Grabar')
page_r.appendFile('Recfile', label='Archivo de salida')[0].val = (
    '05_Media/pantallas_domemaster.mov')
page_r.appendToggle('Record', label='Grabar')[0].val = False
p = page_r.appendInt('Recres', label='Lado del render grabado')[0]
p.normMin, p.normMax, p.val = 1024, 4096, 2048


# ==========================================================================
# 2. Fuente: video + audio
# ==========================================================================
movie = base.create(moviefileinTOP, 'movie1')
movie.nodeX, movie.nodeY = -1100, 0
movie.color = (0.6, 0.4, 0.2)
expr(movie, 'file', "parent().par.Moviefile")
expr(movie, 'play', "parent().par.Play")
expr(movie, 'speed', "parent().par.Speed")
expr(movie, 'extendright', "'loop' if parent().par.Loopvideo else 'hold'")
expr(movie, 'extendleft', "'loop' if parent().par.Loopvideo else 'hold'")

# La fuente plana puede llegar tambien por NDI o por Spout (otro TouchDesigner,
# Resolume, OBS, una camara...). `fuente` elige y es lo que ve el resto de la
# red; movie1 sigue siendo el reloj del video (index/rate) para los momentos.
ndi_in = base.create(ndiinTOP, 'ndi_in')
ndi_in.nodeX, ndi_in.nodeY = -1100, 120
expr(ndi_in, 'name', "parent().par.Ndinombre")
expr(ndi_in, 'active', "parent().par.Fuente == 'ndi'")
spout_in = base.create(syphonspoutinTOP, 'spout_in')
spout_in.nodeX, spout_in.nodeY = -1100, 240
expr(spout_in, 'sendername', "parent().par.Spoutnombre")
# Sin visor: asi no cocinan (ni marcan error) mientras la fuente sea el archivo.
ndi_in.viewer = False
spout_in.viewer = False
fuente = base.create(switchTOP, 'fuente')
fuente.nodeX, fuente.nodeY = -1000, 60
fuente.inputConnectors[0].connect(movie)
fuente.inputConnectors[1].connect(ndi_in)
fuente.inputConnectors[2].connect(spout_in)
expr(fuente, 'index', "parent().par.Fuente.menuIndex")

# audio del propio archivo, sincronizado al TOP. No un Audio File In aparte:
# ese abre el archivo por segunda vez y se desincroniza al cambiar de speed.
amov = base.create(audiomovieCHOP, 'audio_movie')
amov.nodeX, amov.nodeY = -1100, -180
setpar(amov, ['moviefileintop', 'top', 'movietop'], movie.path)

again = base.create(mathCHOP, 'audio_gain')
again.nodeX, again.nodeY = -920, -180
again.inputConnectors[0].connect(amov)
expr(again, 'gain', "parent().par.Volume * parent().par.Audio")

aout = base.create(audiodeviceoutCHOP, 'audio_out')
aout.nodeX, aout.nodeY = -740, -180
aout.inputConnectors[0].connect(again)
expr(aout, 'active', "parent().par.Audio")

soft = base.create(glslTOP, 'soft')
soft.nodeX, soft.nodeY = -900, 0
soft.inputConnectors[0].connect(fuente)
setpar(soft, ['outputresolution'], 'useinput')
write_shader(soft, LENS_FRAG)
# en TD 2025 los uniforms son vec0valuex..w y hace falta escribir vec0name,
# si no el shader nunca ve 'uParams' y los valores no se bindean
setpar(soft, ['vec0name', 'value0name'], 'uParams')
expr(soft, 'vec0valuex', "parent().par.K1")
setpar(soft, ['vec0valuey'], 0.0)
expr(soft, 'vec0valuez', "parent().par.Vignette")
expr(soft, 'vec0valuew', "parent().par.Opacity")

vid = base.create(nullTOP, 'video_out')
vid.nodeX, vid.nodeY = -720, 0
vid.inputConnectors[0].connect(soft)


# ==========================================================================
# 3. La tabla de pantallas -> CHOP -> arrays del shader
# ==========================================================================
mod_dat = base.create(textDAT, 'screens_mod')
mod_dat.nodeX, mod_dat.nodeY = -1100, 240
mod_dat.text = SCREENS_MOD

tabla = base.create(tableDAT, 'screens')
tabla.nodeX, tabla.nodeY = -1100, 160
tabla.color = (0.35, 0.55, 0.35)
if tabla_previa:
    # la tabla que habia se relee y se vuelve a escribir con las columnas de
    # hoy: asi una tabla vieja (sin rep*) se migra sola y de paso se limpian
    # celdas como 'True' que el DAT to CHOP no sabe convertir
    tabla.text = tabla_previa
    SCR['write_table'](tabla, SCR['read_table'](tabla))
else:
    SCR['write_table'](tabla, SCR['rows_from_template']('cine'))

# una fila de la tabla = una muestra del CHOP; cada columna, un canal.
# 'chanpercol' es la clave: con el default ('chanperrow') sale un canal por
# pantalla y el shader no puede leerlo como arrays.
# La columna de texto 'name' viaja como un canal en cero y no molesta: los
# Select CHOP de abajo eligen por nombre.
chop = base.create(dattoCHOP, 'screens_chop')
chop.nodeX, chop.nodeY = -900, 160
setpar(chop, ['dat'], tabla.path)
setpar(chop, ['output'], 'chanpercol')
setpar_any(chop, ['firstrow'], ['names', 'firstrowisnames'], 'First Row')
# y 'First Column' = values: por defecto el DAT to CHOP se COME la primera
# columna como nombres de muestra, y el canal 'yaw' desaparecia sin avisar
setpar_any(chop, ['firstcol', 'firstcolumn'], ['values', 'ignore'], 'First Column')

# seis grupos de cuatro columnas: cada uno entra al shader como un array de
# vec4. El ORDEN de las columnas en la tabla es el orden de x,y,z,w.
GRUPOS = [('pos', SCR['COLS'][0:4]),
          ('size', SCR['COLS'][4:8]),
          ('crop', SCR['COLS'][8:12]),
          ('opt', SCR['COLS'][12:16]),
          ('rep', SCR['COLS'][16:20]),
          ('anm', SCR['COLS'][20:24])]

def cortar_grupos(chop_fuente, sufijo, y0):
    """Parte el CHOP de la tabla en los cinco grupos de cuatro canales."""
    salida = {}
    yy = y0
    for nombre, cols in GRUPOS:
        sel = base.create(selectCHOP, 'sel_' + nombre + sufijo)
        sel.nodeX, sel.nodeY = -560, yy
        sel.inputConnectors[0].connect(chop_fuente)
        setpar(sel, ['channames'], ' '.join(cols))
        salida[nombre] = sel
        yy -= 80
    return salida


sel_chops = cortar_grupos(chop, '', 160)


def bind_arrays(glsl_top, grupos, fuente=None):
    """Conecta los CHOP de la tabla como arrays de vec4 del shader."""
    fuente = fuente if fuente is not None else sel_chops
    array_slots(glsl_top, len(grupos))
    for i, nombre in enumerate(grupos):
        setpar(glsl_top, ['array%dname' % i], 'u' + nombre.capitalize())
        setpar_any(glsl_top, ['array%dtype' % i], ['vec4'], 'Array Type')
        setpar(glsl_top, ['array%dchop' % i], fuente[nombre].path)
        setpar_any(glsl_top, ['array%darraytype' % i],
                   ['uniformarray', 'texturebuffer'], 'Array Kind')


# ---- capa B: el montaje que se esta yendo durante una fusion --------------
# Los momentos encadenan montajes; para pasar de uno a otro sin corte hacen
# falta los dos dibujados a la vez. La capa B es una copia de la A con su
# propia tabla: mientras no hay fusion no cocina (el Switch de abajo solo
# cocina la entrada que usa), asi que no cuesta nada estar quieto.
tabla_b = base.create(tableDAT, 'screens_b')
tabla_b.nodeX, tabla_b.nodeY = -1100, 80
tabla_b.color = (0.35, 0.45, 0.55)
tabla_b.text = tabla.text

chop_b = base.create(dattoCHOP, 'screens_chop_b')
chop_b.nodeX, chop_b.nodeY = -900, 80
setpar(chop_b, ['dat'], tabla_b.path)
setpar(chop_b, ['output'], 'chanpercol')
setpar_any(chop_b, ['firstrow'], ['names', 'firstrowisnames'], 'First Row')
setpar_any(chop_b, ['firstcol', 'firstcolumn'], ['values', 'ignore'], 'First Column')

sel_chops_b = cortar_grupos(chop_b, '_b', -280)


# ==========================================================================
# 4. Mapeo al domemaster
# ==========================================================================
dome = base.create(glslTOP, 'dome_map')
dome.nodeX, dome.nodeY = -360, 0
dome.inputConnectors[0].connect(vid)
write_shader(dome, DOME_FRAG)
setpar(dome, ['outputresolution'], 'custom')
expr(dome, 'resolutionw', "parent().par.Res")
expr(dome, 'resolutionh', "parent().par.Res")
# 16 bit float: el domemaster se estira mucho al proyectar y en 8 bit se ven
# escalones en los degrades del cielo
setpar(dome, ['format'], 'rgba16float')

vec_slots(dome, 3)
setpar(dome, ['vec0name'], 'uView')
expr(dome, 'vec0valuex', "parent().par.Domefov")
expr(dome, 'vec0valuey', "op('fuente').width / max(op('fuente').height, 1)")
expr(dome, 'vec0valuez', "max(op('screens').numRows - 1, 0)")
expr(dome, 'vec0valuew', "parent().par.Yawglobal")
setpar(dome, ['vec1name'], 'uBg')
setpar(dome, ['vec1valuew'], 0)      # 0 = capa de pantallas
# La animacion es un reloj global y cada fila decide cuanto le afecta. Va por
# expresion sobre absTime: cambiar la velocidad da un salto, pero no hace falta
# ningun operador que integre ni nada que se desincronice al recargar.
setpar(dome, ['vec2name'], 'uAnim')
expr(dome, 'vec2valuex', "absTime.seconds * parent().par.Animtravel")
expr(dome, 'vec2valuey', "absTime.seconds * parent().par.Animspin")
bind_arrays(dome, ['pos', 'size', 'crop', 'opt', 'rep', 'anm'])

# --- capa B: mismo shader, otra tabla; solo se usa mientras hay fusion ---
dome_b = base.create(glslTOP, 'dome_map_b')
dome_b.nodeX, dome_b.nodeY = -360, -420
dome_b.inputConnectors[0].connect(vid)
write_shader(dome_b, DOME_FRAG)
setpar(dome_b, ['outputresolution'], 'custom')
expr(dome_b, 'resolutionw', "parent().par.Res")
expr(dome_b, 'resolutionh', "parent().par.Res")
setpar(dome_b, ['format'], 'rgba16float')
vec_slots(dome_b, 3)
setpar(dome_b, ['vec0name'], 'uView')
expr(dome_b, 'vec0valuex', "parent().par.Domefov")
expr(dome_b, 'vec0valuey', "op('fuente').width / max(op('fuente').height, 1)")
expr(dome_b, 'vec0valuez', "max(op('screens_b').numRows - 1, 0)")
expr(dome_b, 'vec0valuew', "parent().par.Yawglobal")
setpar(dome_b, ['vec1name'], 'uBg')
setpar(dome_b, ['vec1valuew'], 0)
setpar(dome_b, ['vec2name'], 'uAnim')
expr(dome_b, 'vec2valuex', "absTime.seconds * parent().par.Animtravel")
expr(dome_b, 'vec2valuey', "absTime.seconds * parent().par.Animspin")
bind_arrays(dome_b, ['pos', 'size', 'crop', 'opt', 'rep', 'anm'], sel_chops_b)

# Fade = 0 es la capa A sola. El Cross TOP mezcla; el Switch de abajo decide
# si hace falta mezclar. Un Switch TOP solo cocina la entrada que usa, asi que
# fuera de las fusiones ni el Cross ni la capa B corren.
cross = base.create(crossTOP, 'fade_cross')
cross.nodeX, cross.nodeY = -200, -420
cross.inputConnectors[0].connect(dome)
cross.inputConnectors[1].connect(dome_b)
expr(cross, 'cross', "parent().par.Fade")

capa = base.create(switchTOP, 'fade_switch')
capa.nodeX, capa.nodeY = -60, -300
capa.inputConnectors[0].connect(dome)
capa.inputConnectors[1].connect(cross)
expr(capa, 'index', "1 if parent().par.Fade > 0.001 else 0")


# ==========================================================================
# 5. Capa de fondo
# ==========================================================================
# El desenfoque va ANTES del mapeo, sobre los 1920x1080 del video: desenfocar
# despues seria sobre 4096x4096, 16 veces mas pixeles para el mismo resultado.
bgsrc = base.create(selectTOP, 'bg_src')
bgsrc.nodeX, bgsrc.nodeY = -720, -220
# OJO: en un par de tipo OP, un nombre pelado es un HERMANO y './nombre' es un
# hijo. Aca hace falta el hermano video_out, asi que va sin './'.
expr(bgsrc, 'top',
     "parent().par.Bgtop.eval().path "
     "if parent().par.Bg.eval() == 'custom' and parent().par.Bgtop.eval() "
     "else 'video_out'")

bgblur = base.create(blurTOP, 'bg_blur')
bgblur.nodeX, bgblur.nodeY = -560, -220
bgblur.inputConnectors[0].connect(bgsrc)
expr(bgblur, 'size', "parent().par.Bgblur")
setpar_any(bgblur, ['extend', 'extendu'], ['mirror', 'hold'], 'Extend')

bglvl = base.create(levelTOP, 'bg_level')
bglvl.nodeX, bglvl.nodeY = -420, -220
bglvl.inputConnectors[0].connect(bgblur)
expr(bglvl, 'brightness1', "parent().par.Bgbright")
expr(bglvl, 'saturation', "parent().par.Bgsat")

bgmap = base.create(glslTOP, 'bg_map')
bgmap.nodeX, bgmap.nodeY = -260, -220
bgmap.inputConnectors[0].connect(bglvl)
write_shader(bgmap, DOME_FRAG)
setpar(bgmap, ['outputresolution'], 'custom')
expr(bgmap, 'resolutionw', "parent().par.Res")
expr(bgmap, 'resolutionh', "parent().par.Res")
setpar(bgmap, ['format'], 'rgba16float')
vec_slots(bgmap, 3)
setpar(bgmap, ['vec0name'], 'uView')
expr(bgmap, 'vec0valuex', "parent().par.Domefov")
expr(bgmap, 'vec0valuey', "op('bg_src').width / max(op('bg_src').height, 1)")
setpar(bgmap, ['vec0valuez'], 0)     # el fondo no usa pantallas
setpar(bgmap, ['vec1name'], 'uBg')
expr(bgmap, 'vec1valuex', "parent().par.Bgzoom")
expr(bgmap, 'vec1valuey', "parent().par.Bgtile")
# el giro del fondo: propio, y opcionalmente sumado al giro global del montaje
expr(bgmap, 'vec1valuez',
     "parent().par.Bgyaw + (parent().par.Yawglobal if parent().par.Bgfollow else 0)")
# modo 4 = envolvente, 5 = lavado. 'custom' usa el lavado sobre el TOP externo.
expr(bgmap, 'vec1valuew', "4 if parent().par.Bg.eval() == 'wrap' else 5")
setpar(bgmap, ['vec2name'], 'uAnim')
# el fondo no dibuja pantallas, pero el shader es el mismo archivo y GLSL exige
# que TODOS los uniforms declarados esten asignados: sin esto TD avisa
# "Uniform 'uPos' is not assigned"
bind_arrays(bgmap, ['pos', 'size', 'crop', 'opt', 'rep', 'anm'])

# la capa de pantallas va ENCIMA del fondo. Over TOP y no Composite: el Over
# respeta el alpha de la entrada de arriba, que es el borde suave de cada
# pantalla.
over = base.create(overTOP, 'comp_bg')
over.nodeX, over.nodeY = -100, -100
over.inputConnectors[0].connect(capa)
over.inputConnectors[1].connect(bgmap)

bgsw = base.create(switchTOP, 'bg_switch')
bgsw.nodeX, bgsw.nodeY = 60, 0
bgsw.inputConnectors[0].connect(capa)
bgsw.inputConnectors[1].connect(over)
expr(bgsw, 'index', "0 if parent().par.Bg.eval() == 'off' else 1")


# ==========================================================================
# 6. Rejilla de referencia
# ==========================================================================
guides = base.create(glslTOP, 'guides')
guides.nodeX, guides.nodeY = 60, 220
write_shader(guides, GUIDE_FRAG)
setpar(guides, ['outputresolution'], 'custom')
expr(guides, 'resolutionw', "parent().par.Res")
expr(guides, 'resolutionh', "parent().par.Res")
vec_slots(guides, 5)
setpar(guides, ['vec0name'], 'uView')
expr(guides, 'vec0valuex', "parent().par.Domefov")
expr(guides, 'vec0valuey', "op('fuente').width / max(op('fuente').height, 1)")
expr(guides, 'vec0valuez', "max(op('screens').numRows - 1, 0)")
expr(guides, 'vec0valuew', "parent().par.Yawglobal")
setpar(guides, ['vec1name'], 'uGuide')
expr(guides, 'vec1valuex', "parent().par.Guidewidth")
expr(guides, 'vec1valuey', "parent().par.Guidealpha")
expr(guides, 'vec1valuez', "parent().par.Guidering")
expr(guides, 'vec1valuew', "parent().par.Guideray")
setpar(guides, ['vec2name'], 'uField')
expr(guides, 'vec2valuex', "parent().par.Viewfov")
expr(guides, 'vec2valuey', "parent().par.Viewpitch")
expr(guides, 'vec2valuez', "parent().par.Viewyaw")
expr(guides, 'vec2valuew', "parent().par.Screen - 1")
setpar(guides, ['vec3name'], 'uSeats')
expr(guides, 'vec3valuex', "parent().par.Views")
setpar(guides, ['vec4name'], 'uAnim')
expr(guides, 'vec4valuex', "absTime.seconds * parent().par.Animtravel")
expr(guides, 'vec4valuey', "absTime.seconds * parent().par.Animspin")
bind_arrays(guides, ['pos', 'size', 'opt', 'rep', 'anm'])

gover = base.create(overTOP, 'comp_guides')
gover.nodeX, gover.nodeY = 220, 120
gover.inputConnectors[0].connect(guides)
gover.inputConnectors[1].connect(bgsw)

gsw = base.create(switchTOP, 'guides_switch')
gsw.nodeX, gsw.nodeY = 380, 0
gsw.inputConnectors[0].connect(bgsw)
gsw.inputConnectors[1].connect(gover)
# no hace falta apagar la rejilla a mano: un Switch TOP solo cocina la entrada
# que usa, asi que con Guides en off este shader de 4096x4096 no corre
expr(gsw, 'index', "parent().par.Guides")


# ==========================================================================
# 7. Salida
# ==========================================================================
flip = base.create(flipTOP, 'flip1')
flip.nodeX, flip.nodeY = 540, 0
flip.inputConnectors[0].connect(gsw)
expr(flip, 'flipx', "parent().par.Flipx")

out = base.create(nullTOP, 'out_dome')
out.nodeX, out.nodeY = 700, 0
out.inputConnectors[0].connect(flip)
out.color = (0.9, 0.5, 0.2)


# ==========================================================================
# 8. Mirar desde adentro del domo
# ==========================================================================
def find_simulator(start, skip, depth=3):
    """Busca el .tox del simulador por su par Camerafov, recorriendo los hijos
    a mano: findChildren() NO devuelve los COMP cargados desde un tox externo,
    asi que con el buscador de TD el simulador del rig NDI queda invisible."""
    nivel = [start]
    for _ in range(depth):
        siguiente = []
        for o in nivel:
            for c in o.children:
                if not c.isCOMP or c is skip:
                    continue
                if getattr(c.par, 'Camerafov', None) is not None:
                    return c
                siguiente.append(c)
        nivel = siguiente
    return None


sim_src = find_simulator(root, base)
sim = None
if sim_src is not None:
    sim = base.copy(sim_src, name='preview_dome')
elif os.path.isfile(SIM_TOX):
    sim = base.create(baseCOMP, 'preview_dome')
    try:
        sim.loadTox(SIM_TOX)
    except Exception as e:
        print('[VIDEO_DOME] no pude cargar el simulador:', e)
else:
    print('[VIDEO_DOME] no encontre el simulador: %s' % SIM_TOX)

if sim is not None:
    sim.nodeX, sim.nodeY = 900, 240
    sim.color = (0.3, 0.6, 0.4)
    try:
        out.outputConnectors[0].connect(sim.inputConnectors[0])
    except Exception as e:
        print('[VIDEO_DOME] conectar out_dome al simulador a mano:', e)
    setpar(sim, ['Inputresolution'], RES)
    setpar(sim, ['Camerafov'], 110.0)
    # allowCooking es un atributo del COMP, no un parametro: no se puede poner
    # por expresion. Lo escribe onValueChange de watcher al tocar Preview.
    sim.allowCooking = bool(base.par.Preview.eval())


# ==========================================================================
# 8b. Editor: ubicar las pantallas con el mouse sobre el domemaster
#
# Un contenedor con el domemaster de fondo. El Panel CHOP da la posicion del
# cursor adentro del panel (u, v) y el click; de ahi se saca la direccion en la
# cupula con la misma cuenta que hace el shader, al reves.
#
# Se dibuja la version CON rejilla y SIN el flip de salida: la rejilla es la
# referencia para ubicar, y el flip es cosa del proyector, no del montaje.
# ==========================================================================
# El panel mide 900 px de lado: mandarle el domemaster de 4096x4096 es pedirle
# a la GPU una textura 20 veces mas grande de lo que se va a ver, y con el
# simulador y la rejilla encendidos al mismo tiempo eso llena la memoria de
# video. Esta copia chica es la que se muestra.
edview = base.create(resolutionTOP, 'editor_view')
edview.nodeX, edview.nodeY = 220, 420
edview.inputConnectors[0].connect(gsw)
setpar(edview, ['outputresolution'], 'custom')
setpar(edview, ['resolutionw'], 1024)
setpar(edview, ['resolutionh'], 1024)

editor = base.create(containerCOMP, 'editor')
editor.nodeX, editor.nodeY = 380, 420
editor.color = (0.25, 0.45, 0.7)
setpar(editor, ['w', 'width'], 900)
setpar(editor, ['h', 'height'], 900)
setpar(editor, ['top'], edview.path)
setpar(editor, ['opacity'], 1.0)
setpar_any(editor, ['topfill'], ['fitbest', 'fit best', 'best'], 'Top Fill')
setpar(editor, ['bgcolorr'], 0.06)
setpar(editor, ['bgcolorg'], 0.06)
setpar(editor, ['bgcolorb'], 0.08)

epanel = base.create(panelCHOP, 'editor_panel')
epanel.nodeX, epanel.nodeY = 560, 420
# OJO: el par se llama 'component', no 'panel'. Con el nombre equivocado el
# Panel CHOP se queda apuntando al COMP de arriba y avisa que no lo encuentra.
setpar(epanel, ['component', 'panel'], editor.path)
# el Panel CHOP saca 50 canales por defecto; con estos tres alcanza y no
# cocina de mas en cada cuadro
setpar(epanel, ['scope'], 'select u v')

eexec = base.create(chopexecuteDAT, 'editor_exec')
eexec.nodeX, eexec.nodeY = 720, 420
setpar(eexec, ['chop'], epanel.path)
setpar(eexec, ['channels'], 'select u v')
setpar(eexec, ['offtoon'], True)
setpar(eexec, ['whileon'], True)
setpar(eexec, ['valuechange'], False)
eexec.text = '''# Editor de pantallas: el mouse sobre el domemaster mueve la fila seleccionada.
#
# El domemaster es azimutal equidistante: el radio desde el centro ES el angulo
# desde el cenit. Por eso pasar de (u, v) del panel a (azimut, elevacion) es la
# misma cuenta del shader dada vuelta, sin proyeccion inversa rara.
import math


def comp():
    return me.parent()


def dome_dir(u, v, fov):
    """(u, v) del panel -> (azimut, elevacion) en grados. None si cae afuera."""
    x = u * 2.0 - 1.0
    y = v * 2.0 - 1.0
    r = math.hypot(x, y)
    if r > 1.0:
        return None
    theta = r * math.radians(fov * 0.5)
    phi = math.atan2(x, -y)              # 0 = abajo del cuadro = frente
    return math.degrees(phi), 90.0 - math.degrees(theta)


def pegar(v, paso):
    return round(v / paso) * paso if paso > 0 else v


def elegir_mas_cerca(c, az, el):
    """Sin el modo mover, un click elige la pantalla cuyo centro este mas cerca:
    asi se pasa de una a otra mirando el domo, no la tabla."""
    mod = c.op('screens_mod').module
    filas = mod.read_table(c.op('screens'))
    if not filas:
        return
    giro = c.par.Yawglobal.eval()
    mejor, dist = 1, 1e9
    for i, f in enumerate(filas):
        d = abs((f['yaw'] + giro - az + 180.0) % 360.0 - 180.0) + abs(f['pitch'] - el)
        if d < dist:
            mejor, dist = i + 1, d
    c.par.Screen = mejor


def aplicar(c, az, el):
    modo = c.par.Editwhat.eval()
    if c.par.Editsnap.eval():
        paso = c.par.Editstep.eval()
        az, el = pegar(az, paso), pegar(el, paso)
    if modo == 'mover':
        # el yaw de la tabla es relativo al giro global del montaje
        c.par.Syaw = (az - c.par.Yawglobal.eval() + 180.0) % 360.0 - 180.0
        c.par.Spitch = max(-20.0, min(90.0, el))
    elif modo == 'tamano':
        # la distancia angular del cursor al centro de la pantalla es el radio:
        # el ancho es el doble
        yaw = c.par.Syaw.eval() + c.par.Yawglobal.eval()
        pitch = c.par.Spitch.eval()
        a1, e1 = math.radians(yaw), math.radians(pitch)
        a2, e2 = math.radians(az), math.radians(el)
        cosang = (math.sin(e1) * math.sin(e2)
                  + math.cos(e1) * math.cos(e2) * math.cos(a2 - a1))
        ang = math.degrees(math.acos(max(-1.0, min(1.0, cosang))))
        c.par.Shfov = max(10.0, min(360.0, ang * 2.0))
    else:
        yaw = c.par.Syaw.eval() + c.par.Yawglobal.eval()
        c.par.Sroll = (az - yaw + 180.0) % 360.0 - 180.0


def mover(channel):
    c = comp()
    ch = channel.owner
    u, v = ch['u'].eval(), ch['v'].eval()
    d = dome_dir(u, v, c.par.Domefov.eval())
    if d is None:
        return
    az, el = d
    if not c.par.Edit.eval():
        return
    aplicar(c, az, el)


def onOffToOn(channel, sampleIndex, val, prev):
    if channel.name != 'select':
        return
    c = comp()
    ch = channel.owner
    d = dome_dir(ch['u'].eval(), ch['v'].eval(), c.par.Domefov.eval())
    if d is None:
        return
    if c.par.Edit.eval():
        aplicar(c, d[0], d[1])
    else:
        # con el modo mover apagado el click no mueve nada: solo selecciona
        elegir_mas_cerca(c, d[0], d[1])
    return


def whileOn(channel, sampleIndex, val, prev):
    if channel.name == 'select':
        mover(channel)
    return
'''


# ==========================================================================
# 9. Grabacion del domemaster
# ==========================================================================
recres = base.create(resolutionTOP, 'rec_res')
recres.nodeX, recres.nodeY = 700, -240
recres.inputConnectors[0].connect(flip)
setpar(recres, ['outputresolution'], 'custom')
expr(recres, 'resolutionw', "parent().par.Recres")
expr(recres, 'resolutionh', "parent().par.Recres")

rec = base.create(moviefileoutTOP, 'rec_out')
rec.nodeX, rec.nodeY = 880, -240
rec.inputConnectors[0].connect(recres)
expr(rec, 'file', "parent().par.Recfile")
expr(rec, 'record', "parent().par.Record")
setpar_any(rec, ['videocodec'], ['hap', 'prores', 'h264'], 'Video Codec')


# ==========================================================================
# 9b. Momentos: encadenar montajes a lo largo de la pelicula
# ==========================================================================
moments = base.create(tableDAT, 'moments')
moments.nodeX, moments.nodeY = -1100, 0
moments.color = (0.55, 0.45, 0.25)
if momentos_previos:
    moments.text = momentos_previos
else:
    moments.appendRow(['t', 'fade', 'layout', 'name'])

mexec = base.create(executeDAT, 'moments_exec')
mexec.nodeX, mexec.nodeY = -900, 0
setpar(mexec, ['framestart'], True)
mexec.text = ("VERSIONS_DIR = r'" + VERSIONS_DIR + "'\n" + '''
import json
import os

# el momento que esta puesto y el estado de la fusion, entre cuadro y cuadro
_estado = {'i': -1, 'fin': 0.0, 'dur': 0.0}


def comp():
    return me.parent()


def segundos(c):
    """Donde va la pelicula, en segundos. El Movie File In no expone la
    duracion pero si el indice de cuadro y su rate, que es lo que hace falta."""
    m = c.op('movie1')
    if m is None or not m.rate:
        return 0.0
    return m.index / m.rate


def momentos(c):
    t = c.op('moments')
    filas = []
    for i in range(1, t.numRows):
        try:
            filas.append({'fila': i,
                          't': float(t[i, 't'].val),
                          'fade': float(t[i, 'fade'].val),
                          'layout': t[i, 'layout'].val,
                          'name': t[i, 'name'].val})
        except ValueError:
            continue
    filas.sort(key=lambda f: f['t'])
    return filas


def cual(filas, t):
    """El ultimo momento que ya empezo. -1 antes del primero."""
    elegido = -1
    for k, f in enumerate(filas):
        if t + 1e-4 >= f['t']:
            elegido = k
        else:
            break
    return elegido


def layout_a_tabla(c, nombre, dat):
    """Escribe en `dat` la tabla de pantallas de una version guardada."""
    mod = c.op('screens_mod').module
    ruta = os.path.join(VERSIONS_DIR, str(nombre) + '.json')
    if os.path.isfile(ruta):
        with open(ruta, 'r', encoding='utf-8') as fh:
            datos = json.load(fh)
        if datos.get('__screens__'):
            dat.text = datos['__screens__']
            mod.write_table(dat, mod.read_table(dat))
            return True
    if nombre in mod.TEMPLATES:
        mod.write_table(dat, mod.rows_from_template(nombre))
        return True
    return False


def aplicar_momento(c, f, fundir=True):
    """El montaje que estaba pasa a la capa B y el nuevo entra en la A; la
    fusion es solo bajar Fade de 1 a 0."""
    if fundir:
        c.op('screens_b').text = c.op('screens').text
    if not layout_a_tabla(c, f['layout'], c.op('screens')):
        print('[VIDEO_DOME] momento sin montaje:', f['layout'])
        return
    dur = max(f['fade'], 0.0)
    if fundir and dur > 0.0:
        c.par.Fade = 1.0
        _estado['fin'] = absTime.seconds + dur
        _estado['dur'] = dur
    else:
        c.par.Fade = 0.0
        _estado['dur'] = 0.0


def onFrameStart(frame):
    c = comp()
    # la fusion corre siempre que este a medias, aunque se apaguen los momentos
    if _estado['dur'] > 0.0:
        queda = _estado['fin'] - absTime.seconds
        c.par.Fade = max(0.0, min(1.0, queda / _estado['dur']))
        if queda <= 0.0:
            _estado['dur'] = 0.0
    if not c.par.Moments.eval():
        return
    filas = momentos(c)
    if not filas:
        return
    i = cual(filas, segundos(c))
    if i != _estado['i']:
        # saltar hacia atras (o rebobinar) no debe fundir desde un montaje que
        # todavia no paso: se aplica seco
        seco = i < _estado['i'] or _estado['i'] < 0
        _estado['i'] = i
        if i >= 0:
            aplicar_momento(c, filas[i], fundir=not seco)
    return
''')


# ==========================================================================
# 10. Callbacks: pulses, edicion de la fila, templates y versiones
# ==========================================================================
watcher = base.create(parameterexecuteDAT, 'watcher')
watcher.nodeX, watcher.nodeY = -920, 240
# el par OP se resuelve DESDE EL DAT, no desde su parent. Con un baseCOMP el
# patron '..' es el correcto; con un containerCOMP mirando sus propios pars
# esto dispara "Cook dependency loop detected".
setpar(watcher, ['op'], '..')
setpar(watcher, ['pars'], '*')
setpar(watcher, ['valuechange'], True)
setpar(watcher, ['onpulse'], True)

watcher.text = ("VERSIONS_DIR = r'" + VERSIONS_DIR + "'\n" + '''
import json
import os

# pares (par de la UI, columna de la tabla)
CAMPOS = [('Sname', 'name'), ('Son', 'on'), ('Smode', 'mode'),
          ('Syaw', 'yaw'), ('Spitch', 'pitch'), ('Sroll', 'roll'),
          ('Shfov', 'hfov'), ('Svfov', 'vfov'), ('Smirror', 'mirror'),
          ('Sopacity', 'opacity'), ('Sfeather', 'feather'), ('Stile', 'tile'),
          ('Scropx', 'cropx'), ('Scropy', 'cropy'),
          ('Scropw', 'cropw'), ('Scroph', 'croph'),
          ('Srep', 'rep'), ('Srepspan', 'repspan'),
          ('Srepmir', 'repmir'), ('Srepofs', 'repofs'),
          ('Sblend', 'blend'), ('Sedges', 'edges'),
          ('Stravel', 'travel'), ('Sspin', 'spin')]

# escribir la fila desde los pars dispara onValueChange de nuevo; esta bandera
# corta el ida y vuelta
_ocupado = [False]


def mod_screens(comp):
    return comp.op('screens_mod').module


def filas(comp):
    return mod_screens(comp).read_table(comp.op('screens'))


def guardar_filas(comp, lista):
    mod_screens(comp).write_table(comp.op('screens'), lista)


def indice(comp, lista):
    """La fila seleccionada, recortada a lo que existe."""
    if not lista:
        return -1
    return max(0, min(int(comp.par.Screen.eval()) - 1, len(lista) - 1))


def par_a_valor(comp, nombre_par, columna):
    p = getattr(comp.par, nombre_par)
    if columna == 'name':
        return p.eval()
    if columna in ('mode', 'mirror', 'edges'):
        return p.menuIndex
    # OJO: un Toggle evalua a True/False y en la celda quedaba el texto 'True',
    # que el DAT to CHOP lee como 0: la pantalla se apagaba sola. Todo lo que
    # no sea el nombre entra a la tabla como numero.
    return mod_screens(comp)._num(p.eval())


def leer_fila(comp):
    """Tabla -> pars. Se llama al cambiar de pantalla o al pulsar Leerfila."""
    lista = filas(comp)
    i = indice(comp, lista)
    if i < 0:
        return
    f = lista[i]
    _ocupado[0] = True
    try:
        for nombre_par, columna in CAMPOS:
            p = getattr(comp.par, nombre_par)
            v = f.get(columna)
            if columna == 'name':
                p.val = v
            elif columna in ('mode', 'mirror', 'edges'):
                p.menuIndex = int(v)
            else:
                p.val = v
    finally:
        _ocupado[0] = False


def escribir_fila(comp):
    """Pars -> tabla. Se llama cuando se mueve cualquier par de la pantalla."""
    if _ocupado[0]:
        return
    lista = filas(comp)
    i = indice(comp, lista)
    if i < 0:
        return
    for nombre_par, columna in CAMPOS:
        lista[i][columna] = par_a_valor(comp, nombre_par, columna)
    guardar_filas(comp, lista)


def auto_vfov(comp):
    """Alto angular a partir del ancho y del aspecto real del archivo.

    Solo tiene sentido en las formas con marco (plana y curva). En banda,
    tunel y cilindro el alto es un tramo de elevacion, no la altura de un
    rectangulo: aplicarle el aspecto del video le ponia 202 grados a un
    cilindro de 360 de ancho y lo dejaba sin imagen.
    """
    if not comp.par.Sautovfov.eval():
        return
    if comp.par.Smode.menuIndex not in (0, 1):
        return
    m = comp.op('movie1')
    if m is None or m.width == 0:
        return
    comp.par.Svfov = comp.par.Shfov.eval() * (m.height / m.width)


def aplicar_template(comp):
    m = mod_screens(comp)
    guardar_filas(comp, m.rows_from_template(comp.par.Template.eval()))
    comp.par.Screen = 1
    leer_fila(comp)


def agregar(comp, duplicar=False):
    m = mod_screens(comp)
    lista = filas(comp)
    if duplicar and lista:
        nueva = dict(lista[indice(comp, lista)])
        nueva['name'] = str(nueva.get('name', 'pantalla')) + '_copia'
        nueva['yaw'] = float(nueva.get('yaw', 0)) + 30.0
    else:
        nueva = dict(m.DEFAULT)
        nueva['name'] = 'pantalla%d' % (len(lista) + 1)
    lista.append(nueva)
    guardar_filas(comp, lista)
    comp.par.Screen = len(lista)
    leer_fila(comp)


def borrar(comp):
    lista = filas(comp)
    if len(lista) <= 1:
        print('[VIDEO_DOME] no borro la ultima pantalla')
        return
    del lista[indice(comp, lista)]
    guardar_filas(comp, lista)
    comp.par.Screen = min(int(comp.par.Screen.eval()), len(lista))
    leer_fila(comp)


def pars_de_version(comp):
    saltar = ('Version', 'Versionname')
    return [p for p in comp.customPars
            if not p.isPulse and not p.isMomentary and p.name not in saltar]


def guardar_version(comp):
    nombre = (comp.par.Versionname.eval() or 'sin_nombre').strip()
    nombre = ''.join(c for c in nombre if c.isalnum() or c in '-_ ').strip()
    if not nombre:
        return
    os.makedirs(VERSIONS_DIR, exist_ok=True)
    datos = {'__pars__': {}, '__screens__': comp.op('screens').text}
    for p in pars_de_version(comp):
        # las expresiones se guardan como expresion, no como su valor evaluado
        if p.mode == ParMode.EXPRESSION:
            datos['__pars__'][p.name] = {'__expr__': p.expr}
        else:
            datos['__pars__'][p.name] = p.eval()
    ruta = os.path.join(VERSIONS_DIR, nombre + '.json')
    with open(ruta, 'w', encoding='utf-8') as fh:
        json.dump(datos, fh, indent=2, ensure_ascii=False)
    print('[VIDEO_DOME] version guardada:', ruta)
    refrescar_versiones(comp, seleccionar=nombre)


def cargar_version(comp, nombre=None):
    nombre = nombre or comp.par.Version.eval()
    ruta = os.path.join(VERSIONS_DIR, str(nombre) + '.json')
    if not os.path.isfile(ruta):
        print('[VIDEO_DOME] no existe la version:', ruta)
        return
    with open(ruta, 'r', encoding='utf-8') as fh:
        datos = json.load(fh)
    _ocupado[0] = True
    try:
        if datos.get('__screens__'):
            t = comp.op('screens')
            t.text = datos['__screens__']
            # una version guardada con columnas viejas se migra al leerla y
            # volverla a escribir: lo que falte sale de los defaults
            m = mod_screens(comp)
            m.write_table(t, m.read_table(t))
        for nombre_par, valor in datos.get('__pars__', {}).items():
            p = getattr(comp.par, nombre_par, None)
            if p is None:
                continue
            try:
                if isinstance(valor, dict) and '__expr__' in valor:
                    p.expr = valor['__expr__']
                else:
                    p.val = valor
            except Exception as e:
                print('[VIDEO_DOME] no pude escribir', nombre_par, e)
    finally:
        _ocupado[0] = False
    leer_fila(comp)
    print('[VIDEO_DOME] version cargada:', nombre)


def refrescar_versiones(comp, seleccionar=None):
    actual = comp.par.Version.eval()
    vers = []
    if os.path.isdir(VERSIONS_DIR):
        vers = sorted(f[:-5] for f in os.listdir(VERSIONS_DIR) if f.endswith('.json'))
    comp.par.Version.menuNames = vers or ['ninguna']
    comp.par.Version.menuLabels = vers or ['(no hay versiones guardadas)']
    destino = seleccionar or actual
    if destino in vers:
        comp.par.Version = destino


# --------------------------------------------------------------------------
# Momentos: marcar un montaje en un punto de la pelicula
#
# El momento guarda SOLO la tabla de pantallas, no los pars globales: al pasar
# por el, el fondo, el volumen y el resto de la configuracion se quedan como
# estan. Para volver a un estado entero estan las versiones.
# --------------------------------------------------------------------------
def limpiar(nombre):
    nombre = ''.join(c for c in str(nombre) if c.isalnum() or c in '-_ ').strip()
    return nombre.replace(' ', '_')


def segundos_video(comp):
    m = comp.op('movie1')
    if m is None or not m.rate:
        return 0.0
    return m.index / m.rate


def guardar_layout(comp, nombre):
    os.makedirs(VERSIONS_DIR, exist_ok=True)
    datos = {'__pars__': {}, '__screens__': comp.op('screens').text}
    with open(os.path.join(VERSIONS_DIR, nombre + '.json'), 'w',
              encoding='utf-8') as fh:
        json.dump(datos, fh, indent=2, ensure_ascii=False)


def filas_momentos(comp):
    t = comp.op('moments')
    return [[t[i, c].val for c in range(t.numCols)] for i in range(1, t.numRows)]


def escribir_momentos(comp, filas):
    t = comp.op('moments')
    cabecera = [t[0, c].val for c in range(t.numCols)]
    filas.sort(key=lambda f: float(f[0]))
    t.clear()
    t.appendRow(cabecera)
    for f in filas:
        t.appendRow(f)


def refrescar_momentos(comp, seleccionar=None):
    t = comp.op('moments')
    nombres = [t[i, 'name'].val for i in range(1, t.numRows)]
    etiquetas = ['%s  ·  %s' % (segundos_a_texto(t[i, 't'].val), t[i, 'name'].val)
                 for i in range(1, t.numRows)]
    comp.par.Moment.menuNames = nombres or ['ninguno']
    comp.par.Moment.menuLabels = etiquetas or ['(no hay momentos)']
    if seleccionar and seleccionar in nombres:
        comp.par.Moment = seleccionar


def segundos_a_texto(s):
    try:
        s = float(s)
    except ValueError:
        return '?'
    return '%d:%05.2f' % (int(s // 60), s % 60)


def agregar_momento(comp):
    existentes = [f[3] for f in filas_momentos(comp)]
    nombre = limpiar(comp.par.Momentname.eval()) or 'momento'
    raiz, k = nombre, 2
    while nombre in existentes:
        nombre = '%s_%d' % (raiz, k)
        k += 1
    layout = 'mom_' + nombre
    guardar_layout(comp, layout)
    filas = filas_momentos(comp)
    filas.append([round(segundos_video(comp), 3),
                  comp.par.Momentfade.eval(), layout, nombre])
    escribir_momentos(comp, filas)
    refrescar_momentos(comp, seleccionar=nombre)
    refrescar_versiones(comp)
    print('[VIDEO_DOME] momento "%s" en %s'
          % (nombre, segundos_a_texto(segundos_video(comp))))


def borrar_momento(comp):
    nombre = comp.par.Moment.eval()
    filas = [f for f in filas_momentos(comp) if f[3] != nombre]
    escribir_momentos(comp, filas)
    refrescar_momentos(comp)


def ir_a_momento(comp):
    nombre = comp.par.Moment.eval()
    for f in filas_momentos(comp):
        if f[3] != nombre:
            continue
        m = comp.op('movie1')
        if m is not None:
            m.par.cuepointunit = 'seconds'
            m.par.cuepoint = float(f[0])
            m.par.cuepulse.pulse()
        # el montaje entra seco: saltar a un punto no es una fusion
        motor = comp.op('moments_exec').module
        motor.aplicar_momento(comp, {'t': float(f[0]), 'fade': 0.0,
                                     'layout': f[2], 'name': f[3]}, fundir=False)
        leer_fila(comp)
        return


def onPulse(par):
    comp = par.owner
    if par.name == 'Cue':
        m = comp.op('movie1')
        if m is not None:
            m.par.cuepulse.pulse()
    elif par.name == 'Applytemplate':
        aplicar_template(comp)
    elif par.name == 'Addscreen':
        agregar(comp)
    elif par.name == 'Dupscreen':
        agregar(comp, duplicar=True)
    elif par.name == 'Delscreen':
        borrar(comp)
    elif par.name == 'Readscreen':
        leer_fila(comp)
    elif par.name == 'Saveversion':
        guardar_version(comp)
    elif par.name == 'Loadversion':
        cargar_version(comp)
    elif par.name == 'Refreshversions':
        refrescar_versiones(comp)
    elif par.name == 'Addmoment':
        agregar_momento(comp)
    elif par.name == 'Gotomoment':
        ir_a_momento(comp)
    elif par.name == 'Delmoment':
        borrar_momento(comp)
    elif par.name == 'Refreshmoments':
        refrescar_momentos(comp)
    elif par.name == 'Openeditor':
        ed = comp.op('editor')
        if ed is not None:
            ed.openViewer(unique=True, borders=True)
    return


def onValueChange(par, prev):
    comp = par.owner
    if par.name == 'Screen':
        leer_fila(comp)
    elif par.name == 'Template':
        aplicar_template(comp)
    elif par.name in ('Shfov', 'Sautovfov'):
        auto_vfov(comp)
        escribir_fila(comp)
    elif par.name.startswith('S') and par.name in [c[0] for c in CAMPOS]:
        escribir_fila(comp)
    elif par.name == 'Edit':
        # sin rejilla el editor es un circulo negro: no se ve donde cae el click
        if par.eval():
            comp.par.Guides = True
    elif par.name == 'Preview':
        sim = comp.op('preview_dome')
        if sim is not None:
            sim.allowCooking = bool(par.eval())
    return
''')

readme = base.create(textDAT, 'README')
readme.nodeX, readme.nodeY = -1100, 420
readme.text = (
    "VIDEO_DOME - video 16:9 adaptado a domemaster, con N pantallas\n"
    "\n"
    "out_dome = imagen cuadrada de domo (Res x Res).\n"
    "\n"
    "La tabla 'screens' es la fuente de verdad: una fila por pantalla. Se puede\n"
    "editar a mano; despues pulsar 'Leer la fila' para poner los pars al dia.\n"
    "\n"
    "Formas (columna mode): 0 plana, 1 curva, 2 banda (puede dar la vuelta),\n"
    "3 tunel (polar, con repeticiones hace anillos que se alejan).\n"
    "Recorte (cropx/y/w/h): que fragmento del cuadro usa esa pantalla.\n"
    "\n"
    "Templates (pagina Montaje) pisan la tabla entera. Versiones (pagina\n"
    "Versiones) guardan pars + tabla en JSON.\n"
    "\n"
    "El build conserva pars y tabla. RESET_DEFAULTS = True vuelve a fabrica.\n"
    "Reconstruye: 10_Video_Domo/build_video_dome.py\n"
)


# ==========================================================================
# 10b. Ordenar la red: cajas con nombre alrededor de cada bloque
#
# Adentro de VIDEO_DOME hay 45 operadores y sin cajas no se sabe donde empieza
# una cosa y termina la otra. Las cajas son solo del editor de red (no cocinan
# ni cuestan nada) pero son la diferencia entre poder abrir esto en un mes o no.
# ==========================================================================
CAJAS = [
    ('1_fuente', 'FUENTE  ·  video + audio + lente', (0.25, 0.18, 0.10),
     ['movie1', 'ndi_in', 'spout_in', 'fuente', 'audio_movie', 'audio_gain', 'audio_out', 'soft', 'video_out']),
    ('2_pantallas', 'PANTALLAS  ·  tabla -> CHOP -> arrays del shader',
     (0.12, 0.22, 0.12),
     ['screens_mod', 'screens', 'screens_chop', 'watcher',
      'sel_pos', 'sel_size', 'sel_crop', 'sel_opt', 'sel_rep', 'sel_anm']),
    ('2b_momentos', 'MOMENTOS  ·  un montaje por tramo, con fusion',
     (0.24, 0.20, 0.10),
     ['moments', 'moments_exec', 'screens_b', 'screens_chop_b',
      'sel_pos_b', 'sel_size_b', 'sel_crop_b', 'sel_opt_b', 'sel_rep_b',
      'sel_anm_b']),
    ('3_fondo', 'FONDO  ·  desenfocado antes de mapear', (0.10, 0.16, 0.24),
     ['bg_src', 'bg_blur', 'bg_level', 'bg_map']),
    ('4_domo', 'MAPEO AL DOMO  ·  cupula = pixeles, no geometria',
     (0.22, 0.12, 0.24),
     ['dome_map', 'dome_map_b', 'fade_cross', 'fade_switch', 'comp_bg',
      'bg_switch', 'guides', 'comp_guides', 'guides_switch', 'flip1',
      'out_dome']),
    ('5_mirar', 'MIRAR Y UBICAR  ·  simulador + editor con el mouse',
     (0.10, 0.20, 0.20),
     ['preview_dome', 'editor_view', 'editor', 'editor_panel', 'editor_exec']),
    ('6_grabar', 'GRABAR  ·  domemaster a HAP', (0.24, 0.14, 0.14),
     ['rec_res', 'rec_out']),
]

# En TD 2025 no hay COMP.addNetworkBox(): la caja con titulo es el Annotate
# COMP, un operador mas que se pone DETRAS de los nodos (Layer Zone = below
# grid) y se estira a mano hasta cubrirlos.
PAD_X, PAD_Y = 40, 60
ANCHO_NODO, ALTO_NODO = 120, 50

for nombre, texto, color, hijos in CAJAS:
    nodos = [base.op(n) for n in hijos]
    nodos = [o for o in nodos if o is not None]
    if not nodos:
        continue
    try:
        # Sin nombre al crear y sin flag utility: en TD 2025.32460 un Annotate
        # COMP creado con nombre, o con utility encendido, se autodestruye unos
        # frames despues. Se renombra al final.
        caja = base.create(annotateCOMP)
        x0 = min(o.nodeX for o in nodos) - PAD_X
        y0 = min(o.nodeY for o in nodos) - PAD_Y
        x1 = max(o.nodeX + max(o.nodeWidth, ANCHO_NODO) for o in nodos) + PAD_X
        y1 = max(o.nodeY + max(o.nodeHeight, ALTO_NODO) for o in nodos) + PAD_Y
        caja.nodeX, caja.nodeY = x0, y0
        caja.nodeWidth, caja.nodeHeight = x1 - x0, y1 - y0
        caja.par.Titletext = texto
        caja.par.Backcolorr, caja.par.Backcolorg, caja.par.Backcolorb = color
        caja.par.Backcoloralpha = 0.85
        setpar_any(caja, ['layerzone'], ['belowgrid', 'below grid'], 'Layer Zone')
        caja.name = nombre
    except Exception as e:
        print('[VIDEO_DOME] sin caja %s: %s' % (nombre, e))


# ==========================================================================
# 11. Devolver los ajustes que habia antes de reconstruir
# ==========================================================================
if pars_previos:
    restaurados = 0
    for nombre_par, (tipo, valor) in pars_previos.items():
        p = getattr(base.par, nombre_par, None)
        if p is None or p.isPulse or p.isMomentary:
            continue
        try:
            if tipo == 'expr':
                p.expr = valor
            else:
                p.val = valor
            restaurados += 1
        except Exception:
            pass
    nuevos = [p.name for p in base.customPars
              if not p.isPulse and p.name not in pars_previos]
    print('[VIDEO_DOME] ajustes conservados: %d de %d%s'
          % (restaurados, len(pars_previos),
             ('  |  pars nuevos: ' + ', '.join(nuevos)) if nuevos else ''))
    if tabla_previa:
        print('[VIDEO_DOME] tabla de pantallas conservada: %d filas'
              % max(tabla.numRows - 1, 0))
else:
    print('[VIDEO_DOME] COMP nuevo, valores de fabrica')

# la timeline al ritmo del archivo (24 fps): si TD corre a 60 el video igual se
# reproduce bien, pero la grabacion del domemaster sale con cuadros repetidos
if globals().get('VIDEO_DOME_SET_FPS', True):
    try:
        op('/').time.rate = FPS
    except Exception:
        print('[VIDEO_DOME] poner la timeline a %d fps a mano' % FPS)

print('[VIDEO_DOME] listo -> %s' % out.path)
print('[VIDEO_DOME] pantallas: %d  |  template: %s  |  campo de mirada: %g'
      % (max(tabla.numRows - 1, 0), base.par.Template.eval(), base.par.Viewfov.eval()))
