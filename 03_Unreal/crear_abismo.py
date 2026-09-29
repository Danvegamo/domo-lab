# -*- coding: utf-8 -*-
"""
crear_abismo.py
===============

Arma el nivel del abismo: la escena submarina que Unreal genera y manda por NDI (el sentido inverso
del proyecto). Ver 04_Docs/09_Abismo_Unreal_a_NDI.md.

Correr con el editor CERRADO y el modulo C++ compilado:

    03_Unreal\\crear_abismo.ps1

Es idempotente. Hace:

1. /Game/Abismo/RTC_Default: un cubo de render que sirve de valor por defecto del parametro `Cubo`.
2. /Game/Abismo/M_CuboADomemaster: convierte el cubo que captura ADomeEmisorNDI en un domemaster
   fisheye equidistante (cenit al centro, frente abajo, como el de TouchDesigner).
3. /Game/Abismo/M_Lecho (el fondo), M_Nieve (las particulas que envuelven la camara) y, si existen
   las mallas de 02_Export/criaturas, los materiales de la fauna.
4. /Game/Maps/Abismo: un nivel con un ADomeEmisorNDI y un AAbismoEscena.

Los mensajes salen como Warning con el prefijo [crear_abismo], por la misma razon que en
crear_media_domo.py (en -run=pythonscript los Display no siempre llegan al log).
"""

import unreal

CARPETA = "/Game/Abismo"
NIVEL = "/Game/Maps/Abismo"

mel = unreal.MaterialEditingLibrary


def log(msg):
    unreal.log_warning("[crear_abismo] {}".format(msg))


def fallar(msg):
    raise RuntimeError("[crear_abismo] {}".format(msg))


def cargar_o_crear(ruta, clase, factory):
    if unreal.EditorAssetLibrary.does_asset_exist(ruta):
        asset = unreal.EditorAssetLibrary.load_asset(ruta)
        if asset is not None:
            return asset, False
    carpeta, nombre = ruta.rsplit("/", 1)
    asset = unreal.AssetToolsHelpers.get_asset_tools().create_asset(nombre, carpeta, clase, factory)
    if asset is None:
        fallar("create_asset devolvio None para {}".format(ruta))
    return asset, True


def nodo(material, clase, x, y):
    return mel.create_material_expression(material, clase, x, y)


def conectar(desde, pin, hacia, entrada):
    if not mel.connect_material_expressions(desde, pin, hacia, entrada):
        fallar("No se pudo conectar {} -> {}.{}".format(desde.get_name(), hacia.get_name(), entrada))


def custom(material, descripcion, codigo, entradas, salida, x, y):
    c = nodo(material, unreal.MaterialExpressionCustom, x, y)
    c.set_editor_property("description", descripcion)
    c.set_editor_property("code", codigo)
    c.set_editor_property("output_type", salida)
    lista = []
    for n in entradas:
        ci = unreal.CustomInput()
        ci.set_editor_property("input_name", n)
        lista.append(ci)
    c.set_editor_property("inputs", lista)
    return c


def escalar(material, nombre, valor, x, y):
    e = nodo(material, unreal.MaterialExpressionScalarParameter, x, y)
    e.set_editor_property("parameter_name", nombre)
    e.set_editor_property("default_value", valor)
    return e


def vector(material, nombre, rgba, x, y):
    e = nodo(material, unreal.MaterialExpressionVectorParameter, x, y)
    e.set_editor_property("parameter_name", nombre)
    e.set_editor_property("default_value", unreal.LinearColor(*rgba))
    return e


def rehacer(ruta):
    m, nuevo = cargar_o_crear(ruta, unreal.Material, unreal.MaterialFactoryNew())
    if not nuevo:
        mel.delete_all_material_expressions(m)
    return m, nuevo


def cerrar(material, nombre, nuevo):
    mel.recompile_material(material)
    unreal.EditorAssetLibrary.save_loaded_asset(material, False)
    log("{} {}.".format(nombre, "creado" if nuevo else "rehecho"))


# ---------------------------------------------------------------------------------------- domemaster

HLSL_DIRECCION = """
// UV del cuadro (0..1) -> direccion en el marco de la camara (X adelante, Y derecha, Z arriba, el cenit de la cupula).
// Domemaster equidistante: el radio de la imagen es proporcional al angulo desde el cenit.
float2 p = float2(UV.x * 2.0 - 1.0, 1.0 - UV.y * 2.0);
float r = length(p);
float theta = min(r, 1.0) * radians(FovGrados) * 0.5;
float s = sin(theta);
float2 h = (r > 1e-5) ? p / r : float2(0.0, 0.0);
// En la imagen, arriba es atras (-X) y la derecha es +Y; el frente queda abajo, como en el domemaster de TouchDesigner.
return float3(-h.y * s, h.x * s, cos(theta));
"""

HLSL_MASCARA = """
float r = length(float2(UV.x * 2.0 - 1.0, 1.0 - UV.y * 2.0));
return r <= 1.0 ? 1.0 : 0.0;
"""


# Modo 0 = domemaster normal; 1 = degradado de UV (prueba del dibujo); 2 = la direccion como color (prueba del mapeo).
HLSL_SALIDA = """
if (Modo > 2.5) return saturate(Cubo * 20.0);
if (Modo > 1.5) return (Dir * 0.5 + 0.5) * Mascara;
if (Modo > 0.5) return float3(UV, 0.0);
return Cubo * Mascara;
"""


def crear_material_domemaster():
    rtc, _ = cargar_o_crear(CARPETA + "/RTC_Default", unreal.TextureRenderTargetCube, unreal.TextureRenderTargetCubeFactoryNew())
    # Un cubo de render nuevo trae tamano 0: si el material lo usa como valor por defecto, la GPU lee memoria
    # que no existe. Se le da un tamano real.
    for prop, valor in (("size_x", 16), ("format", unreal.TextureRenderTargetFormat.RTF_RGBA16F)):
        try:
            rtc.set_editor_property(prop, valor)
        except Exception as e:
            log("RTC_Default.{} no se pudo poner: {}".format(prop, e))
    unreal.EditorAssetLibrary.save_loaded_asset(rtc, False)

    m, nuevo = rehacer(CARPETA + "/M_CuboADomemaster")
    m.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    uv = nodo(m, unreal.MaterialExpressionTextureCoordinate, -1200, 0)
    uv.set_editor_property("coordinate_index", 0)
    fov = escalar(m, "FovGrados", 180.0, -1200, 160)

    dire = custom(m, "DireccionDomo", HLSL_DIRECCION, ["UV", "FovGrados"], unreal.CustomMaterialOutputType.CMOT_FLOAT3, -800, 0)
    conectar(uv, "", dire, "UV")
    conectar(fov, "", dire, "FovGrados")
    masc = custom(m, "Mascara", HLSL_MASCARA, ["UV"], unreal.CustomMaterialOutputType.CMOT_FLOAT1, -800, 220)
    conectar(uv, "", masc, "UV")

    cubo = nodo(m, unreal.MaterialExpressionTextureSampleParameterCube, -480, 0)
    cubo.set_editor_property("parameter_name", "Cubo")
    cubo.set_editor_property("texture", rtc)
    conectar(dire, "", cubo, "UVs")

    modo = escalar(m, "Modo", 0.0, -1200, 300)
    fin = custom(m, "Salida", HLSL_SALIDA, ["UV", "Dir", "Cubo", "Mascara", "Modo"], unreal.CustomMaterialOutputType.CMOT_FLOAT3, -180, 0)
    conectar(uv, "", fin, "UV")
    conectar(dire, "", fin, "Dir")
    conectar(cubo, "RGB", fin, "Cubo")
    conectar(masc, "", fin, "Mascara")
    conectar(modo, "", fin, "Modo")
    mel.connect_material_property(fin, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    cerrar(m, "M_CuboADomemaster", nuevo)


# --------------------------------------------------------------------------------------------- lecho

def crear_material_lecho():
    m, nuevo = rehacer(CARPETA + "/M_Lecho")
    m.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_DEFAULT_LIT)
    vc = nodo(m, unreal.MaterialExpressionVertexColor, -700, 0)
    color = nodo(m, unreal.MaterialExpressionMultiply, -420, 0)
    tono = vector(m, "Tono", (0.85, 1.0, 1.05, 1.0), -700, 200)
    conectar(vc, "", color, "A")
    conectar(tono, "", color, "B")
    mel.connect_material_property(color, "", unreal.MaterialProperty.MP_BASE_COLOR)
    rug = escalar(m, "Rugosidad", 0.9, -420, 200)
    mel.connect_material_property(rug, "", unreal.MaterialProperty.MP_ROUGHNESS)
    # Un poco de luz propia para que el lecho no quede negro donde la luz de la superficie no llega.
    amb = escalar(m, "Ambiente", 0.09, -700, 330)
    emi = nodo(m, unreal.MaterialExpressionMultiply, -420, 330)
    conectar(color, "", emi, "A")
    conectar(amb, "", emi, "B")
    mel.connect_material_property(emi, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    cerrar(m, "M_Lecho", nuevo)


# --------------------------------------------------------------------------------------------- nieve

HLSL_NIEVE_WPO = """
// Cada mota vive en una caja del tamano `Caja` que sigue a la camara: la posicion se envuelve alrededor de
// `Cam`. Ademas se hunde despacio (nieve marina) y se bambolea con una fase propia.
float3 p0 = ObjPos;
float3 f = frac(sin(float3(dot(p0, float3(12.9898, 78.233, 37.719)), dot(p0, float3(93.989, 67.345, 11.135)), dot(p0, float3(39.346, 11.135, 83.155)))) * 43758.5453);
float3 flota = float3(sin(T * 0.21 + f.x * 6.283), sin(T * 0.17 + f.y * 6.283), 0.0) * 24.0
             + float3(0.0, 0.0, -9.0 * T * (0.4 + f.z));
float3 rel = p0 + flota - Cam;
rel = frac(rel / Caja + 0.5) * Caja - 0.5 * Caja;
return (Cam + rel) - p0;
"""

HLSL_NIEVE_EMISIVO = """
float3 p0 = ObjPos;
float3 f = frac(sin(float3(dot(p0, float3(12.9898, 78.233, 37.719)), dot(p0, float3(93.989, 67.345, 11.135)), dot(p0, float3(39.346, 11.135, 83.155)))) * 43758.5453);
// La caja se desvanece en los bordes: no se ve entrar ni salir ninguna mota.
float d = length(WorldPos - Cam) / (0.5 * Caja);
float borde = saturate((1.0 - d) * 3.0);
float chispa = 0.55 + 0.45 * sin(T * (0.8 + 2.2 * f.y) + f.x * 40.0);
// Casi todas frias (cian y blanco azulado); unas pocas ambar y rosa, como plancton y motas de plastico.
float3 frio = lerp(float3(0.25, 0.75, 1.0), float3(0.75, 0.95, 1.0), f.z);
float3 calido = lerp(float3(1.0, 0.55, 0.15), float3(1.0, 0.25, 0.65), f.z);
float3 col = f.x > 0.93 ? calido : frio;
return col * Brillo * chispa * borde;
"""


def crear_material_nieve():
    m, nuevo = rehacer(CARPETA + "/M_Nieve")
    m.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_ADDITIVE)
    m.set_editor_property("two_sided", True)
    # El desplazamiento de las motas es de miles de cm: sin esto las recorta su caja original.
    m.set_editor_property("max_world_position_offset_displacement", 20000.0)
    cam = vector(m, "Camara", (0.0, 0.0, 0.0, 0.0), -1300, 0)
    caja = escalar(m, "Caja", 3600.0, -1300, 140)
    brillo = escalar(m, "Brillo", 14.0, -1300, 240)
    t = nodo(m, unreal.MaterialExpressionTime, -1300, 340)
    obj = nodo(m, unreal.MaterialExpressionObjectPositionWS, -1300, 440)
    wp = nodo(m, unreal.MaterialExpressionWorldPosition, -1300, 540)

    wpo = custom(m, "NieveWPO", HLSL_NIEVE_WPO, ["ObjPos", "Cam", "Caja", "T"], unreal.CustomMaterialOutputType.CMOT_FLOAT3, -800, 0)
    conectar(obj, "", wpo, "ObjPos")
    conectar(cam, "", wpo, "Cam")
    conectar(caja, "", wpo, "Caja")
    conectar(t, "", wpo, "T")
    mel.connect_material_property(wpo, "", unreal.MaterialProperty.MP_WORLD_POSITION_OFFSET)

    # La posicion del mundo del pixel ya incluye el desplazamiento; el "objeto" sigue siendo el original,
    # asi que el hash de cada mota no cambia mientras se mueve.
    emi = custom(m, "NieveEmisivo", HLSL_NIEVE_EMISIVO, ["ObjPos", "WorldPos", "Cam", "Caja", "T", "Brillo"], unreal.CustomMaterialOutputType.CMOT_FLOAT3, -800, 260)
    conectar(obj, "", emi, "ObjPos")
    conectar(wp, "", emi, "WorldPos")
    conectar(cam, "", emi, "Cam")
    conectar(caja, "", emi, "Caja")
    conectar(t, "", emi, "T")
    conectar(brillo, "", emi, "Brillo")
    mel.connect_material_property(emi, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    mel.set_material_usage(m, unreal.MaterialUsage.MATUSAGE_INSTANCED_STATIC_MESHES)
    cerrar(m, "M_Nieve", nuevo)


# ---------------------------------------------------------------------------------- materiales de la fauna

HLSL_NADO = """
// Nado y aleteo sin esqueleto: una onda que viaja por el cuerpo (a lo largo de Eje) mueve los vertices en la
// direccion Lado, y el alfa del color por vertice (Mov: 0 rigido, 1 puntas de cola, aletas y tentaculos) decide cuanto.
float x = dot(LocalPos, Eje);
float onda = sin(x * Onda - T * Vel * 6.2831 + Fase * 6.2831);
float latido = sin(T * Vel * 3.1 + Fase * 9.0);
return Lado * (onda * Amp * Mov) + float3(0.0, 0.0, latido * 0.25 * Amp * Mov);
"""

HLSL_BICHO_EMISIVO = """
// Color propio del patron, un borde de luz (bioluminiscencia) y las manchas turquesa que brillan mas cuando
// la criatura late (Pulso, que sube en el dialogo con la basura).
float pulso = Pulso * (0.45 + 0.55 * sin(T * 3.0 - Fase * 6.2831));
float cian = saturate(Col.g + Col.b - Col.r * 1.4 - 0.85) * 3.0;
float3 base = Col * Nivel;
float3 borde = GlowColor * Fres * (0.5 + 3.0 * pulso);
float3 manchas = Col * cian * (1.5 + 6.0 * pulso);
return base + borde + manchas;
"""

HLSL_PLASTICO_EMISIVO = """
// Plastico: casi transparente, con un borde palido que, cuando las criaturas hablan, responde (Respuesta) con
// un color sintetico (magenta y verde acido) en vez de la luz organica azul.
float r = saturate(Respuesta);
float3 sintetico = lerp(float3(0.9, 0.2, 0.75), float3(0.4, 1.0, 0.3), 0.5 + 0.5 * sin(T * 2.0 + Fase * 6.2831));
float3 palido = float3(0.55, 0.75, 0.9);
float3 borde = lerp(palido, sintetico, r) * Fres * (0.22 + 3.0 * r);
return borde + Col * (0.03 + 0.3 * r);
"""

HLSL_DECORADO_EMISIVO = """
float cian = saturate(Col.g + Col.b - Col.r * 1.4 - 0.85) * 3.0;
return Col * Nivel + Col * cian * (0.8 + 0.5 * sin(T * 0.7 + Fase * 6.2831)) + GlowColor * Fres * 0.4;
"""


def crear_material_bicho(nombre, tipo):
    """tipo: 'organico' (luz propia y pulso), 'plastico' (aditivo, responde) o 'decorado' (roca, coral y alga)."""
    m, nuevo = rehacer(CARPETA + "/" + nombre)
    if tipo == "plastico":
        m.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
        m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_ADDITIVE)
        m.set_editor_property("two_sided", True)
    else:
        m.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_DEFAULT_LIT)
    m.set_editor_property("max_world_position_offset_displacement", 600.0)

    vc = nodo(m, unreal.MaterialExpressionVertexColor, -1500, 0)
    t = nodo(m, unreal.MaterialExpressionTime, -1500, 120)
    fase = nodo(m, unreal.MaterialExpressionPerInstanceCustomData, -1500, 220)
    fase.set_editor_property("data_index", 0)
    fase.set_editor_property("const_default_value", 0.0)
    vel = nodo(m, unreal.MaterialExpressionPerInstanceCustomData, -1500, 320)
    vel.set_editor_property("data_index", 1)
    vel.set_editor_property("const_default_value", 0.4)
    if hasattr(unreal, "MaterialExpressionPreSkinnedLocalPosition"):
        lpos = nodo(m, unreal.MaterialExpressionPreSkinnedLocalPosition, -1500, 420)
    else:
        lpos = nodo(m, unreal.MaterialExpressionLocalPosition, -1500, 420)
    amp = escalar(m, "Amp", 20.0, -1500, 520)
    onda = escalar(m, "Onda", 0.02, -1500, 600)
    eje = vector(m, "Eje", (1.0, 0.0, 0.0, 0.0), -1500, 680)
    lado = vector(m, "Lado", (0.0, 1.0, 0.0, 0.0), -1500, 780)

    wpo = custom(m, "Nado", HLSL_NADO, ["LocalPos", "Eje", "Lado", "Onda", "T", "Vel", "Fase", "Amp", "Mov"],
                 unreal.CustomMaterialOutputType.CMOT_FLOAT3, -1000, 300)
    conectar(lpos, "", wpo, "LocalPos")
    conectar(eje, "", wpo, "Eje")
    conectar(lado, "", wpo, "Lado")
    conectar(onda, "", wpo, "Onda")
    conectar(t, "", wpo, "T")
    conectar(vel, "", wpo, "Vel")
    conectar(fase, "", wpo, "Fase")
    conectar(amp, "", wpo, "Amp")
    conectar(vc, "A", wpo, "Mov")
    a_mundo = nodo(m, unreal.MaterialExpressionTransform, -700, 300)
    a_mundo.set_editor_property("transform_source_type", unreal.MaterialVectorCoordTransformSource.TRANSFORMSOURCE_LOCAL)
    a_mundo.set_editor_property("transform_type", unreal.MaterialVectorCoordTransform.TRANSFORM_WORLD)
    conectar(wpo, "", a_mundo, "")
    mel.connect_material_property(a_mundo, "", unreal.MaterialProperty.MP_WORLD_POSITION_OFFSET)

    fres = nodo(m, unreal.MaterialExpressionFresnel, -1000, 700)
    fres.set_editor_property("exponent", 2.5)
    fres.set_editor_property("base_reflect_fraction", 0.02)
    nivel = escalar(m, "Nivel", 0.35 if tipo != "plastico" else 0.1, -1000, 820)
    glow = vector(m, "GlowColor", (0.2, 0.75, 1.0, 1.0), -1000, 900)
    pulso = escalar(m, "Pulso", 0.0, -1000, 980)
    resp = escalar(m, "Respuesta", 0.0, -1000, 1060)

    if tipo == "organico":
        codigo, entradas = HLSL_BICHO_EMISIVO, ["Col", "T", "Fase", "Pulso", "Nivel", "GlowColor", "Fres"]
    elif tipo == "plastico":
        codigo, entradas = HLSL_PLASTICO_EMISIVO, ["Col", "T", "Fase", "Respuesta", "Fres"]
    else:
        codigo, entradas = HLSL_DECORADO_EMISIVO, ["Col", "T", "Fase", "Nivel", "GlowColor", "Fres"]
    emi = custom(m, "Emisivo", codigo, entradas, unreal.CustomMaterialOutputType.CMOT_FLOAT3, -300, 500)
    fuentes = {"Col": (vc, ""), "T": (t, ""), "Fase": (fase, ""), "Pulso": (pulso, ""), "Nivel": (nivel, ""),
               "GlowColor": (glow, ""), "Fres": (fres, ""), "Respuesta": (resp, "")}
    for n in entradas:
        conectar(fuentes[n][0], fuentes[n][1], emi, n)
    mel.connect_material_property(emi, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    if tipo != "plastico":
        base = nodo(m, unreal.MaterialExpressionMultiply, -300, 100)
        conectar(vc, "", base, "A")
        k = escalar(m, "Brillo", 0.55, -600, 100)
        conectar(k, "", base, "B")
        mel.connect_material_property(base, "", unreal.MaterialProperty.MP_BASE_COLOR)
        rug = escalar(m, "Rugosidad", 0.55, -300, 20)
        mel.connect_material_property(rug, "", unreal.MaterialProperty.MP_ROUGHNESS)
    mel.set_material_usage(m, unreal.MaterialUsage.MATUSAGE_INSTANCED_STATIC_MESHES)
    cerrar(m, nombre, nuevo)


# ---------------------------------------------------------------------------------- onda de dialogo

HLSL_ONDA = """
// Una esfera que se agranda (la escala la pone el codigo) y se desvanece: la onda de luz con que una criatura
// "habla". Solo se ve el borde (Fresnel); Edad va de 0 a 1.
float vida = saturate(1.0 - Edad);
return Color * Fres * vida * vida * 2.4;
"""


def crear_material_onda():
    m, nuevo = rehacer(CARPETA + "/M_Onda")
    m.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_ADDITIVE)
    m.set_editor_property("two_sided", True)
    edad = nodo(m, unreal.MaterialExpressionPerInstanceCustomData, -900, 0)
    edad.set_editor_property("data_index", 0)
    edad.set_editor_property("const_default_value", 1.0)
    fres = nodo(m, unreal.MaterialExpressionFresnel, -900, 120)
    fres.set_editor_property("exponent", 1.6)
    fres.set_editor_property("base_reflect_fraction", 0.0)
    color = vector(m, "Color", (0.25, 0.8, 1.0, 1.0), -900, 240)
    emi = custom(m, "Onda", HLSL_ONDA, ["Edad", "Fres", "Color"], unreal.CustomMaterialOutputType.CMOT_FLOAT3, -500, 100)
    conectar(edad, "", emi, "Edad")
    conectar(fres, "", emi, "Fres")
    conectar(color, "", emi, "Color")
    mel.connect_material_property(emi, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    mel.set_material_usage(m, unreal.MaterialUsage.MATUSAGE_INSTANCED_STATIC_MESHES)
    cerrar(m, "M_Onda", nuevo)


# ------------------------------------------------------------------------------------------- criaturas

IDS_CRIATURAS = ["kronos_jaguar", "amonita_rana", "calla_manati", "desma_orquidea", "kyhy_inia", "belemnita_morpho",
                 "bolsa_plastica", "botella_pet", "red_fantasma", "anillo_lata", "roca_lecho", "coral_abanico", "kelp_tira"]


def importar_criaturas():
    """Importa los FBX de 02_Export/criaturas (01_Blender/generar_criaturas.py) como /Game/Abismo/Criaturas/SM_<id>.
    Sin materiales ni texturas: el color y el movimiento salen del color por vertice (RGB = patron, A = peso de
    movimiento) y de los materiales de crear_abismo.py."""
    import os
    raiz = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "02_Export", "criaturas"))
    destino = CARPETA + "/Criaturas"
    unreal.EditorAssetLibrary.make_directory(destino)
    tareas = []
    for cid in IDS_CRIATURAS:
        ruta = os.path.join(raiz, cid + ".fbx")
        if not os.path.exists(ruta):
            log("Falta {}: correr 01_Blender/generar_criaturas.py.".format(ruta))
            continue
        t = unreal.AssetImportTask()
        t.set_editor_property("filename", ruta)
        t.set_editor_property("destination_path", destino)
        t.set_editor_property("destination_name", "SM_" + cid)
        t.set_editor_property("replace_existing", True)
        t.set_editor_property("automated", True)
        t.set_editor_property("save", True)
        ui = unreal.FbxImportUI()
        ui.set_editor_property("import_mesh", True)
        ui.set_editor_property("import_as_skeletal", False)
        ui.set_editor_property("import_materials", False)
        ui.set_editor_property("import_textures", False)
        ui.set_editor_property("import_animations", False)
        ui.set_editor_property("automated_import_should_detect_type", False)
        ui.set_editor_property("mesh_type_to_import", unreal.FBXImportType.FBXIT_STATIC_MESH)
        smd = ui.static_mesh_import_data
        smd.set_editor_property("combine_meshes", True)
        smd.set_editor_property("generate_lightmap_u_vs", False)
        smd.set_editor_property("auto_generate_collision", False)
        smd.set_editor_property("build_nanite", False)
        smd.set_editor_property("vertex_color_import_option", unreal.VertexColorImportOption.REPLACE)
        smd.set_editor_property("convert_scene", True)
        t.set_editor_property("options", ui)
        tareas.append(t)
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks(tareas)
    for cid in IDS_CRIATURAS:
        malla = unreal.EditorAssetLibrary.load_asset("{}/SM_{}".format(destino, cid))
        if malla is None:
            log("SM_{} no se importo.".format(cid))
            continue
        b = malla.get_bounding_box()
        log("SM_{}: caja {:.0f} x {:.0f} x {:.0f} cm (X, Y, Z)".format(cid, b.max.x - b.min.x, b.max.y - b.min.y, b.max.z - b.min.z))


# ---------------------------------------------------------------------------------------------- nivel

def crear_nivel():
    ls = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    if unreal.EditorAssetLibrary.does_asset_exist(NIVEL):
        if not ls.load_level(NIVEL):
            fallar("No se pudo cargar {}".format(NIVEL))
        actores = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        for a in actores.get_all_level_actors():
            if isinstance(a, (unreal.DomeEmisorNDI, unreal.AbismoEscena, unreal.AbismoFauna)):
                actores.destroy_actor(a)
    else:
        if not ls.new_level(NIVEL):
            fallar("No se pudo crear {}".format(NIVEL))
    actores = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    emisor = actores.spawn_actor_from_class(unreal.DomeEmisorNDI, unreal.Vector(0, 0, 380))
    emisor.set_actor_label("Emisor_NDI")
    escena = actores.spawn_actor_from_class(unreal.AbismoEscena, unreal.Vector(0, 0, 0))
    escena.set_actor_label("Abismo_Escena")
    fauna = actores.spawn_actor_from_class(unreal.AbismoFauna, unreal.Vector(0, 0, 0))
    fauna.set_actor_label("Abismo_Fauna")
    if not ls.save_current_level():
        fallar("No se pudo guardar {}".format(NIVEL))
    log("Nivel {} listo con Emisor_NDI, Abismo_Escena y Abismo_Fauna.".format(NIVEL))


def main():
    log("=== Abismo: Unreal genera el domo y lo manda por NDI ===")
    if not hasattr(unreal, "DomeEmisorNDI") or not hasattr(unreal, "AbismoEscena") or not hasattr(unreal, "AbismoFauna"):
        fallar("Faltan unreal.DomeEmisorNDI / unreal.AbismoEscena: compilar el modulo DomoVR (UnrealBuildTool DomoVREditor).")
    unreal.EditorAssetLibrary.make_directory(CARPETA)
    crear_material_domemaster()
    crear_material_lecho()
    crear_material_nieve()
    crear_material_bicho("M_Criatura", "organico")
    crear_material_bicho("M_Plastico", "plastico")
    crear_material_bicho("M_Decorado", "decorado")
    crear_material_onda()
    importar_criaturas()
    crear_nivel()
    log("=== Fin crear_abismo.py ===")


main()
