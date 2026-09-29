# ==========================================================================
# in_ue.py  ·  modulo IN_UE de DOMO: el domemaster que genera Unreal, directo a las salidas
#
# No se corre solo: build_domo.py lo ejecuta dentro de su propio espacio de nombres, despues de crear
# out_domo y sus salidas. Aqui estan disponibles D (el COMP DOMO), mk, wire, expr, setpar, caja, toggle y
# texto.
#
# Es el sentido inverso del resto del sistema. Los demas modulos entregan un lienzo equirectangular que
# DOMO convierte a domemaster (`domo`); este recibe por NDI el domemaster que ya renderiza Unreal
# (ADomeEmisorNDI, ver 04_Docs/09_Abismo_Unreal_a_NDI.md) y lo pone en out_domo SIN pasar por el
# equirectangular: se evita la conversion de ida y vuelta (domemaster -> equirectangular -> domemaster)
# que suaviza el borde de la cupula. Lo que sale por Spout, NDI o a disco es el mismo domemaster de
# Unreal, con el mismo Master (brillo, contraste, gamma y negro) que las demas fuentes.
#
# Cadena:  ndi (NDI In) -> ajuste (a la resolucion de `domo`) -> nivel (Master) -> out1
# y en DOMO:  salida_domo = Switch(domo, domemaster_ue = Select de IN_UE/out1)  ->  out_domo
#
# Se enciende con DOMO.Uactivo (pagina Unreal). Apagado, el NDI In no cocina y out_domo sigue siendo `domo`.
# La orientacion, el giro y el FOV se ajustan en Unreal (ADomeEmisorNDI: InclinacionDomo, FovDomo); aqui
# no se aplican Yaw, Pitch ni Mapping porque son del lienzo equirectangular.
# ==========================================================================

pu = D.appendCustomPage('Unreal')
toggle(pu, 'Uactivo', 'Domemaster de Unreal (NDI) directo a las salidas', False)
texto(pu, 'Unombre', 'Fuente NDI: nombre o "EQUIPO (nombre)"', 'Unreal_Abismo')
p = pu.appendStr('Uestado', label='Estado')[0]
p.expr = ("('recibiendo %dx%d' % (me.op('IN_UE/ndi').width, me.op('IN_UE/ndi').height)) if me.par.Uactivo else 'apagado'")
p.readOnly = True

M = mk(D, baseCOMP, 'IN_UE', -600, -800)
M.viewer = True

ndi_ue = mk(M, ndiinTOP, 'ndi', 0, 0)
# El NDI In pide el nombre completo, "EQUIPO (fuente)". Si se escribio solo la fuente, se le pone el equipo
# de esta maquina (Unreal en la misma PC); si Unreal corre en otra, se escribe el nombre completo.
expr(ndi_ue, 'name', "(lambda n: n if '(' in n else '%s (%s)' % (__import__('platform').node().upper(), n))(parent.DOMO.par.Unombre.eval())")
expr(ndi_ue, 'active', 'parent.DOMO.par.Uactivo')
setpar(ndi_ue, 'bandwidth', 'high')
ndi_ue.viewer = False

aju = mk(M, fitTOP, 'ajuste', 200, 0, fit='fitbest')
setpar(aju, 'outputresolution', 'custom')
expr(aju, 'resolutionw', "parent.DOMO.op('domo').width")
expr(aju, 'resolutionh', "parent.DOMO.op('domo').height")
wire(ndi_ue, aju)

niv = mk(M, levelTOP, 'nivel', 400, 0)
expr(niv, 'brightness1', "parent.DOMO.par.Brillo * (1 - parent.DOMO.op('negro_rampa')[0])")
expr(niv, 'contrast', 'parent.DOMO.par.Contraste')
expr(niv, 'gamma1', 'parent.DOMO.par.Gamma')
wire(aju, niv)

sal = mk(M, nullTOP, 'out1', 600, 0)
wire(niv, sal)

sw_ue = mk(D, switchTOP, 'salida_domo', 800, 120)
wire(D.op('domo'), sw_ue, 0)
# Un TOP no se cablea a traves del limite de un COMP: se lee con un Select.
sel_ue = mk(D, selectTOP, 'domemaster_ue', 800, 0)
sel_ue.par.top = 'IN_UE/out1'
wire(sel_ue, sw_ue, 1)
expr(sw_ue, 'index', 'int(bool(parent().par.Uactivo))')
wire(sw_ue, D.op('out_domo'), 0)

caja(M, 'nota', 'IN_UE: el domemaster de Unreal por NDI',
     'ndi recibe el domemaster que renderiza Unreal (ADomeEmisorNDI, fuente Unreal_Abismo). ajuste lo lleva a la '
     'resolucion de domo, nivel le aplica el Master (Brillo, Contraste, Gamma, Negro) y out1 sale a DOMO/salida_domo, '
     'un Switch que elige entre domo (el domemaster que sale del lienzo equirectangular) y este. Con Uactivo '
     'encendido el domemaster de Unreal llega a out_domo sin la conversion de ida y vuelta por el equirectangular. '
     'Yaw, Pitch y Mapping no aplican: la orientacion y el FOV se ajustan en Unreal.',
     [ndi_ue, aju, niv, sal], (0.12, 0.20, 0.16))
