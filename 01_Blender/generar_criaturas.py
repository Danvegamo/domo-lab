"""
Genera por completo, de forma idempotente y en headless, las criaturas y los
objetos de la escena submarina del domo (Unreal Engine 5.8): un fondo marino
profundo con particulas y glow donde animales que cruzan la Colombia actual con
el Cretacico del mar epicontinental de Villa de Leyva (Boyaca, hace unos 130
millones de anios) conviven con basura plastica flotando (dialogo del
Antropoceno).

Se ejecuta asi (sin abrir la interfaz):
    blender.exe -b -P 01_Blender\\generar_criaturas.py
    blender.exe -b -P 01_Blender\\generar_criaturas.py -- --solo kronos_jaguar,roca_lecho
    blender.exe -b -P 01_Blender\\generar_criaturas.py -- --vistas C:\\ruta\\carpeta

Escribe:
    02_Export/criaturas/<id>.fbx              un FBX por objeto (15 objetos)
    02_Export/criaturas/manifiesto_criaturas.json   ids, triangulos y cajas medidas
    05_Preview/pruebas/criaturas_hoja.jpg     hoja de contacto (Eevee, fondo oscuro)
    05_Preview/pruebas/criaturas_hoja_mov.jpg la misma hoja con el peso "Mov" como
                                              mapa de calor (para revisar el alfa)

Todo es procedural: sin descargas y sin texturas externas. Cada corrida borra la
escena entera (read_factory_settings) y reescribe los archivos, asi que correrlo
dos veces da el mismo resultado (el azar usa semillas fijas).

CONVENCIONES DE MALLA (ver 04_Docs/08_Criaturas_abismo.md):

- Nariz o frente hacia +X, Z arriba, el largo del objeto a lo largo de X. Las
  criaturas y los objetos flotantes tienen el origen en el centro del cuerpo
  (el torso en los animales de cuello o cola largos). Transformaciones aplicadas
  (la malla se construye directamente en coordenadas de objeto, con rotacion
  cero y escala uno).
- Unidades: se construye en metros. El FBX sale con las coordenadas ya en
  centimetros (geometria multiplicada por 100 y unidad de escena "cm" en la
  cabecera del archivo), de modo que Unreal ve el tamanio correcto con
  "convert_scene_unit" activado o desactivado. Ver exportar_fbx().
- Suavizado normal (todas las caras suaves), una sola capa UV ("UVMap", canal 0).
  Cada parte del objeto (cuerpo, cabeza, aletas, dientes...) es una isla en su
  propia celda de una cuadricula 0-1, sin solapes entre celdas; las piezas
  repetidas identicas (dientes, ojos, boyas) comparten celda a proposito.
- UNA sola capa de color por vertice, "Col": RGB = patron y colores base, A =
  peso de movimiento ("Mov"): 0 en el cuerpo rigido y sube hasta 1 hacia las
  puntas moviles (cola, aletas, tentaculos, alas, tira de alga) para que un
  shader mueva los vertices sin esqueleto. Unreal solo importa una capa, por
  eso el peso viaja en el canal alfa de la misma. Se exporta en modo LINEAR: los
  numeros que se escriben aqui son los numeros del archivo.
"""

import bpy
import bmesh
import json
import math
import os
import random
import sys
from mathutils import Matrix, Vector

# ---------------------------------------------------------------------------
# CONSTANTES EDITABLES
# ---------------------------------------------------------------------------

try:
    CARPETA_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
except NameError:
    CARPETA_BASE = r"C:\Users\Danvegamo\Documents\Domo_VR_Unreal"

CARPETA_FBX = os.path.join(CARPETA_BASE, "02_Export", "criaturas")
RUTA_HOJA = os.path.join(CARPETA_BASE, "05_Preview", "pruebas", "criaturas_hoja.jpg")
RUTA_HOJA_MOV = os.path.join(CARPETA_BASE, "05_Preview", "pruebas", "criaturas_hoja_mov.jpg")
RUTA_MANIFIESTO = os.path.join(CARPETA_FBX, "manifiesto_criaturas.json")

# Topes de triangulos por familia (encargo del 29 sep 2026).
TOPE_TRIS = {"criatura": 12000, "belemnita": 400, "decorado": 3000, "resto": 1500}

X = Vector((1.0, 0.0, 0.0))
Y = Vector((0.0, 1.0, 0.0))
Z = Vector((0.0, 0.0, 1.0))


# ---------------------------------------------------------------------------
# UTILIDADES MATEMATICAS: interpolacion, ruido y celdas de Voronoi
# ---------------------------------------------------------------------------

def sujetar(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def lerp(a, b, t):
    return a + (b - a) * t


def suave(a, b, x):
    """Escalon suave: 0 hasta a, 1 desde b (a puede ser mayor que b)."""
    if a == b:
        return 0.0 if x < a else 1.0
    t = sujetar((x - a) / (b - a))
    return t * t * (3.0 - 2.0 * t)


def rampa(x, a, b, exponente=1.5):
    """0 en x = a, 1 en x = b (lineal y luego elevado): el peso de movimiento de
    una cola crece despacio cerca del cuerpo y rapido hacia la punta."""
    return sujetar((x - a) / (b - a)) ** exponente


def mezcla(c1, c2, t):
    t = sujetar(t)
    return (lerp(c1[0], c2[0], t), lerp(c1[1], c2[1], t), lerp(c1[2], c2[2], t))


def perfil(puntos, negativos=False):
    """Curva suave (Hermite con tangentes por diferencias finitas) que pasa por
    los puntos (x, valor). Se usa para los radios de los cuerpos: se declaran
    unos pocos valores clave y el resto sale redondeado. Nunca devuelve
    valores negativos salvo con negativos=True (curvas de posicion, como la
    altura del eje de una mandibula)."""
    puntos = sorted(puntos)
    piso = -1e9 if negativos else 0.0
    xs = [p[0] for p in puntos]
    ys = [p[1] for p in puntos]
    n = len(puntos)
    ms = []
    for k in range(n):
        if k == 0:
            ms.append((ys[1] - ys[0]) / (xs[1] - xs[0]))
        elif k == n - 1:
            ms.append((ys[-1] - ys[-2]) / (xs[-1] - xs[-2]))
        else:
            ms.append((ys[k + 1] - ys[k - 1]) / (xs[k + 1] - xs[k - 1]))

    def f(x):
        if x <= xs[0]:
            return max(piso, ys[0])
        if x >= xs[-1]:
            return max(piso, ys[-1])
        k = 0
        while xs[k + 1] < x:
            k += 1
        h = xs[k + 1] - xs[k]
        t = (x - xs[k]) / h
        t2, t3 = t * t, t * t * t
        v = ((2 * t3 - 3 * t2 + 1) * ys[k] + (t3 - 2 * t2 + t) * h * ms[k]
             + (-2 * t3 + 3 * t2) * ys[k + 1] + (t3 - t2) * h * ms[k + 1])
        return max(piso, v)
    return f


def _hash(i, j, k, s):
    h = (i * 374761393 + j * 668265263 + k * 2147483647 + s * 1274126177) & 0xFFFFFFFF
    h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
    h ^= h >> 16
    return (h & 0xFFFF) / 65535.0


def ruido3(p, semilla=0):
    """Ruido de valor 3D suave en [0, 1] (celdas de lado 1)."""
    x, y, z = p[0], p[1], p[2]
    xi, yi, zi = math.floor(x), math.floor(y), math.floor(z)
    fx, fy, fz = x - xi, y - yi, z - zi
    fx, fy, fz = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy), fz * fz * (3 - 2 * fz)
    def h(a, b, c):
        return _hash(xi + a, yi + b, zi + c, semilla)
    c00 = lerp(h(0, 0, 0), h(1, 0, 0), fx)
    c10 = lerp(h(0, 1, 0), h(1, 1, 0), fx)
    c01 = lerp(h(0, 0, 1), h(1, 0, 1), fx)
    c11 = lerp(h(0, 1, 1), h(1, 1, 1), fx)
    return lerp(lerp(c00, c10, fy), lerp(c01, c11, fy), fz)


def voronoi3(p, semilla=0):
    """(d1, d2) distancias a los dos centros mas cercanos de una rejilla 3D de
    puntos con jitter (celdas de lado 1). d1 da manchas y anillos; d2 - d1 da
    las lineas de union (escudos de tortuga)."""
    xi, yi, zi = math.floor(p[0]), math.floor(p[1]), math.floor(p[2])
    dist = []
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for dz in (-1, 0, 1):
                i, j, k = xi + dx, yi + dy, zi + dz
                cx = i + _hash(i, j, k, semilla)
                cy = j + _hash(i, j, k, semilla + 17)
                cz = k + _hash(i, j, k, semilla + 43)
                dist.append(math.sqrt((p[0] - cx) ** 2 + (p[1] - cy) ** 2 + (p[2] - cz) ** 2))
    dist.sort()
    return dist[0], dist[1]


# ---------------------------------------------------------------------------
# MALLA PROPIA: vertices con color y peso de movimiento, caras con UV por esquina
# ---------------------------------------------------------------------------

class Malla:
    """Acumula vertices (posicion, RGB, peso Mov) y caras (indices + UV por
    esquina + grupo). Los grupos son las islas UV: cada uno cae en su propia
    celda de la cuadricula del atlas. Los lofts y revoluciones de abajo son los
    unicos que crean geometria; cada uno es un solido cerrado."""

    def __init__(self):
        self.co = []
        self.rgb = []
        self.mov = []
        self.vg = []
        self.caras = []
        self.grupos = []
        self.g = 0

    def grupo(self, nombre):
        if nombre not in self.grupos:
            self.grupos.append(nombre)
        self.g = self.grupos.index(nombre)
        return self.g

    def vert(self, co, rgb, mov):
        self.co.append(Vector(co))
        self.rgb.append(tuple(rgb))
        self.mov.append(float(sujetar(mov)))
        self.vg.append(self.g)
        return len(self.co) - 1

    def cara(self, idx, uv):
        if len(set(idx)) < 3:
            return
        self.caras.append((tuple(idx), tuple(uv), self.g))

    def aplicar(self, fn, grupo=None):
        """Mueve cada vertice (del grupo dado, o todos) con fn(Vector) -> Vector."""
        for i, c in enumerate(self.co):
            if grupo is None or self.vg[i] == grupo:
                self.co[i] = Vector(fn(c))

    def limites(self):
        xs = [c.x for c in self.co]
        ys = [c.y for c in self.co]
        zs = [c.z for c in self.co]
        return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))

    def ajustar(self, longitud, eje=0, criterio="eje"):
        """Escala uniforme respecto del origen para que la caja mida `longitud`
        en el eje dado (0 = X) o, con criterio "max", en su lado mayor."""
        lo, hi = self.limites()
        medida = max(hi[i] - lo[i] for i in range(3)) if criterio == "max" else hi[eje] - lo[eje]
        f = longitud / medida
        for i, c in enumerate(self.co):
            self.co[i] = c * f

    def centrar(self, ejes=(0, 1, 2)):
        lo, hi = self.limites()
        d = Vector([-(lo[i] + hi[i]) / 2.0 if i in ejes else 0.0 for i in range(3)])
        for i, c in enumerate(self.co):
            self.co[i] = c + d

    def topologia(self):
        """(aristas abiertas, aristas repetidas): en un conjunto de solidos
        cerrados y bien orientados las dos son 0."""
        dirigidas = {}
        for idx, _, _ in self.caras:
            for k in range(len(idx)):
                e = (idx[k], idx[(k + 1) % len(idx)])
                dirigidas[e] = dirigidas.get(e, 0) + 1
        repetidas = sum(1 for v in dirigidas.values() if v > 1)
        abiertas = sum(1 for (a, b) in dirigidas if (b, a) not in dirigidas)
        return abiertas, repetidas


def _orientar(m, i0):
    """Voltea las caras creadas desde i0 si el volumen con signo sale negativo,
    para que las normales apunten hacia afuera."""
    vol = 0.0
    for idx, _, _ in m.caras[i0:]:
        p0 = m.co[idx[0]]
        for k in range(1, len(idx) - 1):
            vol += p0.dot(m.co[idx[k]].cross(m.co[idx[k + 1]]))
    if vol < 0:
        for k in range(i0, len(m.caras)):
            idx, uv, g = m.caras[k]
            m.caras[k] = (idx[::-1], uv[::-1], g)


def _color_gris(s, a, p):
    return (0.5, 0.5, 0.5)


def _mov_cero(s, a, p):
    return 0.0


def _anillos(m, est, n, color, mov, forma, bucle, cierre, fase, uv_periodico=True):
    """Nucleo de lofts y revoluciones. `est` es una lista de estaciones
    (C, N, B, radio_n, radio_b, s): un anillo elipse de n vertices en el plano
    (N, B) alrededor de C. Las estaciones con radio 0 (solo en los extremos)
    se vuelven un unico vertice (polo). Con bucle=True el ultimo anillo se une
    al primero (toro)."""
    K = len(est)
    anillos = []
    for (C, N, B, rn_, rb_, s) in est:
        if (rn_ < 1e-5 or rb_ < 1e-5) and not bucle:
            anillos.append(m.vert(C, color(s, 0.0, C), mov(s, 0.0, C)))
            continue
        anillo = []
        for i in range(n):
            ang = fase + 2.0 * math.pi * i / n
            ca, sa = math.cos(ang), math.sin(ang)
            pb = C + N * (ca * rn_) + B * (sa * rb_)
            fn = fb = 1.0
            if forma is not None:
                f = forma(s, ang, pb)
                fn, fb = f if isinstance(f, tuple) else (f, f)
            p = C + N * (ca * rn_ * fn) + B * (sa * rb_ * fb)
            anillo.append(m.vert(p, color(s, ang, p), mov(s, ang, p)))
        anillos.append(anillo)

    nseg = K if bucle else K - 1
    for j in range(nseg):
        j2 = (j + 1) % K
        A, Bq = anillos[j], anillos[j2]
        s0 = est[j][5]
        s1 = 1.0 if (bucle and uv_periodico and j2 == 0) else est[j2][5]
        for i in range(n):
            i2 = (i + 1) % n
            u0, u1 = i / n, (i + 1) / n
            if isinstance(A, int) and isinstance(Bq, int):
                continue
            if isinstance(A, int):
                m.cara((A, Bq[i2], Bq[i]), ((0.5 * (u0 + u1), s0), (u1, s1), (u0, s1)))
            elif isinstance(Bq, int):
                m.cara((A[i], A[i2], Bq), ((u0, s0), (u1, s0), (0.5 * (u0 + u1), s1)))
            else:
                m.cara((A[i], A[i2], Bq[i2], Bq[i]), ((u0, s0), (u1, s0), (u1, s1), (u0, s1)))

    if cierre and not bucle:
        # Tapas planas; su UV colapsa sobre la fila del extremo (son casi
        # siempre invisibles: quedan dentro de otra pieza).
        if isinstance(anillos[0], list):
            s0 = est[0][5]
            m.cara(tuple(reversed(anillos[0])), tuple((i / n, s0) for i in reversed(range(n))))
        if isinstance(anillos[-1], list):
            s1 = est[-1][5]
            m.cara(tuple(anillos[-1]), tuple((i / n, s1) for i in range(n)))


def loft(m, centro, rn, rb, n=12, M=24, color=None, mov=None, ref=None, forma=None,
         k_dist=0.5, cierre=True, bucle=False, fase=0.0, roll=None):
    """Solido por barrido de una elipse a lo largo de una curva.
    centro(s) -> Vector para s en [0, 1]; rn(s) y rb(s) son los semiejes de la
    elipse en las direcciones N y B del marco local (T = tangente,
    N = ref x T, B = T x N; con ref = Z y T = +X: N = +Y y B = +Z). M cortes a
    lo largo, n vertices alrededor. Un semieje 0 en un extremo cierra la punta
    en un solo vertice. k_dist mezcla reparto uniforme (0) con reparto
    coseno (1, mas cortes en las puntas). forma(s, ang, p) puede devolver un
    factor (o un par para N y B) que deforma la seccion (crestas, arrugas)."""
    ref = Z if ref is None else ref
    color = color or _color_gris
    mov = mov or _mov_cero
    i0 = len(m.caras)
    if bucle:
        ss = [j / M for j in range(M)]
    else:
        ss = []
        for j in range(M + 1):
            u = j / M
            ss.append(lerp(u, 0.5 - 0.5 * math.cos(math.pi * u), k_dist))
    eps = 1e-3
    est = []
    for s in ss:
        C = centro(s)
        if bucle:
            T = centro(s + eps) - centro(s - eps)
        else:
            T = centro(min(1.0, s + eps)) - centro(max(0.0, s - eps))
        if T.length < 1e-12:
            T = X.copy()
        T.normalize()
        N = ref.cross(T)
        if N.length < 1e-4:
            N = X.cross(T) if abs(T.dot(X)) < 0.9 else Y.cross(T)
        N.normalize()
        B = T.cross(N)
        if roll is not None:
            R = Matrix.Rotation(roll(s), 3, T)
            N, B = R @ N, R @ B
        est.append((C, N, B, rn(s), rb(s), s))
    _anillos(m, est, n, color, mov, forma, bucle, cierre, fase)
    _orientar(m, i0)


def revolucion(m, puntos, n=20, color=None, mov=None, bucle=False):
    """Superficie de revolucion alrededor del eje X. puntos = [(x, radio, v)]
    en el orden en que se recorre el perfil; con bucle=True el perfil es un
    lazo cerrado (una funda o cascara delgada). Radio 0 en el primer o ultimo
    punto cierra en un polo. v es la coordenada V del UV."""
    color = color or _color_gris
    mov = mov or _mov_cero
    i0 = len(m.caras)
    est = [(Vector((x, 0.0, 0.0)), Y, Z, r, r, v) for (x, r, v) in puntos]
    _anillos(m, est, n, color, mov, None, bucle, True, 0.0, uv_periodico=False)
    _orientar(m, i0)


def elipsoide(m, c, a, b, cz, n=10, mm=8, color=None, mov=None):
    """Elipsoide de semiejes (a en X, b en Y, cz en Z) centrado en c."""
    c = Vector(c)
    loft(m, lambda s: c + X * (-a * math.cos(math.pi * s)),
         lambda s: b * math.sin(math.pi * s), lambda s: cz * math.sin(math.pi * s),
         n=n, M=mm, color=color, mov=mov, k_dist=0.0)


def cono(m, base, punta, radio, n=5, color=None, mov=None, ref=None):
    """Cono (diente, bigote, tentaculo corto): 1 anillo en la base y la punta."""
    base, punta = Vector(base), Vector(punta)
    loft(m, lambda s: base.lerp(punta, s), lambda s: radio * (1.0 - s), lambda s: radio * (1.0 - s),
         n=n, M=1, color=color, mov=mov, ref=ref, k_dist=0.0)


def tubo(m, puntos_ctrl, r0, r1, n=5, M=8, color=None, mov=None, ref=None, k_dist=0.0):
    """Tubo que sigue una curva de Bezier (2, 3 o 4 puntos de control) con radio
    de r0 a r1."""
    P = [Vector(p) for p in puntos_ctrl]

    def centro(s):
        if len(P) == 2:
            return P[0].lerp(P[1], s)
        if len(P) == 3:
            return P[0].lerp(P[1], s).lerp(P[1].lerp(P[2], s), s)
        a = P[0].lerp(P[1], s).lerp(P[1].lerp(P[2], s), s)
        b = P[1].lerp(P[2], s).lerp(P[2].lerp(P[3], s), s)
        return a.lerp(b, s)
    loft(m, centro, lambda s: lerp(r0, r1, s), lambda s: lerp(r0, r1, s), n=n, M=M,
         color=color, mov=mov, ref=ref, k_dist=k_dist)
    return centro


def pala(m, p0, p1, cuerda, grosor, curva=(0.0, 0.0, 0.0), n=8, M=12, color=None, mov=None, ref=None):
    """Aleta o remo plano: barrido de una lente de p0 a p1 con desvio `curva`
    (barrido hacia atras, caida) que crece con el cuadrado de la distancia.
    La cuerda va en la direccion N del marco: con T casi +-Y y ref = Z, la
    cuerda queda a lo largo de X y el grosor en Z."""
    p0, p1, curva = Vector(p0), Vector(p1), Vector(curva)
    prof = perfil([(0.0, 0.7), (0.25, 1.0), (0.6, 0.8), (0.9, 0.35), (1.0, 0.0)])
    loft(m, lambda s: p0 + (p1 - p0) * s + curva * (s * s),
         lambda s: cuerda * prof(s), lambda s: grosor * (1.0 - 0.7 * s),
         n=n, M=M, color=color, mov=mov, ref=ref, k_dist=0.3)


def dientes(m, posiciones, direccion, largo, radio, rgb, n=5):
    for p in posiciones:
        cono(m, p, Vector(p) + Vector(direccion) * largo, radio, n=n, color=lambda s, a, q: rgb)


# ---------------------------------------------------------------------------
# PALETAS Y PATRONES DE COLOR (valores del archivo; ver "modo LINEAR" arriba)
# ---------------------------------------------------------------------------

ORO = (0.86, 0.56, 0.16)
ORO_OSC = (0.60, 0.34, 0.07)
NEGRO_CAL = (0.05, 0.03, 0.02)
CREMA = (0.95, 0.88, 0.70)
BIO_CIAN = (0.15, 1.00, 0.90)
BIO_AZUL = (0.25, 0.60, 1.00)
MARFIL = (0.96, 0.93, 0.80)
OJO_AMBAR = (1.00, 0.72, 0.10)
OJO_NEGRO = (0.02, 0.02, 0.03)


def piel_jaguar(p, sa):
    """Rosetas de jaguar: anillos oscuros alrededor de manchas mas oscuras sobre
    fondo dorado, vientre crema y una linea lateral de puntos bioluminiscentes.
    sa = seno del angulo alrededor de la seccion (1 lomo, -1 vientre). Las
    rosetas salen de celdas de Voronoi 3D de 0,85 m: mas finas que eso no las
    resuelve la densidad de vertices (el detalle fino va por UV en el shader)."""
    d1, _ = voronoi3(p * (1.0 / 0.85), 5)
    anillo = 1.0 - suave(0.0, 0.11, abs(d1 - 0.30))
    interior = 1.0 - suave(0.20, 0.30, d1)
    c = mezcla(ORO, ORO_OSC, interior * 0.8)
    c = mezcla(c, NEGRO_CAL, anillo * 0.95)
    c = mezcla(c, CREMA, suave(0.05, -0.55, sa))
    lateral = (1.0 - suave(0.10, 0.28, abs(sa))) * suave(0.55, 0.85, math.cos(p.x * 10.0))
    return mezcla(c, BIO_CIAN, lateral)


# ---------------------------------------------------------------------------
# CRIATURAS
# ---------------------------------------------------------------------------

def crear_kronos_jaguar():
    """Pliosaurio de cabeza enorme y mandibula con dientes, cuatro aletas y piel
    de rosetas de jaguar. ~7 m. Cruce: Kronosaurus boyacensis + jaguar."""
    m = Malla()
    x0, x1 = -3.5, 3.5
    # Cuerpo y craneo son UN solo barrido (sin junta): cola fina, torso ancho,
    # cuello corto y angosto, y un craneo que vuelve a ensancharse y se afina
    # hasta el hocico.
    ry = perfil([(-3.5, 0.0), (-3.42, 0.03), (-3.0, 0.10), (-2.4, 0.20), (-1.6, 0.34), (-0.8, 0.48),
                 (-0.2, 0.52), (0.6, 0.47), (1.2, 0.36), (1.5, 0.42), (1.85, 0.52), (2.3, 0.42),
                 (2.8, 0.27), (3.2, 0.18), (3.42, 0.12), (3.5, 0.0)])
    rz = perfil([(-3.5, 0.0), (-3.42, 0.03), (-3.0, 0.11), (-2.4, 0.20), (-1.6, 0.33), (-0.8, 0.45),
                 (-0.2, 0.48), (0.6, 0.43), (1.2, 0.33), (1.5, 0.36), (1.85, 0.38), (2.3, 0.29),
                 (2.8, 0.19), (3.2, 0.13), (3.42, 0.08), (3.5, 0.0)])
    cz = perfil([(-3.5, 0.0), (1.2, 0.0), (1.9, 0.03), (3.5, 0.03)], negativos=True)

    def col_cuerpo(s, a, p):
        return piel_jaguar(p, math.sin(a))

    def mov_cuerpo(s, a, p):
        return rampa(p.x, -1.0, -3.5)

    m.grupo("cuerpo")
    loft(m, lambda s: Vector((lerp(x0, x1, s), 0.0, cz(lerp(x0, x1, s)))),
         lambda s: ry(lerp(x0, x1, s)), lambda s: rz(lerp(x0, x1, s)),
         n=28, M=104, color=col_cuerpo, mov=mov_cuerpo, k_dist=0.25)

    # Mandibula: mas corta y angosta, entreabierta hacia abajo (debajo del craneo).
    jx0, jx1 = 1.5, 3.3
    jry = perfil([(1.5, 0.30), (2.0, 0.32), (2.8, 0.19), (3.2, 0.11), (3.3, 0.0)])
    jrz = perfil([(1.5, 0.12), (2.0, 0.13), (2.8, 0.08), (3.2, 0.055), (3.3, 0.0)])
    jcz = perfil([(1.5, -0.24), (3.3, -0.36)], negativos=True)
    m.grupo("mandibula")
    loft(m, lambda s: Vector((lerp(jx0, jx1, s), 0.0, jcz(lerp(jx0, jx1, s)))),
         lambda s: jry(lerp(jx0, jx1, s)), lambda s: jrz(lerp(jx0, jx1, s)),
         n=14, M=24, color=lambda s, a, p: mezcla(CREMA, ORO, suave(-0.2, 0.8, math.sin(a))), mov=_mov_cero)

    # Dientes: dos hileras por lado, arriba hacia abajo y abajo hacia arriba.
    m.grupo("dientes")
    for lado in (1.0, -1.0):
        sup, inf = [], []
        for k in range(11):
            x = 2.25 + 0.105 * k
            sup.append(Vector((x, lado * ry(x) * 0.80, cz(x) - rz(x) * 0.66)))
            xi = x + 0.02
            inf.append(Vector((xi, lado * jry(xi) * 0.78, jcz(xi) + jrz(xi) * 0.66)))
        dientes(m, sup, (0.0, 0.0, -1.0), 0.14, 0.022, MARFIL)
        dientes(m, inf, (0.0, 0.0, 1.0), 0.12, 0.020, MARFIL)

    m.grupo("ojos")
    for lado in (1.0, -1.0):
        elipsoide(m, (2.05, lado * 0.42, 0.14), 0.05, 0.04, 0.05, n=8, mm=6, color=lambda s, a, p: OJO_AMBAR)

    # Cuatro aletas: remos largos, lentes delgadas, peso Mov 0 -> 1 hacia la punta.
    m.grupo("aletas")
    for x_raiz, y_punta, chord, barrido in ((0.6, 1.55, 0.36, -0.55), (-1.2, 1.35, 0.32, -0.5)):
        for lado in (1.0, -1.0):
            pala(m, (x_raiz, lado * 0.36, -0.28), (x_raiz + barrido * 0.5, lado * y_punta, -0.62),
                 chord, 0.05, curva=(barrido * 0.5, 0.0, -0.05), n=8, M=14,
                 color=lambda s, a, p: piel_jaguar(p, 0.0),
                 mov=lambda s, a, p: sujetar(s))
    m.ajustar(7.0)
    return m


def crear_amonita_rana():
    """Concha de amonita en espiral logaritmica con tentaculos colgando y los
    colores de advertencia de una rana venenosa (amarillo, azul y negro). ~1,2 m.
    Cruce: amonitas de Villa de Leyva + Phyllobates / Oophaga."""
    m = Malla()
    AMARILLO, AZUL, NEGRO = (0.98, 0.82, 0.05), (0.06, 0.28, 0.95), (0.02, 0.02, 0.04)
    n_vueltas = 3.0
    th_fin = 1.5 * math.pi
    th_ini = th_fin - 2.0 * math.pi * n_vueltas
    crec = 2.0                       # cuanto crece el radio por vuelta
    b = math.log(crec) / (2.0 * math.pi)
    r_fin = 0.34

    def radio_esp(th):
        return r_fin * math.exp(b * (th - th_fin))

    def th_de(s):
        return lerp(th_ini, th_fin, s)

    def centro(s):
        th = th_de(s)
        r = radio_esp(th)
        return Vector((r * math.cos(th), 0.0, r * math.sin(th)))

    def costilla(s):
        # costillas radiales: ~18 por vuelta
        return 1.0 + 0.07 * math.cos(th_de(s) * 18.0)

    def col_concha(s, a, p):
        th = th_de(s)
        franja = int(math.floor((th - th_ini) / (2.0 * math.pi) * 6.0)) % 2
        base = AMARILLO if franja == 0 else AZUL
        # lomo (a hacia afuera de la espiral) mas oscuro; manchas negras con ruido
        lomo = suave(0.3, 0.9, math.cos(a))
        mancha = suave(0.62, 0.72, ruido3(Vector((th * 1.6, math.cos(a) * 2.2, math.sin(a) * 2.2)), 3))
        c = mezcla(base, NEGRO, lomo * 0.8)
        return mezcla(c, NEGRO, mancha)

    m.grupo("concha")
    # ref = Y: N queda en el plano de la espiral (radial) y B a lo ancho (Y).
    loft(m, centro, lambda s: 0.30 * radio_esp(th_de(s)) * costilla(s) + 0.003,
         lambda s: 0.24 * radio_esp(th_de(s)) * costilla(s) + 0.003,
         n=14, M=130, color=col_concha, ref=Y, k_dist=0.0)

    # Cuerpo blando asomando por la boca (la boca mira a +X, abajo de la concha).
    C_boca = centro(1.0)
    m.grupo("cuerpo")
    elipsoide(m, C_boca + Vector((0.05, 0.0, 0.0)), 0.10, 0.075, 0.075, n=10, mm=8,
              color=lambda s, a, p: mezcla(AMARILLO, (1.0, 0.55, 0.05), 0.5))
    m.grupo("ojos")
    for lado in (1.0, -1.0):
        elipsoide(m, C_boca + Vector((0.13, lado * 0.06, 0.03)), 0.022, 0.02, 0.02, n=6, mm=5,
                  color=lambda s, a, p: OJO_NEGRO)

    # Ocho tentaculos: bajan y se enroscan, azul en la punta con brillo cian.
    rng = random.Random(11)
    m.grupo("tentaculos")
    for k in range(8):
        y0 = lerp(-0.075, 0.075, k / 7.0)
        z0 = C_boca.z + 0.03 * math.sin(k * 1.7)
        largo = 0.62 + 0.14 * rng.random()
        caida = 0.10 + 0.18 * rng.random()
        rizo = (rng.random() - 0.5) * 0.14
        P = [Vector((C_boca.x + 0.12, y0, z0)),
             Vector((C_boca.x + 0.12 + largo * 0.35, y0 * 1.6 + rizo, z0 - caida * 0.2)),
             Vector((C_boca.x + 0.12 + largo * 0.75, y0 * 2.2 - rizo, z0 - caida)),
             Vector((C_boca.x + 0.12 + largo, y0 * 2.0 + rizo * 1.5, z0 - caida * 0.55))]

        def col_t(s, a, p):
            c = mezcla(AMARILLO, AZUL, suave(0.1, 0.7, s))
            return mezcla(c, BIO_CIAN, suave(0.8, 1.0, s))
        tubo(m, P, 0.030, 0.004, n=5, M=16, color=col_t, mov=lambda s, a, p: sujetar(s) ** 1.2, k_dist=0.0)
    m.ajustar(1.2)
    return m


def crear_calla_manati():
    """Plesiosaurio de cuello largo y cuerpo redondeado con hocico ancho de
    manati y bigotes cortos. ~5 m. Cruce: Callawayasaurus colombiensis +
    Trichechus manatus."""
    m = Malla()
    GRIS, VIENTRE = (0.40, 0.46, 0.50), (0.68, 0.68, 0.64)

    def piel(p, sa, tinte=1.0):
        c = mezcla(GRIS, VIENTRE, suave(0.0, -0.6, sa))
        # arrugas: anillos suaves a lo largo del cuello, y pecas bioluminiscentes
        peca = suave(0.80, 0.86, ruido3(p * 8.0, 9))
        return mezcla(c, BIO_CIAN, peca * 0.95)

    tx0, tx1 = -2.2, 1.10
    ry = perfil([(-2.2, 0.0), (-2.15, 0.02), (-1.7, 0.08), (-1.2, 0.17), (-0.7, 0.37), (-0.2, 0.55), (0.3, 0.62), (0.8, 0.53), (0.98, 0.40), (1.10, 0.0)])
    rz = perfil([(-2.2, 0.0), (-2.15, 0.02), (-1.7, 0.07), (-1.2, 0.14), (-0.7, 0.29), (-0.2, 0.42), (0.3, 0.46), (0.8, 0.40), (0.98, 0.30), (1.10, 0.0)])
    cz_cola = lambda x: 0.28 * sujetar((-0.8 - x) / 1.4) ** 2

    m.grupo("cuerpo")
    loft(m, lambda s: Vector((lerp(tx0, tx1, s), 0.0, cz_cola(lerp(tx0, tx1, s)))),
         lambda s: ry(lerp(tx0, tx1, s)), lambda s: rz(lerp(tx0, tx1, s)),
         n=24, M=56, color=lambda s, a, p: piel(p, math.sin(a)),
         mov=lambda s, a, p: rampa(p.x, -0.9, -2.2))

    # Cuello: curva en S en el plano XZ (ref = Y: N en el plano, B a lo ancho).
    P = [Vector((0.40, 0.0, 0.00)), Vector((1.30, 0.0, 0.05)), Vector((1.55, 0.0, 0.85)), Vector((2.25, 0.0, 0.72))]
    r_cuello = perfil([(0.0, 0.40), (0.2, 0.30), (0.45, 0.18), (0.7, 0.14), (1.0, 0.105)])
    m.grupo("cuello")

    def centro_cuello(s):
        a = P[0].lerp(P[1], s).lerp(P[1].lerp(P[2], s), s)
        b = P[1].lerp(P[2], s).lerp(P[2].lerp(P[3], s), s)
        return a.lerp(b, s)
    loft(m, centro_cuello, lambda s: r_cuello(s), lambda s: r_cuello(s) * 1.05, n=14, M=34, ref=Y,
         color=lambda s, a, p: piel(p, math.sin(a) * 0.3),
         mov=lambda s, a, p: 0.45 * s)

    # Cabeza de manati: craneo redondo, hocico ancho y romo inclinado hacia abajo.
    H0 = centro_cuello(1.0) - Vector((0.06, 0.0, 0.0))
    lat = perfil([(0.0, 0.10), (0.15, 0.13), (0.35, 0.135), (0.55, 0.165), (0.63, 0.14), (0.68, 0.0)])
    alto = perfil([(0.0, 0.09), (0.15, 0.11), (0.35, 0.095), (0.55, 0.09), (0.63, 0.065), (0.68, 0.0)])
    Lh = 0.68
    m.grupo("cabeza")
    loft(m, lambda s: H0 + Vector((Lh * s, 0.0, -0.13 * s * s)),
         lambda s: lat(s * Lh), lambda s: alto(s * Lh), n=16, M=20,
         color=lambda s, a, p: piel(p, math.sin(a) * 0.5), mov=lambda s, a, p: 0.5 + 0.2 * s)
    m.grupo("ojos")
    for lado in (1.0, -1.0):
        elipsoide(m, H0 + Vector((0.28, lado * 0.115, 0.045)), 0.02, 0.016, 0.016, n=6, mm=5,
                  color=lambda s, a, p: OJO_NEGRO)
    # Bigotes cortos alrededor del labio, mirando hacia adelante y afuera.
    m.grupo("bigotes")
    punta = H0 + Vector((Lh * 0.90, 0.0, -0.13 * 0.81))
    for i in range(16):
        ang = math.pi * (-0.75 + 1.5 * i / 15.0)
        base = punta + Vector((0.0, math.sin(ang) * 0.085, math.cos(ang) * 0.055 - 0.02))
        d = Vector((1.0, math.sin(ang) * 0.6, (math.cos(ang) - 0.2) * 0.35)).normalized()
        cono(m, base, base + d * 0.10, 0.004, n=4, ref=Y,
             color=lambda s, a, p: (0.85, 0.80, 0.68), mov=lambda s, a, p: sujetar(s))

    m.grupo("aletas")
    col_al = lambda s, a, p: piel(p, 0.0)
    for x_raiz, x_pun, y_pun, ch in ((0.55, 0.00, 1.55, 0.26), (-0.65, -1.25, 1.50, 0.28)):
        for lado in (1.0, -1.0):
            pala(m, (x_raiz, lado * 0.40, -0.22), (x_pun, lado * y_pun, -0.55), ch, 0.045,
                 curva=(-0.25, 0.0, -0.05), n=8, M=14, color=col_al, mov=lambda s, a, p: sujetar(s))
    m.ajustar(5.0)
    return m


def crear_desma_orquidea():
    """Tortuga marina grande cuyo caparazon esta cubierto de crecimientos de
    orquidea y coral hechos de geometria real. ~3 m. Cruce: Desmatochelys
    padillai + orquideas y corales del Caribe."""
    m = Malla()
    OLIVA, LINEA, CENTRO = (0.16, 0.20, 0.10), (0.03, 0.04, 0.03), (0.30, 0.38, 0.20)
    PIEL, PIEL_CLARA = (0.36, 0.44, 0.34), (0.86, 0.80, 0.62)

    def col_caparazon(s, a, p):
        d1, d2 = voronoi3(p * (1.0 / 0.32), 21)
        junta = 1.0 - suave(0.0, 0.22, d2 - d1)
        c = mezcla(mezcla(OLIVA, CENTRO, suave(0.0, 0.5, d1) * 0.6), LINEA, junta * 0.9)
        liquen = suave(0.72, 0.80, ruido3(p * 5.0, 4))
        c = mezcla(c, (0.16, 0.55, 0.22), liquen * 0.8)
        return mezcla(c, PIEL_CLARA, suave(0.0, -0.5, math.sin(a)))

    cx0, cx1 = -1.0, 0.95
    ry = perfil([(-1.0, 0.0), (-0.97, 0.12), (-0.8, 0.38), (-0.4, 0.62), (0.0, 0.70), (0.4, 0.64), (0.7, 0.50), (0.88, 0.28), (0.95, 0.0)])
    rz = perfil([(-1.0, 0.0), (-0.97, 0.08), (-0.8, 0.22), (-0.4, 0.36), (0.0, 0.42), (0.4, 0.38), (0.7, 0.28), (0.88, 0.15), (0.95, 0.0)])

    def forma_cap(s, a, p):
        sa = math.sin(a)
        plano = 1.0 - 0.66 * suave(0.0, -0.3, sa)                  # plastron plano
        cresta = 0.0
        for a0 in (math.pi / 2.0, math.pi / 2.0 + 0.62, math.pi / 2.0 - 0.62):
            cresta += 0.06 * math.exp(-((a - a0) / 0.22) ** 2)
        return (1.0, plano * (1.0 + cresta))

    m.grupo("caparazon")
    loft(m, lambda s: Vector((lerp(cx0, cx1, s), 0.0, 0.0)),
         lambda s: ry(lerp(cx0, cx1, s)), lambda s: rz(lerp(cx0, cx1, s)),
         n=36, M=44, color=col_caparazon, forma=forma_cap, k_dist=0.4)

    # Cabeza con pico y cuello corto.
    m.grupo("cabeza")
    hlat = perfil([(0.75, 0.13), (0.95, 0.14), (1.15, 0.16), (1.35, 0.125), (1.5, 0.075), (1.56, 0.0)])
    halto = perfil([(0.75, 0.11), (1.0, 0.13), (1.15, 0.15), (1.35, 0.10), (1.5, 0.06), (1.56, 0.0)])
    loft(m, lambda s: Vector((lerp(0.75, 1.56, s), 0.0, 0.07 - 0.05 * s)),
         lambda s: hlat(lerp(0.75, 1.56, s)), lambda s: halto(lerp(0.75, 1.56, s)), n=14, M=20,
         color=lambda s, a, p: mezcla(PIEL, PIEL_CLARA, suave(0.0, -0.6, math.sin(a))),
         mov=lambda s, a, p: 0.1 * s)
    m.grupo("ojos")
    for lado in (1.0, -1.0):
        elipsoide(m, (1.28, lado * 0.135, 0.13), 0.028, 0.022, 0.022, n=6, mm=5, color=lambda s, a, p: OJO_AMBAR)

    # Cola corta.
    m.grupo("cola")
    tubo(m, [(-0.92, 0.0, -0.02), (-1.15, 0.0, -0.03), (-1.35, 0.0, -0.06)], 0.07, 0.01, n=8, M=8,
         color=lambda s, a, p: PIEL, mov=lambda s, a, p: 0.4 + 0.6 * s)

    # Aletas: delanteras grandes (en forma de ala), traseras chicas.
    m.grupo("aletas")
    col_al = lambda s, a, p: mezcla(PIEL, PIEL_CLARA, suave(0.0, -0.7, math.sin(a))) if suave(0.83, 0.9, ruido3(p * 7.0, 8)) < 0.5 else BIO_CIAN
    for lado in (1.0, -1.0):
        pala(m, (0.55, lado * 0.50, -0.06), (-0.10, lado * 1.55, -0.14), 0.30, 0.04,
             curva=(-0.20, 0.0, -0.05), n=8, M=14, color=col_al, mov=lambda s, a, p: sujetar(s))
        pala(m, (-0.70, lado * 0.40, -0.06), (-1.15, lado * 0.95, -0.10), 0.20, 0.035,
             curva=(-0.10, 0.0, -0.03), n=8, M=10, color=col_al, mov=lambda s, a, p: sujetar(s))

    # Crecimientos sobre el caparazon: orquideas y corales, en puntos del lomo
    # elegidos con semilla fija; cada uno se orienta por la normal de la superficie.
    rng = random.Random(29)

    def punto_superficie(x, a):
        f = forma_cap(0.0, a, None)
        r_n, r_b = ry(x), rz(x) * f[1]
        return Vector((x, r_n * math.cos(a), r_b * math.sin(a)))

    def normal_superficie(x, a):
        p = punto_superficie(x, a)
        g = lambda q: (q.y / max(1e-3, ry(q.x))) ** 2 + (q.z / max(1e-3, rz(q.x) * (forma_cap(0, a, None)[1]))) ** 2
        e = 0.01
        n = Vector((g(p + X * e) - g(p - X * e), g(p + Y * e) - g(p - Y * e), g(p + Z * e) - g(p - Z * e)))
        return n.normalized()

    def orquidea(P, nrm, alto, escala):
        ref = X if abs(nrm.dot(X)) < 0.9 else Y
        u = nrm.cross(ref).normalized()
        v = nrm.cross(u)
        F = P + nrm * alto
        tubo(m, [P - nrm * 0.02, P + nrm * alto * 0.5 + u * 0.02, F], 0.009 * escala, 0.005 * escala, n=5, M=3,
             color=lambda s, a, p: (0.20, 0.50, 0.15), mov=lambda s, a, p: 0.15 + 0.3 * s, ref=ref)
        fase = rng.random() * 6.28
        rosa = mezcla((0.95, 0.20, 0.60), (0.60, 0.30, 0.95), rng.random())
        prof = perfil([(0.0, 0.3), (0.4, 1.0), (0.8, 0.75), (1.0, 0.0)])
        for k in range(6):
            lip = (k == 5)
            ang = fase + 2.0 * math.pi * k / 5.0
            el = math.radians(-20.0 if lip else 35.0)
            d = (u * math.cos(ang) + v * math.sin(ang)) * math.cos(el) + nrm * math.sin(el)
            L = (0.05 if lip else 0.075) * escala
            ch = (0.022 if lip else 0.026) * escala
            col_p = (lambda s, a, p: mezcla((1.0, 0.85, 0.2), (1.0, 0.5, 0.1), s)) if lip else \
                    (lambda s, a, p, r=rosa: mezcla(r, (1.0, 0.92, 0.97), suave(0.5, 1.0, s)))
            loft(m, lambda s, d=d: F + d * (L * s), lambda s: ch * prof(s), lambda s: 0.003 * escala,
                 n=4, M=4, color=col_p, mov=lambda s, a, p: 0.25 + 0.55 * s, ref=nrm, k_dist=0.0)

    def coral(P, nrm, escala):
        ref = X if abs(nrm.dot(X)) < 0.9 else Y
        u = nrm.cross(ref).normalized()
        fin = P + nrm * 0.11 * escala
        col_c = lambda s, a, p: mezcla((0.95, 0.40, 0.12), (1.0, 0.85, 0.30), s)
        tubo(m, [P - nrm * 0.01, fin], 0.012 * escala, 0.008 * escala, n=5, M=2, color=col_c,
             mov=lambda s, a, p: 0.1 + 0.2 * s, ref=ref)
        for sg in (1.0, -1.0):
            d = (nrm * 0.8 + u * 0.6 * sg).normalized()
            tubo(m, [fin, fin + d * 0.08 * escala], 0.008 * escala, 0.003 * escala, n=5, M=2,
                 color=lambda s, a, p: mezcla((1.0, 0.7, 0.2), BIO_CIAN, suave(0.5, 1.0, s)),
                 mov=lambda s, a, p: 0.3 + 0.5 * s, ref=ref)

    m.grupo("orquideas")
    for k in range(16):
        x = lerp(-0.72, 0.68, rng.random())
        a = math.pi / 2.0 + (rng.random() - 0.5) * 2.0 * 0.95
        P = punto_superficie(x, a)
        nrm = (normal_superficie(x, a) + Vector((-0.35, 0.0, 0.0))).normalized()
        orquidea(P, nrm, 0.09 + 0.06 * rng.random(), 0.8 + 0.5 * rng.random())
    m.grupo("corales")
    for k in range(12):
        x = lerp(-0.75, 0.72, rng.random())
        a = math.pi / 2.0 + (rng.random() - 0.5) * 2.0 * 1.05
        P = punto_superficie(x, a)
        nrm = (normal_superficie(x, a) + Vector((-0.2, 0.0, 0.0))).normalized()
        coral(P, nrm, 0.8 + 0.7 * rng.random())
    m.ajustar(3.0)
    return m


def crear_kyhy_inia():
    """Ictiosaurio esbelto con el melon redondeado y el hocico largo del delfin
    rosado, cola de aleta vertical. ~3,5 m. Cruce: Kyhytysuka sachicarum +
    Inia geoffrensis."""
    m = Malla()
    ESPALDA, COSTADO, VIENTRE = (0.66, 0.44, 0.52), (0.95, 0.62, 0.68), (0.99, 0.86, 0.86)

    def piel(p, sa):
        c = mezcla(COSTADO, ESPALDA, suave(0.2, 0.9, sa))
        c = mezcla(c, VIENTRE, suave(-0.15, -0.8, sa))
        # fotoforos: puntos cian en una linea bajo el costado y sobre el melon
        foto = (1.0 - suave(0.08, 0.22, abs(sa + 0.15))) * suave(0.72, 0.9, math.cos(p.x * 11.0))
        c = mezcla(c, BIO_AZUL, foto)
        melon = suave(0.75, 0.9, ruido3(p * 14.0, 6)) * suave(0.7, 1.1, p.x) * suave(-0.2, 0.4, sa)
        return mezcla(c, BIO_CIAN, melon)

    # Cuerpo, melon y rostro son UN solo barrido (sin junta entre tronco y cabeza).
    bx0, bx1 = -1.5, 1.75
    lat = perfil([(-1.5, 0.0), (-1.47, 0.02), (-1.25, 0.045), (-0.9, 0.11), (-0.4, 0.22), (0.1, 0.30),
                  (0.5, 0.29), (0.75, 0.25), (1.05, 0.23), (1.25, 0.15), (1.45, 0.075), (1.6, 0.05),
                  (1.72, 0.03), (1.75, 0.0)])
    ver = perfil([(-1.5, 0.0), (-1.47, 0.02), (-1.25, 0.045), (-0.9, 0.11), (-0.4, 0.23), (0.1, 0.315),
                  (0.5, 0.305), (0.75, 0.28), (0.9, 0.31), (1.05, 0.34), (1.2, 0.22), (1.4, 0.09),
                  (1.6, 0.05), (1.72, 0.03), (1.75, 0.0)])
    cz = perfil([(-1.5, -0.07), (-1.0, 0.0), (0.6, 0.0), (1.0, 0.06), (1.4, 0.0), (1.75, -0.02)], negativos=True)
    m.grupo("cuerpo")
    loft(m, lambda s: Vector((lerp(bx0, bx1, s), 0.0, cz(lerp(bx0, bx1, s)))),
         lambda s: lat(lerp(bx0, bx1, s)), lambda s: ver(lerp(bx0, bx1, s)),
         n=22, M=84, color=lambda s, a, p: piel(p, math.sin(a)),
         mov=lambda s, a, p: rampa(p.x, 0.1, -1.5), k_dist=0.3)

    jx0, jx1 = 0.75, 1.68
    jl = perfil([(0.75, 0.17), (1.05, 0.13), (1.4, 0.06), (1.65, 0.03), (1.68, 0.0)])
    ja = perfil([(0.75, 0.08), (1.05, 0.07), (1.4, 0.04), (1.65, 0.025), (1.68, 0.0)])
    jc = perfil([(0.75, -0.24), (1.05, -0.22), (1.4, -0.14), (1.68, -0.085)], negativos=True)
    m.grupo("mandibula")
    loft(m, lambda s: Vector((lerp(jx0, jx1, s), 0.0, jc(lerp(jx0, jx1, s)))),
         lambda s: jl(lerp(jx0, jx1, s)), lambda s: ja(lerp(jx0, jx1, s)),
         n=12, M=20, color=lambda s, a, p: mezcla(VIENTRE, COSTADO, suave(-0.3, 0.8, math.sin(a))))

    m.grupo("dientes")
    for lado in (1.0, -1.0):
        sup, inf = [], []
        for k in range(14):
            x = 1.18 + 0.038 * k
            sup.append(Vector((x, lado * lat(x) * 0.78, cz(x) - ver(x) * 0.80)))
            inf.append(Vector((x + 0.01, lado * jl(x + 0.01) * 0.75, jc(x + 0.01) + ja(x + 0.01) * 0.75)))
        dientes(m, sup, (0.0, 0.0, -1.0), 0.04, 0.0075, MARFIL, n=4)
        dientes(m, inf, (0.0, 0.0, 1.0), 0.035, 0.007, MARFIL, n=4)
    m.grupo("ojos")
    for lado in (1.0, -1.0):
        elipsoide(m, (0.98, lado * 0.215, 0.05), 0.022, 0.02, 0.02, n=6, mm=5, color=lambda s, a, p: OJO_NEGRO)

    m.grupo("aletas")
    col_f = lambda s, a, p: piel(p, -0.2)
    # dorsal: cuchilla vertical en el plano XZ (ref = Y)
    pala(m, (-0.10, 0.0, 0.27), (-0.50, 0.0, 0.70), 0.17, 0.014, curva=(-0.10, 0.0, 0.0), n=6, M=10,
         color=col_f, mov=lambda s, a, p: 0.35 * s, ref=Y)
    for lado in (1.0, -1.0):
        pala(m, (0.50, lado * 0.20, -0.14), (0.08, lado * 0.75, -0.34), 0.11, 0.02, curva=(-0.10, 0.0, -0.04),
             n=6, M=10, color=col_f, mov=lambda s, a, p: sujetar(s) * 0.9)
        pala(m, (-0.55, lado * 0.10, -0.08), (-0.85, lado * 0.42, -0.17), 0.07, 0.015,
             n=6, M=8, color=col_f, mov=lambda s, a, p: sujetar(s))
    # cola: dos lobulos en media luna; el inferior algo mas largo (cola de ictiosaurio)
    for signo, largo, dx in ((1.0, 0.44, -0.30), (-1.0, 0.52, -0.33)):
        p0 = Vector((-1.50, 0.0, -0.06 + 0.02 * signo))
        p1 = Vector((-1.50 + dx, 0.0, -0.06 + signo * largo))
        ctrl = Vector((-1.50, 0.0, -0.06 + signo * largo * 0.5))
        prof = perfil([(0.0, 0.5), (0.35, 1.0), (0.8, 0.6), (1.0, 0.0)])
        loft(m, lambda s, p0=p0, p1=p1, ctrl=ctrl: p0.lerp(ctrl, s).lerp(ctrl.lerp(p1, s), s),
             lambda s: 0.13 * prof(s), lambda s: 0.014 * (1.0 - 0.6 * s), n=6, M=12,
             color=lambda s, a, p: mezcla(ESPALDA, COSTADO, s),
             mov=lambda s, a, p: 0.65 + 0.35 * s, ref=Y, k_dist=0.3)
    m.ajustar(3.5)
    return m


def crear_belemnita_morpho():
    """Belemnita (cuerpo de bala con aletas y brazos) con dos alas grandes de
    mariposa Morpho que aletean. ~0,4 m, muy pocas caras: se instancia
    cientos de veces. Cruce: belemnites del Cretacico + Morpho."""
    m = Malla()
    AMBAR = (0.55, 0.30, 0.08)
    r = perfil([(-0.19, 0.0), (-0.185, 0.03), (-0.10, 0.043), (0.05, 0.045), (0.13, 0.038), (0.19, 0.018), (0.2, 0.0)])
    m.grupo("cuerpo")
    loft(m, lambda s: Vector((lerp(-0.19, 0.2, s), 0.0, 0.0)),
         lambda s: r(lerp(-0.19, 0.2, s)), lambda s: r(lerp(-0.19, 0.2, s)),
         n=6, M=10, color=lambda s, a, p: mezcla(AMBAR, BIO_CIAN, suave(0.1, 0.2, p.x)) if p.x > 0.1 else mezcla((0.25, 0.14, 0.05), AMBAR, suave(-0.19, 0.0, p.x)))
    prof = perfil([(0.0, 0.35), (0.3, 0.75), (0.7, 1.0), (0.92, 0.65), (1.0, 0.0)])

    def col_ala(s, a, p):
        borde = suave(0.55, 0.95, abs(math.cos(a)))
        c = mezcla((0.05, 0.28, 1.0), (0.25, 0.85, 1.0), s * 0.7)
        c = mezcla(c, (0.02, 0.02, 0.06), max(borde, suave(0.78, 0.95, s)))
        return mezcla(c, (0.95, 0.95, 1.0), suave(0.92, 1.0, borde) * suave(0.3, 0.7, s) * (0.5 + 0.5 * math.cos(s * 40.0)))
    m.grupo("alas")
    for lado in (1.0, -1.0):
        loft(m, lambda s, l=lado: Vector((lerp(0.04, -0.03, s), l * lerp(0.03, 0.24, s), lerp(0.03, 0.08, s))),
             lambda s: 0.095 * prof(s), lambda s: 0.004, n=8, M=6, color=col_ala,
             mov=lambda s, a, p: sujetar(s), ref=Z, k_dist=0.2)
    m.grupo("aletas")
    for lado in (1.0, -1.0):
        loft(m, lambda s, l=lado: Vector((lerp(-0.14, -0.20, s), l * lerp(0.03, 0.09, s), 0.0)),
             lambda s: 0.03 * (1.0 - 0.7 * s) if s < 1.0 else 0.0, lambda s: 0.004, n=4, M=3,
             color=lambda s, a, p: AMBAR, mov=lambda s, a, p: 0.5 * s, ref=Z, k_dist=0.0)
    m.grupo("brazos")
    for k in range(4):
        ang = math.pi * 2.0 * k / 4.0 + 0.4
        base = Vector((0.185, 0.008 * math.cos(ang), 0.008 * math.sin(ang)))
        cono(m, base, base + Vector((0.06, 0.025 * math.cos(ang), 0.025 * math.sin(ang))), 0.006, n=4,
             color=lambda s, a, p: mezcla(AMBAR, BIO_CIAN, s), mov=lambda s, a, p: 0.6 * s)
    m.ajustar(0.4)
    return m


# ---------------------------------------------------------------------------
# BASURA PLASTICA
# ---------------------------------------------------------------------------

def crear_bolsa_plastica():
    """Bolsa que flota como una medusa: campana arrugada y translucida (la
    translucidez la pone el material) y cintas colgando por atras. ~0,6 m."""
    m = Malla()
    BLANCO, ROJO = (0.80, 0.88, 0.92), (0.80, 0.10, 0.10)
    ry = perfil([(0.30, 0.0), (0.29, 0.04), (0.22, 0.12), (0.12, 0.163), (0.0, 0.17), (-0.10, 0.13),
                 (-0.17, 0.08), (-0.22, 0.06), (-0.25, 0.09), (-0.27, 0.05), (-0.28, 0.0)])

    def col(s, a, p):
        # banda impresa en rojo sobre un costado y un poco de suciedad
        banda = suave(0.55, 0.8, math.cos(a)) * (1.0 - suave(0.15, 0.25, abs(p.x - 0.02)))
        suciedad = ruido3(p * 6.0, 2) * 0.25
        return mezcla(mezcla(BLANCO, (0.55, 0.60, 0.55), suciedad), ROJO, banda)

    def arrugas(s, a, p):
        f = 1.0 + 0.36 * (ruido3(p * 5.5, 12) - 0.5) + 0.05 * (ruido3(p * 14.0, 13) - 0.5) + 0.06 * math.sin(6.0 * a + 9.0 * s)
        return f

    m.grupo("campana")
    loft(m, lambda s: Vector((lerp(0.30, -0.28, s), 0.0, 0.0)),
         lambda s: ry(lerp(0.30, -0.28, s)), lambda s: ry(lerp(0.30, -0.28, s)) * 0.65,
         n=14, M=26, color=col, forma=arrugas,
         mov=lambda s, a, p: 0.6 * suave(0.1, -0.28, p.x), k_dist=0.3)
    m.grupo("cintas")
    rng = random.Random(3)
    for k in range(6):
        ang = 2.0 * math.pi * k / 6.0 + 0.3
        y0, z0 = 0.07 * math.cos(ang), 0.05 * math.sin(ang)
        P = [Vector((-0.24, y0, z0)), Vector((-0.30, y0 * 2.2, z0 * 2.2 + 0.03 * rng.random())),
             Vector((-0.36, y0 * 3.0, z0 * 2.5 - 0.03)), Vector((-0.42, y0 * 3.6, z0 * 3.0 + 0.02))]
        tubo(m, P, 0.012, 0.004, n=4, M=8, color=lambda s, a, p: BLANCO,
             mov=lambda s, a, p: 0.3 + 0.7 * s, ref=Y)
    m.ajustar(0.6)
    return m


def crear_botella_pet():
    """Botella de plastico PET con tapa y etiqueta (la etiqueta es una funda en
    su propia isla UV, u alrededor y v a lo largo, para pegarle un patron). ~0,3 m."""
    m = Malla()
    PET, TAPA = (0.60, 0.84, 0.88), (0.10, 0.30, 0.90)
    R = 0.034
    perf = [(-0.150, 0.0, 0.00), (-0.146, 0.018, 0.03), (-0.140, 0.029, 0.06), (-0.133, R, 0.10), (-0.10, R, 0.20),
            (0.0, R, 0.50), (0.03, R, 0.58), (0.05, 0.030, 0.68), (0.075, 0.020, 0.80), (0.088, 0.0135, 0.88),
            (0.093, 0.0135, 0.92), (0.100, 0.0168, 0.95), (0.104, 0.0168, 0.98), (0.108, 0.0135, 1.0)]
    m.grupo("botella")
    revolucion(m, perf, n=20, color=lambda s, a, p: mezcla(PET, (0.75, 0.92, 0.95), 0.5 + 0.5 * math.cos(a)))
    m.grupo("tapa")
    revolucion(m, [(0.106, 0.0, 0.0), (0.106, 0.0158, 0.2), (0.150, 0.0158, 0.8), (0.150, 0.0, 1.0)], n=20,
               color=lambda s, a, p: TAPA)
    # Etiqueta: funda cerrada de 1 mm; lazo exterior (v de 0 a 1) e interior (v de 1 a 0).
    x0, x1 = -0.075, 0.015
    ext = [(lerp(x0, x1, k / 5.0), R + 0.0014, k / 5.0) for k in range(6)]
    inte = [(lerp(x1, x0, k / 5.0), R + 0.0005, 1.0 - k / 5.0) for k in range(6)]

    def col_et(s, a, p):
        franja = suave(0.15, 0.25, s) - suave(0.75, 0.85, s)
        c = mezcla((0.93, 0.93, 0.90), (0.85, 0.10, 0.12), franja)
        return mezcla(c, (0.10, 0.25, 0.75), suave(0.42, 0.5, s) * (1.0 - suave(0.5, 0.58, s)))
    m.grupo("etiqueta")
    revolucion(m, ext + inte, n=20, color=col_et, bucle=True)
    m.ajustar(0.3)
    return m


def crear_red_fantasma():
    """Fragmento de red de pesca abandonada: malla en rombos de tubos finos,
    rasgada, con cuerda de flotacion y boyas. ~2 m."""
    m = Malla()
    NYLON, BOYA, CUERDA = (0.16, 0.50, 0.38), (0.95, 0.38, 0.05), (0.55, 0.45, 0.25)
    ancho, alto = 2.0, 1.2
    rng = random.Random(5)

    def z_red(x, y):
        # cuelga en arco y se arruga; el borde de la cuerda (y = +alto/2) queda mas alto
        yy = (y + alto / 2.0) / alto
        return -0.30 * (1.0 - (2.0 * x / ancho) ** 2) * (1.0 - 0.55 * yy) + 0.06 * (ruido3(Vector((x * 2.2, y * 2.2, 0.3)), 1) - 0.5)

    def mov_red(x, y):
        return sujetar((alto / 2.0 - y) / alto) ** 1.2

    hueco = (0.35, -0.10, 0.28)          # rasgadura circular (cx, cy, radio)
    m.grupo("malla")
    for familia in (1.0, -1.0):
        cs = [-1.6 + 0.4 * k for k in range(9)]
        for c in cs:
            # familia +1: x - y = c ; familia -1: x + y = c
            xa = max(-ancho / 2.0, c - alto / 2.0)
            xb = min(ancho / 2.0, c + alto / 2.0)
            if xb - xa < 0.12:
                continue
            # tramos de la linea: se parte donde cae el hueco y se acortan los bordes rasgados
            largo = (xb - xa) * math.sqrt(2.0)
            k_seg = max(2, int(largo / 0.17))
            pts = []
            for k in range(k_seg + 1):
                x = lerp(xa, xb, k / k_seg)
                y = (x - c) if familia > 0 else (c - x)
                pts.append((x, y))
            tramo = []
            tramos = []
            for (x, y) in pts:
                dentro = math.hypot(x - hueco[0], y - hueco[1]) < hueco[2]
                borde_roto = x > 0.75 and rng.random() < 0.25
                if dentro or borde_roto:
                    if len(tramo) >= 2:
                        tramos.append(tramo)
                    tramo = []
                else:
                    tramo.append((x, y))
            if len(tramo) >= 2:
                tramos.append(tramo)
            for tr in tramos:
                cuerpo = [Vector((x, y, z_red(x, y))) for (x, y) in tr]
                movs = [mov_red(x, y) for (x, y) in tr]
                K = len(cuerpo) - 1

                def centro(s, cuerpo=cuerpo, K=K):
                    f = s * K
                    i = min(K - 1, int(f))
                    return cuerpo[i].lerp(cuerpo[i + 1], f - i)

                def mv(s, a, p, movs=movs, K=K):
                    f = s * K
                    i = min(K - 1, int(f))
                    return lerp(movs[i], movs[i + 1], f - i)
                loft(m, centro, lambda s: 0.0085, lambda s: 0.0085, n=4, M=K,
                     color=lambda s, a, p: mezcla(NYLON, (0.30, 0.55, 0.25), suave(0.6, 0.8, ruido3(p * 4.0, 5))),
                     mov=mv, k_dist=0.0, fase=math.pi / 4.0)
    # Cuerda de flotacion en el borde y boyas.
    m.grupo("cuerda")
    xs = [lerp(-ancho / 2.0, ancho / 2.0, k / 12.0) for k in range(13)]
    yb = alto / 2.0
    cuerda = [Vector((x, yb, z_red(x, yb) + 0.01)) for x in xs]

    def centro_c(s):
        f = s * 12
        i = min(11, int(f))
        return cuerda[i].lerp(cuerda[i + 1], f - i)
    loft(m, centro_c, lambda s: 0.014, lambda s: 0.014, n=5, M=12, color=lambda s, a, p: CUERDA, k_dist=0.0)
    m.grupo("boyas")
    for x in (-0.75, -0.25, 0.25, 0.75):
        elipsoide(m, (x, yb + 0.02, z_red(x, yb) + 0.05), 0.075, 0.04, 0.04, n=8, mm=6, color=lambda s, a, p: BOYA)
    m.ajustar(2.0)
    return m


def crear_anillo_lata():
    """Portalatas de seis anillos de plastico. ~0,15 m."""
    m = Malla()
    PLASTICO = (0.72, 0.78, 0.82)
    Rc, tr = 0.0215, 0.0038
    m.grupo("anillos")
    centros = [(cx, cy) for cy in (-0.025, 0.025) for cx in (-0.05, 0.0, 0.05)]
    for (cx, cy) in centros:
        loft(m, lambda s, cx=cx, cy=cy: Vector((cx + Rc * math.cos(2 * math.pi * s), cy + Rc * math.sin(2 * math.pi * s), 0.0)),
             lambda s: tr, lambda s: tr * 0.9, n=6, M=14, bucle=True,
             color=lambda s, a, p: PLASTICO)
    m.grupo("uniones")
    for k in range(3):
        cx = (-0.05, 0.0, 0.05)[k]
        loft(m, lambda s, cx=cx: Vector((cx, lerp(-0.0065, 0.0065, s), 0.0)),
             lambda s: 0.0075, lambda s: 0.0035, n=4, M=1, fase=math.pi / 4.0, color=lambda s, a, p: PLASTICO, k_dist=0.0)
    for cy in (-0.025, 0.025):
        for cx in (-0.025, 0.025):
            loft(m, lambda s, cx=cx, cy=cy: Vector((lerp(cx - 0.0035, cx + 0.0035, s), cy, 0.0)),
                 lambda s: 0.0075, lambda s: 0.0035, n=4, M=1, fase=math.pi / 4.0, color=lambda s, a, p: PLASTICO, k_dist=0.0)
    m.ajustar(0.15)
    return m


# ---------------------------------------------------------------------------
# DECORADO DEL LECHO
# ---------------------------------------------------------------------------

def crear_roca_lecho():
    """Roca irregular del fondo, con musgo y liquenes que brillan. ~1 m."""
    m = Malla()

    def col(s, a, p):
        roca = mezcla((0.20, 0.18, 0.16), (0.34, 0.30, 0.26), ruido3(p * 3.0, 4))
        musgo = suave(0.05, 0.28, p.z) * suave(0.45, 0.6, ruido3(p * 4.0, 7))
        c = mezcla(roca, (0.10, 0.30, 0.10), musgo)
        return mezcla(c, BIO_CIAN, suave(0.80, 0.86, ruido3(p * 10.0, 9)) * 0.9)

    m.grupo("roca")
    elipsoide(m, (0, 0, 0), 0.55, 0.45, 0.38, n=24, mm=18, color=col)
    # Se deforma despues con ruido sobre la posicion y se aplana la base.

    def deformar(c):
        f = 1.0 + 0.30 * (ruido3(c * 2.0, 1) - 0.5) * 2.0 + 0.08 * (ruido3(c * 7.0, 2) - 0.5) * 2.0
        c = c * f
        c.z = max(c.z, -0.27)         # base plana apoyada en el lecho
        return c
    m.aplicar(deformar)
    m.ajustar(1.0, criterio="max")
    m.centrar()
    return m


def crear_coral_abanico():
    """Abanico de coral (gorgonia): tronco corto y ramas que se abren en un solo
    plano, con ramillas. ~0,8 m."""
    m = Malla()
    rng = random.Random(7)
    col_r = lambda s0: (lambda s, a, p: mezcla(mezcla((0.55, 0.08, 0.28), (1.0, 0.45, 0.15), suave(-0.3, 0.5, p.z)),
                                               (1.0, 0.95, 0.55), suave(0.75, 1.0, s)))
    m.grupo("tronco")
    tubo(m, [(0, 0, -0.42), (0, 0, -0.27)], 0.035, 0.028, n=8, M=4, color=lambda s, a, p: (0.45, 0.06, 0.24))
    m.grupo("ramas")
    base = Vector((0, 0, -0.27))
    for k in range(7):
        phi = math.radians(lerp(-52, 52, k / 6.0))
        d = Vector((math.sin(phi), 0.0, math.cos(phi)))
        L = 0.52 - 0.10 * abs(k - 3) / 3.0
        off = (rng.random() - 0.5) * 0.03
        P = [base, base + d * L * 0.5 + Vector((0, off, 0)), base + d * L + Vector((0.05 * math.sin(phi), off, 0))]
        cen = tubo(m, P, 0.013, 0.006, n=5, M=8, color=col_r(0), mov=lambda s, a, p: 0.2 + 0.8 * s * s)
        for s_r in (0.35, 0.58, 0.80):
            for lado in (1.0, -1.0):
                ang = math.radians(32.0 * lado)
                ds = Matrix.Rotation(ang, 3, 'Y') @ d
                q0 = cen(s_r)
                ll = L * 0.40 * (1.0 - 0.45 * s_r)
                Q = [q0, q0 + ds * ll * 0.5, q0 + ds * ll + Vector((0, (rng.random() - 0.5) * 0.02, 0))]
                tubo(m, Q, 0.006, 0.0025, n=4, M=3, color=col_r(0),
                     mov=lambda s, a, p, s_r=s_r: 0.2 + 0.8 * (s_r * s_r) + 0.2 * s)
    m.ajustar(0.8, criterio="max")
    m.centrar()
    return m


def crear_kelp_tira():
    """Tira de alga de 3 m, con muchos cortes a lo largo para doblarla con un
    shader; el peso Mov sube de 0 en la base a 1 en la punta. Base a -X."""
    m = Malla()
    x0, x1 = -1.5, 1.5

    def forma(s, a, p):
        # borde ondulado (la lamina se ondula a lo ancho, no a lo largo)
        return (1.0 + 0.16 * math.sin(s * 60.0 + 0.7 * ruido3(p * 3.0, 2)), 1.0)

    def col(s, a, p):
        c = mezcla((0.18, 0.28, 0.06), (0.58, 0.46, 0.10), s)
        borde = suave(0.6, 0.95, abs(math.cos(a)))
        return mezcla(c, BIO_CIAN, borde * suave(0.5, 0.75, ruido3(Vector((p.x * 6.0, 0.0, 0.0)), 3)) * 0.9)

    ancho = perfil([(0.0, 0.04), (0.10, 0.085), (0.70, 0.09), (0.93, 0.06), (1.0, 0.0)])
    m.grupo("lamina")
    loft(m, lambda s: Vector((lerp(x0, x1, s), 0.0, 0.0)),
         lambda s: ancho(s), lambda s: 0.006, n=6, M=60, color=col, forma=forma, mov=lambda s, a, p: s ** 1.4, k_dist=0.0)
    m.grupo("raiz")
    for k in range(6):
        ang = 2.0 * math.pi * k / 6.0
        base = Vector((x0 + 0.02, 0.0, 0.0))
        cono(m, base, base + Vector((-0.10, 0.09 * math.cos(ang), 0.09 * math.sin(ang))), 0.018, n=5,
             color=lambda s, a, p: (0.20, 0.14, 0.06))
    m.ajustar(3.0)
    return m


# ---------------------------------------------------------------------------
# CATALOGO
# ---------------------------------------------------------------------------

# id -> (funcion, familia de topes, familia de material de la vista previa, centrar)
CATALOGO = [
    ("kronos_jaguar", crear_kronos_jaguar, "criatura", "criatura"),
    ("amonita_rana", crear_amonita_rana, "criatura", "criatura"),
    ("calla_manati", crear_calla_manati, "criatura", "criatura"),
    ("desma_orquidea", crear_desma_orquidea, "criatura", "criatura"),
    ("kyhy_inia", crear_kyhy_inia, "criatura", "criatura"),
    ("belemnita_morpho", crear_belemnita_morpho, "belemnita", "criatura"),
    ("bolsa_plastica", crear_bolsa_plastica, "resto", "plastico"),
    ("botella_pet", crear_botella_pet, "resto", "plastico"),
    ("red_fantasma", crear_red_fantasma, "resto", "plastico"),
    ("anillo_lata", crear_anillo_lata, "resto", "plastico"),
    ("roca_lecho", crear_roca_lecho, "decorado", "decorado"),
    ("coral_abanico", crear_coral_abanico, "decorado", "criatura"),
    ("kelp_tira", crear_kelp_tira, "decorado", "criatura"),
]

MATERIAL_FBX = {"criatura": "M_Criatura", "plastico": "M_Plastico", "decorado": "M_Decorado"}


# ---------------------------------------------------------------------------
# DE MALLA A OBJETO DE BLENDER
# ---------------------------------------------------------------------------

def limpiar_escena():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.unit_settings.system = 'METRIC'
    bpy.context.scene.unit_settings.scale_length = 1.0


def construir_objeto(m, nombre, material_fbx):
    """Convierte la Malla en un objeto: caras suaves, UV0 con una celda por
    grupo, capa de color "Col" (RGB + peso Mov en A) y un solo material."""
    ng = len(m.grupos)
    cols = max(1, math.ceil(math.sqrt(ng)))
    margen = 0.03
    bm = bmesh.new()
    verts = [bm.verts.new(c) for c in m.co]
    uvl = bm.loops.layers.uv.new("UVMap")
    col = bm.loops.layers.float_color.new("Col")
    omitidas = 0
    for idx, uvs, g in m.caras:
        try:
            f = bm.faces.new([verts[i] for i in idx])
        except ValueError:
            omitidas += 1
            continue
        f.smooth = True
        cx, cy = g % cols, g // cols
        for loop, uv in zip(f.loops, uvs):
            loop[uvl].uv = ((cx + margen + uv[0] * (1.0 - 2 * margen)) / cols,
                            (cy + margen + uv[1] * (1.0 - 2 * margen)) / cols)
    bm.verts.index_update()
    for f in bm.faces:
        for loop in f.loops:
            i = loop.vert.index
            r, gg, b = m.rgb[i]
            loop[col] = (r, gg, b, m.mov[i])
    me = bpy.data.meshes.new(nombre)
    bm.to_mesh(me)
    bm.free()
    me.validate()
    if "Col" in me.color_attributes:
        me.color_attributes.active_color = me.color_attributes["Col"]
        me.color_attributes.render_color_index = me.color_attributes.find("Col")
    mat = bpy.data.materials.new(material_fbx)
    me.materials.append(mat)
    obj = bpy.data.objects.new(nombre, me)
    bpy.context.collection.objects.link(obj)
    if omitidas:
        print("  aviso: {} caras omitidas por duplicadas en {}".format(omitidas, nombre))
    return obj


def triangulos(malla_bl):
    return sum(len(p.vertices) - 2 for p in malla_bl.polygons)


# ---------------------------------------------------------------------------
# EXPORTACION Y VERIFICACION DEL FBX
# ---------------------------------------------------------------------------

def exportar_fbx(obj, ruta):
    """FBX para Unreal, con la geometria ya en centimetros y el archivo
    declarando centimetros como unidad. Se comprobo (Blender 5.2) que:
      - global_scale=1 con apply_unit_scale=True (lo que usa la sala) deja la
        geometria en metros y mete el 100 en la transformacion del nodo o en
        la unidad del archivo: Unreal solo lo aplica si "convert_scene_unit"
        esta activo (por eso el importador de la sala lo fuerza).
      - apply_unit_scale=False con apply_scale_options='FBX_SCALE_NONE' y
        global_scale=1 escribe los vertices en centimetros, deja la unidad del
        archivo en cm (UnitScaleFactor = 1) y el nodo con escala 1: el tamanio
        es correcto con "convert_scene_unit" activo o no.
    Ejes de Blender tal cual (Y adelante, Z arriba): la malla ya esta orientada
    con la nariz en +X y Unreal no tiene que girarla. colors_type='LINEAR'
    escribe los numeros de la capa "Col" sin conversion sRGB."""
    if os.path.exists(ruta):
        os.remove(ruta)
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.export_scene.fbx(
        filepath=ruta, use_selection=True, object_types={'MESH'},
        global_scale=1.0, apply_unit_scale=False, apply_scale_options='FBX_SCALE_NONE',
        bake_space_transform=True, axis_forward='Y', axis_up='Z',
        mesh_smooth_type='FACE', use_mesh_modifiers=False, colors_type='LINEAR',
        path_mode='STRIP', embed_textures=False,
    )


def importar_fbx(ruta):
    """Importa un FBX de criatura y devuelve el objeto con la escala aplicada
    (la malla vuelve a estar en metros)."""
    antes = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=ruta)
    nuevos = [o for o in bpy.data.objects if o not in antes and o.type == 'MESH']
    obj = nuevos[0]
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    return obj


def medir(obj):
    me = obj.data
    xs = [v.co.x for v in me.vertices]
    ys = [v.co.y for v in me.vertices]
    zs = [v.co.z for v in me.vertices]
    return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))


def verificar_fbx(id_, ruta, malla, familia):
    """Reimporta el FBX y comprueba: caja igual a la construida (tamanio en
    metros y orientacion, nariz en +X), triangulos bajo el tope, una capa UV
    en [0, 1], la capa de color "Col" con alfa que conserva el peso Mov, y
    normales hacia afuera. Devuelve el resumen y una lista de problemas."""
    problemas = []
    obj = importar_fbx(ruta)
    me = obj.data
    lo, hi = medir(obj)
    lo0, hi0 = malla.limites()
    for i, eje in enumerate("XYZ"):
        if abs(lo[i] - lo0[i]) > 5e-4 or abs(hi[i] - hi0[i]) > 5e-4:
            problemas.append("caja {} distinta: FBX [{:.4f}, {:.4f}] contra [{:.4f}, {:.4f}]".format(
                eje, lo[i], hi[i], lo0[i], hi0[i]))
    tris = triangulos(me)
    if tris > TOPE_TRIS[familia]:
        problemas.append("{} triangulos pasan el tope de {}".format(tris, TOPE_TRIS[familia]))
    capas_uv = [l.name for l in me.uv_layers]
    if len(capas_uv) != 1:
        problemas.append("capas UV: {}".format(capas_uv))
    else:
        us = [d.uv.x for d in me.uv_layers[0].data]
        vs = [d.uv.y for d in me.uv_layers[0].data]
        if min(us) < -1e-6 or max(us) > 1 + 1e-6 or min(vs) < -1e-6 or max(vs) > 1 + 1e-6:
            problemas.append("UV fuera de [0,1]")
    capas_col = [a.name for a in me.color_attributes]
    if capas_col != ["Col"]:
        problemas.append("capas de color: {} (se esperaba solo Col)".format(capas_col))
    a_min = a_max = None
    if "Col" in me.color_attributes:
        datos = me.color_attributes["Col"].data
        alfas = [d.color[3] for d in datos]
        a_min, a_max = min(alfas), max(alfas)
        esperado_max = max(malla.mov)
        if abs(a_max - esperado_max) > 0.02:
            problemas.append("alfa maximo {:.3f} distinto del Mov construido {:.3f}".format(a_max, esperado_max))
    # normales hacia afuera: volumen con signo de los triangulos > 0
    vol = 0.0
    for p in me.polygons:
        vs_ = [me.vertices[i].co for i in p.vertices]
        for k in range(1, len(vs_) - 1):
            vol += vs_[0].dot(vs_[k].cross(vs_[k + 1]))
    if vol <= 0:
        problemas.append("volumen con signo <= 0 (normales hacia adentro)")
    # escala aplicada dejada por el importador: ya se aplico, debe ser 1
    dims = (hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2])
    return {"tris": tris, "dims": dims, "alfa": (a_min, a_max), "problemas": problemas}


def leer_unidad_fbx(ruta):
    """UnitScaleFactor de la cabecera del FBX binario (1 = centimetros)."""
    import struct
    datos = open(ruta, "rb").read()
    k = datos.find(b"UnitScaleFactor")
    idx = datos.find(b"Number", k)
    return struct.unpack("<d", datos[idx + 12: idx + 20])[0]


# ---------------------------------------------------------------------------
# HOJA DE CONTACTO Y VISTAS (EEVEE)
# ---------------------------------------------------------------------------

def material_vista(nombre, plastico, mapa_mov=False):
    mat = bpy.data.materials.new(nombre)
    mat.use_nodes = True
    nt = mat.node_tree
    p = nt.nodes["Principled BSDF"]
    vc = nt.nodes.new("ShaderNodeVertexColor")
    vc.layer_name = "Col"
    if mapa_mov:
        # el alfa de "Col" como mapa de calor: azul = rigido, rojo = movil
        rampa_n = nt.nodes.new("ShaderNodeValToRGB")
        rampa_n.color_ramp.elements[0].color = (0.0, 0.05, 0.5, 1.0)
        rampa_n.color_ramp.elements[1].color = (1.0, 0.1, 0.0, 1.0)
        nt.links.new(vc.outputs["Alpha"], rampa_n.inputs["Fac"])
        nt.links.new(rampa_n.outputs["Color"], p.inputs["Base Color"])
        nt.links.new(rampa_n.outputs["Color"], p.inputs["Emission Color"])
        p.inputs["Emission Strength"].default_value = 0.9
        return mat
    nt.links.new(vc.outputs["Color"], p.inputs["Base Color"])
    nt.links.new(vc.outputs["Color"], p.inputs["Emission Color"])
    p.inputs["Emission Strength"].default_value = 0.10 if plastico else 0.30
    p.inputs["Roughness"].default_value = 0.2 if plastico else 0.55
    if plastico:
        p.inputs["Alpha"].default_value = 0.55
        try:
            mat.surface_render_method = 'BLENDED'
        except Exception:
            pass
    return mat


def preparar_escena_render(ancho, alto, muestras=24):
    limpiar_escena()
    esc = bpy.context.scene
    esc.render.engine = 'BLENDER_EEVEE'
    esc.render.resolution_x = ancho
    esc.render.resolution_y = alto
    esc.render.resolution_percentage = 100
    esc.render.image_settings.file_format = 'JPEG'
    esc.render.image_settings.quality = 88
    try:
        esc.eevee.taa_render_samples = muestras
    except Exception:
        pass
    esc.view_settings.view_transform = 'Standard'
    mundo = bpy.data.worlds.new("Abismo")
    mundo.use_nodes = True
    bg = mundo.node_tree.nodes["Background"]
    bg.inputs[0].default_value = (0.004, 0.012, 0.028, 1.0)
    bg.inputs[1].default_value = 1.0
    esc.world = mundo
    # luz clave fria desde arriba-adelante y relleno calido desde abajo-atras
    for nombre, energia, color, rot in (("clave", 3.2, (0.65, 0.85, 1.0), (math.radians(50), 0, math.radians(-25))),
                                        ("relleno", 1.1, (1.0, 0.75, 0.55), (math.radians(120), 0, math.radians(150)))):
        luz = bpy.data.lights.new(nombre, 'SUN')
        luz.energy = energia
        luz.color = color
        ob = bpy.data.objects.new(nombre, luz)
        ob.rotation_euler = rot
        bpy.context.collection.objects.link(ob)
    return esc


def texto_3d(cuerpo, ubicacion, rotacion, tamano=0.20):
    cur = bpy.data.curves.new("txt", 'FONT')
    cur.body = cuerpo
    cur.size = tamano
    cur.align_x = 'CENTER'
    ob = bpy.data.objects.new("txt", cur)
    ob.location = ubicacion
    ob.rotation_euler = rotacion
    mat = bpy.data.materials.new("txt")
    mat.use_nodes = True
    p = mat.node_tree.nodes["Principled BSDF"]
    p.inputs["Base Color"].default_value = (0.9, 0.95, 1.0, 1.0)
    p.inputs["Emission Color"].default_value = (0.9, 0.95, 1.0, 1.0)
    p.inputs["Emission Strength"].default_value = 1.2
    cur.materials.append(mat)
    bpy.context.collection.objects.link(ob)
    return ob


def renderizar_hoja(resultados, ruta_png, mapa_mov=False):
    """Hoja de contacto: los objetos reimportados desde sus FBX, cada uno
    escalado para caber en una celda (la medida real va en la etiqueta), vistos
    desde arriba-adelante con camara ortografica."""
    columnas, filas = 5, 3
    paso = 3.4
    paso_y = 5.0
    esc = preparar_escena_render(2800, 1700)
    mats = {
        "criatura": material_vista("v_criatura", False, mapa_mov),
        "decorado": material_vista("v_decorado", False, mapa_mov),
        "plastico": material_vista("v_plastico", True, mapa_mov),
    }
    elev = math.radians(40.0)
    rot_cam = (math.radians(90.0) - elev, 0.0, 0.0)
    for k, r in enumerate(resultados):
        col, fila = k % columnas, k // columnas
        cx = (col - (columnas - 1) / 2.0) * paso
        cy = ((filas - 1) / 2.0 - fila) * paso_y
        obj = importar_fbx(r["ruta"])
        lo, hi = medir(obj)
        centro = Vector([(lo[i] + hi[i]) / 2.0 for i in range(3)])
        lado = max(hi[i] - lo[i] for i in range(3))
        f = 2.3 / lado
        obj.data.transform(Matrix.Translation(-centro))
        obj.data.transform(Matrix.Scale(f, 4))
        obj.location = (cx, cy, 0.0)
        obj.data.materials.clear()
        obj.data.materials.append(mats[r["material_vista"]])
        arriba = Vector((0.0, math.sin(elev), math.cos(elev)))
        d = r["dims"]
        etiqueta = "{}\n{:.2f} x {:.2f} x {:.2f} m  |  {} tris".format(r["id"], d[0], d[1], d[2], r["tris"])
        texto_3d(etiqueta, Vector((cx, cy, 0.0)) - arriba * 1.55, rot_cam, 0.17)
    cam_d = bpy.data.cameras.new("cam")
    cam_d.type = 'ORTHO'
    cam_d.ortho_scale = columnas * paso + 0.4
    cam_d.clip_end = 200.0
    cam = bpy.data.objects.new("cam", cam_d)
    bpy.context.collection.objects.link(cam)
    cam.rotation_euler = rot_cam
    dist = 40.0
    cam.location = Vector((0.0, -dist * math.cos(elev), dist * math.sin(elev)))
    esc.camera = cam
    esc.render.filepath = ruta_png
    bpy.ops.render.render(write_still=True)


def renderizar_vistas(ids, carpeta):
    """Vistas de depuracion (perspectiva) de los FBX ya escritos: lateral,
    superior, tres cuartos y mapa de Mov. No las usa la corrida normal."""
    os.makedirs(carpeta, exist_ok=True)
    for id_ in ids:
        for nombre_vista, az, el, mov in (("lat", -90.0, 5.0, False), ("sup", -90.0, 88.0, False),
                                          ("34", -55.0, 25.0, False), ("mov", -90.0, 10.0, True)):
            esc = preparar_escena_render(1500, 800, 16)
            obj = importar_fbx(os.path.join(CARPETA_FBX, id_ + ".fbx"))
            familia = [c[3] for c in CATALOGO if c[0] == id_][0]
            obj.data.materials.clear()
            obj.data.materials.append(material_vista("v", familia == "plastico", mov))
            lo, hi = medir(obj)
            centro = Vector([(lo[i] + hi[i]) / 2.0 for i in range(3)])
            radio = max(hi[i] - lo[i] for i in range(3)) / 2.0
            cam_d = bpy.data.cameras.new("cam")
            cam_d.lens = 50.0
            cam_d.clip_end = 1000.0
            cam = bpy.data.objects.new("cam", cam_d)
            bpy.context.collection.objects.link(cam)
            dist = radio * 3.2
            az_r, el_r = math.radians(az), math.radians(el)
            cam.location = centro + Vector((math.cos(el_r) * math.cos(az_r),
                                            math.cos(el_r) * math.sin(az_r), math.sin(el_r))) * dist
            cam.rotation_euler = (centro - cam.location).to_track_quat('-Z', 'Y').to_euler()
            esc.camera = cam
            esc.render.filepath = os.path.join(carpeta, "{}_{}.jpg".format(id_, nombre_vista))
            bpy.ops.render.render(write_still=True)


# ---------------------------------------------------------------------------
# PRINCIPAL
# ---------------------------------------------------------------------------

def _argumentos_propios():
    if "--" not in sys.argv:
        return []
    return sys.argv[sys.argv.index("--") + 1:]


def main():
    args = _argumentos_propios()
    solo = None
    vistas = None
    for i, a in enumerate(args):
        if a == "--solo" and i + 1 < len(args):
            solo = set(args[i + 1].split(","))
        if a == "--vistas" and i + 1 < len(args):
            vistas = args[i + 1]
    catalogo = [c for c in CATALOGO if solo is None or c[0] in solo]
    os.makedirs(CARPETA_FBX, exist_ok=True)
    os.makedirs(os.path.dirname(RUTA_HOJA), exist_ok=True)

    resultados = []
    hay_problemas = False
    print("\n--- Construccion y exportacion ({} objetos) ---".format(len(catalogo)))
    for id_, fabrica, familia, mat_vista in catalogo:
        limpiar_escena()
        m = fabrica()
        abiertas, repetidas = m.topologia()
        obj = construir_objeto(m, id_, MATERIAL_FBX[mat_vista])
        ruta = os.path.join(CARPETA_FBX, id_ + ".fbx")
        exportar_fbx(obj, ruta)
        limpiar_escena()
        v = verificar_fbx(id_, ruta, m, familia)
        v["unidad_fbx"] = leer_unidad_fbx(ruta)
        if v["unidad_fbx"] != 1.0:
            v["problemas"].append("la cabecera del FBX no declara centimetros ({})".format(v["unidad_fbx"]))
        if abiertas or repetidas:
            v["problemas"].append("topologia: {} aristas abiertas, {} repetidas".format(abiertas, repetidas))
        print("{:<18} {:>6} tris  caja {:.3f} x {:.3f} x {:.3f} m  alfa [{:.2f}, {:.2f}]  UV: {} islas  {}".format(
            id_, v["tris"], v["dims"][0], v["dims"][1], v["dims"][2], v["alfa"][0], v["alfa"][1],
            len(m.grupos), "OK" if not v["problemas"] else "PROBLEMAS"))
        for p in v["problemas"]:
            print("    !", p)
            hay_problemas = True
        resultados.append({"id": id_, "ruta": ruta, "familia": familia, "material_vista": mat_vista,
                           "tris": v["tris"], "dims": v["dims"], "alfa": v["alfa"],
                           "islas_uv": m.grupos, "problemas": v["problemas"]})

    if solo is None:
        manifiesto = [{
            "id": r["id"], "fbx": os.path.basename(r["ruta"]), "triangulos": r["tris"],
            "caja_m": [round(d, 4) for d in r["dims"]], "caja_cm": [round(d * 100.0, 2) for d in r["dims"]],
            "islas_uv": r["islas_uv"], "material_fbx": MATERIAL_FBX[r["material_vista"]],
        } for r in resultados]
        with open(RUTA_MANIFIESTO, "w", encoding="utf-8") as fh:
            json.dump(manifiesto, fh, indent=2, ensure_ascii=False)
        renderizar_hoja(resultados, RUTA_HOJA)
        renderizar_hoja(resultados, RUTA_HOJA_MOV, mapa_mov=True)
        print("Hoja de contacto:", RUTA_HOJA)
    if vistas:
        renderizar_vistas([c[0] for c in catalogo], vistas)
    if hay_problemas:
        raise SystemExit("Hay problemas en la verificacion de los FBX (ver arriba).")


if __name__ == "__main__":
    main()
