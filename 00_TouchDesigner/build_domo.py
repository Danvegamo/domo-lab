"""
Construye /project1/DOMO: el sistema de senal para cupula.

Se ejecuta DENTRO de TouchDesigner (Textport, un Execute DAT, o por MCP):

    BUILD_DIR = r'C:/ruta/al/repo/00_TouchDesigner'
    exec(open(BUILD_DIR + '/build_domo.py', encoding='utf-8').read())

Es idempotente: si /project1/DOMO ya existe lo destruye y lo vuelve a crear,
pero antes guarda el valor de todos los parametros personalizados (rutas de
video, angulos, nombres de Spout...) y los reescribe al final. Asi se puede
volver a correr tras editar este archivo sin perder la configuracion.

Estructura que deja:

    DOMO                      COMP raiz, atajo `parent.DOMO`, paginas Domo, 360, 180, 16:9, Mapping y Salidas
      IN_360                  video 360 equirectangular (+ costura opcional, + giro esferico Yaw/Pitch/Roll)
      IN_180                  domemaster fisheye, VR180 mono o VR180 lado a lado (+ giro esferico)
      IN_169                  video plano sobre pantallas en la cupula (VIDEO_DOME adentro, + Pitch/Roll)
      AUDIO                   sigue a la fuente al aire (solo suena ese video), o un archivo, o la entrada
      mezcla -> equi          la fuente elegida, como lienzo equirectangular 2:1
      domo -> out_domo        el domemaster fisheye con el FOV del modelo de sala
      spout_domo / ndi_domo   salidas del domemaster
      para_unreal -> spout_unreal   la version equirectangular que espera la sala VR
      grabar                  Movie File Out del domemaster

Cada modulo tiene su parametro `Activo`: apagado, el modulo entrega negro y
no cocina (el Switch solo cocina la entrada elegida). Cada bloque lleva su
caja de comentario (Annotate COMP) que explica que hace.

Convencion del lienzo equirectangular: u = 0.5 es el frente, v = 0.5 el
horizonte y v = 1 el cenit. La mitad superior del lienzo ES la cupula. Es el
mismo formato que espera la cupula de la sala VR en Unreal.
"""

import os

try:
    BUILD_DIR
except NameError:
    BUILD_DIR = os.path.dirname(os.path.abspath(__file__)) if '__file__' in globals() else project.folder + '/00_TouchDesigner'

RAIZ = op('/project1')
NOMBRE = 'DOMO'
VERSION = '1.2 (18 sep 2026)'

# ---------------------------------------------------------------- utilidades

def leer(nombre):
    ruta = os.path.join(BUILD_DIR, 'shaders', nombre)
    with open(ruta, encoding='utf-8') as f:
        return f.read()


def setpar(o, nombres, val):
    """Escribe el primer parametro que exista de la lista. Devuelve True si pudo."""
    if isinstance(nombres, str):
        nombres = [nombres]
    for n in nombres:
        p = getattr(o.par, n, None)
        if p is not None:
            try:
                p.val = val
                return True
            except Exception as e:
                print('[DOMO] %s.%s = %r fallo: %s' % (o.path, n, val, e))
                return False
    print('[DOMO] %s no tiene ninguno de %s' % (o.path, nombres))
    return False


def expr(o, nombre, e):
    p = getattr(o.par, nombre, None)
    if p is None:
        print('[DOMO] %s no tiene el par %s' % (o.path, nombre))
        return
    p.expr = e


def mk(padre, tipo, nombre, x, y, **pars):
    viejo = padre.op(nombre)
    if viejo:
        viejo.destroy()
    o = padre.create(tipo, nombre)
    o.nodeX, o.nodeY = x, y
    o.viewer = True
    for k, v in pars.items():
        setpar(o, k, v)
    return o


def wire(a, b, i=0):
    b.inputConnectors[i].connect(a.outputConnectors[0])


def lienzo(o):
    """Resolucion del lienzo equirectangular: Ancho x Ancho/2 del COMP raiz."""
    setpar(o, 'outputresolution', 'custom')
    expr(o, 'resolutionw', 'parent.DOMO.par.Ancho')
    expr(o, 'resolutionh', 'parent.DOMO.par.Ancho // 2')


def caja(padre, nombre, titulo, cuerpo, nodos, color=(0.16, 0.18, 0.22), pad=(60, 60), extra_arriba=0, rect=None):
    """Annotate COMP que encierra `nodos` con un titulo y un texto explicativo.
    Con `rect` = (x0, y0, x1, y1) la caja va ahi y no encierra nada: es una nota.

    Trampas medidas en TD 2025.32460: si el Annotate COMP se crea con nombre
    (`create(annotateCOMP, 'x')`) o se le enciende el flag `utility`, se
    autodestruye unos frames despues. Hay que crearlo sin nombre, configurarlo
    y renombrarlo al final. El aviso "Invalid path for node .../annotate/annotation"
    en su `back` interno lo trae de fabrica y no afecta.
    """
    viejo = padre.op(nombre)
    if viejo:
        viejo.destroy()
    c = padre.create(annotateCOMP)
    if rect is not None:
        x0, y0, x1, y1 = rect
    else:
        x0 = min(n.nodeX for n in nodos) - pad[0]
        y0 = min(n.nodeY for n in nodos) - pad[1]
        x1 = max(n.nodeX + max(n.nodeWidth, 160) for n in nodos) + pad[0]
        y1 = max(n.nodeY + max(n.nodeHeight, 100) for n in nodos) + pad[1] + extra_arriba
    c.nodeX, c.nodeY = x0, y0
    c.nodeWidth, c.nodeHeight = x1 - x0, y1 - y0
    setpar(c, 'Titletext', titulo)
    setpar(c, 'Bodytext', cuerpo)
    setpar(c, 'Bodywordwrap', True)
    setpar(c, 'Bodyfontsize', 11)
    setpar(c, 'Backcolorr', color[0])
    setpar(c, 'Backcolorg', color[1])
    setpar(c, 'Backcolorb', color[2])
    setpar(c, 'Backcoloralpha', 0.9)
    setpar(c, 'layerzone', 'belowgrid')
    c.name = nombre
    return c


def menu(pagina, nombre, etiqueta, nombres, etiquetas, defecto=0):
    p = pagina.appendMenu(nombre, label=etiqueta)[0]
    p.menuNames = nombres
    p.menuLabels = etiquetas
    p.val = nombres[defecto]
    p.default = nombres[defecto]
    return p


def flotante(pagina, nombre, etiqueta, val, lo=None, hi=None):
    p = pagina.appendFloat(nombre, label=etiqueta)[0]
    p.val = val
    p.default = val
    if lo is not None:
        p.normMin = lo
        p.min = lo
        p.clampMin = True
    if hi is not None:
        p.normMax = hi
    return p


def toggle(pagina, nombre, etiqueta, val):
    p = pagina.appendToggle(nombre, label=etiqueta)[0]
    p.val = val
    p.default = val
    return p


def texto(pagina, nombre, etiqueta, val):
    p = pagina.appendStr(nombre, label=etiqueta)[0]
    p.val = val
    p.default = val
    return p


def negro_y_salida(comp, resultado, x):
    """Cierra un modulo: Switch [negro, resultado] gobernado por Activo, y out1."""
    negro = mk(comp, constantTOP, 'negro', x, -150, colorr=0, colorg=0, colorb=0, alpha=1)
    lienzo(negro)
    sw = mk(comp, switchTOP, 'activo', x + 200, 0)
    wire(negro, sw, 0)
    wire(resultado, sw, 1)
    expr(sw, 'index', 'int(parent().par.Activo)')
    salida = mk(comp, outTOP, 'out1', x + 400, 0)
    wire(sw, salida)
    return sw, salida


def orientador(comp, entrada, x, guia='0', costura_pos='0', yaw='parent().par.Yaw', corte='-90'):
    """Rotacion esferica del lienzo (shaders/orientar.frag) gobernada por los
    pars Yaw, Pitch y Roll del modulo. Con los tres en cero y sin guia, el
    Switch `orientado` deja pasar la entrada tal cual y el GLSL no cocina."""
    dat = mk(comp, textDAT, 'orientar_glsl', x, -250)
    dat.text = leer('orientar.frag')
    g = mk(comp, glslTOP, 'orientar', x, 0)
    g.par.pixeldat = dat
    setpar(g, 'inputextenduv', 'repeat')
    setpar(g, 'vec', 2)
    setpar(g, 'vec0name', 'uRot')
    expr(g, 'vec0valuex', yaw)
    expr(g, 'vec0valuey', 'parent().par.Pitch')
    expr(g, 'vec0valuez', 'parent().par.Roll')
    expr(g, 'vec0valuew', guia)
    setpar(g, 'vec1name', 'uSeam')
    expr(g, 'vec1valuex', costura_pos)
    setpar(g, 'vec1valuey', 0.006)
    expr(g, 'vec1valuez', corte)
    setpar(g, 'vec1valuew', 0)
    wire(entrada, g)
    sw = mk(comp, switchTOP, 'orientado', x + 200, 0)
    wire(entrada, sw, 0)
    wire(g, sw, 1)
    expr(sw, 'index', 'int(bool((%s) or parent().par.Pitch or parent().par.Roll or (%s)))' % (yaw, guia))
    return [dat, g, sw], sw


def pagina_orientacion(comp, nombre_pagina, con_yaw=True):
    """Pars Yaw, Pitch y Roll del modulo (quedan en Bind contra la raiz).
    IN_169 no lleva Yaw propio: su azimut es Yawglobal de VIDEO_DOME."""
    pg = comp.appendCustomPage(nombre_pagina)
    if con_yaw:
        flotante(pg, 'Yaw', 'Girar en azimut (grados)', 0, -180, 180)
    flotante(pg, 'Pitch', 'Inclinar: el frente hacia el cenit (grados)', 0, -180, 180)
    flotante(pg, 'Roll', 'Rodar sobre el eje del frente (grados)', 0, -180, 180)
    for n in ('Yaw', 'Pitch', 'Roll'):
        p = getattr(comp.par, n, None)
        if p is not None:
            p.clampMin = False
    return pg


# ------------------------------------------------- conservar la configuracion

guardado = {}
vd_previo = {'pars': {}, 'screens': None, 'moments': None}
viejo = RAIZ.op(NOMBRE)
if viejo:
    # VIDEO_DOME (dentro de IN_169) guarda su montaje en pars y en dos tablas;
    # su propio constructor no lo puede conservar porque aqui se destruye todo
    # DOMO antes de que corra. Se copia aqui y se reescribe al final.
    vd = viejo.op('IN_169/VIDEO_DOME')
    if vd is not None:
        for p in vd.customPars:
            if p.isPulse or p.isMomentary:
                continue
            try:
                vd_previo['pars'][p.name] = ('expr', p.expr) if p.mode == ParMode.EXPRESSION else ('val', p.eval())
            except Exception:
                pass
        for t in ('screens', 'moments'):
            d = vd.op(t)
            if d is not None and d.numRows > 1:
                vd_previo[t] = d.text
    for comp in [viejo] + [c for c in viejo.children if c.isCOMP and c.customPars]:
        rel = comp.path[len(viejo.path):] or '.'
        guardado[rel] = {}
        for p in comp.customPars:
            if p.mode == ParMode.CONSTANT and p.style not in ('Pulse',):
                try:
                    guardado[rel][p.name] = p.val
                except Exception:
                    pass
    viejo.destroy()
    print('[DOMO] configuracion guardada de %d COMPs' % len(guardado))

# --------------------------------------------------------------------- raiz

D = RAIZ.create(baseCOMP, NOMBRE)
D.nodeX, D.nodeY = 0, 0
D.viewer = True
D.par.parentshortcut = 'DOMO'

pg = D.appendCustomPage('Domo')
menu(pg, 'Fuente', 'Fuente al aire',
     ['v360', 'v180', 'v169', 'patron'],
     ['Video 360 (IN_360)', 'Video 180 / domemaster (IN_180)', 'Video plano 16:9 (IN_169)',
      'Patron de prueba (calibrar la sala)'], 0)
menu(pg, 'Modelo', 'Modelo de sala',
     ['domo180', 'domo90', 'domo45', 'custom'],
     ['Domo 180 (media esfera, planetario)', 'Sala 90: de pie con barandas (pantalla 180, inclinada 45)',
      'Sala 45: tipo Maloka (pantalla 180, inclinada 27)', 'Otro FOV'], 0)
flotante(pg, 'Fovcustom', 'FOV si el modelo es Otro (grados)', 120, 10, 360)
flotante(pg, 'Yaw', 'Girar el contenido en azimut (grados)', 0, -180, 180)
flotante(pg, 'Pitch', 'Inclinar el contenido hacia el cenit (grados)', 0, -90, 90)
menu(pg, 'Res', 'Resolucion del domemaster',
     ['r1024', 'r2048', 'r4096'], ['1024 (ensayo)', '2048 (tiempo real)', '4096 (grabar)'], 1)
p = pg.appendInt('Ancho', label='Ancho del lienzo equirectangular')[0]
p.val = 4096
p.default = 4096
p.normMin, p.normMax = 1024, 8192
p = pg.appendStr('Version', label='Version')[0]
p.val = VERSION
p.readOnly = True

# Mapping: lo que en la sala real se ajusta desde TouchDesigner mientras el
# servidor del domo solo recibe. Aqui pasa lo mismo: Unreal recibe y estos
# pars mueven lo que se ve, sin tocar el nivel.
pmap = D.appendCustomPage('Mapping')
toggle(pmap, 'Fovauto', 'FOV del contenido = FOV del modelo de sala', True)
flotante(pmap, 'Fovcontenido', 'FOV del contenido si no es automatico (grados)', 230, 90, 360)
flotante(pmap, 'Centrox', 'Mover el cenit en X (fraccion del domemaster)', 0, -0.5, 0.5)
flotante(pmap, 'Centroy', 'Mover el cenit en Y (fraccion del domemaster)', 0, -0.5, 0.5)
flotante(pmap, 'Escala', 'Escala del domemaster', 1.0, 0.5, 2.0)
flotante(pmap, 'Rotar', 'Rotar el domemaster (grados)', 0, -180, 180)

ps = D.appendCustomPage('Salidas')
toggle(ps, 'Spoutunreal', 'Spout a la sala VR (equirectangular)', True)
texto(ps, 'Spoutunrealnombre', 'Nombre del sender para Unreal', 'TD_Domo_Lab')
toggle(ps, 'Spoutdomo', 'Spout del domemaster', False)
texto(ps, 'Spoutdomonombre', 'Nombre del sender domemaster', 'TD_Domemaster')
toggle(ps, 'Ndi', 'NDI del domemaster', False)
texto(ps, 'Ndinombre', 'Nombre NDI', 'TD_Domemaster')
toggle(ps, 'Grabar', 'Grabar el domemaster (HAP)', False)
p = ps.appendFolder('Grabarcarpeta', label='Carpeta de grabacion')[0]
p.val = '05_Media'
p.default = '05_Media'

# ------------------------------------------------------------------ IN_360

M = D.create(baseCOMP, 'IN_360')
M.nodeX, M.nodeY = -600, 450
M.viewer = True
pm = M.appendCustomPage('Video360')
toggle(pm, 'Activo', 'Activo', True)
p = pm.appendFile('Archivo', label='Archivo 360 equirectangular (2:1)')[0]
p.val = ''
toggle(pm, 'Play', 'Reproducir', True)
flotante(pm, 'Velocidad', 'Velocidad', 1.0, 0, 4)
toggle(pm, 'Costura', 'Fundir la costura del stitching', False)
flotante(pm, 'Costurapos', 'Posicion de la costura (0..1 en u)', 0.0, 0, 1)
flotante(pm, 'Costuraancho', 'Ancho de la franja', 0.03, 0, 0.2)
flotante(pm, 'Costurablur', 'Desenfoque horizontal', 0.02, 0, 0.1)
flotante(pm, 'Costuraoffsety', 'Corrimiento vertical del lado derecho', 0.0, -0.05, 0.05)
flotante(pm, 'Costuraganancia', 'Ganancia del lado derecho', 1.0, 0.5, 1.5)
toggle(pm, 'Costuraguia', 'Pintar la costura en rojo', False)

video = mk(M, moviefileinTOP, 'video', 0, 0)
expr(video, 'file', 'parent().par.Archivo')
expr(video, 'play', 'parent().par.Play')
expr(video, 'speed', 'parent().par.Velocidad')
setpar(video, 'textendright', 'cycle')

glsl_dat = mk(M, textDAT, 'costura_glsl', 200, -250)
glsl_dat.text = leer('costura.frag')
cos = mk(M, glslTOP, 'costura', 200, 0)
cos.par.pixeldat = glsl_dat
setpar(cos, 'inputextenduv', 'repeat')
setpar(cos, 'vec', 2)
setpar(cos, 'vec0name', 'uSeam')
expr(cos, 'vec0valuex', 'parent().par.Costurapos')
expr(cos, 'vec0valuey', 'parent().par.Costuraancho')
expr(cos, 'vec0valuez', 'parent().par.Costurablur')
expr(cos, 'vec0valuew', 'int(parent().par.Costuraguia)')
setpar(cos, 'vec1name', 'uFix')
expr(cos, 'vec1valuex', 'parent().par.Costuraoffsety')
expr(cos, 'vec1valuey', 'parent().par.Costuraganancia')
setpar(cos, 'vec1valuez', 0)
setpar(cos, 'vec1valuew', 0)
wire(video, cos)

sw_cos = mk(M, switchTOP, 'con_costura', 400, 0)
wire(video, sw_cos, 0)
wire(cos, sw_cos, 1)
expr(sw_cos, 'index', 'int(parent().par.Costura)')

fit360 = mk(M, fitTOP, 'lienzo', 600, 0, fit='fitbest')
lienzo(fit360)
wire(sw_cos, fit360)

# Orientacion: la costura de un 360 es un meridiano de polo a polo (u = 0), y
# un corrimiento en u solo la cambia de azimut: siempre sube hasta el cenit.
# Para sacarla de la cupula hay que girar la esfera (Pitch/Roll). Patron
# reemplaza el video por el patron de prueba de DOMO (costura gruesa en u = 0)
# para apuntar sin video; Vercostura pinta de rojo por donde pasa la costura
# del archivo (Costurapos) despues de girar.
po = pagina_orientacion(M, 'Orientacion')
toggle(po, 'Patron', 'Ver el patron de prueba en vez del video', False)
toggle(po, 'Vercostura', 'Pintar la costura (Costurapos) en rojo', False)
pat360 = mk(M, selectTOP, 'patron', 600, -150)
pat360.par.top = '../patron'
sw_pat = mk(M, switchTOP, 'video_o_patron', 800, 0)
wire(fit360, sw_pat, 0)
wire(pat360, sw_pat, 1)
expr(sw_pat, 'index', 'int(parent().par.Patron)')
nodos_or, orient360 = orientador(M, sw_pat, 1000, guia='int(parent().par.Vercostura)',
                                 costura_pos='parent().par.Costurapos')
negro_y_salida(M, orient360, 1400)

caja(M, 'nota', 'IN_360: video 360 equirectangular',
     'El archivo ya viene en el formato del lienzo (2:1, el frente en el centro), asi que solo se '
     'ajusta al tamano del lienzo. Si el stitching dejo una linea vertical, enciende Costura y mueve '
     'Costurapos hasta que la guia roja caiga sobre ella; luego apaga la guia. orientar gira la '
     'esfera (Yaw, Pitch, Roll, pagina 360 de DOMO) antes del domemaster: la costura es un meridiano '
     'de polo a polo, y con Pitch 90 queda entera bajo el horizonte, fuera de la cupula. Patron pone '
     'el patron de prueba en lugar del video para apuntar; Vercostura pinta la costura en rojo.',
     [video, cos, sw_cos, fit360, pat360, sw_pat] + nodos_or +
     [M.op('negro'), M.op('activo'), M.op('out1')], (0.13, 0.20, 0.16))

# ------------------------------------------------------------------ IN_180

M = D.create(baseCOMP, 'IN_180')
M.nodeX, M.nodeY = -600, 250
M.viewer = True
pm = M.appendCustomPage('Video180')
toggle(pm, 'Activo', 'Activo', True)
p = pm.appendFile('Archivo', label='Archivo 180 (domemaster o VR180)')[0]
p.val = ''
toggle(pm, 'Play', 'Reproducir', True)
flotante(pm, 'Velocidad', 'Velocidad', 1.0, 0, 4)
menu(pm, 'Formato', 'Formato del archivo',
     ['domemaster', 'vr180', 'vr180sbs'],
     ['Domemaster (fisheye 180, cuadrado)', 'VR180 mono (media equirectangular, cuadrado)', 'VR180 lado a lado (se usa el ojo izquierdo)'], 0)

video = mk(M, moviefileinTOP, 'video', 0, 0)
expr(video, 'file', 'parent().par.Archivo')
expr(video, 'play', 'parent().par.Play')
expr(video, 'speed', 'parent().par.Velocidad')
setpar(video, 'textendright', 'cycle')

dm = mk(M, projectionTOP, 'domemaster_a_equi', 200, 150, input='fisheye', output='equirectangular', fov=180, rx=-90)
lienzo(dm)
wire(video, dm)

sbs = mk(M, cropTOP, 'ojo_izquierdo', 200, -100, cropright=0.5, croprightunit='fraction')
wire(video, sbs)
sw_ojo = mk(M, switchTOP, 'mono_o_sbs', 400, -100)
wire(video, sw_ojo, 0)
wire(sbs, sw_ojo, 1)
expr(sw_ojo, 'index', "1 if parent().par.Formato == 'vr180sbs' else 0")
fit180 = mk(M, fitTOP, 'al_centro', 600, -100, fit='fitbest', justifyh='center', justifyv='center')
lienzo(fit180)
wire(sw_ojo, fit180)

sw_fmt = mk(M, switchTOP, 'formato', 800, 0)
wire(dm, sw_fmt, 0)
wire(fit180, sw_fmt, 1)
expr(sw_fmt, 'index', "0 if parent().par.Formato == 'domemaster' else 1")
pagina_orientacion(M, 'Orientacion')
nodos_or, orient180 = orientador(M, sw_fmt, 1000)
negro_y_salida(M, orient180, 1400)

caja(M, 'nota', 'IN_180: domemaster o VR180',
     'Un domemaster (fisheye 180) se convierte a equirectangular con el Projection TOP; rx = -90 deja '
     'el cenit arriba, en la mitad superior del lienzo. Un VR180 (media esfera, cuadrado) se centra '
     'en el lienzo con bandas negras a los lados: ocupa el frente, del horizonte al cenit y hacia abajo. '
     'Para llevarlo a la cupula sube Pitch en la pagina 180 de DOMO (solo este modulo) o en la pagina '
     'Domo (todas las fuentes). orientar gira la esfera con Yaw, Pitch y Roll antes del domemaster.',
     [video, dm, sbs, sw_ojo, fit180, sw_fmt] + nodos_or +
     [M.op('negro'), M.op('activo'), M.op('out1')], (0.13, 0.17, 0.22))

# ------------------------------------------------------------------ IN_169
#
# El video plano no va sobre una sola pantalla: es el sistema de pantallas de
# Domo_Pantallas (video_dome/build_video_dome.py), que se construye aqui
# adentro. Sus montajes (una pantalla al frente, cuatro salas, corona cosida,
# anillos, cilindro, mosaico...) viven en la tabla `screens` y en los templates
# y versiones; el fondo desenfocado, el editor con el mouse y los momentos
# vienen con el. Su fuente puede ser un archivo, NDI o Spout (par Fuente de
# VIDEO_DOME). Entrega un domemaster con el frente ABAJO, la misma convencion
# que `domo`, y aqui se pasa al lienzo equirectangular con la misma receta que
# para_unreal: fisheye -> equirect rx -90 y corrimiento de -0.25.

M = D.create(baseCOMP, 'IN_169')
M.nodeX, M.nodeY = -600, 50
M.viewer = True
pm = M.appendCustomPage('Video169')
toggle(pm, 'Activo', 'Activo', True)
p = pm.appendStr('Donde', label='El montaje se edita en')[0]
p.val = 'DOMO, pagina 16:9 (lo principal); el resto en IN_169/VIDEO_DOME'
p.readOnly = True

ns = dict(globals())
ns.update({
    'TEMPLATE_TARGET': M.path,
    'VIDEO_DOME_DIR': os.path.join(BUILD_DIR, 'video_dome'),
    'VIDEO_DOME_VIDEO': '',
    'VIDEO_DOME_SET_FPS': False,
    'RESET_DEFAULTS': True,
})
with open(os.path.join(BUILD_DIR, 'video_dome', 'build_video_dome.py'), encoding='utf-8') as fh:
    exec(compile(fh.read(), 'build_video_dome.py', 'exec'), ns)
vd = M.op('VIDEO_DOME')
vd.nodeX, vd.nodeY = 0, 0

# VIDEO_DOME termina en un Null (out_dome), no en un Out TOP: se lee con un Select.
sel_vd = mk(M, selectTOP, 'domemaster', 300, 0)
sel_vd.par.top = 'VIDEO_DOME/out_dome'
a_equi = mk(M, projectionTOP, 'domemaster_a_equi', 500, 0, input='fisheye', output='equirectangular', rx=-90, ry=0, rz=0)
expr(a_equi, 'fov', "op('VIDEO_DOME').par.Domefov")
lienzo(a_equi)
wire(sel_vd, a_equi)
giro169 = mk(M, transformTOP, 'al_frente', 700, 0, tunit='fraction', extend='repeat', tx=-0.25)
wire(a_equi, giro169)
# El domo interno de VIDEO_DOME se inclina y se rueda entero aqui (Pitch,
# Roll; pagina 16:9 de DOMO, Vdpitch y Vdroll). Su azimut es Yawglobal, que
# VIDEO_DOME ya aplica adentro y que el fondo sigue con Bgfollow.
pagina_orientacion(M, 'Orientacion', con_yaw=False)
nodos_or169, orient169 = orientador(M, giro169, 900, yaw='0',
                                   corte="90 - op('VIDEO_DOME').par.Domefov / 2")
negro_y_salida(M, orient169, 1300)

caja(M, 'nota', 'IN_169: video plano sobre pantallas en la cupula',
     'VIDEO_DOME es el sistema de pantallas de Domo_Pantallas: el shader recorre el domemaster y '
     'pregunta que pantalla cubre cada pixel; las pantallas son filas de la tabla screens. Ahi '
     'estan los templates (una al frente, sala de 4, corona cosida, anillos, cilindro, mosaico), '
     'el fondo desenfocado, el editor con el mouse y las versiones guardadas. Lo principal '
     '(template, fuente, pantallas, fondo) se maneja desde la pagina 16:9 de DOMO. Su domemaster '
     '(frente abajo) se pasa al lienzo equirectangular igual que para_unreal. orientar inclina '
     '(Pitch) y rueda (Roll) el domo interno entero; el giro en azimut es Yawglobal. El audio de '
     'movie1 no sale por el audio_out de VIDEO_DOME (apagado aqui): lo toma DOMO/AUDIO solo cuando '
     'el 16:9 esta al aire.',
     [vd, sel_vd, a_equi, giro169] + nodos_or169 +
     [M.op('negro'), M.op('activo'), M.op('out1')], (0.22, 0.17, 0.13))

# ------------------------------- paginas 360, 180 y 16:9 en la raiz DOMO
#
# Cada fuente se edita al mismo nivel desde la raiz: la pagina 360 (IN_360),
# la 180 (IN_180) y la 16:9 (IN_169 y su VIDEO_DOME) tienen los pars que
# importan, y los de abajo quedan en modo Bind apuntando a ellos
# (parent.DOMO.par.X). El bind va en los dos sentidos: mover un par arriba lo
# mueve abajo, y cuando VIDEO_DOME escribe sus pars (al aplicar un template o
# elegir otra pantalla) la pagina 16:9 se pone al dia. El watcher de
# VIDEO_DOME ve el cambio de Template aunque venga por el bind, asi que el
# template se aplica solo, sin pulso.
# Los binds se ponen al final del build, despues de restaurar la configuracion
# (ver mas abajo), para que reconstruir no dispare un template y pise la tabla.
#
# (nombre en DOMO, COMP de destino relativo a DOMO, par en ese COMP, etiqueta)
VD = 'IN_169/VIDEO_DOME'
P360 = [
    ('Ractivo', 'IN_360', 'Activo', 'Modulo 360 activo'),
    ('Rarchivo', 'IN_360', 'Archivo', 'Archivo 360 equirectangular (2:1)'),
    ('Rplay', 'IN_360', 'Play', 'Reproducir'),
    ('Rvelocidad', 'IN_360', 'Velocidad', 'Velocidad'),
    ('Ryaw', 'IN_360', 'Yaw', 'Girar la esfera en azimut (grados)'),
    ('Rpitch', 'IN_360', 'Pitch', 'Inclinar la esfera: el frente hacia el cenit (grados)'),
    ('Rroll', 'IN_360', 'Roll', 'Rodar la esfera sobre el eje del frente (grados)'),
    ('Rpatron', 'IN_360', 'Patron', 'Ver el patron de prueba en vez del video'),
    ('Rvercostura', 'IN_360', 'Vercostura', 'Pintar la costura en rojo (donde cae tras girar)'),
    ('Rcosturapos', 'IN_360', 'Costurapos', 'Posicion de la costura del archivo (u, 0 a 1)'),
    ('Rcostura', 'IN_360', 'Costura', 'Fundir la costura del stitching'),
]
P180 = [
    ('Mactivo', 'IN_180', 'Activo', 'Modulo 180 activo'),
    ('Marchivo', 'IN_180', 'Archivo', 'Archivo 180 (domemaster o VR180)'),
    ('Mplay', 'IN_180', 'Play', 'Reproducir'),
    ('Mformato', 'IN_180', 'Formato', 'Formato del archivo'),
    ('Myaw', 'IN_180', 'Yaw', 'Girar en azimut (grados)'),
    ('Mpitch', 'IN_180', 'Pitch', 'Inclinar: el frente hacia el cenit (grados)'),
    ('Mroll', 'IN_180', 'Roll', 'Rodar sobre el eje del frente (grados)'),
]
V169 = [
    ('Vactivo', 'IN_169', 'Activo', 'Modulo 16:9 activo'),
    ('Vfuente', VD, 'Fuente', 'Fuente del video plano'),
    ('Vmoviefile', VD, 'Moviefile', 'Archivo de video'),
    ('Vndinombre', VD, 'Ndinombre', 'Fuente NDI (nombre)'),
    ('Vspoutnombre', VD, 'Spoutnombre', 'Sender Spout (nombre)'),
    ('Vplay', VD, 'Play', 'Reproducir'),
    ('Vtemplate', VD, 'Template', 'Template (se aplica al elegirlo, pisa la tabla)'),
    # el domo interno de VIDEO_DOME, visto y movido desde afuera
    ('Vyawglobal', VD, 'Yawglobal', 'Girar todo el montaje (azimut, grados)'),
    ('Vdpitch', 'IN_169', 'Pitch', 'Inclinar el domo interno: el frente hacia el cenit (grados)'),
    ('Vdroll', 'IN_169', 'Roll', 'Rodar el domo interno sobre el eje del frente (grados)'),
    ('Vdomefov', VD, 'Domefov', 'FOV del domo interno (grados; 180 = media esfera)'),
    ('Vflipx', VD, 'Flipx', 'Espejo horizontal del domo interno'),
    ('Vscreen', VD, 'Screen', 'Pantalla que se edita (fila de la tabla)'),
    ('Vsmode', VD, 'Smode', 'Forma / curvatura'),
    ('Vsyaw', VD, 'Syaw', 'Azimut (grados)'),
    ('Vspitch', VD, 'Spitch', 'Elevacion (grados)'),
    ('Vshfov', VD, 'Shfov', 'Ancho angular (grados)'),
    ('Vsautovfov', VD, 'Sautovfov', 'Alto automatico (aspecto del video)'),
    ('Vsvfov', VD, 'Svfov', 'Alto angular (grados)'),
    ('Vsrep', VD, 'Srep', 'Copias en anillo'),
    ('Vsrepspan', VD, 'Srepspan', 'Arco que ocupan las copias (separacion, grados)'),
    ('Vsblend', VD, 'Sblend', 'Costura entre copias (grados)'),
    ('Vbg', VD, 'Bg', 'Fondo'),
    ('Vbgblur', VD, 'Bgblur', 'Fondo: desenfoque'),
    ('Vbgbright', VD, 'Bgbright', 'Fondo: brillo'),
    ('Vbgsat', VD, 'Bgsat', 'Fondo: saturacion'),
    ('Vbgzoom', VD, 'Bgzoom', 'Fondo: zoom del lavado (>= 1.78)'),
    ('Vbgtile', VD, 'Bgtile', 'Fondo: repeticiones del envolvente'),
    ('Vbgyaw', VD, 'Bgyaw', 'Fondo: girar (grados)'),
    ('Vbgfollow', VD, 'Bgfollow', 'Fondo: sigue el giro global'),
    ('Vguides', VD, 'Guides', 'Ver la rejilla y las miradas del publico'),
    ('Vguidealpha', VD, 'Guidealpha', 'Opacidad de la rejilla'),
    ('Vviewfov', VD, 'Viewfov', 'Campo de una mirada (grados)'),
    ('Vviewpitch', VD, 'Viewpitch', 'Elevacion de la mirada (grados)'),
    ('Vviewyaw', VD, 'Viewyaw', 'Azimut de la mirada (grados)'),
    ('Vviews', VD, 'Views', 'Puntos de vista del publico'),
    ('Vpreview', VD, 'Preview', 'Simulador de domo (mirar desde adentro)'),
]
PAGINAS = [
    ('360', P360, {'Ractivo': 'Video', 'Ryaw': 'Orientacion de la esfera (antes del domemaster)',
                   'Rpatron': 'Costura'}),
    ('180', P180, {'Mactivo': 'Video', 'Myaw': 'Orientacion (antes del domemaster)'}),
    ('16:9', V169, {'Vactivo': 'Fuente', 'Vtemplate': 'Montaje',
                    'Vyawglobal': 'Domo interno (orientacion y FOV)',
                    'Vscreen': 'Pantalla elegida', 'Vbg': 'Fondo',
                    'Vguides': 'Guias: seguir el domo interno desde afuera'}),
]


def destino(ruta, par):
    return getattr(D.op(ruta).par, par)


for nombre_pag, filas, cabeceras in PAGINAS:
    pagina = D.appendCustomPage(nombre_pag)
    for nombre, ruta, par, etiqueta in filas:
        if nombre in cabeceras:
            pagina.appendHeader('H' + nombre.lower(), label=cabeceras[nombre])
        src = destino(ruta, par)
        estilo = src.style
        if estilo == 'Menu':
            p = pagina.appendMenu(nombre, label=etiqueta)[0]
            p.menuNames = list(src.menuNames)
            p.menuLabels = list(src.menuLabels)
        elif estilo == 'File':
            p = pagina.appendFile(nombre, label=etiqueta)[0]
        elif estilo == 'Str':
            p = pagina.appendStr(nombre, label=etiqueta)[0]
        elif estilo == 'Toggle':
            p = pagina.appendToggle(nombre, label=etiqueta)[0]
        elif estilo == 'Int':
            p = pagina.appendInt(nombre, label=etiqueta)[0]
        else:
            p = pagina.appendFloat(nombre, label=etiqueta)[0]
        if estilo in ('Float', 'Int'):
            p.normMin, p.normMax = src.normMin, src.normMax
            if src.clampMin:
                p.min, p.clampMin = src.min, True
            if src.clampMax:
                p.max, p.clampMax = src.max, True
        p.val = src.eval()
        try:
            p.default = src.default
        except Exception:
            pass
D.sortCustomPages('Domo', '360', '180', '16:9', 'Mapping', 'Salidas')

# ------------------------------------------------------------------- AUDIO

M = D.create(baseCOMP, 'AUDIO')
M.nodeX, M.nodeY = -600, -200
M.viewer = True
pm = M.appendCustomPage('Audio')
toggle(pm, 'Activo', 'Activo', True)
menu(pm, 'Fuente', 'Fuente de audio', ['video', 'archivo', 'entrada'],
     ['Sigue a la fuente al aire (solo suena el video de DOMO.Fuente)', 'Un archivo de audio',
      'La entrada de audio del equipo'], 0)
p = pm.appendFile('Archivo', label='Archivo de audio')[0]
p.val = ''
flotante(pm, 'Ganancia', 'Ganancia', 1.0, 0, 4)
flotante(pm, 'Graves', 'Graves 100 Hz (dB)', 0, -12, 12)
flotante(pm, 'Medios', 'Medios 1 kHz (dB)', 0, -12, 12)
flotante(pm, 'Agudos', 'Agudos 8 kHz (dB)', 0, -12, 12)
flotante(pm, 'Retardo', 'Retardo para sincronizar con la imagen (ms)', 0, 0, 2000)
toggle(pm, 'Limitador', 'Limitador de picos', True)

# Sigue a la fuente: un Audio Movie CHOP por modulo, atado a su Movie File In
# (asi el sonido va sincronizado con ESE video, incluso con otra velocidad), y
# un Switch CHOP que solo cocina la entrada elegida. Los modulos que no estan
# al aire no suenan; el patron, un modulo apagado o un 16:9 que viene por NDI
# o Spout dan silencio. El 16:9 se toma de VIDEO_DOME/audio_gain (su propio
# Audio Movie por Volume y Audio), y el audio_out de VIDEO_DOME se apaga al
# final del build: antes sonaba siempre, aunque el 16:9 no estuviera al aire.
a360 = mk(M, audiomovieCHOP, 'de_360', 0, 250)
setpar(a360, 'moviefileintop', '../IN_360/video')
a180 = mk(M, audiomovieCHOP, 'de_180', 0, 150)
setpar(a180, 'moviefileintop', '../IN_180/video')
a169 = mk(M, selectCHOP, 'de_169', 0, 50)
setpar(a169, 'chop', '../IN_169/VIDEO_DOME/audio_gain')
silencio = mk(M, constantCHOP, 'silencio', 0, -50)
silencio.par.name0 = 'chan1'
silencio.par.name1 = 'chan2'
setpar(silencio, 'value0', 0)
setpar(silencio, 'value1', 0)
setpar(silencio, 'rate', 44100)
al_aire = mk(M, switchCHOP, 'al_aire', 200, 150)
wire(a360, al_aire, 0)
wire(a180, al_aire, 1)
wire(a169, al_aire, 2)
wire(silencio, al_aire, 3)
expr(al_aire, 'index',
     "(lambda D, f: 3 if f == 'patron' else "
     "(0 if D.op('IN_360').par.Activo else 3) if f == 'v360' else "
     "(1 if D.op('IN_180').par.Activo else 3) if f == 'v180' else "
     "(2 if D.op('IN_169').par.Activo and D.op('IN_169/VIDEO_DOME').par.Fuente == 'archivo' else 3))"
     "(parent.DOMO, parent.DOMO.par.Fuente.eval())")
a_video = al_aire
a_arch = mk(M, audiofileinCHOP, 'archivo', 0, -200, repeat=True)
expr(a_arch, 'file', 'parent().par.Archivo')
expr(a_arch, 'play', "parent().par.Activo and parent().par.Fuente == 'archivo'")
a_in = mk(M, audiodeviceinCHOP, 'entrada', 0, -350)
expr(a_in, 'active', "parent().par.Activo and parent().par.Fuente == 'entrada'")

sw_a = mk(M, switchCHOP, 'fuente', 400, 0)
wire(a_video, sw_a, 0)
wire(a_arch, sw_a, 1)
wire(a_in, sw_a, 2)
expr(sw_a, 'index', 'parent().par.Fuente.menuIndex')

gan = mk(M, mathCHOP, 'ganancia', 600, 0)
expr(gan, 'gain', 'parent().par.Ganancia')
wire(sw_a, gan)

eq = mk(M, audioparaeqCHOP, 'eq', 800, 0, units='frequency',
        enableeq1=True, frequencyhz1=100, bandwidth1=1.0,
        enableeq2=True, frequencyhz2=1000, bandwidth2=1.0,
        enableeq3=True, frequencyhz3=8000, bandwidth3=1.0)
expr(eq, 'boost1', 'parent().par.Graves')
expr(eq, 'boost2', 'parent().par.Medios')
expr(eq, 'boost3', 'parent().par.Agudos')
wire(gan, eq)

ret = mk(M, delayCHOP, 'retardo', 1000, 0, delayunit='seconds')
expr(ret, 'delay', 'parent().par.Retardo / 1000.0')
wire(eq, ret)

din = mk(M, audiodynamicsCHOP, 'dinamica', 1200, 0, enablecompressor=False, thresholdlimiter=-1.0)
expr(din, 'enablelimiter', 'parent().par.Limitador')
wire(ret, din)

a_out = mk(M, outCHOP, 'out1', 1400, 100)
wire(din, a_out)
dev = mk(M, audiodeviceoutCHOP, 'salida', 1400, -100)
expr(dev, 'active', 'parent().par.Activo')
wire(din, dev)

caja(M, 'nota', 'AUDIO: la cadena de sonido',
     'Por defecto sigue a la fuente al aire: al_aire elige el audio del video de DOMO.Fuente '
     '(de_360, de_180 o de_169, cada uno atado a su Movie File In y sincronizado con el) y los '
     'demas modulos no suenan. El patron, un modulo apagado o un 16:9 por NDI o Spout dan '
     'silencio. Fuente tambien puede ser un archivo aparte o la entrada del equipo. Luego '
     'ganancia, EQ de tres bandas, retardo en milisegundos para cuadrar con la imagen y un '
     'limitador. Sale por el dispositivo por defecto y por out1 (NDI y grabacion). El audio_out '
     'de VIDEO_DOME queda apagado: el unico sonido sale de aqui.',
     [a360, a180, a169, silencio, al_aire, a_arch, a_in, sw_a, gan, eq, ret, din, a_out, dev],
     (0.20, 0.13, 0.20))

# --------------------------------------------------------- mezcla y modelo

# Patron de prueba: arriba verde (la cupula), abajo rojo (bajo el horizonte),
# columna negra en u = 0 (la costura del lienzo), cuadro blanco al frente a
# 45 grados de elevacion y marca azul en el cenit. Con el se verifico la
# orientacion del domemaster y de la sala VR (ver 05_Preview/pruebas/).
patron_dat = mk(D, textDAT, 'patron_glsl', -400, -100)
patron_dat.text = leer('patron.frag')
patron = mk(D, glslTOP, 'patron', -200, -100)
patron.par.pixeldat = patron_dat
lienzo(patron)

mez = mk(D, switchTOP, 'mezcla', -200, 250)
wire(D.op('IN_360'), mez, 0)
wire(D.op('IN_180'), mez, 1)
wire(D.op('IN_169'), mez, 2)
wire(patron, mez, 3)
expr(mez, 'index', 'parent().par.Fuente.menuIndex')
equi = mk(D, nullTOP, 'equi', 0, 250)
wire(mez, equi)

# Yaw: un corrimiento horizontal del lienzo equirectangular es un giro puro en
# azimut, independiente del orden de rotaciones del Projection TOP.
giro = mk(D, transformTOP, 'giro', 200, 250, tunit='fraction', extend='repeat')
expr(giro, 'tx', 'parent().par.Yaw / 360.0')
wire(equi, giro)

# Medido con el patron (17 sep 2026): equirect -> fisheye deja el centro del
# fisheye en el horizonte del frente; rx = 90 sube el cenit al centro, ry = 90
# gira el domemaster para que el frente quede ABAJO del cuadro (convencion
# domemaster), y el Pitch va restando de rx: 90 - Pitch inclina el contenido
# del frente hacia el cenit.
# FOV del contenido: normalmente el del modelo de sala. Con Fovauto apagado y
# Fovcontenido = 230, el domemaster mete 230 grados de contenido en el mismo
# circulo; para_unreal (y el servidor del domo real) lo leen como si fuera el
# FOV de la sala, asi que en la cupula de 180 se ve tambien lo que estaba
# hasta 25 grados bajo el horizonte: mas espacio para lo que se creo.
# Las salas 90 y 45 son pantallas de 180 grados inclinadas; la inclinacion va
# en la geometria de la sala, no en el Pitch.
FOV_SALA = "[180, 180, 180, parent().par.Fovcustom][parent().par.Modelo.menuIndex]"
domo = mk(D, projectionTOP, 'domo', 400, 250, input='equirectangular', output='fisheye', ry=90, rz=0)
expr(domo, 'fov', "(%s) if parent().par.Fovauto else parent().par.Fovcontenido" % FOV_SALA)
expr(domo, 'rx', '90 - parent().par.Pitch')
setpar(domo, 'outputresolution', 'custom')
expr(domo, 'resolutionw', '[1024, 2048, 4096][parent().par.Res.menuIndex]')
expr(domo, 'resolutionh', '[1024, 2048, 4096][parent().par.Res.menuIndex]')
wire(giro, domo)

# mapping del domemaster: mover el cenit, escalar y rotar, como se hace en
# vivo sobre el servidor de un domo real. Fuera del cuadro queda negro.
mapping = mk(D, transformTOP, 'mapping', 600, 250, tunit='fraction', extend='zero')
expr(mapping, 'tx', 'parent().par.Centrox')
expr(mapping, 'ty', 'parent().par.Centroy')
expr(mapping, 'sx', 'parent().par.Escala')
expr(mapping, 'sy', 'parent().par.Escala')
expr(mapping, 'rotate', 'parent().par.Rotar')
wire(domo, mapping)
out_domo = mk(D, nullTOP, 'out_domo', 800, 250)
wire(mapping, out_domo)
D.par.opviewer = out_domo

caja(D, 'nota_mezcla', 'Mezcla y modelo de sala',
     'mezcla elige el modulo al aire (DOMO.Fuente) y equi es el lienzo equirectangular comun: '
     'u 0.5 al frente, v 0.5 en el horizonte, v 1 en el cenit. giro aplica Yaw como corrimiento '
     'horizontal. domo lo pasa a fisheye con el FOV del modelo de sala (180 media esfera, 90 y 45 '
     'casquetes): rx 90 pone el cenit en el centro, ry 90 deja el frente abajo, Pitch resta de rx. '
     'mapping mueve el cenit, escala y rota el domemaster (pagina Mapping), y con Fovauto apagado '
     'el contenido puede cubrir mas grados que la sala (230 sobre 180). out_domo es el domemaster.',
     [patron_dat, patron, mez, equi, giro, domo, mapping, out_domo], (0.16, 0.20, 0.24))

# ------------------------------------------------------------------ salidas

sp_domo = mk(D, syphonspoutoutTOP, 'spout_domo', 1000, 400)
expr(sp_domo, 'sendername', 'parent().par.Spoutdomonombre')
expr(sp_domo, 'active', 'parent().par.Spoutdomo')
wire(out_domo, sp_domo)

ndi = mk(D, ndioutTOP, 'ndi_domo', 1000, 250)
expr(ndi, 'name', 'parent().par.Ndinombre')
expr(ndi, 'active', 'parent().par.Ndi')
setpar(ndi, 'audiochop', 'AUDIO/out1')
wire(out_domo, ndi)

grab = mk(D, moviefileoutTOP, 'grabar', 1000, 100, type='movie', uniquesuff=True)
setpar(grab, 'videocodec', 'hap')
expr(grab, 'file', "parent().par.Grabarcarpeta + '/domemaster.mov'")
expr(grab, 'record', 'parent().par.Grabar')
setpar(grab, 'audiochop', 'AUDIO/out1')
wire(out_domo, grab)

# La sala VR quiere el lienzo equirectangular (cupula en la mitad superior),
# ya con Yaw, Pitch y el FOV del modelo aplicados. Se reconstruye desde el
# domemaster con fisheye -> equirect rx -90; como el domemaster va girado 90
# grados (ry 90 de `domo`), giro_unreal lo devuelve con un corrimiento de -0.25.
# Medido con el patron: el cuadro blanco del frente vuelve a (u 0.5, v 0.75).
unreal = mk(D, projectionTOP, 'para_unreal', 1000, -100, input='fisheye', output='equirectangular', rx=-90, ry=0, rz=0)
expr(unreal, 'fov', FOV_SALA)   # el de la SALA, no el del contenido: asi 230 grados caben en 180
lienzo(unreal)
wire(out_domo, unreal)
giro_un = mk(D, transformTOP, 'giro_unreal', 1200, -100, tunit='fraction', extend='repeat', tx=-0.25)
wire(unreal, giro_un)
# El receptor Spout de Unreal solo lee texturas de 8 bits: con el lienzo en
# 16-bit float (lo que sale de VIDEO_DOME) se queda con el ultimo frame que
# pudo leer, sin avisar. Aqui se fija el formato antes del sender.
alfa = mk(D, reorderTOP, 'alfa_unreal', 1400, -100, outputalphachan='one', format='rgba8fixed')
wire(giro_un, alfa)
sp_un = mk(D, syphonspoutoutTOP, 'spout_unreal', 1600, -100)
expr(sp_un, 'sendername', 'parent().par.Spoutunrealnombre')
expr(sp_un, 'active', 'parent().par.Spoutunreal')
wire(alfa, sp_un)

caja(D, 'nota_salidas', 'Salidas',
     'Del domemaster salen Spout y NDI (para un servidor de domo o Resolume) y la grabacion en HAP. '
     'La sala VR en Unreal no quiere el domemaster sino el lienzo equirectangular con la cupula en '
     'la mitad superior: para_unreal lo reconstruye desde el domemaster (rx -90), giro_unreal '
     'deshace el giro de 90 del domemaster y spout_unreal lo manda con el nombre que lee el '
     'SpoutDomeReceiver (TD_Domo_Lab). Los toggles estan en la pagina Salidas.',
     [sp_domo, ndi, grab, unreal, giro_un, alfa, sp_un], (0.24, 0.20, 0.14))

caja(D, 'nota_modulos', 'Modulos de entrada',
     'Cada modulo lee su propio archivo y entrega el mismo lienzo equirectangular. Su parametro '
     'Activo apagado entrega negro y deja de cocinar. Solo el modulo elegido en DOMO.Fuente llega '
     'a la salida; los demas no gastan GPU aunque esten activos, y solo ese suena (AUDIO). Cada uno '
     'tiene su pagina en la raiz (360, 180, 16:9) con su orientacion esferica.',
     [D.op('IN_360'), D.op('IN_180'), D.op('IN_169'), D.op('AUDIO')], (0.14, 0.14, 0.18))

caja(D, 'nota_169', 'Pagina 16:9: el video plano desde aqui',
     'El 16:9 se maneja desde la pagina 16:9 de DOMO, igual que el 360 y el 180 desde sus paginas. Template '
     'cambia el montaje de pantallas al elegirlo (sala_corona, anillo_doble, sala_4...), sin pulso; '
     'ojo que pisa la tabla de pantallas. Fuente elige archivo, NDI o Spout. Pantalla elegida '
     'dice que fila se edita: azimut, elevacion, ancho, forma (plana, curva, banda, tunel, cilindro), '
     'copias en anillo y el arco que ocupan (la separacion). Fondo: modo, desenfoque, brillo, zoom. '
     'Esos pars de IN_169/VIDEO_DOME estan en modo Bind contra estos, en los dos sentidos: lo que '
     'se mueve aqui se mueve alla y viceversa, y reconstruir DOMO lo conserva. Lo fino (recortes, '
     'espejo, animacion, momentos, versiones, editor con el mouse) sigue en VIDEO_DOME. Domo interno: '
     'Yawglobal gira, Vdpitch inclina y Vdroll rueda todo el montaje (antes del domemaster, como la '
     'pagina 360), Vdomefov es el FOV con que VIDEO_DOME dibuja (subirlo a 230 acompana a Mapping con '
     'Fovauto apagado). Guias: Vguides pinta sobre la salida la rejilla y los circulos de mirada del '
     'publico (Vviewfov, Vviewpitch, Vviewyaw, Vviews) para seguir el domo interno desde afuera.',
     [], (0.26, 0.19, 0.12), rect=(-1200, -150, -720, 450))

# ------------------------------------------------- reescribir la configuracion

restaurados = 0
for rel, pares in guardado.items():
    comp = D if rel == '.' else D.op(rel.strip('/'))
    if comp is None:
        continue
    for nombre, val in pares.items():
        p = getattr(comp.par, nombre, None)
        if p is not None and p.mode == ParMode.CONSTANT and not p.readOnly:
            try:
                p.val = val
                restaurados += 1
            except Exception as e:
                print('[DOMO] no se pudo restaurar %s.%s: %s' % (comp.path, nombre, e))
if guardado:
    print('[DOMO] %d parametros restaurados' % restaurados)

vd = D.op('IN_169/VIDEO_DOME')
if vd is not None and (vd_previo['pars'] or vd_previo['screens']):
    # El watcher de VIDEO_DOME reacciona unos frames DESPUES del cambio: al
    # restaurar Template (cine -> el que habia) aplica ese template sobre la
    # tabla recien restaurada y se pierden las ediciones de pantalla (medido:
    # apagar el watcher mientras tanto no alcanza, dispara al volver a
    # prenderlo). Por eso la tabla se vuelve a escribir despues, con un run
    # diferido, y se releen los pars de la pantalla elegida.
    if vd_previo['screens']:
        vd.store('_tabla_restaurar', vd_previo['screens'])
        run("vd = op(%r)\n"
            "t = vd.fetch('_tabla_restaurar', None, search=False) if vd is not None else None\n"
            "if t:\n"
            "    vd.op('screens').text = t\n"
            "    vd.unstore('_tabla_restaurar')\n"
            "    vd.op('watcher').module.leer_fila(vd)\n" % vd.path, delayFrames=15)
    n = 0
    for nombre, (tipo, valor) in vd_previo['pars'].items():
        p = getattr(vd.par, nombre, None)
        if p is None or p.isPulse or p.isMomentary:
            continue
        try:
            if tipo == 'expr':
                p.expr = valor
            else:
                p.val = valor
            n += 1
        except Exception:
            pass
    for t in ('screens', 'moments'):
        if vd_previo[t] and vd.op(t) is not None:
            vd.op(t).text = vd_previo[t]
    print('[DOMO] VIDEO_DOME: %d pars y sus tablas restaurados' % n)

# Paginas 360, 180 y 16:9: se decide que lado manda y solo despues se ponen
# los binds, para que al enlazar no cambie nada.
# - Pars de VIDEO_DOME: manda abajo. VIDEO_DOME ya tiene su configuracion y
#   la tabla que le corresponde; como los dos lados quedan iguales, el
#   watcher no vuelve a aplicar el template sobre la tabla.
# - Pars de los modulos (IN_360, IN_180, IN_169): manda arriba si la raiz ya
#   tenia ese par guardado (el modulo nace con su valor por defecto, porque un
#   par en Bind no se guarda); si es la primera vez, sube el valor del modulo.
guardado_raiz = guardado.get('.', {})
enlazados = 0
for nombre_pag, filas, cabeceras in PAGINAS:
    for nombre, ruta, par, etiqueta in filas:
        abajo = destino(ruta, par)
        arriba = getattr(D.par, nombre)
        try:
            if ruta == VD or nombre not in guardado_raiz:
                arriba.val = abajo.eval()
            abajo.bindExpr = 'parent.DOMO.par.' + nombre
            abajo.mode = ParMode.BIND
            enlazados += 1
        except Exception as e:
            print('[DOMO] no se pudo enlazar %s -> %s.%s: %s' % (nombre, abajo.owner.path, abajo.name, e))
print('[DOMO] paginas 360, 180 y 16:9: %d pars enlazados' % enlazados)

# El sonido de DOMO sale solo por AUDIO/salida. El audio_out propio de
# VIDEO_DOME sonaba siempre (aunque el 16:9 no estuviera al aire): aqui se
# apaga. Su audio_movie y audio_gain siguen vivos para AUDIO/de_169.
vd = D.op(VD)
if vd is not None and vd.op('audio_out') is not None:
    ao = vd.op('audio_out').par.active
    ao.expr = ''
    ao.mode = ParMode.CONSTANT
    ao.val = False

print('[DOMO] construido: %s, %d operadores' % (D.path, len(D.findChildren())))
