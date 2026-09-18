# -*- coding: utf-8 -*-
"""
realismo_sala.py
================

Materiales PBR, Nanite y detalles de escala de las tres salas (DomoVR,
DomoVR_45, DomoVR_90). Lo usa importar_sala.py en cada importacion, y tambien
se puede correr solo, headless, sobre los niveles que ya existen:

    03_Unreal\\importar_sala.ps1 -ScriptName realismo_sala.py

Corrido solo, NO reimporta el FBX ni vacia el nivel: rehace los materiales,
vuelve a asignarlos a las mallas, prende Nanite donde corresponde, cambia los
detalles (actores con la etiqueta domo_detalle) y ajusta el post proceso y el
SkyLight de cada nivel. El SpoutDomeReceiver y el DomeMediaController quedan
como estaban. Es idempotente: se puede correr las veces que haga falta.

Que hace (ver 04_Docs/02_Sala_Unreal.md, seccion "Realismo"):

1. Importa las texturas de 03_Unreal/Texturas_PBR/ (las escribe
   generar_texturas_pbr.py, numpy -> PNG de 512, tileables) a
   /Game/Sala/TexturasPBR. Si una ya existe, se reimporta encima (no se
   borra), para no romper las referencias de los materiales.
2. Arma dos materiales base en /Game/Sala/Materials:
   - M_SalaPBR: Default Lit, proyeccion triplanar en coordenadas de mundo
     (la escala de cada textura se da en METROS por mosaico, igual en las
     tres salas, sin depender de la UV de Blender), color, rugosidad y normal
     de la textura, variacion macro para que no se note la repeticion, y la
     normal en espacio de mundo. Uso Nanite marcado.
   - M_SalaEmisivo: LEDs de paso, senal de salida, monitores, vidrio de
     cabina.
3. Una instancia (MI_*) por superficie: tela de butacas, madera de listones,
   alfombra, fieltro acustico, metal cepillado, tarima, pintura de puertas.
4. Detalles: senal verde de salida sobre cada puerta; en el 180, luces de
   pasillo en el piso, anillo de luz en el borde de la tarima y monitores en
   el control; en las salas frontales, la ventana de la cabina de proyeccion
   en la pared del fondo.
"""

import math
import os
import sys

import unreal

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TEXTURAS_DIR = os.path.join(SCRIPT_DIR, "Texturas_PBR")

CARPETA_TEXTURAS = "/Game/Sala/TexturasPBR"
CARPETA_MATERIALES = "/Game/Sala/Materials"
M_PBR_PATH = CARPETA_MATERIALES + "/M_SalaPBR"
M_EMISIVO_PATH = CARPETA_MATERIALES + "/M_SalaEmisivo"

ETIQUETA_DETALLE = "domo_detalle"
CARPETA_DETALLES = "Detalles"

CUBO = "/Engine/BasicShapes/Cube.Cube"
PLANO = "/Engine/BasicShapes/Plane.Plane"
BLANCO = "/Engine/EngineResources/WhiteSquareTexture"

TEXTURAS = ["Tela", "Madera", "Alfombra", "MetalCepillado", "Fieltro", "Tarima", "Pintura"]

# Superficies. escala_m = metros que mide un mosaico de la textura en la sala.
# tinte: el color de la textura se multiplica por tinte * 2 (0.5 = la textura
# tal cual). rug_mul / rug_add ajustan la rugosidad; normal = fuerza del
# relieve; macro = variacion lenta de color (fraccion) para romper la
# repeticion.
SUPERFICIES = {
    "Tela": dict(textura="Tela", escala_m=0.30, tinte=(0.12, 0.12, 0.13), metalico=0.0,
                 rug_mul=1.0, rug_add=0.0, normal=0.8, macro=0.10),
    "Madera": dict(textura="Madera", escala_m=0.60, tinte=(0.45, 0.45, 0.45), metalico=0.0,
                   rug_mul=1.0, rug_add=0.0, normal=0.6, macro=0.12),
    "Alfombra": dict(textura="Alfombra", escala_m=0.70, tinte=(0.075, 0.078, 0.09), metalico=0.0,
                     rug_mul=1.0, rug_add=0.0, normal=0.9, macro=0.15),
    "Fieltro": dict(textura="Fieltro", escala_m=0.80, tinte=(0.05, 0.05, 0.056), metalico=0.0,
                    rug_mul=1.0, rug_add=0.0, normal=0.6, macro=0.08),
    "Metal": dict(textura="MetalCepillado", escala_m=0.50, tinte=(0.5, 0.5, 0.5), metalico=1.0,
                  rug_mul=1.0, rug_add=0.0, normal=0.4, macro=0.05),
    "Tarima": dict(textura="Tarima", escala_m=1.00, tinte=(0.5, 0.5, 0.5), metalico=0.0,
                   rug_mul=1.0, rug_add=0.0, normal=0.7, macro=0.10),
    "Pintura": dict(textura="Pintura", escala_m=0.60, tinte=(0.08, 0.08, 0.085), metalico=0.0,
                    rug_mul=1.0, rug_add=0.0, normal=0.5, macro=0.05),
}

# Material logico de cada malla -> superficie, con el tinte que toque.
# Domo 180 (planetario): nombres del contrato de importar_sala.py.
MATERIALES_180 = {
    "M_Muro": ("Fieltro", None),
    "M_Madera": ("Madera", None),
    "M_Piso": ("Alfombra", None),
    "M_Butaca": ("Tela", (0.055, 0.07, 0.15)),     # azul profundo de planetario
    "M_Tarima": ("Tarima", None),
    "M_Control": ("Pintura", (0.05, 0.05, 0.055)),
    "M_Puerta": ("Pintura", (0.07, 0.066, 0.062)),
}
# Salas frontales: los nombres de material vienen del JSON de Blender. El
# tinte sale del color de trabajo del JSON (asi el rojo de las butacas de la
# 45 sigue siendo el de Blender), salvo que aqui se fije otro.
MATERIALES_FRONTALES = {
    "M_Piso": ("Alfombra", None),
    "M_Grada": ("Alfombra", (0.09, 0.09, 0.1)),
    "M_Muro": ("Fieltro", None),
    "M_Baranda": ("Metal", (0.5, 0.5, 0.5)),
    "M_Butaca": ("Tela", (0.16, 0.018, 0.022)),   # rojo de cine, algo menos saturado que el de Blender
    "M_Puerta": ("Pintura", (0.07, 0.066, 0.062)),
}

# Emisivos: color lineal e intensidad (en las unidades de emision de Unreal;
# la cupula blanca vale 1).
EMISIVOS = {
    "MI_LedAmbar": dict(color=(1.0, 0.50, 0.14), intensidad=2.0),
    "MI_LedTarima": dict(color=(0.40, 0.60, 1.0), intensidad=1.2),
    "MI_Salida": dict(color=(1.0, 1.0, 1.0), intensidad=1.6, textura="SenalSalida"),
    "MI_Monitor": dict(color=(0.55, 0.65, 0.85), intensidad=0.2),
    "MI_VidrioCabina": dict(color=(1.0, 0.72, 0.45), intensidad=0.035, rugosidad=0.05, base=(0.01, 0.01, 0.012)),
}

# Orientacion de los planos de /Engine/BasicShapes/Plane (normal +Z): con
# roll 90, pitch 0 y yaw = direccion - 90, la normal queda horizontal en la
# direccion pedida y el eje X local del plano queda horizontal. ROLL_PLANO
# (+90 o -90) elige cual de las dos caras mira hacia afuera; se midio con la
# senal de salida (texto derecho y legible desde la sala).
ROLL_PLANO = 90.0


def log(msg):
    unreal.log_warning("[realismo_sala] {}".format(msg))


def fallar(msg):
    raise RuntimeError("[realismo_sala] {}".format(msg))


# ---------------------------------------------------------------------------
# Texturas
# ---------------------------------------------------------------------------

def _importar_textura(archivo, nombre_asset, tipo):
    ruta_asset = "{}/{}".format(CARPETA_TEXTURAS, nombre_asset)
    task = unreal.AssetImportTask()
    task.set_editor_property("filename", archivo)
    task.set_editor_property("destination_path", CARPETA_TEXTURAS)
    task.set_editor_property("destination_name", nombre_asset)
    task.set_editor_property("replace_existing", True)
    task.set_editor_property("automated", True)
    task.set_editor_property("save", False)
    task.set_editor_property("factory", unreal.TextureFactory())
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    tex = unreal.EditorAssetLibrary.load_asset(ruta_asset)
    if tex is None:
        fallar("No se pudo importar {} como {}".format(archivo, ruta_asset))
    if tipo == "Normal":
        tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_NORMALMAP)
        tex.set_editor_property("srgb", False)
    elif tipo == "Roughness":
        tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_GRAYSCALE)
        tex.set_editor_property("srgb", False)
    else:
        tex.set_editor_property("srgb", True)
    unreal.EditorAssetLibrary.save_loaded_asset(tex, False)
    return tex


_cache_texturas = {}


def textura(nombre, tipo):
    clave = (nombre, tipo)
    if clave not in _cache_texturas:
        archivo = os.path.join(TEXTURAS_DIR, "{}_{}.png".format(nombre, tipo))
        if not os.path.isfile(archivo):
            fallar("Falta {}. Correr antes: python 03_Unreal/generar_texturas_pbr.py".format(archivo))
        _cache_texturas[clave] = _importar_textura(archivo, "T_{}_{}".format(nombre, tipo), tipo)
    return _cache_texturas[clave]


def importar_texturas():
    if not unreal.EditorAssetLibrary.does_directory_exist(CARPETA_TEXTURAS):
        unreal.EditorAssetLibrary.make_directory(CARPETA_TEXTURAS)
    for n in TEXTURAS:
        for t in ("BaseColor", "Roughness", "Normal"):
            textura(n, t)
    textura("SenalSalida", "BaseColor")
    log("Texturas PBR importadas en {} ({} archivos).".format(CARPETA_TEXTURAS, len(_cache_texturas)))


# ---------------------------------------------------------------------------
# Materiales base
# ---------------------------------------------------------------------------

# Codigo comun de los tres nodos Custom de M_SalaPBR. Entradas: WP (posicion
# de mundo, cm), VN (normal de vertice en mundo), Escala (m por mosaico),
# Nitidez (de la mezcla triplanar). Proyeccion: en las caras que miran a X o
# a Y la v de la textura baja con la altura (la veta de la madera queda
# vertical) y la u corre hacia la derecha de quien mira la cara; en las que
# miran a Z, u = x, v = y.
HLSL_TRIPLANAR = r"""
float3 n = normalize(VN);
float3 w = pow(abs(n), Nitidez);
w /= max(w.x + w.y + w.z, 1e-4);
float3 p = WP * (0.01 / max(Escala, 0.001));
float sx = n.x >= 0.0 ? -1.0 : 1.0;
float sy = n.y >= 0.0 ? 1.0 : -1.0;
float2 uvX = float2(p.y * sx, -p.z);
float2 uvY = float2(p.x * sy, -p.z);
float2 uvZ = float2(p.x, p.y);
"""

HLSL_COLOR = HLSL_TRIPLANAR + r"""
float3 c = Texture2DSample(TexColor, TexColorSampler, uvX).rgb * w.x
         + Texture2DSample(TexColor, TexColorSampler, uvY).rgb * w.y
         + Texture2DSample(TexColor, TexColorSampler, uvZ).rgb * w.z;
// Variacion macro: ruido de valor 3D de 1,9 m, para que la repeticion del
// mosaico no se lea a la distancia.
float3 q = WP * (0.01 / 1.9);
float3 i = floor(q);
float3 f = frac(q);
f = f * f * (3.0 - 2.0 * f);
float3 K = float3(127.1, 311.7, 74.7);
float a000 = frac(sin(dot(i + float3(0, 0, 0), K)) * 43758.5453);
float a100 = frac(sin(dot(i + float3(1, 0, 0), K)) * 43758.5453);
float a010 = frac(sin(dot(i + float3(0, 1, 0), K)) * 43758.5453);
float a110 = frac(sin(dot(i + float3(1, 1, 0), K)) * 43758.5453);
float a001 = frac(sin(dot(i + float3(0, 0, 1), K)) * 43758.5453);
float a101 = frac(sin(dot(i + float3(1, 0, 1), K)) * 43758.5453);
float a011 = frac(sin(dot(i + float3(0, 1, 1), K)) * 43758.5453);
float a111 = frac(sin(dot(i + float3(1, 1, 1), K)) * 43758.5453);
float ruido = lerp(lerp(lerp(a000, a100, f.x), lerp(a010, a110, f.x), f.y),
                   lerp(lerp(a001, a101, f.x), lerp(a011, a111, f.x), f.y), f.z);
float macro = 1.0 + Macro * (ruido * 2.0 - 1.0);
return saturate(c * Tinte * 2.0 * macro);
"""

HLSL_RUGOSIDAD = HLSL_TRIPLANAR + r"""
float r = Texture2DSample(TexRug, TexRugSampler, uvX).r * w.x
        + Texture2DSample(TexRug, TexRugSampler, uvY).r * w.y
        + Texture2DSample(TexRug, TexRugSampler, uvZ).r * w.z;
return saturate(r * RugMul + RugAdd);
"""

# Normal en espacio de MUNDO (el material lleva tangent_space_normal = False).
# Cada proyeccion suma su relieve sobre los ejes de mundo en los que corren su
# u y su v; la mezcla va sobre la normal de la geometria.
HLSL_NORMAL = HLSL_TRIPLANAR + r"""
float2 tX = (Texture2DSample(TexNorm, TexNormSampler, uvX).rg * 2.0 - 1.0) * NormalFuerza;
float2 tY = (Texture2DSample(TexNorm, TexNormSampler, uvY).rg * 2.0 - 1.0) * NormalFuerza;
float2 tZ = (Texture2DSample(TexNorm, TexNormSampler, uvZ).rg * 2.0 - 1.0) * NormalFuerza;
float3 dX = float3(0.0, sx, 0.0) * tX.x + float3(0.0, 0.0, -1.0) * tX.y;
float3 dY = float3(sy, 0.0, 0.0) * tY.x + float3(0.0, 0.0, -1.0) * tY.y;
float3 dZ = float3(1.0, 0.0, 0.0) * tZ.x + float3(0.0, 1.0, 0.0) * tZ.y;
return normalize(n + dX * w.x + dY * w.y + dZ * w.z);
"""


def _cargar_o_crear_material(ruta):
    """Material base que se rehace en su lugar (sin borrarlo), para que las
    instancias y las mallas que lo usan no pierdan la referencia."""
    mel = unreal.MaterialEditingLibrary
    if unreal.EditorAssetLibrary.does_asset_exist(ruta):
        m = unreal.EditorAssetLibrary.load_asset(ruta)
        if not isinstance(m, unreal.Material):
            unreal.EditorAssetLibrary.delete_asset(ruta)
            m = None
        else:
            mel.delete_all_material_expressions(m)
            return m
    carpeta, nombre = ruta.rsplit("/", 1)
    m = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
        nombre, carpeta, unreal.Material, unreal.MaterialFactoryNew())
    if m is None:
        fallar("No se pudo crear {}".format(ruta))
    return m


def _custom(material, descripcion, codigo, tipo_salida, entradas, x, y):
    mel = unreal.MaterialEditingLibrary
    c = mel.create_material_expression(material, unreal.MaterialExpressionCustom, x, y)
    c.set_editor_property("description", descripcion)
    c.set_editor_property("code", codigo)
    c.set_editor_property("output_type", tipo_salida)
    lista = []
    for nombre in entradas:
        ci = unreal.CustomInput()
        ci.set_editor_property("input_name", nombre)
        lista.append(ci)
    c.set_editor_property("inputs", lista)
    return c


def _conectar(desde, pin, hacia, entrada):
    if not unreal.MaterialEditingLibrary.connect_material_expressions(desde, pin, hacia, entrada):
        fallar("No se pudo conectar {} -> {}.{}".format(desde.get_name(), hacia.get_name(), entrada))


def crear_material_pbr():
    mel = unreal.MaterialEditingLibrary
    m = _cargar_o_crear_material(M_PBR_PATH)
    m.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_DEFAULT_LIT)
    m.set_editor_property("tangent_space_normal", False)
    m.set_editor_property("two_sided", False)

    wp = mel.create_material_expression(m, unreal.MaterialExpressionWorldPosition, -1400, 0)
    vn = mel.create_material_expression(m, unreal.MaterialExpressionVertexNormalWS, -1400, 120)

    def escalar(nombre, valor, y):
        e = mel.create_material_expression(m, unreal.MaterialExpressionScalarParameter, -1400, y)
        e.set_editor_property("parameter_name", nombre)
        e.set_editor_property("default_value", valor)
        e.set_editor_property("group", "Sala")
        return e

    def tex_obj(nombre, tex, sampler, y):
        e = mel.create_material_expression(m, unreal.MaterialExpressionTextureObjectParameter, -1400, y)
        e.set_editor_property("parameter_name", nombre)
        e.set_editor_property("texture", tex)
        e.set_editor_property("sampler_type", sampler)
        e.set_editor_property("group", "Texturas")
        return e

    escala = escalar("EscalaM", 0.6, 240)
    nitidez = escalar("Nitidez", 6.0, 320)
    macro = escalar("Macro", 0.1, 400)
    rug_mul = escalar("RugMul", 1.0, 480)
    rug_add = escalar("RugAdd", 0.0, 560)
    normal_f = escalar("NormalFuerza", 1.0, 640)
    metal = escalar("Metallic", 0.0, 720)
    tinte = mel.create_material_expression(m, unreal.MaterialExpressionVectorParameter, -1400, 800)
    tinte.set_editor_property("parameter_name", "Tinte")
    tinte.set_editor_property("default_value", unreal.LinearColor(0.5, 0.5, 0.5, 1.0))
    tinte.set_editor_property("group", "Sala")

    t_color = tex_obj("TexColor", textura("Pintura", "BaseColor"), unreal.MaterialSamplerType.SAMPLERTYPE_COLOR, 900)
    t_rug = tex_obj("TexRug", textura("Pintura", "Roughness"), unreal.MaterialSamplerType.SAMPLERTYPE_GRAYSCALE, 1000)
    t_norm = tex_obj("TexNorm", textura("Pintura", "Normal"), unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL, 1100)

    comunes = ["WP", "VN", "Escala", "Nitidez"]
    c_color = _custom(m, "TriplanarColor", HLSL_COLOR, unreal.CustomMaterialOutputType.CMOT_FLOAT3,
                      comunes + ["TexColor", "Tinte", "Macro"], -800, -200)
    c_rug = _custom(m, "TriplanarRugosidad", HLSL_RUGOSIDAD, unreal.CustomMaterialOutputType.CMOT_FLOAT1,
                    comunes + ["TexRug", "RugMul", "RugAdd"], -800, 200)
    c_norm = _custom(m, "TriplanarNormal", HLSL_NORMAL, unreal.CustomMaterialOutputType.CMOT_FLOAT3,
                     comunes + ["TexNorm", "NormalFuerza"], -800, 600)
    for c in (c_color, c_rug, c_norm):
        _conectar(wp, "", c, "WP")
        _conectar(vn, "", c, "VN")
        _conectar(escala, "", c, "Escala")
        _conectar(nitidez, "", c, "Nitidez")
    _conectar(t_color, "", c_color, "TexColor")
    _conectar(tinte, "RGB", c_color, "Tinte")
    _conectar(macro, "", c_color, "Macro")
    _conectar(t_rug, "", c_rug, "TexRug")
    _conectar(rug_mul, "", c_rug, "RugMul")
    _conectar(rug_add, "", c_rug, "RugAdd")
    _conectar(t_norm, "", c_norm, "TexNorm")
    _conectar(normal_f, "", c_norm, "NormalFuerza")

    mel.connect_material_property(c_color, "", unreal.MaterialProperty.MP_BASE_COLOR)
    mel.connect_material_property(c_rug, "", unreal.MaterialProperty.MP_ROUGHNESS)
    mel.connect_material_property(c_norm, "", unreal.MaterialProperty.MP_NORMAL)
    mel.connect_material_property(metal, "", unreal.MaterialProperty.MP_METALLIC)

    mel.set_base_material_usage(m, unreal.MaterialUsage.MATUSAGE_NANITE, True)
    mel.set_base_material_usage(m, unreal.MaterialUsage.MATUSAGE_STATIC_LIGHTING, True)
    mel.recompile_material(m)
    unreal.EditorAssetLibrary.save_loaded_asset(m, False)
    log("M_SalaPBR (triplanar en metros, normal en mundo, uso Nanite) listo.")
    return m


def crear_material_emisivo():
    mel = unreal.MaterialEditingLibrary
    m = _cargar_o_crear_material(M_EMISIVO_PATH)
    m.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_DEFAULT_LIT)
    base = mel.create_material_expression(m, unreal.MaterialExpressionVectorParameter, -700, -200)
    base.set_editor_property("parameter_name", "BaseColor")
    base.set_editor_property("default_value", unreal.LinearColor(0.02, 0.02, 0.02, 1.0))
    rug = mel.create_material_expression(m, unreal.MaterialExpressionScalarParameter, -700, -60)
    rug.set_editor_property("parameter_name", "Roughness")
    rug.set_editor_property("default_value", 0.5)
    color = mel.create_material_expression(m, unreal.MaterialExpressionVectorParameter, -700, 60)
    color.set_editor_property("parameter_name", "Color")
    color.set_editor_property("default_value", unreal.LinearColor(1.0, 1.0, 1.0, 1.0))
    inten = mel.create_material_expression(m, unreal.MaterialExpressionScalarParameter, -700, 200)
    inten.set_editor_property("parameter_name", "Intensidad")
    inten.set_editor_property("default_value", 1.0)
    tex = mel.create_material_expression(m, unreal.MaterialExpressionTextureSampleParameter2D, -700, 300)
    tex.set_editor_property("parameter_name", "TexturaEmisiva")
    blanco = unreal.EditorAssetLibrary.load_asset(BLANCO)
    if blanco is not None:
        tex.set_editor_property("texture", blanco)
    tex.set_editor_property("sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_COLOR)
    m1 = mel.create_material_expression(m, unreal.MaterialExpressionMultiply, -400, 100)
    _conectar(color, "RGB", m1, "A")
    _conectar(inten, "", m1, "B")
    m2 = mel.create_material_expression(m, unreal.MaterialExpressionMultiply, -250, 150)
    _conectar(m1, "", m2, "A")
    _conectar(tex, "RGB", m2, "B")
    mel.connect_material_property(base, "RGB", unreal.MaterialProperty.MP_BASE_COLOR)
    mel.connect_material_property(rug, "", unreal.MaterialProperty.MP_ROUGHNESS)
    mel.connect_material_property(m2, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    mel.set_base_material_usage(m, unreal.MaterialUsage.MATUSAGE_NANITE, True)
    mel.recompile_material(m)
    unreal.EditorAssetLibrary.save_loaded_asset(m, False)
    log("M_SalaEmisivo listo.")
    return m


_maestros = {}


def preparar():
    """Texturas y materiales base. Idempotente; se llama una vez por corrida."""
    if _maestros:
        return _maestros
    importar_texturas()
    _maestros["pbr"] = crear_material_pbr()
    _maestros["emisivo"] = crear_material_emisivo()
    return _maestros


# ---------------------------------------------------------------------------
# Instancias
# ---------------------------------------------------------------------------

def _instancia(ruta, padre):
    mel = unreal.MaterialEditingLibrary
    mi = None
    if unreal.EditorAssetLibrary.does_asset_exist(ruta):
        mi = unreal.EditorAssetLibrary.load_asset(ruta)
        if not isinstance(mi, unreal.MaterialInstanceConstant):
            # Un Material viejo con el mismo nombre (M_Muro, M_Piso, ...).
            unreal.EditorAssetLibrary.delete_asset(ruta)
            mi = None
    if mi is None:
        carpeta, nombre = ruta.rsplit("/", 1)
        if not unreal.EditorAssetLibrary.does_directory_exist(carpeta):
            unreal.EditorAssetLibrary.make_directory(carpeta)
        mi = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
            nombre, carpeta, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
        if mi is None:
            fallar("No se pudo crear la instancia {}".format(ruta))
    mel.set_material_instance_parent(mi, padre)
    return mi


def instancia_superficie(ruta, superficie, tinte=None):
    mel = unreal.MaterialEditingLibrary
    s = dict(SUPERFICIES[superficie])
    if tinte is not None:
        s["tinte"] = tinte
    mi = _instancia(ruta, preparar()["pbr"])
    mel.set_material_instance_texture_parameter_value(mi, "TexColor", textura(s["textura"], "BaseColor"))
    mel.set_material_instance_texture_parameter_value(mi, "TexRug", textura(s["textura"], "Roughness"))
    mel.set_material_instance_texture_parameter_value(mi, "TexNorm", textura(s["textura"], "Normal"))
    mel.set_material_instance_scalar_parameter_value(mi, "EscalaM", s["escala_m"])
    mel.set_material_instance_scalar_parameter_value(mi, "Macro", s["macro"])
    mel.set_material_instance_scalar_parameter_value(mi, "RugMul", s["rug_mul"])
    mel.set_material_instance_scalar_parameter_value(mi, "RugAdd", s["rug_add"])
    mel.set_material_instance_scalar_parameter_value(mi, "NormalFuerza", s["normal"])
    mel.set_material_instance_scalar_parameter_value(mi, "Metallic", s["metalico"])
    t = s["tinte"]
    mel.set_material_instance_vector_parameter_value(mi, "Tinte", unreal.LinearColor(t[0], t[1], t[2], 1.0))
    mel.update_material_instance(mi)
    unreal.EditorAssetLibrary.save_loaded_asset(mi, False)
    return mi


def instancia_emisiva(ruta, color, intensidad, rugosidad=0.5, base=(0.02, 0.02, 0.02), textura_nombre=None):
    mel = unreal.MaterialEditingLibrary
    mi = _instancia(ruta, preparar()["emisivo"])
    mel.set_material_instance_vector_parameter_value(mi, "Color", unreal.LinearColor(color[0], color[1], color[2], 1.0))
    mel.set_material_instance_scalar_parameter_value(mi, "Intensidad", float(intensidad))
    mel.set_material_instance_scalar_parameter_value(mi, "Roughness", float(rugosidad))
    mel.set_material_instance_vector_parameter_value(mi, "BaseColor", unreal.LinearColor(base[0], base[1], base[2], 1.0))
    if textura_nombre:
        mel.set_material_instance_texture_parameter_value(mi, "TexturaEmisiva", textura(textura_nombre, "BaseColor"))
    mel.update_material_instance(mi)
    unreal.EditorAssetLibrary.save_loaded_asset(mi, False)
    return mi


def materiales_de_sala(fov, datos_sala, carpeta):
    """Devuelve {nombre_logico: MaterialInstance} para la sala. carpeta es
    /Game/Sala/Materials (180) o /Game/Sala/Domo_45/Materials (frontales).
    Las instancias se llaman MI_<nombre sin M_>."""
    res = {}
    if datos_sala is None:
        for nombre, (sup, tinte) in MATERIALES_180.items():
            res[nombre] = instancia_superficie("{}/MI_{}".format(carpeta, nombre[2:]), sup, tinte)
    else:
        for nombre, datos in sorted(datos_sala["materiales"].items()):
            ruta = "{}/MI_{}".format(carpeta, nombre[2:])
            if datos.get("emision"):
                em = datos["emision"]
                res[nombre] = instancia_emisiva(ruta, em, EMISIVOS["MI_LedAmbar"]["intensidad"])
                continue
            sup, tinte = MATERIALES_FRONTALES.get(nombre, ("Pintura", None))
            if tinte is None and sup != "Metal":
                c = datos["color"]
                tinte = (c[0], c[1], c[2])
            res[nombre] = instancia_superficie(ruta, sup, tinte)
    log("Instancias de material de la sala {:g}: {}".format(fov, sorted(res.keys())))
    return res


def instancias_detalle():
    res = {}
    for nombre, e in EMISIVOS.items():
        res[nombre] = instancia_emisiva("{}/{}".format(CARPETA_MATERIALES, nombre), e["color"], e["intensidad"],
                                        e.get("rugosidad", 0.5), e.get("base", (0.02, 0.02, 0.02)), e.get("textura"))
    res["MI_CajaSenal"] = instancia_superficie("{}/MI_CajaSenal".format(CARPETA_MATERIALES), "Pintura",
                                               (0.02, 0.02, 0.022))
    res["MI_MarcoCabina"] = instancia_superficie("{}/MI_MarcoCabina".format(CARPETA_MATERIALES), "Metal",
                                                 (0.18, 0.18, 0.19))
    return res


def borrar_materiales_viejos(carpeta, nombres):
    """Los M_Muro, M_Piso, ... de antes (Materials con color plano o con la
    textura horneada) ya no los usa nadie: se borran, y con ellos las
    texturas horneadas de /Game/Sala/Textures."""
    for n in nombres:
        ruta = "{}/{}".format(carpeta, n)
        if unreal.EditorAssetLibrary.does_asset_exist(ruta):
            a = unreal.EditorAssetLibrary.load_asset(ruta)
            if isinstance(a, unreal.Material):
                unreal.EditorAssetLibrary.delete_asset(ruta)
                log("Borrado el material viejo {}".format(ruta))


# ---------------------------------------------------------------------------
# Nanite
# ---------------------------------------------------------------------------

def aplicar_nanite(mesh, nombre):
    """Nanite en todas las mallas estaticas salvo la cupula: SM_Domo lleva un
    material de cielo (is_sky) que el SkyLight captura cada cuadro, y esa
    captura dibuja la malla por la ruta clasica. La cupula se queda sin
    Nanite. fallback_relative_error = 0 para que el trazado de rayos use la
    malla completa (son mallas livianas)."""
    querer = nombre != "SM_Domo"
    sub = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    try:
        ajustes = sub.get_nanite_settings(mesh)
    except Exception:  # noqa: BLE001
        ajustes = mesh.get_editor_property("nanite_settings")
    cambia = bool(ajustes.get_editor_property("enabled")) != querer
    ajustes.set_editor_property("enabled", querer)
    for prop, valor in (("fallback_relative_error", 0.0), ("fallback_percent_triangles", 1.0)):
        try:
            if abs(float(ajustes.get_editor_property(prop)) - valor) > 1e-6:
                ajustes.set_editor_property(prop, valor)
                cambia = True
        except Exception:  # noqa: BLE001
            pass
    if cambia:
        try:
            sub.set_nanite_settings(mesh, ajustes, True)
        except Exception:  # noqa: BLE001
            mesh.set_editor_property("nanite_settings", ajustes)
        unreal.EditorAssetLibrary.save_loaded_asset(mesh, False)
    return querer


# ---------------------------------------------------------------------------
# Detalles en el nivel
# ---------------------------------------------------------------------------

def borrar_detalles(actor_subsystem):
    viejos = [a for a in actor_subsystem.get_all_level_actors() if a.actor_has_tag(ETIQUETA_DETALLE)]
    if viejos:
        actor_subsystem.destroy_actors(viejos)
    return len(viejos)


def _pieza(actor_subsystem, malla, material, pos_cm, tam_m, rot, etiqueta, sombra=True):
    """Un StaticMeshActor con una forma basica del motor (cubo o plano de
    100 uu), escalada a tam_m metros."""
    a = actor_subsystem.spawn_actor_from_class(unreal.StaticMeshActor, pos_cm, rot)
    if a is None:
        fallar("spawn_actor_from_class devolvio None para {}".format(etiqueta))
    comp = a.static_mesh_component
    comp.set_static_mesh(malla)
    comp.set_material(0, material)
    comp.set_editor_property("cast_shadow", sombra)
    a.set_actor_scale3d(unreal.Vector(tam_m[0], tam_m[1], tam_m[2]))
    a.set_actor_label(etiqueta)
    a.tags = [unreal.Name(ETIQUETA_DETALLE)]
    a.set_folder_path(CARPETA_DETALLES)
    return a


def _rot_plano(yaw_deg):
    """Plano de Engine (normal +Z) girado para que su normal apunte en
    direccion yaw (horizontal)."""
    return unreal.Rotator(roll=ROLL_PLANO, pitch=0.0, yaw=yaw_deg - 90.0 * (ROLL_PLANO / 90.0))


def _semiejes(fov, datos_sala):
    if datos_sala is None:
        return 11.5, 11.5
    a, b = datos_sala["pantalla"]["planta_elipse_m"]
    return a / 2.0, b / 2.0


def senales_salida(actor_subsystem, mats, fov, datos_sala):
    cubo = unreal.EditorAssetLibrary.load_asset(CUBO)
    plano = unreal.EditorAssetLibrary.load_asset(PLANO)
    ax, by = _semiejes(fov, datos_sala)
    n = 0
    for actor in actor_subsystem.get_all_level_actors():
        etiqueta = actor.get_actor_label()
        if not (etiqueta.startswith("Puerta_") and etiqueta.endswith("_Actor")):
            continue
        origen, ext = actor.get_actor_bounds(False)
        x, y = origen.x / 100.0, origen.y / 100.0
        # normal hacia adentro de la elipse (circulo en el 180)
        nx, ny = -x / (ax * ax), -y / (by * by)
        largo = math.hypot(nx, ny) or 1.0
        nx, ny = nx / largo, ny / largo
        yaw = math.degrees(math.atan2(ny, nx))
        z_top = (origen.z + ext.z) / 100.0
        cz = z_top + 0.22
        # caja
        cx, cy = x + nx * 0.10, y + ny * 0.10
        _pieza(actor_subsystem, cubo, mats["MI_CajaSenal"], unreal.Vector(cx * 100, cy * 100, cz * 100),
               (0.06, 0.44, 0.19), unreal.Rotator(0.0, 0.0, yaw), "Salida_Caja_{}".format(etiqueta[7:9]))
        # cara luminosa, 1 cm delante de la caja
        fx, fy = x + nx * 0.135, y + ny * 0.135
        _pieza(actor_subsystem, plano, mats["MI_Salida"], unreal.Vector(fx * 100, fy * 100, cz * 100),
               (0.40, 0.15, 1.0), _rot_plano(yaw), "Salida_Cara_{}".format(etiqueta[7:9]), sombra=False)
        log("Senal de salida sobre {} en ({:.0f}, {:.0f}, {:.0f}) cm, mirando a yaw {:.0f}".format(
            etiqueta, fx * 100, fy * 100, cz * 100, yaw))
        n += 1
    return n


def detalles_180(actor_subsystem, mats):
    """Luces de pasillo (en el piso, en el eje de cada pasillo entre cunas),
    anillo de luz en el borde de la tarima y monitores en la consola de
    control. Angulos como en 01_Blender/generar_sala_domo.py
    (calcular_layout_sala): control de 7 m de arco centrado en -X, 6 cunas en
    el resto. La planta es simetrica en Y, asi que el cambio de signo de Y
    Blender -> Unreal no mueve nada."""
    cubo = unreal.EditorAssetLibrary.load_asset(CUBO)
    plano = unreal.EditorAssetLibrary.load_asset(PLANO)
    radio, ancho_control = 11.5, 7.0
    ang_control = math.degrees(ancho_control / radio)
    paso = (360.0 - ang_control) / 6.0
    inicio = 180.0 + ang_control / 2.0
    n = 0
    for k in range(7):
        ang = math.radians(inicio + k * paso)
        # los pasillos que bordean el control llegan solo hasta su antepecho
        r_max = 6.3 if k in (0, 6) else 10.9
        r = 2.6
        i = 0
        while r <= r_max:
            x, y = r * math.cos(ang), -r * math.sin(ang)
            _pieza(actor_subsystem, cubo, mats["MI_LedAmbar"], unreal.Vector(x * 100, y * 100, 1.2),
                   (0.07, 0.035, 0.024), unreal.Rotator(0.0, 0.0, -math.degrees(ang)),
                   "LedPasillo_{}_{:02d}".format(k, i), sombra=False)
            r += 1.2
            i += 1
            n += 1
    # anillo en el borde superior de la tarima (r 1,5 m, 1 m de alto)
    segs = 72
    r_t = 1.508
    largo = 2 * math.pi * r_t / segs * 0.8
    for i in range(segs):
        a = 2 * math.pi * (i + 0.5) / segs
        x, y = r_t * math.cos(a), r_t * math.sin(a)
        _pieza(actor_subsystem, cubo, mats["MI_LedTarima"], unreal.Vector(x * 100, y * 100, 97.0),
               (0.012, largo, 0.018), unreal.Rotator(0.0, 0.0, math.degrees(a)),
               "LedTarima_{:02d}".format(i), sombra=False)
    n += segs
    # monitores: la fila de monitores de la consola esta en x = -9,45 m,
    # de 0,80 a 1,30 m de alto; se ponen tres pantallas encendidas, tenues.
    for j, yy in enumerate((-1.3, 0.0, 1.3)):
        _pieza(actor_subsystem, plano, mats["MI_Monitor"], unreal.Vector(-944.0, yy * 100, 105.0),
               (1.10, 0.42, 1.0), _rot_plano(0.0), "Monitor_{}".format(j + 1), sombra=False)
        n += 1
    return n


def detalles_frontal(actor_subsystem, mats, fov, datos_sala):
    """Ventana de la cabina de proyeccion en la pared del fondo (-X), por
    encima de la ultima fila o plataforma: vidrio oscuro con un resplandor
    calido muy tenue y un marco de metal."""
    cubo = unreal.EditorAssetLibrary.load_asset(CUBO)
    plano = unreal.EditorAssetLibrary.load_asset(PLANO)
    ax, by = _semiejes(fov, datos_sala)
    sala = datos_sala["sala"]
    if sala.get("filas"):
        z_ultimo = max(f["z_piso_m"] for f in sala["filas"])
    else:
        z_ultimo = max(p.get("z_piso_m", 0.0) for p in sala.get("plataformas", [{"z_piso_m": 2.0}]))
    ancho, alto = 4.0, 1.1
    z0 = z_ultimo + 2.3
    zc = z0 + alto / 2.0
    y_borde = ancho / 2.0 + 0.1
    x_pared = -ax * math.sqrt(max(0.0, 1.0 - (y_borde / by) ** 2))
    x_vidrio = x_pared + 0.03
    _pieza(actor_subsystem, plano, mats["MI_VidrioCabina"], unreal.Vector(x_vidrio * 100, 0.0, zc * 100),
           (ancho, alto, 1.0), _rot_plano(0.0), "Cabina_Vidrio", sombra=False)
    marco = 0.08
    for nombre, pos, tam in (
            ("Cabina_MarcoInf", (x_vidrio, 0.0, z0 - marco / 2), (0.12, ancho + 2 * marco, marco)),
            ("Cabina_MarcoSup", (x_vidrio, 0.0, z0 + alto + marco / 2), (0.12, ancho + 2 * marco, marco)),
            ("Cabina_MarcoIzq", (x_vidrio, -(ancho / 2 + marco / 2), zc), (0.12, marco, alto)),
            ("Cabina_MarcoDer", (x_vidrio, ancho / 2 + marco / 2, zc), (0.12, marco, alto)),
            ("Cabina_Parteluz", (x_vidrio, 0.0, zc), (0.06, 0.04, alto))):
        _pieza(actor_subsystem, cubo, mats["MI_MarcoCabina"],
               unreal.Vector(pos[0] * 100, pos[1] * 100, pos[2] * 100), tam, unreal.Rotator(0, 0, 0), nombre)
    return 6


def colocar_detalles(actor_subsystem, fov, datos_sala):
    mats = instancias_detalle()
    borrados = borrar_detalles(actor_subsystem)
    n = senales_salida(actor_subsystem, mats, fov, datos_sala)
    if datos_sala is None:
        n += detalles_180(actor_subsystem, mats)
    else:
        n += detalles_frontal(actor_subsystem, mats, fov, datos_sala)
    log("Detalles de la sala {:g}: {} actores (se reemplazaron {}).".format(fov, n, borrados))
    return n


# ---------------------------------------------------------------------------
# Post proceso y SkyLight
# ---------------------------------------------------------------------------

# Luz de la sala. La cupula es la unica fuente: el SkyLight la captura y
# Lumen la reparte. SkyLight 1 seria la luminancia de la cupula tal cual; se
# usa 2,5 (una sala real tiene la cupula mas reflectiva que un emisivo de 1 y
# el ojo se adapta a la oscuridad), con el rebote de Lumen sin multiplicar.
# Antes eran SkyLight 2 con el rebote por 8: la sala salia saturada del color
# del contenido. Exposicion -0,8 para que el papel blanco del video no se
# queme.
SKYLIGHT_INTENSIDAD = 2.5
SKYLIGHT_RESOLUCION = 256
REBOTE_INDIRECTO = 1.0
EXPOSICION_BIAS = -0.8


def ajustar_post_proceso(ppv):
    s = ppv.settings
    def poner(prop, valor):
        s.set_editor_property("override_" + prop, True)
        s.set_editor_property(prop, valor)
    poner("auto_exposure_method", unreal.AutoExposureMethod.AEM_MANUAL)
    poner("auto_exposure_apply_physical_camera_exposure", False)
    poner("auto_exposure_bias", EXPOSICION_BIAS)
    poner("auto_exposure_min_brightness", 1.0)
    poner("auto_exposure_max_brightness", 1.0)
    poner("indirect_lighting_intensity", REBOTE_INDIRECTO)
    poner("lumen_scene_lighting_quality", 2.0)
    poner("lumen_scene_detail", 2.0)
    poner("lumen_final_gather_quality", 2.0)
    poner("lumen_reflection_quality", 2.0)
    poner("bloom_intensity", 0.25)
    poner("vignette_intensity", 0.15)
    poner("scene_fringe_intensity", 0.0)
    poner("film_grain_intensity", 0.0)
    try:
        poner("lumen_max_reflection_bounces", 2)
    except Exception:  # noqa: BLE001
        pass
    ppv.set_editor_property("settings", s)


def ajustar_skylight(sky):
    comp = sky.get_component_by_class(unreal.SkyLightComponent)
    comp.set_editor_property("intensity", SKYLIGHT_INTENSIDAD)
    comp.set_editor_property("cubemap_resolution", SKYLIGHT_RESOLUCION)
    comp.set_editor_property("real_time_capture", True)


# ---------------------------------------------------------------------------
# Corrida suelta sobre los niveles existentes
# ---------------------------------------------------------------------------

NIVELES = [(180.0, "/Game/Maps/DomoVR", None), (45.0, "/Game/Maps/DomoVR_45", "sala_domo_45.json"),
           (90.0, "/Game/Maps/DomoVR_90", "sala_domo_90.json")]

MALLA_A_MATERIAL_180 = {
    "SM_Muro": "M_Muro", "SM_Listones": "M_Madera", "SM_Piso": "M_Piso",
    "SM_Tarima": "M_Tarima", "SM_Control": "M_Control",
}


def _material_logico_180(nombre_malla):
    if nombre_malla in MALLA_A_MATERIAL_180:
        return MALLA_A_MATERIAL_180[nombre_malla]
    if nombre_malla.startswith("SM_Butacas"):
        return "M_Butaca"
    if nombre_malla.startswith("SM_Puerta"):
        return "M_Puerta"
    return None


def _nombre_malla(mesh):
    """sala_domo_45_SM_Piso -> SM_Piso."""
    n = mesh.get_name()
    i = n.find("SM_")
    return n[i:] if i >= 0 else n


def rehacer_nivel(fov, ruta_nivel, json_nombre):
    import json
    level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    if not unreal.EditorAssetLibrary.does_asset_exist(ruta_nivel):
        log("{} no existe; se salta.".format(ruta_nivel))
        return
    datos = None
    carpeta = CARPETA_MATERIALES
    if json_nombre:
        with open(os.path.join(os.path.dirname(SCRIPT_DIR), "02_Export", json_nombre), "r", encoding="utf-8") as fh:
            datos = json.load(fh)
        carpeta = "/Game/Sala/Domo_{:g}/Materials".format(fov)
    if not level_subsystem.load_level(ruta_nivel):
        fallar("No se pudo cargar {}".format(ruta_nivel))
    mats = materiales_de_sala(fov, datos, carpeta)
    tocadas = set()
    for actor in actor_subsystem.get_all_level_actors():
        if not isinstance(actor, unreal.StaticMeshActor) or actor.actor_has_tag(ETIQUETA_DETALLE):
            continue
        mesh = actor.static_mesh_component.static_mesh
        if mesh is None or mesh.get_path_name() in tocadas:
            continue
        tocadas.add(mesh.get_path_name())
        nombre = _nombre_malla(mesh)
        if datos is None:
            logico = _material_logico_180(nombre)
        else:
            logico = datos["material_por_malla"].get(nombre)
        if logico in mats:
            mesh.set_material(0, mats[logico])
        aplicar_nanite(mesh, nombre)
        unreal.EditorAssetLibrary.save_loaded_asset(mesh, False)
    for actor in actor_subsystem.get_all_level_actors():
        if isinstance(actor, unreal.PostProcessVolume):
            ajustar_post_proceso(actor)
        elif isinstance(actor, unreal.SkyLight):
            ajustar_skylight(actor)
    colocar_detalles(actor_subsystem, fov, datos)
    if not level_subsystem.save_current_level():
        log("AVISO: save_current_level devolvio False en {}".format(ruta_nivel))
    if datos is not None:
        # Los materiales de color plano de antes quedan huerfanos.
        borrar_materiales_viejos(carpeta, list(datos["materiales"].keys()))
    log("{} rehecho: {} mallas.".format(ruta_nivel, len(tocadas)))


def main():
    preparar()
    for fov, ruta, js in NIVELES:
        rehacer_nivel(fov, ruta, js)
    borrar_materiales_viejos(CARPETA_MATERIALES, list(MATERIALES_180.keys()))
    if unreal.EditorAssetLibrary.does_directory_exist("/Game/Sala/Textures"):
        unreal.EditorAssetLibrary.delete_directory("/Game/Sala/Textures")
        log("Borradas las texturas horneadas viejas de /Game/Sala/Textures.")
    unreal.EditorAssetLibrary.save_directory("/Game/Sala", False, True)
    log("=== Fin realismo_sala.py ===")


if __name__ == "__main__":
    main()
