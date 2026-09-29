# ==========================================================================
# unreal_udp.py  ·  panel de control del ejecutable de Unreal por UDP
#
# Lo ejecuta build_domo.py al final de las salidas. El ejecutable de la sala
# VR (DomoVR, ADomeMediaController) escucha en 127.0.0.1:7000 y acepta lineas
# de texto que empiezan con "domo." (una por linea, las mismas que su consola):
# domo.Cue N, domo.Siguiente, domo.Anterior, domo.Pausa, domo.Negro 0|1,
# domo.Luces 0|1|auto, domo.Plantilla id, domo.Abrir Ruta, domo.Modo
# caminar|volar|fantasma, domo.Fuente Spout|Media, domo.Param Nombre Valor...
#
# Sin Parameter Execute DAT: un parameterexecuteDAT mirando los pars de su
# propio COMP colgo antes el MCP (dependencia ciclica). Aqui un Parameter CHOP
# lee los pars U* de DOMO (los pulsos llegan como un 1 de un cuadro) y un CHOP
# Execute DAT reacciona: pulsos con onOffToOn, menus y toggles con
# onValueChange. Todo lo que manda queda en la tabla `unreal_log` y en el par
# de solo lectura Uultimo.
# ==========================================================================

try:
    _plantillas = list(D.op('IN_169/VIDEO_DOME').par.Template.menuNames)
except Exception:
    _plantillas = ['cine', 'sala_2', 'sala_4', 'sala_corona', 'anillo', 'tunel', 'cilindro']

pu = D.appendCustomPage('Unreal')
pu.appendHeader('Huconexion', label='Conexion (UDP al ejecutable)')
toggle(pu, 'Uactivo', 'Mandar por UDP', True)
texto(pu, 'Uhost', 'Equipo (IP)', '127.0.0.1')
p = pu.appendInt('Upuerto', label='Puerto')[0]
p.val = p.default = 7000
p.normMin, p.normMax = 1024, 65535
p.min, p.clampMin, p.max, p.clampMax = 1, True, 65535, True
pu.appendHeader('Hucues', label='Cues (lista del ejecutable)')
p = pu.appendInt('Ucue', label='Cue (desde 1)')[0]
p.val = p.default = 1
p.normMin, p.normMax = 1, 20
p.min, p.clampMin = 1, True
pu.appendPulse('Uircue', label='Ir a ese cue')
pu.appendPulse('Uanterior', label='Cue anterior')
pu.appendPulse('Usiguiente', label='Cue siguiente')
pu.appendPulse('Upausa', label='Pausa / play')
pu.appendHeader('Husala', label='Sala (se manda al cambiar)')
menu(pu, 'Uluces', 'Luces de la sala', ['auto', 'off', 'on'],
     ['Automaticas (se apagan con la senal)', 'Apagadas', 'Encendidas'], 0)
toggle(pu, 'Unegro', 'Negro en el ejecutable', False)
menu(pu, 'Umodo', 'Jugador', ['caminar', 'volar', 'fantasma'], ['Caminar', 'Volar', 'Fantasma'], 0)
menu(pu, 'Ufuente', 'Fuente de la cupula', ['Spout', 'Media'],
     ['Spout (lo que manda este TouchDesigner)', 'Media (la lista de videos del ejecutable)'], 0)
pu.appendHeader('Huplantilla', label='Pantallas 16:9 en Unreal')
menu(pu, 'Uplantilla', 'Plantilla', _plantillas, _plantillas, 0)
pu.appendPulse('Uenviarplantilla', label='Mandar la plantilla')
toggle(pu, 'Useguir', 'Seguir la plantilla de la pagina 16:9 (Vtemplate)', False)
pu.appendHeader('Huvideo', label='Video')
p = pu.appendFile('Uabrir', label='Video a abrir en el ejecutable')[0]
p.val = ''
pu.appendPulse('Uabrirenviar', label='Abrir ese video')
pu.appendHeader('Huparam', label='Parametro (domo.Param Nombre Valor)')
texto(pu, 'Uparam', 'Nombre', 'Resplandor')
flotante(pu, 'Uvalor', 'Valor', 0.5, -10, 10)
D.par.Uvalor.clampMin = False
pu.appendPulse('Uparamenviar', label='Mandar el parametro')
pu.appendHeader('Hulibre', label='Comando libre')
texto(pu, 'Ucomando', 'Linea (con o sin domo.)', 'domo.Estado')
pu.appendPulse('Uenviar', label='Mandar')
p = pu.appendStr('Uultimo', label='Ultimo enviado')[0]
p.readOnly = True

udp = mk(D, udpoutDAT, 'udp_unreal', 1000, -350, protocol='msging', format='perline')
expr(udp, 'address', 'parent().par.Uhost')
expr(udp, 'port', 'parent().par.Upuerto')
expr(udp, 'active', 'parent().par.Uactivo')

log = mk(D, tableDAT, 'unreal_log', 1200, -500)
log.clear()
log.appendRow(['frame', 'linea'])

upars = mk(D, parameterCHOP, 'unreal_pars', 1000, -500)
upars.par.ops = '..'
upars.par.parameters = ('Uircue Uanterior Usiguiente Upausa Uluces Unegro Umodo Ufuente '
                        'Uenviarplantilla Uabrirenviar Uparamenviar Uenviar Vtemplate Negro')
upars.par.custom = True
upars.par.builtin = False

uexec = mk(D, chopexecuteDAT, 'unreal_exec', 1200, -350)
uexec.par.chop = 'unreal_pars'
setpar(uexec, 'offtoon', True)
setpar(uexec, 'valuechange', True)
setpar(uexec, 'ontooff', False)
setpar(uexec, 'whileon', False)
uexec.text = r'''# Panel Unreal: de los pars U* de DOMO a lineas domo.* por UDP.
# Lo llaman el CHOP Execute (pulsos y cambios) y cualquiera que quiera mandar
# algo a mano: op('DOMO/unreal_exec').module.mandar('domo.Estado')

def D():
    return me.parent()


def mandar(linea):
    linea = str(linea).strip()
    if not linea:
        return False
    if not linea.lower().startswith('domo.'):
        linea = 'domo.' + linea
    d = D()
    ok = False
    if d.par.Uactivo.eval():
        try:
            d.op('udp_unreal').send(linea + '\n', terminator='')
            ok = True
        except Exception as e:
            print('[DOMO] UDP a Unreal fallo:', e)
    log = d.op('unreal_log')
    log.appendRow([absTime.frame, linea if ok else '(sin enviar) ' + linea])
    while log.numRows > 60:
        log.deleteRow(1)
    d.par.Uultimo.val = linea
    return ok


def _cue(delta):
    d = D()
    n = max(1, int(d.par.Ucue.eval()) + delta)
    d.par.Ucue.val = n


def pulso(nombre):
    d = D()
    if nombre == 'Uircue':
        mandar('domo.Cue %d' % int(d.par.Ucue.eval()))
    elif nombre == 'Uanterior':
        _cue(-1)
        mandar('domo.Anterior')
    elif nombre == 'Usiguiente':
        _cue(1)
        mandar('domo.Siguiente')
    elif nombre == 'Upausa':
        mandar('domo.Pausa')
    elif nombre == 'Uenviarplantilla':
        mandar('domo.Plantilla ' + d.par.Uplantilla.eval())
    elif nombre == 'Uabrirenviar':
        ruta = d.par.Uabrir.eval()
        if ruta:
            # el ejecutable quiere la ruta completa; con barras normales
            mandar('domo.Abrir ' + project.folder.replace('\\', '/') + '/' + ruta
                   if not (':' in ruta or ruta.startswith('/')) else 'domo.Abrir ' + ruta.replace('\\', '/'))
    elif nombre == 'Uparamenviar':
        mandar('domo.Param %s %g' % (d.par.Uparam.eval(), d.par.Uvalor.eval()))
    elif nombre == 'Uenviar':
        mandar(d.par.Ucomando.eval())


def cambio(nombre):
    d = D()
    if nombre == 'Uluces':
        mandar('domo.Luces ' + {'auto': 'auto', 'off': '0', 'on': '1'}.get(d.par.Uluces.eval(), 'auto'))
    elif nombre == 'Unegro':
        mandar('domo.Negro %d' % int(d.par.Unegro.eval()))
    elif nombre == 'Umodo':
        mandar('domo.Modo ' + d.par.Umodo.eval())
    elif nombre == 'Ufuente':
        mandar('domo.Fuente ' + d.par.Ufuente.eval())
    elif nombre == 'Vtemplate' and d.par.Useguir.eval():
        t = d.par.Vtemplate.eval()
        if t in d.par.Uplantilla.menuNames:
            d.par.Uplantilla.val = t
        mandar('domo.Plantilla ' + t)
    elif nombre == 'Negro' and d.par.Negrounreal.eval():
        mandar('domo.Negro %d' % int(d.par.Negro.eval()))


PULSOS = ('Uircue', 'Uanterior', 'Usiguiente', 'Upausa', 'Uenviarplantilla',
          'Uabrirenviar', 'Uparamenviar', 'Uenviar')


def onOffToOn(channel, sampleIndex, val, prev):
    if channel.name in PULSOS:
        pulso(channel.name)
    return


def onValueChange(channel, sampleIndex, val, prev):
    if channel.name not in PULSOS:
        cambio(channel.name)
    return


def onOnToOff(channel, sampleIndex, val, prev):
    return


def whileOn(channel, sampleIndex, val, prev):
    return


def whileOff(channel, sampleIndex, val, prev):
    return
'''

caja(D, 'nota_unreal', 'Panel Unreal: control del ejecutable por UDP',
     'Pagina Unreal de DOMO. udp_unreal (UDP Out DAT) manda lineas domo.* a Uhost:Upuerto '
     '(127.0.0.1:7000, lo que escucha DomoVR). unreal_pars (Parameter CHOP) lee los pars U*, Vtemplate y '
     'Negro, y unreal_exec (CHOP Execute) reacciona: los pulsos mandan Cue, Anterior, Siguiente, Pausa, '
     'Plantilla, Abrir, Param o el comando libre; Luces, Negro, Modo y Fuente se mandan al cambiar. Useguir '
     'manda la plantilla cada vez que cambia Vtemplate. Sin Parameter Execute a proposito (colgaba el MCP). '
     'Lo enviado queda en unreal_log y en Uultimo. A mano: op(\'unreal_exec\').module.mandar(\'domo.Estado\').',
     [udp, log, upars, uexec], (0.14, 0.18, 0.22))
