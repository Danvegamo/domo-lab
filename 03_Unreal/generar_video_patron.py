# -*- coding: utf-8 -*-
"""
generar_video_patron.py
=======================

Genera el video de prueba de la cupula: el patron de
00_TouchDesigner/shaders/patron.frag como MP4 H.264 de 4096 x 2048, con un
contador de cuadros (para ver que el video corre) y un pitido por segundo en
el audio (para ver que el audio sigue al cue).

    python 03_Unreal/generar_video_patron.py [salida.mp4] [--segundos 12]
        [--formato 360|domemaster|vr180]

Sin salida, escribe 03_Unreal/DomoVR/Content/Movies/patron_4096x2048.mp4, que
es el primer cue de la playlist de ejemplo (03_Unreal/Movies_ejemplo). Ese
archivo no va al repositorio (.gitignore): se regenera con este script.

Con --formato domemaster sale el mismo patron como domemaster de 2048 x 2048
(cenit al centro, frente abajo; la cuenta de domo_mapping.frag en su modo 0),
y con --formato vr180 la mitad del frente (u 0.25 a 0.75) como cuadro de
2048 x 2048. En la cupula tienen que verse igual que el 360 (el vr180, solo
la mitad del frente): asi se comprueban los formatos 1 y 2 del material.

Necesita Pillow y ffmpeg en el PATH. Corre fuera de Unreal.

Reglas del patron (iguales a patron.frag; v = 0 abajo, v = 1 arriba):
  rojo     v 0.00-0.25   bajo el horizonte, lejos
  amarillo v 0.25-0.50   justo bajo el horizonte
  verde    v 0.50-0.75   la cupula, del horizonte a 45 grados
  cian     v 0.75-1.00   la cupula, de 45 grados al cenit
  negro    meridianos cada 45 grados (u cada 0.125); el de u = 0, mas grueso,
           es la costura del lienzo (azimut 180, detras)
  blanco   cuadro en u 0.5, v 0.75: el frente, a 45 grados de elevacion
  magenta  marca en u 0.5, v 0.97: casi el cenit
"""

import argparse
import math
import os
import shutil
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SALIDA_DEFECTO = os.path.join(SCRIPT_DIR, "DomoVR", "Content", "Movies", "patron_4096x2048.mp4")
ANCHO, ALTO = 4096, 2048


def dibujar_patron(ancho=ANCHO, alto=ALTO):
    img = Image.new("RGB", (ancho, alto))
    d = ImageDraw.Draw(img)

    def fila(v):
        # v del shader (0 abajo) -> fila de la imagen (0 arriba)
        return alto * (1.0 - v)

    def col(u):
        return ancho * u

    bandas = [(0.0, 0.25, (255, 0, 0)), (0.25, 0.5, (255, 255, 0)),
              (0.5, 0.75, (0, 255, 0)), (0.75, 1.0, (0, 255, 255))]
    for v0, v1, color in bandas:
        d.rectangle([0, fila(v1), ancho - 1, fila(v0) - 1], fill=color)

    # meridianos: mod(u, 0.125) < 0.003
    for k in range(8):
        x0 = col(k * 0.125)
        d.rectangle([x0, 0, x0 + col(0.003) - 1, alto - 1], fill=(0, 0, 0))
    # costura: u < 0.012
    d.rectangle([0, 0, col(0.012) - 1, alto - 1], fill=(0, 0, 0))
    # frente: |u - 0.5| < 0.03, |v - 0.75| < 0.06
    d.rectangle([col(0.47), fila(0.81), col(0.53) - 1, fila(0.69) - 1], fill=(255, 255, 255))
    # casi el cenit: |u - 0.5| < 0.015, |v - 0.97| < 0.03
    d.rectangle([col(0.485), fila(1.0), col(0.515) - 1, fila(0.94) - 1], fill=(255, 0, 255))
    return img


def a_domemaster(equi, lado=2048):
    """domo_mapping.frag, modo 0, con FOV 180 y sin mapping: cada pixel del
    domemaster (y arriba, cenit al centro, frente abajo) busca su direccion en
    el lienzo equirectangular."""
    src = equi.load()
    ew, eh = equi.size
    out = Image.new("RGB", (lado, lado))
    dst = out.load()
    for j in range(lado):
        py = 1.0 - 2.0 * (j + 0.5) / lado
        for i in range(lado):
            px = 2.0 * (i + 0.5) / lado - 1.0
            r = math.hypot(px, py)
            if r > 1.0:
                continue
            th = r * math.pi * 0.5
            az = math.atan2(px, -py)
            dx, dy, dz = math.sin(th) * math.sin(az), math.cos(th), math.sin(th) * math.cos(az)
            u = (math.atan2(dx, dz) / (2.0 * math.pi) + 0.5) % 1.0
            v = math.asin(max(-1.0, min(1.0, dy))) / math.pi + 0.5
            dst[i, j] = src[min(int(u * ew), ew - 1), min(int((1.0 - v) * eh), eh - 1)]
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("salida", nargs="?", default=SALIDA_DEFECTO)
    ap.add_argument("--segundos", type=float, default=12.0)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--formato", choices=["360", "domemaster", "vr180"], default="360")
    args = ap.parse_args()
    if args.salida == SALIDA_DEFECTO and args.formato != "360":
        args.salida = os.path.join(os.path.dirname(SALIDA_DEFECTO), "patron_{}_2048.mp4".format(args.formato))

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        sys.exit("No se encontro ffmpeg en el PATH.")

    os.makedirs(os.path.dirname(os.path.abspath(args.salida)), exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="patron_domo_")
    png = os.path.join(tmp, "patron.png")
    patron = dibujar_patron()
    if args.formato == "domemaster":
        patron = a_domemaster(patron)
    elif args.formato == "vr180":
        patron = patron.crop((ANCHO // 4, 0, 3 * ANCHO // 4, ALTO))
    patron.save(png)

    # Contador de cuadros sobre la banda verde, al frente (u 0.5, v ~0.6),
    # para confirmar a simple vista que el video avanza.
    fuente = "C\\:/Windows/Fonts/arial.ttf"
    texto = ("drawtext=fontfile='{f}':text='%{{frame_num}}':fontsize=120:fontcolor=black:"
             "x=(w-text_w)/2:y=h*0.36").format(f=fuente)
    cmd = [
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
        "-loop", "1", "-framerate", str(args.fps), "-i", png,
        "-f", "lavfi", "-i", "sine=frequency=440:beep_factor=4:sample_rate=48000",
        "-t", str(args.segundos),
        "-vf", texto,
        "-c:v", "libx264", "-profile:v", "high", "-level:v", "5.1", "-pix_fmt", "yuv420p",
        "-preset", "medium", "-crf", "18", "-g", str(args.fps),
        "-c:a", "aac", "-b:a", "128k", "-ac", "2",
        "-movflags", "+faststart", "-shortest",
        args.salida,
    ]
    subprocess.run(cmd, check=True)
    shutil.rmtree(tmp, ignore_errors=True)
    print("Video de prueba escrito en {}".format(os.path.abspath(args.salida)))


if __name__ == "__main__":
    main()
