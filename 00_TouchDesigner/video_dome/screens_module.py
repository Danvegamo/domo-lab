# ==========================================================================
# screens_module.py  ·  la tabla de pantallas de VIDEO_DOME
#
# Este archivo se copia adentro del .toe como el Text DAT
# /project1/VIDEO_DOME/screens_mod y lo usan los callbacks. Se mantiene aca
# afuera para poder editarlo con un editor de verdad y volver a correr el
# build.
#
# Una fila de la tabla `screens` = una pantalla dentro de la cupula. La tabla
# es la unica fuente de verdad: los parametros de la pagina "Pantalla" leen y
# escriben la fila seleccionada, los templates guardan la tabla entera, y el
# shader la lee convertida a CHOP. Por eso se pueden agregar, mover y borrar
# pantallas sin tocar la red.
#
# Una fila puede repetirse en anillo (columnas rep/repspan/repmir/repofs). Eso
# es lo que permite pensar el domo como una sala con varios puntos de vista en
# vez de una sola persona mirando al frente: con rep=4 hay una pantalla
# enfrente de cada cuarto de la sala y todas se mueven juntas.
#
# Y la costura entre esas copias es `blend`: los grados que se encima una copia
# con la siguiente. El shader reparte el pixel del solape entre las dos y el
# anillo deja de leerse como pantallas pegadas. Con `edges=1` el degradado va
# a los cuatro lados o solo a los costados. Con `edges=1` el anillo queda con
# el borde de arriba neto y se lee como un objeto; con `edges=0` se funde hacia
# el cenit y hacia el horizonte, que es lo que hace falta cuando hay otra
# pantalla encima. La costura de los costados sale pareja en los dos casos.
# ==========================================================================

# El ORDEN de las columnas importa: el shader recibe seis arrays de vec4 y
# cada uno toma cuatro columnas seguidas, en este orden.
COLS = ['yaw', 'pitch', 'roll', 'mode',
        'hfov', 'vfov', 'mirror', 'opacity',
        'cropx', 'cropy', 'cropw', 'croph',
        'on', 'feather', 'tile', 'blend',
        'rep', 'repspan', 'repmir', 'repofs',
        'travel', 'spin', 'edges', 'spare',
        'name']

# columnas que viajan a los arrays del shader (todas menos 'name')
NUMCOLS = COLS[:-1]

MODES = {0: 'plana', 1: 'curva', 2: 'banda', 3: 'tunel', 4: 'cilindro'}
MIRRORS = {0: 'no', 1: 'horizontal', 2: 'vertical', 3: 'ambos'}
# que bordes se degradan. En un anillo cosido interesa 'lados': si el borde de
# arriba tambien se degrada, la corona se lee como una fila de manchas.
EDGES = {0: 'todos', 1: 'lados', 2: 'arriba y abajo'}

# valores de una pantalla nueva
DEFAULT = dict(yaw=0.0, pitch=45.0, roll=0.0, mode=0,
               hfov=70.0, vfov=39.0, mirror=0, opacity=1.0,
               cropx=0.0, cropy=0.0, cropw=1.0, croph=1.0,
               on=1, feather=0.04, tile=1.0, blend=0.0,
               rep=1, repspan=360.0, repmir=0, repofs=0.0,
               travel=0.0, spin=0.0, edges=0, spare=0.0,
               name='pantalla')


def screen(**kw):
    d = dict(DEFAULT)
    d.update(kw)
    return d


def _num(v):
    """Todo lo que no sea 'name' entra a la tabla como numero.

    Sin esto un par Toggle escribia el texto 'True' en la celda, el DAT to CHOP
    no lo podia convertir y lo dejaba en 0: la pantalla se apagaba sola apenas
    se tocaba cualquier parametro.
    """
    if isinstance(v, bool):
        return int(v)
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 0.0
    return int(f) if f == int(f) else f


# --------------------------------------------------------------------------
# Templates: cada uno es una lista de pantallas.
#
# El domo es tipo planetario: esta elevado, se mira hacia arriba y el publico
# esta repartido por toda la sala. Dos consecuencias:
#
#  - las elevaciones utiles arrancan mas alto que en un domo de horizonte, por
#    eso casi todo vive entre 30 y 60 grados;
#  - un montaje de una sola pantalla al frente solo funciona para quien esta
#    mirando hacia ahi. Los templates "sala_*" reparten la imagen en anillo
#    para que cada sector del publico tenga algo enfrente.
# --------------------------------------------------------------------------
TEMPLATES = {
    # ---- un punto de vista (ensayo, o publico mirando al frente) ----
    'cine': [
        screen(name='cine', yaw=0, pitch=45, hfov=70, vfov=39, mode=0),
    ],
    'grande': [
        screen(name='grande', yaw=0, pitch=48, hfov=95, vfov=53, mode=0),
    ],
    'bajo': [
        screen(name='bajo', yaw=0, pitch=28, hfov=80, vfov=45, mode=0),
    ],
    'cenital': [
        screen(name='cenital', yaw=0, pitch=70, hfov=90, vfov=51, mode=0),
    ],

    # ---- sala llena: la misma imagen enfrente de cada sector ----
    'sala_2': [
        # dos pantallas grandes, una frente a cada mitad de la sala
        screen(name='dos_grandes', yaw=0, pitch=44, hfov=170, vfov=59, mode=1,
               rep=2, repspan=360, blend=12, edges=1),
    ],
    'sala_4': [
        # 90 grados de paso: con hfov 82 + blend 8 el anillo cierra sin huecos
        screen(name='cuatro', yaw=0, pitch=42, hfov=82, vfov=46, mode=0,
               rep=4, repspan=360, blend=8, edges=1),
    ],
    'sala_6': [
        screen(name='seis', yaw=0, pitch=40, hfov=54, vfov=30, mode=0,
               rep=6, repspan=360, blend=6, edges=1),
    ],
    'sala_4_espejo': [
        # espejadas de a una: los bordes de dos pantallas vecinas se encuentran
        # con la misma parte del cuadro y el anillo se lee como un solo objeto
        screen(name='cuatro_espejo', yaw=0, pitch=42, hfov=82, vfov=46, mode=0,
               rep=4, repspan=360, repmir=1, blend=8, edges=1),
    ],
    'sala_6_mosaico': [
        # cada sector ve un sexto distinto del cuadro: la sala entera arma la
        # pelicula completa y nadie ve lo mismo que su vecino. El recorte de
        # cada copia es un poco mas ancho que 1/6 para que el solape muestre la
        # MISMA parte de la imagen desde los dos lados y la costura desaparezca.
        screen(name='mosaico', yaw=0, pitch=40, hfov=54, vfov=54, mode=0,
               rep=6, repspan=360, repofs=1.0 / 6.0, cropx=-0.01,
               cropw=1.0 / 6.0 + 0.02, blend=6, edges=1),
    ],
    'sala_corona': [
        # EL QUE MEJOR FUNCIONA. Anillo bajo cosido + una cenital encima.
        #
        # Las tres cosas que lo sacan de "collage": el solape reparte el pixel
        # entre copias vecinas; el degradado va a los CUATRO lados (edges=0),
        # asi el anillo se funde con el cenit en vez de cortar un hexagono; y
        # la cenital pisa por arriba con un borde larguisimo.
        #
        # edges=1 (solo los costados) es para cuando el anillo tiene que
        # leerse como un objeto con borde neto contra el negro, no aca.
        screen(name='corona', yaw=0, pitch=32, hfov=66, vfov=42, mode=0,
               rep=6, repspan=360, repmir=1, blend=8, edges=0),
        screen(name='cenital', yaw=0, pitch=70, hfov=96, vfov=96, mode=1,
               opacity=0.85, feather=0.30),
    ],
    'sala_corona_panorama': [
        # la corona, pero cada sector con su pedazo del cuadro: la sala arma un
        # panoramico continuo de 360 y las costuras caen donde la imagen sigue
        screen(name='corona_pan', yaw=0, pitch=32, hfov=66, vfov=42, mode=0,
               rep=6, repspan=360, repofs=1.0 / 6.0, cropx=-0.012,
               cropw=1.0 / 6.0 + 0.024, blend=8, edges=0),
        screen(name='cenital', yaw=0, pitch=70, hfov=96, vfov=96, mode=1,
               opacity=0.75, feather=0.30),
    ],

    # ---- montajes de composicion ----
    'tres': [
        screen(name='izq', yaw=-38, pitch=45, hfov=34, vfov=19, mode=0, mirror=1),
        screen(name='centro', yaw=0, pitch=45, hfov=34, vfov=19, mode=0),
        screen(name='der', yaw=38, pitch=45, hfov=34, vfov=19, mode=0, mirror=1),
    ],
    'espejo': [
        screen(name='a', yaw=-42, pitch=45, hfov=60, vfov=34, mode=0),
        screen(name='b_espejo', yaw=42, pitch=45, hfov=60, vfov=34, mode=0, mirror=1),
    ],
    'anillo': [
        # una banda que da la vuelta entera con el video repetido 3 veces: el
        # modo 'banda' es el unico que puede cerrar los 360 sin deformarse
        screen(name='anillo', yaw=0, pitch=40, hfov=360, vfov=34, mode=2, tile=3),
    ],
    'anillo_doble': [
        screen(name='anillo_bajo', yaw=0, pitch=28, hfov=360, vfov=24, mode=2, tile=4),
        screen(name='anillo_alto', yaw=180, pitch=58, hfov=360, vfov=22, mode=2,
               tile=2, mirror=2, opacity=0.85),
    ],
    'tunel': [
        # centrada en el cenit: el video se enrosca y las repeticiones hacen
        # los anillos que se alejan
        screen(name='tunel', yaw=0, pitch=90, hfov=170, vfov=170, mode=3, tile=4),
    ],
    'tunel_con_sala': [
        screen(name='tunel', yaw=0, pitch=90, hfov=170, vfov=170, mode=3,
               tile=5, opacity=0.6),
        screen(name='sala', yaw=0, pitch=38, hfov=70, vfov=39, mode=0,
               rep=4, repspan=360, feather=0.06),
    ],
    'cilindro': [
        # una pared cilindrica alrededor del publico. La altura del impacto es
        # tan(elevacion), asi que la imagen se comprime sola hacia el cenit y
        # eso es lo que da la fuga. Con `travel` la pared se lleva hacia arriba
        # y el domo se convierte en un ascensor.
        screen(name='cilindro', yaw=0, pitch=8, hfov=360, vfov=60, mode=4,
               tile=3, travel=1.0, edges=2, feather=0.10),
    ],
    'cilindro_doble': [
        screen(name='pared', yaw=0, pitch=6, hfov=360, vfov=50, mode=4,
               tile=3, travel=1.0, edges=2, feather=0.08),
        screen(name='pared_alta', yaw=180, pitch=40, hfov=360, vfov=40, mode=4,
               tile=2, travel=-0.6, mirror=2, opacity=0.7, edges=2, feather=0.12),
    ],
    'cilindro_con_sala': [
        # el cilindro de fondo llevandose, y la sala cosida encima
        screen(name='cilindro', yaw=0, pitch=8, hfov=360, vfov=70, mode=4,
               tile=3, travel=1.0, opacity=0.55, edges=2, feather=0.10),
        screen(name='sala', yaw=0, pitch=38, hfov=70, vfov=39, mode=0,
               rep=4, repspan=360, blend=8, edges=1),
    ],
    'fragmentos': [
        # la misma pelicula partida en tres: cada ventana muestra un tercio
        # distinto del cuadro, asi el domo arma un panoramico falso
        screen(name='frag_izq', yaw=-46, pitch=45, hfov=42, vfov=42, mode=0,
               cropx=0.0, cropw=0.34),
        screen(name='frag_centro', yaw=0, pitch=45, hfov=42, vfov=42, mode=0,
               cropx=0.33, cropw=0.34),
        screen(name='frag_der', yaw=46, pitch=45, hfov=42, vfov=42, mode=0,
               cropx=0.66, cropw=0.34),
    ],
}


def rows_from_template(nombre):
    return [dict(d) for d in TEMPLATES.get(nombre, TEMPLATES['cine'])]


def write_table(dat, filas):
    """Vuelca una lista de pantallas a la tabla: todo numerico menos el nombre."""
    dat.clear()
    dat.appendRow(COLS)
    for f in filas:
        fila = []
        for c in COLS:
            v = f.get(c, DEFAULT[c])
            fila.append(str(v) if c == 'name' else _num(v))
        dat.appendRow(fila)


def read_table(dat):
    """Lee la tabla a una lista de diccionarios.

    Tolera tablas del formato viejo (sin las columnas rep*): lo que falte sale
    del DEFAULT, asi que un .toe o una version guardada antes siguen abriendo.
    """
    filas = []
    if dat.numRows < 2:
        return filas
    cabecera = [c.val for c in dat.row(0)]
    for i in range(1, dat.numRows):
        fila = dict(DEFAULT)
        for j, col in enumerate(cabecera):
            if col not in DEFAULT:
                continue
            v = dat[i, j].val
            texto = str(v).strip().lower()
            if col == 'name':
                fila[col] = v
            elif texto in ('true', 'on'):
                fila[col] = 1
            elif texto in ('false', 'off', ''):
                fila[col] = 0
            else:
                try:
                    fila[col] = float(v)
                except ValueError:
                    fila[col] = DEFAULT.get(col, 0.0)
        filas.append(fila)
    return filas
