# -*- coding: utf-8 -*-
"""
generar_texturas_pbr.py
=======================

Genera las texturas PBR de la sala (tela de butacas, madera de listones,
alfombra, metal cepillado, fieltro acustico, tarima y pintura) con numpy, sin
depender de ninguna libreria de materiales. Cada textura es tileable (el
ruido se filtra en el dominio de Fourier, que es periodico por construccion)
y pequena (512 x 512), y sale en tres mapas:

    <nombre>_BaseColor.png   color, sRGB. Las neutras (tela, alfombra,
                             fieltro, metal, pintura) rondan el gris medio: el
                             material las multiplica por Tinte * 2, asi que el
                             color final lo decide la sala.
    <nombre>_Roughness.png   rugosidad lineal, un canal.
    <nombre>_Normal.png      normal en espacio tangente: x = u a la derecha,
                             y = v hacia abajo (fila de la imagen), z hacia
                             afuera. El nodo triplanar de M_SalaPBR la lee con
                             esa misma convencion.

Tambien escribe SenalSalida_BaseColor.png, la cara de la senal verde de salida.

Uso (cualquier Python con numpy y Pillow; no hace falta Unreal):

    python 03_Unreal/generar_texturas_pbr.py

Salida: 03_Unreal/Texturas_PBR/. Las lee importar_sala.py. La escala en
metros de cada textura (cuanto mide un mosaico en la sala) esta en
realismo_sala.py (MATERIALES_SALA), no aqui.

Es determinista (semilla fija): correrlo dos veces da los mismos archivos.
"""

import os

import numpy as np
from PIL import Image, ImageDraw, ImageFont

TAM = 512
SALIDA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Texturas_PBR")


# ---------------------------------------------------------------------------
# Ruido tileable
# ---------------------------------------------------------------------------

def _frecuencias(n=TAM):
    f = np.fft.fftfreq(n) * n  # ciclos por mosaico
    fx, fy = np.meshgrid(f, f)
    return fx, fy


def ruido(rng, escala_ciclos, anis_x=1.0, anis_y=1.0, pendiente=0.0, n=TAM):
    """Ruido gaussiano filtrado en frecuencia: periodico en los dos ejes.
    escala_ciclos: frecuencia caracteristica (ciclos por mosaico). anis_x /
    anis_y > 1 alargan el grano en ese eje. pendiente > 0 agrega 1/f."""
    fx, fy = _frecuencias(n)
    r = np.sqrt((fx * anis_x) ** 2 + (fy * anis_y) ** 2)
    filtro = np.exp(-(r / max(escala_ciclos, 1e-3)) ** 2)
    if pendiente > 0:
        filtro = filtro / np.maximum(r, 1.0) ** pendiente
    filtro[0, 0] = 0.0
    blanco = rng.standard_normal((n, n))
    campo = np.real(np.fft.ifft2(np.fft.fft2(blanco) * filtro))
    campo -= campo.mean()
    campo /= campo.std() + 1e-9
    return campo


def norm01(a):
    a = a - a.min()
    return a / (a.max() + 1e-9)


def normal_desde_altura(h, fuerza):
    """h en [0,1] -> normal tangente (x = u, y = v hacia abajo). Diferencias
    centradas con envoltura (np.roll) para que la normal tambien sea tileable."""
    dhdu = (np.roll(h, -1, axis=1) - np.roll(h, 1, axis=1)) * 0.5
    dhdv = (np.roll(h, -1, axis=0) - np.roll(h, 1, axis=0)) * 0.5
    nx = -dhdu * fuerza
    ny = -dhdv * fuerza
    nz = np.ones_like(h)
    largo = np.sqrt(nx * nx + ny * ny + nz * nz)
    n = np.stack([nx / largo, ny / largo, nz / largo], axis=-1)
    return n


def lineal_a_srgb(c):
    c = np.clip(c, 0.0, 1.0)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1.0 / 2.4) - 0.055)


def guardar(nombre, color_lineal, rugosidad, normal):
    os.makedirs(SALIDA, exist_ok=True)
    rgb = (lineal_a_srgb(color_lineal) * 255.0 + 0.5).astype(np.uint8)
    Image.fromarray(rgb, "RGB").save(os.path.join(SALIDA, nombre + "_BaseColor.png"), optimize=True)
    r = (np.clip(rugosidad, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)
    Image.fromarray(r, "L").save(os.path.join(SALIDA, nombre + "_Roughness.png"), optimize=True)
    n = ((normal * 0.5 + 0.5) * 255.0 + 0.5).astype(np.uint8)
    Image.fromarray(n, "RGB").save(os.path.join(SALIDA, nombre + "_Normal.png"), optimize=True)
    media = color_lineal.reshape(-1, 3).mean(0)
    print("{:<16} color medio lineal ({:.3f}, {:.3f}, {:.3f})  rugosidad {:.2f}..{:.2f}".format(
        nombre, media[0], media[1], media[2], float(rugosidad.min()), float(rugosidad.max())))


def gris(valor):
    return np.repeat(valor[..., None], 3, axis=-1)


# ---------------------------------------------------------------------------
# Materiales
# ---------------------------------------------------------------------------

def tela(rng):
    """Tapiz de butaca: tejido de sarga fina (hilos cada 4 px, en un mosaico
    de 0,25 m son ~2 mm), motas de uso y pelusa. Neutra: la tine la sala."""
    y, x = np.mgrid[0:TAM, 0:TAM].astype(float)
    periodo = 4.0
    # sarga: diagonal que avanza un hilo por fila
    trama = 0.5 + 0.5 * np.cos(2 * np.pi * (x + y * 0.5) / periodo)
    urdimbre = 0.5 + 0.5 * np.cos(2 * np.pi * y / periodo)
    tejido = np.maximum(trama * 0.9, urdimbre * 0.6)
    pelusa = ruido(rng, 90)
    motas = ruido(rng, 6, pendiente=0.5)
    altura = norm01(tejido * 0.7 + pelusa * 0.12)
    valor = 0.46 + 0.05 * (tejido - 0.5) + 0.025 * pelusa + 0.035 * motas
    rug = np.clip(0.86 + 0.06 * pelusa - 0.05 * norm01(motas), 0.7, 1.0)
    guardar("Tela", gris(valor), rug, normal_desde_altura(altura, 1.2))


def madera(rng):
    """Listones de nogal barnizado: veta vertical (a lo largo de v), anillos
    ondulados y poros. Ya trae su color."""
    y, x = np.mgrid[0:TAM, 0:TAM].astype(float)
    ondulacion = ruido(rng, 3, anis_x=1.0, anis_y=6.0) * 9.0
    veta_larga = ruido(rng, 40, anis_x=1.0, anis_y=25.0)  # fibras largas en v
    anillos = 0.5 + 0.5 * np.sin(2 * np.pi * (x + ondulacion) / 23.0 + ruido(rng, 4) * 0.8)
    anillos = anillos ** 3
    poros = np.clip(ruido(rng, 160, anis_x=1.0, anis_y=12.0), 1.2, 4.0) - 1.2
    t = np.clip(0.55 * anillos + 0.18 * veta_larga + 0.35, 0.0, 1.0)
    claro = np.array([0.30, 0.165, 0.075])
    oscuro = np.array([0.105, 0.050, 0.022])
    color = oscuro + (claro - oscuro) * t[..., None]
    color *= (1.0 - 0.35 * poros[..., None])
    rug = np.clip(0.42 + 0.10 * (1 - t) + 0.25 * poros, 0.3, 0.8)
    altura = norm01(0.4 * t - 0.8 * poros + 0.1 * veta_larga)
    guardar("Madera", color, rug, normal_desde_altura(altura, 1.5))


def alfombra(rng):
    """Alfombra de bucle: grano muy fino, surcos suaves en una direccion y
    manchas grandes de desgaste. Neutra."""
    y, x = np.mgrid[0:TAM, 0:TAM].astype(float)
    bucle = ruido(rng, 170)
    hileras = 0.5 + 0.5 * np.cos(2 * np.pi * y / 3.0)
    manchas = ruido(rng, 3, pendiente=0.3)
    moteado = np.clip(ruido(rng, 120), 1.4, 5) - 1.4
    valor = 0.45 + 0.07 * bucle + 0.03 * manchas + 0.12 * moteado + 0.02 * (hileras - 0.5)
    rug = np.clip(0.93 + 0.04 * bucle, 0.85, 1.0)
    altura = norm01(bucle + 0.5 * hileras)
    guardar("Alfombra", gris(valor), rug, normal_desde_altura(altura, 2.2))


def metal_cepillado(rng):
    """Acero inoxidable cepillado: rayas largas a lo largo de u. Neutro
    (el material lo usa metalico, con Tinte ~0,5)."""
    rayas = ruido(rng, 200, anis_x=60.0, anis_y=1.0)
    rayas_suaves = ruido(rng, 30, anis_x=20.0, anis_y=1.0)
    manchas = ruido(rng, 3)
    valor = 0.62 + 0.035 * rayas + 0.02 * rayas_suaves + 0.015 * manchas
    rug = np.clip(0.30 + 0.06 * rayas + 0.05 * manchas, 0.18, 0.5)
    altura = norm01(rayas * 0.6 + rayas_suaves * 0.4)
    guardar("MetalCepillado", gris(valor), rug, normal_desde_altura(altura, 0.35))


def fieltro(rng):
    """Panel acustico forrado en tela: fibra corta y ondulaciones suaves.
    Neutro, muy mate."""
    fibra = ruido(rng, 110, pendiente=0.2)
    ondas = ruido(rng, 4)
    valor = 0.47 + 0.03 * fibra + 0.02 * ondas
    rug = np.clip(0.95 + 0.03 * fibra, 0.88, 1.0)
    altura = norm01(fibra + 0.6 * ondas)
    guardar("Fieltro", gris(valor), rug, normal_desde_altura(altura, 1.4))


def tarima(rng):
    """Tarima de escenario pintada de negro: tablas de 0,14 m (en un mosaico
    de 1 m), rayones claros y zonas pulidas por el paso."""
    y, x = np.mgrid[0:TAM, 0:TAM].astype(float)
    ancho_tabla = TAM / 7.0
    junta = np.abs(((x % ancho_tabla) / ancho_tabla) - 0.5) > 0.49
    uso = norm01(ruido(rng, 3))
    rayones = np.clip(ruido(rng, 220, anis_x=1.0, anis_y=40.0), 2.2, 6.0) - 2.2
    rayones += np.clip(ruido(rng, 220, anis_x=35.0, anis_y=1.0), 2.4, 6.0) - 2.4
    valor = 0.030 + 0.012 * uso + 0.05 * rayones
    valor = np.where(junta, 0.012, valor)
    rug = np.clip(0.72 - 0.25 * uso + 0.15 * rayones, 0.35, 0.95)
    altura = norm01(np.where(junta, 0.0, 1.0) - 0.2 * rayones)
    guardar("Tarima", gris(valor), rug, normal_desde_altura(altura, 2.0))


def pintura(rng):
    """Pintura satinada sobre metal (puertas, marcos, consola): piel de
    naranja muy suave. Neutra."""
    piel = ruido(rng, 60)
    manchas = ruido(rng, 4)
    valor = 0.48 + 0.01 * piel + 0.015 * manchas
    rug = np.clip(0.40 + 0.04 * piel + 0.05 * manchas, 0.3, 0.55)
    altura = norm01(piel)
    guardar("Pintura", gris(valor), rug, normal_desde_altura(altura, 0.3))


def senal_salida():
    """Cara de la senal de salida: fondo verde, figura y texto blancos."""
    ancho, alto = 512, 192
    img = Image.new("RGB", (ancho, alto), (8, 150, 60))
    d = ImageDraw.Draw(img)
    d.rectangle([4, 4, ancho - 5, alto - 5], outline=(235, 255, 240), width=4)
    fuente = None
    for ruta in (r"C:\Windows\Fonts\arialbd.ttf", r"C:\Windows\Fonts\segoeuib.ttf"):
        if os.path.isfile(ruta):
            fuente = ImageFont.truetype(ruta, 78)
            break
    if fuente is None:
        fuente = ImageFont.load_default()
    d.text((166, alto / 2 + 2), "SALIDA", fill=(240, 255, 244), font=fuente, anchor="lm")
    # figura corriendo muy simplificada + flecha
    blanco = (240, 255, 244)
    d.ellipse([70, 34, 98, 62], fill=blanco)
    d.line([(84, 66), (74, 116)], fill=blanco, width=16)
    d.line([(74, 116), (104, 156)], fill=blanco, width=14)
    d.line([(74, 116), (44, 150)], fill=blanco, width=14)
    d.line([(80, 80), (112, 100)], fill=blanco, width=12)
    d.line([(80, 80), (50, 96)], fill=blanco, width=12)
    d.polygon([(120, 96), (150, 70), (150, 122)], fill=blanco)
    os.makedirs(SALIDA, exist_ok=True)
    img.save(os.path.join(SALIDA, "SenalSalida_BaseColor.png"), optimize=True)
    print("SenalSalida      {}x{}".format(ancho, alto))


def main():
    rng = np.random.default_rng(20260918)
    for fn in (tela, madera, alfombra, metal_cepillado, fieltro, tarima, pintura):
        fn(rng)
    senal_salida()
    total = sum(os.path.getsize(os.path.join(SALIDA, f)) for f in os.listdir(SALIDA))
    print("Total en {}: {:.1f} MB".format(SALIDA, total / 1e6))


if __name__ == "__main__":
    main()
