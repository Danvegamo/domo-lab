"""
Conservar la disposicion de la red al regenerar /project1/DOMO.

build_domo.py destruye y vuelve a crear DOMO, y eso antes se llevaba la disposicion que
uno hubiera armado a mano: la posicion, el tamano y el color de cada nodo, y la caja de cada
nota. Este archivo lo evita. Lo ejecuta build_domo.py en su propio espacio de nombres
(necesita BUILD_DIR, os y la API de TouchDesigner), no se corre solo.

Que se conserva
    - Posicion (nodeX, nodeY), tamano y color de todos los operadores debajo de DOMO,
      incluidas las notas (Annotate COMP): la nota queda donde y del tamano que la dejaste.
    - Los nodos que borraste a mano en la red. Si no se guardaran, el constructor los
      volveria a crear. Van a la lista `omitidos` del archivo de disposicion y el constructor
      los borra al terminar de construir.

De donde sale la disposicion
    1. La red que existe ahora en TouchDesigner (lo mas reciente: manda).
    2. Si no hay red, o le faltan nodos, 00_TouchDesigner/layout_domo.json. El constructor lo
       reescribe al terminar, asi que sigue al repositorio y sobrevive a abrir un proyecto
       nuevo o a construir en otra maquina.

Red de seguridad
    Antes de destruir la red vieja se guarda una copia en 00_TouchDesigner/respaldo/
    (DOMO_AAAAMMDD_HHMMSS.tox, las ultimas 8; la carpeta no va al repositorio). Lo que uno
    agregue a mano y el constructor no cree se pierde de la red nueva, pero queda en esa
    copia, y el constructor lo lista al terminar.

Cuando se infiere que borraste un nodo
    Solo si la red viva se construyo con la misma version del constructor que dejo el archivo
    de disposicion (el parametro Version de DOMO). Con otra version no se puede saber si a un
    nodo le falta porque lo borraste o porque el constructor aun no lo creaba. Los `omitidos`
    que ya estan escritos en el archivo se respetan siempre; para volver a tener un nodo,
    quitalo de esa lista.
"""

import json
import time

LAYOUT_ARCHIVO = os.path.join(BUILD_DIR, 'layout_domo.json')
RESPALDO_DIR = os.path.join(BUILD_DIR, 'respaldo')
RESPALDOS_MAX = 8


def _rel(o, raiz):
    return o.path[len(raiz.path) + 1:]


def _es_interno_de_nota(o):
    """Los hijos de un Annotate COMP (annotation, back...) los maneja TouchDesigner."""
    padre = o.parent()
    return padre is not None and padre.OPType == 'annotateCOMP'


def capturar_layout(raiz):
    """{ruta relativa a `raiz`: [x, y, ancho, alto, [r, g, b]]} de todo lo que hay debajo."""
    datos = {}
    if raiz is None:
        return datos
    for o in raiz.findChildren():
        if _es_interno_de_nota(o):
            continue
        try:
            c = [round(float(v), 3) for v in o.color]
            datos[_rel(o, raiz)] = [int(o.nodeX), int(o.nodeY), int(o.nodeWidth), int(o.nodeHeight), c]
        except Exception as e:
            print('[DOMO] layout: no pude leer %s: %s' % (o.path, e))
    return datos


def cargar_layout():
    """El archivo de disposicion, o uno vacio si no existe o esta danado."""
    vacio = {'version_constructor': None, 'omitidos': [], 'nodos': {}}
    try:
        with open(LAYOUT_ARCHIVO, encoding='utf-8') as f:
            d = json.load(f)
        d.setdefault('omitidos', [])
        d.setdefault('nodos', {})
        d.setdefault('version_constructor', None)
        return d
    except FileNotFoundError:
        return vacio
    except Exception as e:
        print('[DOMO] layout: %s no se pudo leer (%s); se ignora' % (LAYOUT_ARCHIVO, e))
        return vacio


def guardar_layout(nodos, omitidos, version):
    """Escribe el archivo con un nodo por linea, para que el diff de git se pueda leer."""
    lineas = ['{', '  "version_constructor": %s,' % json.dumps(version, ensure_ascii=False),
              '  "omitidos": %s,' % json.dumps(sorted(omitidos), ensure_ascii=False), '  "nodos": {']
    claves = sorted(nodos)
    for i, k in enumerate(claves):
        coma = ',' if i < len(claves) - 1 else ''
        lineas.append('    %s: %s%s' % (json.dumps(k, ensure_ascii=False), json.dumps(nodos[k]), coma))
    lineas += ['  }', '}', '']
    with open(LAYOUT_ARCHIVO, 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(lineas))


def respaldar(comp):
    """Guarda `comp` como .tox antes de destruirlo y deja solo los ultimos RESPALDOS_MAX."""
    try:
        os.makedirs(RESPALDO_DIR, exist_ok=True)
        ruta = os.path.join(RESPALDO_DIR, 'DOMO_%s.tox' % time.strftime('%Y%m%d_%H%M%S'))
        comp.save(ruta)
        viejos = sorted(f for f in os.listdir(RESPALDO_DIR) if f.startswith('DOMO_') and f.endswith('.tox'))
        for f in viejos[:-RESPALDOS_MAX]:
            os.remove(os.path.join(RESPALDO_DIR, f))
        print('[DOMO] respaldo de la red anterior: %s' % ruta)
        return ruta
    except Exception as e:
        print('[DOMO] AVISO: no se pudo respaldar la red anterior (%s)' % e)
        return None


def preparar_regeneracion(viejo, version_nueva):
    """Se llama antes de destruir `viejo` (o con None si no hay red). Devuelve el estado que
    `terminar_regeneracion` usa al final: la disposicion a aplicar, los omitidos y lo que habia."""
    # Regenerar con el NDI de IN_UE recibiendo cuelga el servidor MCP de TouchDesigner (29 sep 2026, causa probable, no aislada: al guardar
    # la copia de respaldo con un NDI In activo, TouchDesigner sigue vivo pero el exec server no vuelve a responder).
    # Se aborta antes de tocar nada.
    if viejo is not None:
        activo = getattr(viejo.par, 'Uactivo', None)
        if activo is not None and activo.eval():
            raise RuntimeError('[DOMO] DOMO.Uactivo (pagina Unreal) esta encendido: apagalo y vuelve a regenerar. '
                               'No se toco la red.')
    previo = cargar_layout()
    vivo = capturar_layout(viejo)
    omitidos = set(previo['omitidos'])
    respaldo = None
    if viejo is not None:
        version_viva = None
        try:
            version_viva = viejo.par.Version.eval()
        except Exception:
            pass
        if version_viva is not None and version_viva == previo['version_constructor']:
            for k in previo['nodos']:
                if k not in vivo and not any(k.startswith(o + '/') for o in omitidos):
                    omitidos.add(k)
                    print('[DOMO] layout: %s ya no esta en la red; se respeta y no se vuelve a crear' % k)
        respaldo = respaldar(viejo)
    nodos = dict(previo['nodos'])
    nodos.update(vivo)  # la red viva manda sobre el archivo
    return {'nodos': nodos, 'omitidos': omitidos, 'vivo': vivo, 'respaldo': respaldo}


def terminar_regeneracion(raiz, estado, version):
    """Se llama al final de la construccion: borra lo omitido, devuelve cada nodo a su sitio,
    avisa de lo que no se pudo conservar y reescribe el archivo de disposicion."""
    borrados = 0
    for rel in sorted(estado['omitidos'], key=len):
        o = raiz.op(rel)
        if o is not None:
            try:
                o.destroy()
                borrados += 1
            except Exception as e:
                print('[DOMO] layout: no pude borrar %s: %s' % (rel, e))
    puestos = 0
    for rel, v in estado['nodos'].items():
        o = raiz.op(rel)
        if o is None or _es_interno_de_nota(o):
            continue
        try:
            o.nodeX, o.nodeY = v[0], v[1]
            o.nodeWidth, o.nodeHeight = v[2], v[3]
            if len(v) > 4 and v[4]:
                o.color = tuple(v[4])
            puestos += 1
        except Exception as e:
            print('[DOMO] layout: no pude colocar %s: %s' % (rel, e))
    ahora = capturar_layout(raiz)
    nuevos = [k for k in ahora if k not in estado['nodos']]
    perdidos = [k for k in estado['vivo'] if k not in ahora]
    print('[DOMO] layout: %d nodos en su sitio, %d omitidos borrados, %d nodos nuevos con la posicion del constructor'
          % (puestos, borrados, len(nuevos)))
    if perdidos:
        print('[DOMO] AVISO: estos %d nodos estaban en la red anterior y el constructor ya no los crea '
              '(si los agregaste a mano, estan en el respaldo %s):' % (len(perdidos), estado['respaldo'] or 'sin respaldo'))
        for k in perdidos[:40]:
            print('         ' + k)
    guardar_layout(ahora, estado['omitidos'], version)
