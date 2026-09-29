# ==========================================================================
# master.py  ·  brillo y negro global de DOMO
#
# Lo ejecuta build_domo.py justo despues de crear `equi`, con sus utilidades
# en el espacio de nombres. Deja en MASTER_SALIDA el TOP del que tiene que
# colgar `giro`: asi el master alcanza a todo lo que sale (domemaster, Spout,
# NDI, grabacion y el lienzo de Unreal) y a todas las fuentes por igual.
#
# Negro no corta: funde. `negro_rampa` es un Speed CHOP que sube o baja a
# 1/Fundido por segundo entre 0 y 1, asi el fundido dura exactamente Fundido
# segundos y se puede revertir a mitad de camino sin saltos.
# ==========================================================================

pmas = D.appendCustomPage('Master')
flotante(pmas, 'Brillo', 'Brillo general (x)', 1.0, 0, 2)
D.par.Brillo.max, D.par.Brillo.clampMax = 4.0, True
flotante(pmas, 'Contraste', 'Contraste', 1.0, 0.5, 2)
D.par.Contraste.min = 0.1
flotante(pmas, 'Gamma', 'Gamma', 1.0, 0.5, 2)
D.par.Gamma.min = 0.1
toggle(pmas, 'Negro', 'Negro (fundido)', False)
flotante(pmas, 'Fundido', 'Duracion del fundido (segundos)', 2.0, 0, 10)
toggle(pmas, 'Negrounreal', 'Mandar tambien el Negro al ejecutable de Unreal', False)
p = pmas.appendFloat('Negroactual', label='Negro ahora (0 = imagen, 1 = negro)')[0]
# en un par del propio COMP op('x') busca al lado del COMP, no adentro: me.op
p.expr = "me.op('negro_rampa')[0]"
p.readOnly = True

objetivo = mk(D, constantCHOP, 'negro_objetivo', -200, 500)
objetivo.par.name0 = 'negro'
expr(objetivo, 'value0', '(1 if parent().par.Negro else -1) / max(parent().par.Fundido, 0.01)')
rampa = mk(D, speedCHOP, 'negro_rampa', 0, 500, limittype='clamp', min=0, max=1)
wire(objetivo, rampa)

mas = mk(D, levelTOP, 'master', 0, 400)
expr(mas, 'brightness1', "parent().par.Brillo * (1 - op('negro_rampa')[0])")
expr(mas, 'contrast', 'parent().par.Contraste')
expr(mas, 'gamma1', 'parent().par.Gamma')
wire(equi, mas)
mas_sw = mk(D, switchTOP, 'master_on', 200, 400)
wire(equi, mas_sw, 0)
wire(mas, mas_sw, 1)
# neutro (todo en 1 y sin negro) el Level TOP no cocina
expr(mas_sw, 'index', "int(parent().par.Brillo != 1 or parent().par.Contraste != 1 "
                      "or parent().par.Gamma != 1 or op('negro_rampa')[0] > 0.0001)")
MASTER_SALIDA = mas_sw

caja(D, 'nota_master', 'Master: brillo y negro',
     'master (Level TOP) va entre equi y giro, asi toca todas las fuentes y todas las salidas '
     '(domemaster, Spout, NDI, grabacion y Unreal). Pagina Master: Brillo, Contraste, Gamma y Negro. '
     'Negro funde en Fundido segundos (negro_rampa, un Speed CHOP entre 0 y 1) y se puede revertir a '
     'mitad de camino. Con todo neutro master_on deja pasar equi y el Level no cocina. Negrounreal '
     'manda ademas domo.Negro al ejecutable.',
     [objetivo, rampa, mas, mas_sw], (0.10, 0.10, 0.10))
