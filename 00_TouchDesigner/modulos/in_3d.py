# ==========================================================================
# in_3d.py  ·  modulo IN_3D de DOMO: objetos 3D animados alrededor del publico
#
# No se corre solo: build_domo.py lo ejecuta dentro de su propio espacio de
# nombres (D, mk, wire, expr, setpar, lienzo, caja, menu, flotante, toggle,
# pagina_orientacion, orientador, negro_y_salida).
#
# La camara esta en el centro de la sala (el publico) y renderiza un CUBEMAP:
# seis caras, todas las direcciones. El Projection TOP lo pasa a
# equirectangular 2:1 y de ahi en adelante es un lienzo como el del 360. Se
# eligio cubemap y no el modo fisheye del Render TOP porque el fisheye deforma
# en el vertice (los poligonos grandes se rompen si no se teselan) y porque el
# Line MAT no funciona con fisheye; con cubemap cada cara es una perspectiva
# normal y el Projection TOP hace la curva por pixel.
#
# Todo sale de SOPs primitivos (Torus, Sphere, Box) instanciados con Script
# CHOPs: no hay fbxCOMP ni fileinSOP, porque crearlos desde el MCP colgo el
# servidor de TouchDesigner (29 sep 2026). Para enchufar un modelo propio ver
# la caja `nota_modelo` y 04_Docs/04_Senal_TouchDesigner.md.
#
# Convencion de la escena (la de TouchDesigner): Y arriba, el frente de la
# sala es -Z (hacia donde mira una camara sin rotar), X a la derecha.
# ==========================================================================

M = D.create(baseCOMP, 'IN_3D')
M.nodeX, M.nodeY = -600, -600
M.viewer = True
pm = M.appendCustomPage('Objetos3D')
toggle(pm, 'Activo', 'Activo', True)
flotante(pm, 'Velocidad', 'Velocidad de la animacion (x)', 1.0, 0, 3)
toggle(pm, 'Toro', 'Toro sobre el publico', True)
toggle(pm, 'Anillos', 'Anillos concentricos', True)
toggle(pm, 'Esferas', 'Esferas en orbita', True)
toggle(pm, 'Cajas', 'Cajas en espiral', True)
toggle(pm, 'Modelo', 'Modelo propio (geo modelo, ver la nota)', False)
p = pm.appendInt('Ncajas', label='Cantidad de cajas')[0]
p.val, p.default, p.normMin, p.normMax = 160, 160, 10, 600
p.min, p.clampMin, p.max, p.clampMax = 1, True, 2000, True
p = pm.appendInt('Nesferas', label='Cantidad de esferas')[0]
p.val, p.default, p.normMin, p.normMax = 18, 18, 3, 64
p.min, p.clampMin, p.max, p.clampMax = 1, True, 256, True
flotante(pm, 'Tamano', 'Tamano de los objetos (x)', 1.0, 0.2, 3)
flotante(pm, 'Distancia', 'Distancia al publico (x)', 1.0, 0.4, 2)
p = pm.appendRGB('Color1', label='Color A (toro y anillos)')
p[0].val, p[1].val, p[2].val = 0.15, 0.65, 1.0
for c in p:
    c.default = c.val
p = pm.appendRGB('Color2', label='Color B (esferas y cajas)')
p[0].val, p[1].val, p[2].val = 1.0, 0.35, 0.65
for c in p:
    c.default = c.val
flotante(pm, 'Emision', 'Brillo propio (0 = solo luz)', 0.35, 0, 1)
toggle(pm, 'Alambre', 'Alambre (wireframe)', False)
flotante(pm, 'Reactividad', 'Reaccion al audio (0 = nada)', 0.5, 0, 2)
pc = M.appendCustomPage('Camara')
flotante(pc, 'Orbitaradio', 'Orbita de la camara: radio (m, 0 = quieta en el centro)', 1.5, 0, 6)
flotante(pc, 'Orbitavel', 'Orbita: velocidad (grados por segundo)', 8.0, -60, 60)
M.par.Orbitavel.clampMin = False
flotante(pc, 'Orbitaalto', 'Altura de la camara (m)', 0.0, -3, 3)
M.par.Orbitaalto.clampMin = False
toggle(pc, 'Mirarcentro', 'La camara gira para mirar siempre al centro', False)
menu(pc, 'Cubo', 'Resolucion de cada cara del cubo',
     ['c512', 'c1024', 'c2048'], ['512 (ensayo)', '1024 (tiempo real)', '2048 (grabar)'], 1)
p = pc.appendRGB('Fondo', label='Color de fondo')
for c in p:
    c.val = 0.0
    c.default = 0.0

# ------------------------------------------------------------ reloj y audio
vel = mk(M, constantCHOP, 'velocidad', -800, 400)
vel.par.name0 = 't'
expr(vel, 'value0', 'parent().par.Velocidad')
vel.par.name1 = 'orbita'
expr(vel, 'value1', 'parent().par.Orbitavel')
reloj = mk(M, speedCHOP, 'reloj', -600, 400, limittype='loop', min=0, max=3600)
wire(vel, reloj)
nv = mk(M, selectCHOP, 'audio', -600, 250)
setpar(nv, 'chop', '../AUDIO/niveles')

# ------------------------------------------ instancias (Script CHOP + numpy)
INST_CB = r'''# Instancias de IN_3D. Un solo archivo para los tres Script CHOP: cada uno
# mira su propio nombre (inst_esferas, inst_cajas, inst_anillos). Leer
# op('reloj') y los pars del COMP deja la dependencia hecha: cocina cada cuadro.
import numpy as np


def _audio(c):
    a = c.op('audio')
    if a is None or a.numChans == 0:
        return 0.0, 0.0
    r = c.par.Reactividad.eval()
    g = a['graves']
    n = a['nivel']
    vg = float(g[0]) * r if g is not None else 0.0
    vn = float(n[0]) * r if n is not None else 0.0
    # un NaN en la escala hace desaparecer la instancia sin error
    return (vg if vg == vg else 0.0, vn if vn == vn else 0.0)


def onCook(scriptOp):
    scriptOp.clear()
    c = scriptOp.parent()
    t = float(c.op('reloj')['t'][0])
    dist = c.par.Distancia.eval()
    tam = c.par.Tamano.eval()
    graves, nivel = _audio(c)
    nombre = scriptOp.name
    if nombre == 'inst_esferas':
        n = max(int(c.par.Nesferas.eval()), 1)
        i = np.arange(n)
        a = i / n * 2 * np.pi + t * 0.25
        radio = 7.5 * dist
        tx = radio * np.sin(a)
        tz = -radio * np.cos(a)
        ty = (3.2 + 1.6 * np.sin(a * 3 + t * 0.9)) * dist
        s = (0.55 + 0.25 * np.sin(i * 1.7 + t * 2.0)) * tam * (1 + 0.8 * graves)
        cols = {'tx': tx, 'ty': ty, 'tz': tz, 'sx': s, 'sy': s, 'sz': s}
    elif nombre == 'inst_cajas':
        n = max(int(c.par.Ncajas.eval()), 1)
        i = np.arange(n)
        f = i / n
        # espiral sobre una cupula: sube de 5 a 80 grados dando 5 vueltas
        el = np.radians(5 + 75 * f)
        az = f * 5 * 2 * np.pi - t * 0.15
        radio = 13.0 * dist
        tx = radio * np.cos(el) * np.sin(az)
        tz = -radio * np.cos(el) * np.cos(az)
        ty = radio * np.sin(el)
        s = (0.35 + 0.35 * np.abs(np.sin(i * 12.9898))) * tam * (1 + 0.6 * graves)
        cols = {'tx': tx, 'ty': ty, 'tz': tz,
                'rx': (i * 37.0 + t * 40.0) % 360, 'ry': (i * 53.0 + t * 25.0) % 360, 'rz': (i * 11.0) % 360,
                'sx': s, 'sy': s, 'sz': s}
    else:  # inst_anillos
        n = 5
        i = np.arange(n)
        radio = (9.0 + 2.2 * i) * dist
        ty = (2.0 + 2.2 * i) * dist
        signo = np.where(i % 2 == 0, 1.0, -1.0)
        cols = {'tx': np.zeros(n), 'ty': ty, 'tz': np.zeros(n),
                'rx': 8.0 * np.sin(t * 0.4 + i), 'ry': (signo * t * (12 + 4 * i)) % 360,
                'rz': 8.0 * np.cos(t * 0.3 + i),
                'sx': radio, 'sy': radio * (1 + 0.5 * nivel), 'sz': radio}
    scriptOp.numSamples = len(next(iter(cols.values())))
    for k, v in cols.items():
        ch = scriptOp.appendChan(k)
        ch.vals = [float(x) for x in v]
    return
'''
cb = mk(M, textDAT, 'instancias_py', -600, 100)
cb.text = INST_CB

MAT_Y = -250


def material(nombre, x, color):
    m = mk(M, phongMAT, nombre, x, MAT_Y)
    for comp in 'rgb':
        expr(m, 'diff' + comp, 'parent().par.%s%s' % (color, comp))
        expr(m, 'emit' + comp, 'parent().par.%s%s * parent().par.Emision' % (color, comp))
    setpar(m, 'shininess', 40)
    expr(m, 'wireframe', "'topology' if parent().par.Alambre else 'off'")
    return m


def geo(nombre, x, y, sop, pars_sop, mat, visible, inst=None):
    """geometryCOMP con un solo SOP primitivo adentro; con `inst` se instancia
    desde ese CHOP (tx..sz). El torus1 que trae de fabrica se borra."""
    g = mk(M, geometryCOMP, nombre, x, y)
    for hijo in list(g.children):
        hijo.destroy()
    s = g.create(sop, 'forma')
    for k, v in pars_sop.items():
        setpar(s, k, v)
    s.render = True
    s.display = True
    # en un par OP de un COMP el nombre pelado es un HERMANO (con '../' TD
    # buscaba en DOMO y dejaba el material por defecto, blanco)
    g.par.material = mat.name if mat is not None else ''
    expr(g, 'render', visible)
    if inst is not None:
        g.par.instancing = True
        g.par.instanceop = inst.name
        for canal in ('tx', 'ty', 'tz', 'rx', 'ry', 'rz', 'sx', 'sy', 'sz'):
            if inst[canal] is not None or canal in ('tx', 'ty', 'tz', 'sx', 'sy', 'sz'):
                setpar(g, 'instance' + canal, canal)
    return g


m_a = material('mat_a', -400, 'Color1')
m_b = material('mat_b', -200, 'Color2')

i_esf = mk(M, scriptCHOP, 'inst_esferas', -400, 250)
setpar(i_esf, 'callbacks', cb.name)
i_caj = mk(M, scriptCHOP, 'inst_cajas', -200, 250)
setpar(i_caj, 'callbacks', cb.name)
i_ani = mk(M, scriptCHOP, 'inst_anillos', 0, 250)
setpar(i_ani, 'callbacks', cb.name)
for s in (i_esf, i_caj, i_ani):
    # el Script CHOP nace con su propio DAT de callbacks: sobra
    sobra = M.op(s.name + '_callbacks')
    if sobra is not None:
        sobra.destroy()
    s.cook(force=True)

g_toro = geo('toro', -400, 0, torusSOP, {'radx': 5.0, 'rady': 0.55, 'rows': 24, 'cols': 96, 'orient': 'y'},
             m_a, 'parent().par.Toro')
# el toro sobre el publico: centrado en el eje del cenit, cabeceando despacio
expr(g_toro, 'ty', '7.5 * parent().par.Distancia')
expr(g_toro, 'rx', "12 * math.sin(op('reloj')['t'] * 0.5)")
expr(g_toro, 'ry', "(op('reloj')['t'] * 20) % 360")
expr(g_toro, 'rz', "10 * math.cos(op('reloj')['t'] * 0.37)")
expr(g_toro, 'scale', 'parent().par.Tamano')
g_ani = geo('anillos', -200, 0, torusSOP, {'radx': 1.0, 'rady': 0.025, 'rows': 8, 'cols': 128, 'orient': 'y'},
            m_a, 'parent().par.Anillos', inst=i_ani)
g_esf = geo('esferas', 0, 0, sphereSOP, {'rows': 20, 'cols': 32, 'radx': 1, 'rady': 1, 'radz': 1},
            m_b, 'parent().par.Esferas', inst=i_esf)
g_caj = geo('cajas', 200, 0, boxSOP, {}, m_b, 'parent().par.Cajas', inst=i_caj)

# Ranura para un modelo propio: vacia (un Null SOP) y apagada. Ver nota_modelo.
g_mod = mk(M, geometryCOMP, 'modelo', 400, 0)
for hijo in list(g_mod.children):
    hijo.destroy()
# un Add SOP sin puntos: geometria vacia sin error (el Null SOP sin entrada
# marca "Not enough sources")
ns = g_mod.create(addSOP, 'aqui_el_modelo')
ns.render = True
ns.display = True
g_mod.par.material = 'mat_b'
expr(g_mod, 'render', 'parent().par.Modelo')
expr(g_mod, 'scale', 'parent().par.Tamano')
expr(g_mod, 'ty', '6 * parent().par.Distancia')
expr(g_mod, 'ry', "(op('reloj')['t'] * 15) % 360")

cam = mk(M, cameraCOMP, 'camara', -400, -450)
# orbita: la camara da vueltas alrededor del centro de la sala. Sin
# Mirarcentro no rota, asi el frente de la sala sigue siendo el frente.
expr(cam, 'tx', "parent().par.Orbitaradio * math.sin(math.radians(op('reloj')['orbita']))")
expr(cam, 'tz', "parent().par.Orbitaradio * math.cos(math.radians(op('reloj')['orbita']))")
expr(cam, 'ty', 'parent().par.Orbitaalto')
expr(cam, 'ry', "op('reloj')['orbita'] if parent().par.Mirarcentro else 0")
luz = mk(M, lightCOMP, 'luz', -200, -450, lighttype='point', dimmer=1.0)
luz.par.ty = 2.0
amb = mk(M, ambientlightCOMP, 'ambiente', 0, -450, dimmer=0.25)

ren = mk(M, renderTOP, 'render', 600, 0, rendermode='cubemap', antialias='aa4')
ren.par.camera = 'camara'
ren.par.geometry = 'toro anillos esferas cajas modelo'
ren.par.lights = 'luz ambiente'
setpar(ren, 'outputresolution', 'custom')
expr(ren, 'resolutionw', '[512, 1024, 2048][parent().par.Cubo.menuIndex]')
expr(ren, 'resolutionh', '[512, 1024, 2048][parent().par.Cubo.menuIndex]')
expr(ren, 'bgcolorr', 'parent().par.Fondor')
expr(ren, 'bgcolorg', 'parent().par.Fondog')
expr(ren, 'bgcolorb', 'parent().par.Fondob')
setpar(ren, 'bgcolora', 1.0)

equi3d = mk(M, projectionTOP, 'cubo_a_equi', 800, 0, input='cubemap', output='equirectangular')
lienzo(equi3d)
wire(ren, equi3d)
# Medido el 29 sep 2026 con dos esferas marcadoras: el Projection TOP deja el
# frente de la escena (-Z) en u = 0.75 y la derecha (+X) en u = 1.0, con +Y
# arriba. La derecha queda un cuarto de vuelta despues del frente, igual que
# en el lienzo, asi que no hay espejo: basta correr -0.25 para que el frente
# caiga en u = 0.5, la convencion de DOMO.
frente3d = mk(M, transformTOP, 'al_frente', 1000, 0, tunit='fraction', extend='repeat', tx=-0.25)
wire(equi3d, frente3d)

pagina_orientacion(M, 'Orientacion')
nodos_or3d, orient3d = orientador(M, frente3d, 1200)
negro_y_salida(M, orient3d, 1600)

caja(M, 'nota', 'IN_3D: objetos 3D alrededor del publico',
     'La camara esta en el centro de la sala y render dibuja un cubemap (seis caras, todas las '
     'direcciones); cubo_a_equi lo pasa al lienzo equirectangular. Cubemap y no fisheye: el fisheye del '
     'Render TOP deforma en el vertice y rompe los poligonos grandes. Objetos: toro sobre el publico, '
     'cinco anillos concentricos que giran en sentidos opuestos, esferas en orbita y cajas en espiral '
     'hasta el cenit; todos SOPs primitivos, instanciados por Script CHOPs (instancias_py). reloj '
     'integra el tiempo (Velocidad) y la orbita de la camara (Orbitaradio, Orbitavel; Mirarcentro la '
     'hace girar hacia el centro). audio lee DOMO/AUDIO/niveles: los graves inflan esferas y cajas.',
     [vel, reloj, nv, cb, m_a, m_b, i_esf, i_caj, i_ani, g_toro, g_ani, g_esf, g_caj, cam, luz, amb,
      ren, equi3d, frente3d] + nodos_or3d + [M.op('negro'), M.op('activo'), M.op('out1')],
     (0.20, 0.14, 0.24))
caja(M, 'nota_modelo', 'Enchufar un modelo propio',
     'modelo es una geometria vacia (un Add SOP sin puntos) que ya esta en la lista del render, con el material B, '
     'la escala de Tamano y un giro lento. Para usarla: entrar a modelo, reemplazar aqui_el_modelo por un '
     'File In SOP (.obj, .fbx, .bgeo) o arrastrar el archivo a la red, poner display y render en ese SOP y '
     'encender el par Modelo. Hacerlo a mano en la interfaz: crear fileinSOP o fbxCOMP desde el MCP colgo '
     'el servidor de TouchDesigner. Un FBX con varias piezas va mejor como FBX COMP aparte, agregado al '
     'par Geometry de render. El modelo se ve desde adentro: ponerlo a 5 a 15 m del centro.',
     [], (0.16, 0.16, 0.16), rect=(380, -700, 980, -520))
