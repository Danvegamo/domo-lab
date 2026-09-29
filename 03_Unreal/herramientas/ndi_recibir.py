# -*- coding: utf-8 -*-
"""
ndi_recibir.py
==============

Receptor NDI de una sola tarea, sin TouchDesigner ni NDI Tools: busca una fuente por nombre, recibe
unos segundos de video, cuenta los cuadros por segundo y guarda el ultimo cuadro como PNG. Sirve para
comprobar que Unreal esta anunciando el domemaster (03_Unreal/DomoVR: ADomeEmisorNDI) y a que cadencia.

Usa la libreria de NDI que trae el propio motor (Processing.NDI.Lib.x64.dll, plugin NDIMedia de UE 5.8)
por ctypes; no instala nada. Necesita Pillow para el PNG.

    python ndi_recibir.py Unreal_Abismo salida.png --segundos 6

Codigo de salida 0 si llego al menos un cuadro, 1 si no.
"""

import argparse
import ctypes
import os
import sys
import time

DLL = r"C:\Program Files\Epic Games\UE_5.8\Engine\Plugins\Media\NDIMedia\Binaries\ThirdParty\Win64\Processing.NDI.Lib.x64.dll"


class Fuente(ctypes.Structure):
    _fields_ = [("p_ndi_name", ctypes.c_char_p), ("p_url_address", ctypes.c_char_p)]


class CrearBusqueda(ctypes.Structure):
    _fields_ = [("show_local_sources", ctypes.c_bool), ("p_groups", ctypes.c_char_p), ("p_extra_ips", ctypes.c_char_p)]


class CrearReceptor(ctypes.Structure):
    _fields_ = [("source_to_connect_to", Fuente), ("color_format", ctypes.c_int), ("bandwidth", ctypes.c_int),
                ("allow_video_fields", ctypes.c_bool), ("p_ndi_recv_name", ctypes.c_char_p)]


class Cuadro(ctypes.Structure):
    _fields_ = [("xres", ctypes.c_int), ("yres", ctypes.c_int), ("FourCC", ctypes.c_uint32),
                ("frame_rate_N", ctypes.c_int), ("frame_rate_D", ctypes.c_int),
                ("picture_aspect_ratio", ctypes.c_float), ("frame_format_type", ctypes.c_int),
                ("timecode", ctypes.c_int64), ("p_data", ctypes.POINTER(ctypes.c_ubyte)),
                ("line_stride_in_bytes", ctypes.c_int), ("p_metadata", ctypes.c_char_p),
                ("timestamp", ctypes.c_int64)]


def main():
    ap = argparse.ArgumentParser(description="Recibe una fuente NDI y guarda un cuadro.")
    ap.add_argument("nombre", help="parte del nombre de la fuente, por ejemplo Unreal_Abismo")
    ap.add_argument("png", nargs="?", help="donde guardar el ultimo cuadro")
    ap.add_argument("--segundos", type=float, default=6.0, help="cuanto tiempo recibir (por defecto 6)")
    ap.add_argument("--espera", type=float, default=20.0, help="cuanto esperar a que aparezca la fuente (por defecto 20)")
    a = ap.parse_args()

    lib = ctypes.CDLL(os.environ.get("NDI_DLL", DLL))
    lib.NDIlib_initialize.restype = ctypes.c_bool
    if not lib.NDIlib_initialize():
        print("NDIlib_initialize fallo (la CPU no lo soporta o falta la libreria)")
        return 1
    lib.NDIlib_find_create_v2.restype = ctypes.c_void_p
    lib.NDIlib_find_create_v2.argtypes = [ctypes.POINTER(CrearBusqueda)]
    lib.NDIlib_find_wait_for_sources.restype = ctypes.c_bool
    lib.NDIlib_find_wait_for_sources.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    lib.NDIlib_find_get_current_sources.restype = ctypes.POINTER(Fuente)
    lib.NDIlib_find_get_current_sources.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
    lib.NDIlib_recv_create_v3.restype = ctypes.c_void_p
    lib.NDIlib_recv_create_v3.argtypes = [ctypes.POINTER(CrearReceptor)]
    lib.NDIlib_recv_capture_v2.restype = ctypes.c_int
    lib.NDIlib_recv_capture_v2.argtypes = [ctypes.c_void_p, ctypes.POINTER(Cuadro), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32]
    lib.NDIlib_recv_free_video_v2.argtypes = [ctypes.c_void_p, ctypes.POINTER(Cuadro)]

    crear = CrearBusqueda(True, None, None)
    busca = lib.NDIlib_find_create_v2(ctypes.byref(crear))
    elegida = None
    limite = time.time() + a.espera
    while time.time() < limite and elegida is None:
        lib.NDIlib_find_wait_for_sources(busca, 1000)
        n = ctypes.c_uint32(0)
        fuentes = lib.NDIlib_find_get_current_sources(busca, ctypes.byref(n))
        nombres = [fuentes[i].p_ndi_name.decode("utf-8", "replace") for i in range(n.value)]
        for i, nom in enumerate(nombres):
            if a.nombre.lower() in nom.lower():
                elegida = Fuente(fuentes[i].p_ndi_name, fuentes[i].p_url_address)
                break
    if elegida is None:
        print("no aparecio ninguna fuente con '%s'; vistas: %s" % (a.nombre, nombres))
        return 1
    print("fuente:", elegida.p_ndi_name.decode("utf-8", "replace"))

    rc = CrearReceptor(elegida, 0, 100, False, b"ndi_recibir")  # BGRX_BGRA, ancho de banda maximo
    rx = lib.NDIlib_recv_create_v3(ctypes.byref(rc))
    cuadros = 0
    ultimo = None
    t0 = None
    fin = time.time() + a.espera + a.segundos
    while time.time() < fin:
        v = Cuadro()
        tipo = lib.NDIlib_recv_capture_v2(rx, ctypes.byref(v), None, None, 500)
        if tipo == 1:  # video
            if t0 is None:
                t0 = time.time()
                fin = t0 + a.segundos
                print("primer cuadro: %dx%d, %d/%d fps anunciados" % (v.xres, v.yres, v.frame_rate_N, v.frame_rate_D))
            cuadros += 1
            if a.png:
                paso = v.line_stride_in_bytes or v.xres * 4
                ultimo = (v.xres, v.yres, ctypes.string_at(v.p_data, paso * v.yres), paso)
            lib.NDIlib_recv_free_video_v2(rx, ctypes.byref(v))
    if cuadros == 0:
        print("la fuente aparecio pero no llego ningun cuadro")
        return 1
    dt = max(time.time() - t0, 1e-6)
    print("%d cuadros en %.1f s: %.1f fps" % (cuadros, dt, cuadros / dt))
    if a.png and ultimo:
        from PIL import Image
        x, y, datos, paso = ultimo
        im = Image.frombuffer("RGBA", (x, y), datos, "raw", "BGRA", paso, 1).convert("RGB")
        im.save(a.png)
        print("guardado", a.png)
    return 0


if __name__ == "__main__":
    sys.exit(main())
