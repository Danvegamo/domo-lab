# ==========================================================================
# in_fx.py  ·  modulo IN_FX de DOMO: visualizaciones generativas en GLSL
#
# No se corre solo: build_domo.py lo ejecuta dentro de su propio espacio de
# nombres, asi que aqui estan disponibles D (el COMP DOMO), mk, wire, expr,
# setpar, lienzo, caja, menu, flotante, toggle, leer, pagina_orientacion,
# orientador y negro_y_salida.
#
# Por que sale en equirectangular 2:1 y no en 16:9 hacia VIDEO_DOME: un efecto
# generativo no tiene cuadro, tiene espacio. Pintado directo sobre la esfera
# (shaders/efectos.frag calcula la direccion de cada pixel del lienzo) llena
# la cupula entera sin costura ni pellizco en el cenit, y pasa por la misma
# orientacion (Yaw, Pitch, Roll, Horizonte) y por el mismo domemaster que el
# 360. Si se quisiera un efecto adentro de una pantalla, basta con mandar este
# TOP como fuente Spout o como fondo `custom` de VIDEO_DOME.
#
# Cadena: reloj (Speed CHOP: el tiempo se integra, asi cambiar la velocidad no
# da un salto) -> efectos (GLSL TOP a Resfx x Resfx/2) -> lienzo (Fit TOP al
# ancho de DOMO) -> orientar -> activo -> out1.
# ==========================================================================

EFECTOS = ['tunel', 'ondas', 'estrellas', 'caleidoscopio', 'plasma', 'flujo', 'rejilla', 'aurora']
EFECTOS_ETIQ = ['Tunel de vuelo hacia el cenit', 'Ondas que bajan del cenit',
                'Campo de estrellas (vuelo)', 'Caleidoscopio', 'Plasma',
                'Flujo (tinta en agua)', 'Rejilla neon (techo en perspectiva)', 'Aurora']

M = D.create(baseCOMP, 'IN_FX')
M.nodeX, M.nodeY = -600, -400
M.viewer = True
pm = M.appendCustomPage('Efectos')
toggle(pm, 'Activo', 'Activo', True)
menu(pm, 'Efecto', 'Efecto', EFECTOS, EFECTOS_ETIQ, 0)
flotante(pm, 'Velocidad', 'Velocidad (x)', 1.0, 0, 3)
flotante(pm, 'Giro', 'Giro continuo (grados por segundo)', 0.0, -30, 30)
M.par.Giro.clampMin = False
flotante(pm, 'Escala', 'Escala (mas = patron mas fino)', 1.0, 0.25, 3)
M.par.Escala.min, M.par.Escala.clampMin = 0.05, True
flotante(pm, 'Detalle', 'Detalle (octavas, lineas, segmentos)', 0.5, 0, 1)
M.par.Detalle.max, M.par.Detalle.clampMax = 1.0, True
flotante(pm, 'Intensidad', 'Intensidad', 1.0, 0, 2)
p = pm.appendRGB('Color1', label='Color A')
p[0].val, p[1].val, p[2].val = 0.10, 0.60, 1.00
for c in p:
    c.default = c.val
p = pm.appendRGB('Color2', label='Color B')
p[0].val, p[1].val, p[2].val = 1.00, 0.25, 0.70
for c in p:
    c.default = c.val
flotante(pm, 'Reactividad', 'Reaccion al audio (0 = nada)', 0.5, 0, 2)
flotante(pm, 'Empuje', 'El audio acelera el tiempo (x)', 0.5, 0, 2)
menu(pm, 'Resfx', 'Resolucion del efecto (ancho del lienzo propio)',
     ['r1024', 'r2048', 'r4096'], ['1024 x 512 (ensayo)', '2048 x 1024 (tiempo real)', '4096 x 2048 (grabar)'], 1)

# Niveles de audio: los calcula DOMO/AUDIO/niveles (nivel, graves, medios,
# agudos, 0..1 y suavizados). Aqui solo se leen.
nv = mk(M, selectCHOP, 'audio', 0, 200)
setpar(nv, 'chop', '../AUDIO/niveles')

# el tiempo se integra: tiempo += Velocidad * (1 + Empuje * graves)
vel = mk(M, constantCHOP, 'velocidad', 0, 350)
vel.par.name0 = 't'
expr(vel, 'value0', "parent().par.Velocidad * (1 + parent().par.Empuje * parent().par.Reactividad "
                    "* (op('audio')['graves'][0] if op('audio').numChans else 0))")
vel.par.name1 = 'giro'
expr(vel, 'value1', 'parent().par.Giro')
reloj = mk(M, speedCHOP, 'reloj', 200, 350, limittype='loop', min=0, max=3600)
wire(vel, reloj)

dat = mk(M, textDAT, 'efectos_glsl', 200, -250)
dat.text = leer('efectos.frag')
g = mk(M, glslTOP, 'efectos', 200, 0)
g.par.pixeldat = dat
setpar(g, 'outputresolution', 'custom')
expr(g, 'resolutionw', '[1024, 2048, 4096][parent().par.Resfx.menuIndex]')
expr(g, 'resolutionh', '[512, 1024, 2048][parent().par.Resfx.menuIndex]')
setpar(g, 'format', 'rgba8fixed')
setpar(g, 'vec', 4)
setpar(g, 'vec0name', 'uFx')
expr(g, 'vec0valuex', 'parent().par.Efecto.menuIndex')
expr(g, 'vec0valuey', "op('reloj')['t']")
expr(g, 'vec0valuez', "op('reloj')['giro'] % 360")
expr(g, 'vec0valuew', 'parent().par.Intensidad')
setpar(g, 'vec1name', 'uCol1')
expr(g, 'vec1valuex', 'parent().par.Color1r')
expr(g, 'vec1valuey', 'parent().par.Color1g')
expr(g, 'vec1valuez', 'parent().par.Color1b')
expr(g, 'vec1valuew', 'parent().par.Escala')
setpar(g, 'vec2name', 'uCol2')
expr(g, 'vec2valuex', 'parent().par.Color2r')
expr(g, 'vec2valuey', 'parent().par.Color2g')
expr(g, 'vec2valuez', 'parent().par.Color2b')
expr(g, 'vec2valuew', 'parent().par.Detalle')
setpar(g, 'vec3name', 'uAudio')
for comp, canal in zip('xyzw', ('nivel', 'graves', 'medios', 'agudos')):
    expr(g, 'vec3value' + comp,
         "parent().par.Reactividad * (op('audio')['%s'][0] if op('audio')['%s'] is not None else 0)" % (canal, canal))

fitfx = mk(M, fitTOP, 'lienzo', 400, 0, fit='fitbest')
lienzo(fitfx)
wire(g, fitfx)

pagina_orientacion(M, 'Orientacion')
nodos_orfx, orientfx = orientador(M, fitfx, 600)
negro_y_salida(M, orientfx, 1000)

caja(M, 'nota', 'IN_FX: visualizaciones generativas',
     'efectos (GLSL, shaders/efectos.frag) pinta el lienzo equirectangular directamente: cada pixel '
     'calcula su direccion en la esfera y el efecto se evalua ahi, asi no hay costura atras ni pellizco '
     'en el cenit. Ocho efectos (Efecto): tunel de vuelo, ondas, estrellas, caleidoscopio, plasma, '
     'flujo, rejilla neon y aurora; Color A y B, Escala, Detalle, Velocidad, Giro e Intensidad los '
     'manejan todos. reloj integra el tiempo (cambiar la velocidad no salta) y el audio lo empuja '
     '(Empuje). audio lee DOMO/AUDIO/niveles (nivel, graves, medios, agudos) y Reactividad dice cuanto '
     'pesa. Resfx baja la resolucion del efecto si falta GPU: lienzo lo lleva al ancho de DOMO. '
     'Despues, el mismo orientar que el 360 (Yaw, Pitch, Roll, Horizonte, Curva).',
     [nv, vel, reloj, dat, g, fitfx] + nodos_orfx + [M.op('negro'), M.op('activo'), M.op('out1')],
     (0.12, 0.16, 0.24))
