# -*- coding: utf-8 -*-
"""
crear_media_domo.py
===================

Arma la version standalone de la sala: Unreal reproduce los videos en la
cupula sin TouchDesigner. Ver 04_Docs/06_Unreal_standalone.md.

Correr DESPUES de importar_sala.py y conectar_spout.py (necesita los niveles,
Domo_Actor y el SpoutDomeReceiver), con el editor CERRADO:

    03_Unreal\\crear_media_domo.ps1

Es idempotente. Hace, en este orden:

1. /Game/Media/MP_Domo (MediaPlayer) y /Game/Media/MT_Domo (MediaTexture,
   sRGB, sin mips, salida "new style" para que el material la lea como
   Texture2D comun). Si ya existen, los reutiliza y les reescribe la
   configuracion.
2. /Game/Media/M_DomoMedia: Unlit, dos caras, is_sky (igual que M_Domo, para
   que el SkyLight_Domo siga iluminando la sala con lo que se proyecta). Todo
   el mapeo va en un nodo Custom de HLSL que hace, por pixel de la cupula, la
   cadena de TouchDesigner al reves: domo_mapping.frag (FOV de la sala, FOV
   del contenido, mapping), orientar.frag (Horizonte, Curva, Yaw, Pitch, Roll)
   y la lectura segun el formato del video (360, domemaster, VR180, VR180
   lado a lado, 16:9 en una pantalla como pantalla169.frag). M_Domo, el de
   Spout, no se toca. El grafo se borra y se rehace en cada corrida.
3. /Game/Media/MI_DomoMedia, instancia de M_DomoMedia.
4. En cada nivel que exista (/Game/Maps/DomoVR, DomoVR_45, DomoVR_90): borra
   los DomeMediaController que hubiera y coloca uno nuevo apuntando a MP_Domo,
   MT_Domo, MI_DomoMedia, la malla de Domo_Actor y el SpoutDomeReceiver.
   Guarda solo ese nivel.
5. Copia 03_Unreal/Movies_ejemplo/playlist.json a Content/Movies/ si ahi no
   hay playlist todavia (nunca pisa la que ya exista).
6. /Game/Media/RC_Domo: preset de Remote Control con las funciones y
   propiedades del controlador del nivel DomoVR. Solo con el editor completo
   (no en -run=pythonscript; ver main()).

Los mensajes salen como Warning con prefijo [crear_media_domo], por la misma
razon que en importar_sala.py (en -run=pythonscript los Display no siempre
llegan al log).
"""

import os
import shutil

import unreal

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROYECTO_DIR = os.path.join(SCRIPT_DIR, "DomoVR")

CARPETA_MEDIA = "/Game/Media"
MP_PATH = CARPETA_MEDIA + "/MP_Domo"
MT_PATH = CARPETA_MEDIA + "/MT_Domo"
M_PATH = CARPETA_MEDIA + "/M_DomoMedia"
MI_PATH = CARPETA_MEDIA + "/MI_DomoMedia"
RC_PATH = CARPETA_MEDIA + "/RC_Domo"

NIVELES = ["/Game/Maps/DomoVR_45", "/Game/Maps/DomoVR_90", "/Game/Maps/DomoVR"]
NIVEL_RC = "/Game/Maps/DomoVR"

# Fuente con la que arranca cada nivel. "Media" es la version standalone; con
# "Spout" los niveles se comportan como antes (TouchDesigner en vivo) y el
# video se enciende con la tecla S, domo.Fuente Media o Remote Control.
FUENTE_INICIAL = "Media"

PLAYLIST_EJEMPLO = os.path.join(SCRIPT_DIR, "Movies_ejemplo", "playlist.json")
PLAYLIST_PROYECTO = os.path.join(PROYECTO_DIR, "Content", "Movies", "playlist.json")

# (nombre, valor por defecto). El orden es el de las entradas del nodo
# Custom. Los nombres tienen que coincidir con DomoParam en
# Source/DomoVR/DomeMediaController.cpp.
PARAMETROS = [
    ("Formato", 0.0),
    ("EspejoU", 1.0),
    ("FovSala", 180.0),
    ("FovContenido", 0.0),
    ("Yaw", 0.0),
    ("Pitch", 0.0),
    ("Roll", 0.0),
    ("Horizonte", 0.0),
    ("Curva", 1.0),
    ("CentroX", 0.0),
    ("CentroY", 0.0),
    ("Escala", 1.0),
    ("Rotar", 0.0),
    ("PantallaAzimut", 0.0),
    ("PantallaElevacion", 30.0),
    ("PantallaAncho", 100.0),
    ("PantallaAlto", 56.0),
    ("PantallaCurva", 0.0),
    ("PantallaBorde", 0.02),
]

# HLSL del nodo Custom. Entradas: UV (TexCoord 0 de la cupula), Tex (la
# MediaTexture) y los PARAMETROS. Sale el color RGB ya leido del video.
#
# Convencion (la de todo el repo): direccion x a la derecha, y arriba, z al
# frente. Lienzo equirectangular: u 0.5 el frente, v 0.5 el horizonte, v 1
# el cenit. La UV de la cupula en Unreal tiene V invertida respecto de
# Blender (el FBX la voltea): V = 0 en el cenit, por eso v = 1 - UV.y. Lo
# mismo al leer el video: la fila 0 de la textura es la de arriba, asi que un
# punto (u, v) del lienzo se lee en (u, 1 - v).
#
# Se lee con SampleLevel nivel 0 (MT_Domo no tiene mips, y aunque los
# tuviera): con derivadas, el salto de u de 1 a 0 en la costura elegiria un
# mip chico y dejaria una linea gris, igual que en TouchDesigner.
#
# No se puede declarar PI: Common.ush ya lo define como macro.
HLSL = r"""
const float K_PI = 3.14159265;
const float3 NEGRO = float3(0.0, 0.0, 0.0);

// 1) Pixel de la cupula -> punto p del domemaster de la sala
//    (domo_mapping.frag, modo 1: el lienzo que antes mandaba para_unreal).
// EspejoU: la U de la cupula crece hacia la IZQUIERDA de quien mira desde
// adentro (azimut antihorario visto desde arriba, en Blender y en Unreal),
// mientras que en TouchDesigner u crece hacia la derecha (x = sin(az)). Sin
// voltearla, un texto del video se lee al reves en la cupula (medido el 18
// sep 2026 con el contador del patron). El frente (u 0.5) y la costura
// (u 0 = 1) quedan donde estaban.
float u = EspejoU > 0.5 ? 1.0 - UV.x : UV.x;
float v = 1.0 - UV.y;
float azs = (u - 0.5) * 2.0 * K_PI;
float el = (v - 0.5) * K_PI;
float r = (0.5 * K_PI - el) / (radians(max(FovSala, 1.0)) * 0.5);
if (r > 1.0) return NEGRO;
float2 p = r * float2(sin(azs), -cos(azs));

// 2) Deshacer el mapping (inverso de escalar, rotar y trasladar) y pasar por
//    el fisheye equidistante del contenido.
float2 q = p - 2.0 * float2(CentroX, CentroY);
float a = radians(-Rotar);
q = float2(cos(a) * q.x - sin(a) * q.y, sin(a) * q.x + cos(a) * q.y);
q /= max(Escala, 1e-4);
float fovc = FovContenido > 0.0 ? FovContenido : FovSala;
float th = length(q) * radians(fovc) * 0.5;
if (th > K_PI) return NEGRO;
float azq = atan2(q.x, -q.y);
float3 d = float3(sin(th) * sin(azq), cos(th), sin(th) * cos(azq));
float2 c = float2(frac(atan2(d.x, d.z) / (2.0 * K_PI) + 0.5),
                  asin(clamp(d.y, -1.0, 1.0)) / K_PI + 0.5);

// 3) orientar.frag: Horizonte y Curva (cenit fijo), despues el giro esferico
//    inverso Yaw, Pitch, Roll.
float H = min(Horizonte, 80.0);
float g = max(Curva, 0.05);
if (abs(H) > 1e-4 || abs(g - 1.0) > 1e-4)
{
    float t = (1.0 - c.y) * 2.0;
    float e = 90.0 - 90.0 * pow(t / ((90.0 - H) / 90.0), g);
    if (e < -90.0) return NEGRO;
    c.y = e / 180.0 + 0.5;
}
float az3 = (c.x - 0.5) * 2.0 * K_PI;
float el3 = (c.y - 0.5) * K_PI;
float3 dd = float3(cos(el3) * sin(az3), sin(el3), cos(el3) * cos(az3));
float ca = cos(radians(Yaw)), sa = sin(radians(Yaw));
dd = float3(ca * dd.x - sa * dd.z, dd.y, sa * dd.x + ca * dd.z);
ca = cos(radians(Pitch)); sa = sin(radians(Pitch));
dd = float3(dd.x, ca * dd.y - sa * dd.z, sa * dd.y + ca * dd.z);
ca = cos(radians(Roll)); sa = sin(radians(Roll));
dd = float3(ca * dd.x + sa * dd.y, -sa * dd.x + ca * dd.y, dd.z);
float2 src = float2(frac(atan2(dd.x, dd.z) / (2.0 * K_PI) + 0.5),
                    asin(clamp(dd.y, -1.0, 1.0)) / K_PI + 0.5);

// 4) Leer el video segun el formato.
int f = (int)round(Formato);
float2 tuv;
float m = 1.0;
if (f == 1)
{
    // domemaster fisheye 180: cenit al centro, frente abajo del cuadro
    float thf = acos(clamp(dd.y, -1.0, 1.0));
    float rf = thf / (0.5 * K_PI);
    if (rf > 1.0) return NEGRO;
    float azf = atan2(dd.x, dd.z);
    float2 pf = rf * float2(sin(azf), -cos(azf));
    tuv = float2(pf.x * 0.5 + 0.5, 0.5 - pf.y * 0.5);
}
else if (f == 2 || f == 3)
{
    // VR180: media esfera centrada en el lienzo, u 0.25 a 0.75
    if (src.x < 0.25 || src.x > 0.75) return NEGRO;
    float x = (src.x - 0.25) * 2.0;
    if (f == 3) x *= 0.5;             // lado a lado: el ojo izquierdo
    tuv = float2(x, 1.0 - src.y);
}
else if (f == 4)
{
    // pantalla plana sobre la cupula (pantalla169.frag)
    float paz = radians(PantallaAzimut), pel = radians(PantallaElevacion);
    float3 C = float3(cos(pel) * sin(paz), sin(pel), cos(pel) * cos(paz));
    float3 R = normalize(cross(float3(0.0, 1.0, 0.0), C));
    float3 U = cross(C, R);
    float hh = radians(max(PantallaAncho, 1.0)) * 0.5;
    float hv = radians(max(PantallaAlto, 1.0)) * 0.5;
    float t = dot(dd, C);
    float x, y;
    bool ok;
    if (PantallaCurva < 0.5)
    {
        ok = t > 0.001;
        float tt = max(t, 0.001);
        x = dot(dd, R) / tt / tan(hh);
        y = dot(dd, U) / tt / tan(hv);
    }
    else
    {
        ok = t > -0.999;
        x = atan2(dot(dd, R), t) / hh;
        y = asin(clamp(dot(dd, U), -1.0, 1.0)) / hv;
    }
    if (!ok) return NEGRO;
    float2 suv = float2(x, y) * 0.5 + 0.5;
    float b = max(PantallaBorde, 1e-4);
    m = smoothstep(0.0, b, suv.x) * smoothstep(0.0, b, 1.0 - suv.x)
      * smoothstep(0.0, b, suv.y) * smoothstep(0.0, b, 1.0 - suv.y);
    if (m <= 0.0) return NEGRO;
    tuv = float2(clamp(suv.x, 0.0, 1.0), clamp(1.0 - suv.y, 0.0, 1.0));
}
else
{
    // 360 equirectangular: el archivo ya es el lienzo
    tuv = float2(src.x, 1.0 - src.y);
}
return Tex.SampleLevel(TexSampler, tuv, 0).rgb * m;
"""


def log(msg):
    unreal.log_warning("[crear_media_domo] {}".format(msg))


def fallar(msg):
    raise RuntimeError("[crear_media_domo] {}".format(msg))


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


def crear_player_y_textura():
    mp, nuevo = cargar_o_crear(MP_PATH, unreal.MediaPlayer, unreal.MediaPlayerFactoryNew())
    mp.set_editor_property("play_on_open", True)
    mp.set_editor_property("loop", False)
    log("MP_Domo {}.".format("creado" if nuevo else "reutilizado"))

    mt, nuevo = cargar_o_crear(MT_PATH, unreal.MediaTexture, unreal.MediaTextureFactoryNew())
    mt.set_editor_property("media_player", mp)
    mt.set_editor_property("new_style_output", True)
    mt.set_editor_property("enable_gen_mips", False)
    mt.set_editor_property("srgb", True)
    mt.set_editor_property("auto_clear", True)
    mt.set_editor_property("clear_color", unreal.LinearColor(0.0, 0.0, 0.0, 1.0))
    # u da la vuelta (un 360 cierra sobre si mismo); v no.
    mt.set_editor_property("address_x", unreal.TextureAddress.TA_WRAP)
    mt.set_editor_property("address_y", unreal.TextureAddress.TA_CLAMP)
    log("MT_Domo {} (sRGB, sin mips, new style output).".format("creada" if nuevo else "reutilizada"))

    unreal.EditorAssetLibrary.save_loaded_asset(mp, False)
    unreal.EditorAssetLibrary.save_loaded_asset(mt, False)
    return mp, mt


def crear_material(mt):
    mel = unreal.MaterialEditingLibrary
    material, nuevo = cargar_o_crear(M_PATH, unreal.Material, unreal.MaterialFactoryNew())
    if not nuevo:
        mel.delete_all_material_expressions(material)

    material.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    material.set_editor_property("two_sided", True)
    material.set_editor_property("is_sky", True)

    y = -600
    uv = mel.create_material_expression(material, unreal.MaterialExpressionTextureCoordinate, -900, y)
    uv.set_editor_property("coordinate_index", 0)

    tex = mel.create_material_expression(material, unreal.MaterialExpressionTextureObjectParameter, -900, y + 120)
    tex.set_editor_property("parameter_name", "MediaTexture")
    tex.set_editor_property("texture", mt)
    tex.set_editor_property("sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_COLOR)

    custom = mel.create_material_expression(material, unreal.MaterialExpressionCustom, -450, 0)
    custom.set_editor_property("description", "DomoMapeo")
    custom.set_editor_property("code", HLSL)
    custom.set_editor_property("output_type", unreal.CustomMaterialOutputType.CMOT_FLOAT3)

    entradas = []
    for nombre in ["UV", "Tex"] + [p[0] for p in PARAMETROS]:
        ci = unreal.CustomInput()
        ci.set_editor_property("input_name", nombre)
        entradas.append(ci)
    custom.set_editor_property("inputs", entradas)

    def conectar(desde, pin_salida, hacia):
        if not mel.connect_material_expressions(desde, pin_salida, custom, hacia):
            fallar("No se pudo conectar {} a la entrada {} del nodo Custom.".format(desde.get_name(), hacia))

    conectar(uv, "", "UV")
    conectar(tex, "", "Tex")
    for i, (nombre, defecto) in enumerate(PARAMETROS):
        e = mel.create_material_expression(material, unreal.MaterialExpressionScalarParameter, -900, y + 260 + i * 70)
        e.set_editor_property("parameter_name", nombre)
        e.set_editor_property("default_value", defecto)
        e.set_editor_property("group", "Domo")
        conectar(e, "", nombre)

    brillo = mel.create_material_expression(material, unreal.MaterialExpressionScalarParameter, -250, 200)
    brillo.set_editor_property("parameter_name", "Brillo")
    brillo.set_editor_property("default_value", 1.0)
    mult = mel.create_material_expression(material, unreal.MaterialExpressionMultiply, -120, 0)
    mel.connect_material_expressions(custom, "", mult, "A")
    mel.connect_material_expressions(brillo, "", mult, "B")
    mel.connect_material_property(mult, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)

    # Con el indicador de uso Nanite apagado, un nivel cuya cupula sea Nanite
    # dibuja el material por defecto en el juego ("missing usage flag
    # Nanite", visto el 18 sep 2026). Prenderlo no cuesta nada si no lo es.
    mel.set_base_material_usage(material, unreal.MaterialUsage.MATUSAGE_NANITE, True)
    mel.recompile_material(material)
    unreal.EditorAssetLibrary.save_loaded_asset(material, False)
    log("M_DomoMedia {} con {} parametros.".format("creado" if nuevo else "rehecho", len(PARAMETROS) + 2))

    mi, nuevo = cargar_o_crear(MI_PATH, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    mel.set_material_instance_parent(mi, material)
    unreal.EditorAssetLibrary.save_loaded_asset(mi, False)
    log("MI_DomoMedia {}.".format("creada" if nuevo else "reutilizada"))
    return material, mi


def colocar_en_nivel(ruta_nivel, mp, mt, mi):
    level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    if not unreal.EditorAssetLibrary.does_asset_exist(ruta_nivel):
        log("{} no existe; se salta (correr importar_sala.ps1 para ese modelo).".format(ruta_nivel))
        return None
    if not level_subsystem.load_level(ruta_nivel):
        fallar("No se pudo cargar {}".format(ruta_nivel))

    actores = actor_subsystem.get_all_level_actors()
    domo = next((a for a in actores if a.get_actor_label() == "Domo_Actor"), None)
    if domo is None:
        fallar("{} no tiene Domo_Actor. Correr importar_sala.ps1 antes.".format(ruta_nivel))
    # isinstance, no get_class() ==: la comparacion de clases por igualdad
    # no encuentra nada desde Python (medido el 18 sep 2026).
    receptor = next((a for a in actores if isinstance(a, unreal.SpoutDomeReceiver)), None)
    if receptor is None:
        log("AVISO: {} no tiene SpoutDomeReceiver; la fuente Spout no va a estar disponible ahi.".format(ruta_nivel))

    viejos = [a for a in actores if isinstance(a, unreal.DomeMediaController)]
    if viejos:
        actor_subsystem.destroy_actors(viejos)

    ctrl = actor_subsystem.spawn_actor_from_class(
        unreal.DomeMediaController, unreal.Vector(0.0, 0.0, 200.0), unreal.Rotator(0.0, 0.0, 0.0))
    if ctrl is None:
        fallar("spawn_actor_from_class devolvio None para DomeMediaController en {}".format(ruta_nivel))
    ctrl.set_actor_label("DomeMediaController")
    ctrl.set_editor_property("media_player", mp)
    ctrl.set_editor_property("media_texture", mt)
    ctrl.set_editor_property("media_material", mi)
    ctrl.set_editor_property("target_mesh_component", domo.static_mesh_component)
    ctrl.set_editor_property("target_material_slot", 0)
    if receptor is not None:
        ctrl.set_editor_property("spout_receiver", receptor)
    fuente = unreal.DomeFuente.MEDIA if FUENTE_INICIAL == "Media" else unreal.DomeFuente.SPOUT
    ctrl.set_editor_property("fuente", fuente)

    if not level_subsystem.save_current_level():
        log("AVISO: save_current_level devolvio False en {}".format(ruta_nivel))
    log("{}: DomeMediaController colocado (reemplazo {} previos), fuente {}.".format(
        ruta_nivel, len(viejos), FUENTE_INICIAL))
    return ctrl


def crear_preset_rc(ctrl):
    """RC_Domo con las funciones del controlador del nivel DomoVR. El preset
    queda ligado a ese actor de ese nivel."""
    if not hasattr(unreal, "RemoteControlPreset"):
        log("AVISO: el plugin RemoteControl no esta cargado; no se crea RC_Domo.")
        return
    if unreal.EditorAssetLibrary.does_asset_exist(RC_PATH):
        unreal.EditorAssetLibrary.delete_asset(RC_PATH)
    factory = getattr(unreal, "RemoteControlPresetFactory", None)
    preset = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
        "RC_Domo", CARPETA_MEDIA, unreal.RemoteControlPreset, factory() if factory else None)
    if preset is None:
        log("AVISO: no se pudo crear RC_Domo desde Python; se puede armar a mano (ver 06_Unreal_standalone.md).")
        return
    lib = unreal.RemoteControlFunctionLibrary
    expuestas = []
    for funcion in ["Play", "Pause", "TogglePause", "Next", "Prev", "GoToCue", "Reiniciar",
                    "SetParam", "Blackout", "ToggleBlackout", "SetFuente", "ToggleFuente", "RecargarPlaylist"]:
        args = unreal.RemoteControlOptionalExposeArgs()
        args.set_editor_property("display_name", funcion)
        try:
            if lib.expose_function(preset, ctrl, funcion, args):
                expuestas.append(funcion)
        except Exception as exc:  # noqa: BLE001 - un fallo aqui no debe tumbar el resto
            log("AVISO: expose_function({}) fallo: {}".format(funcion, exc))
    for prop in ["Fuente", "Brillo", "bNegro"]:
        args = unreal.RemoteControlOptionalExposeArgs()
        args.set_editor_property("display_name", prop)
        try:
            if lib.expose_property(preset, ctrl, prop, args):
                expuestas.append(prop)
        except Exception as exc:  # noqa: BLE001
            log("AVISO: expose_property({}) fallo: {}".format(prop, exc))
    unreal.EditorAssetLibrary.save_loaded_asset(preset, False)
    log("RC_Domo: {} campos expuestos: {}".format(len(expuestas), ", ".join(expuestas)))


def copiar_playlist_ejemplo():
    if os.path.isfile(PLAYLIST_PROYECTO):
        log("Content/Movies/playlist.json ya existe; no se toca.")
        return
    os.makedirs(os.path.dirname(PLAYLIST_PROYECTO), exist_ok=True)
    shutil.copyfile(PLAYLIST_EJEMPLO, PLAYLIST_PROYECTO)
    log("Playlist de ejemplo copiada a {}".format(PLAYLIST_PROYECTO))


def main():
    log("=== Version standalone: video en la cupula con Media Framework ===")
    if not hasattr(unreal, "DomeMediaController"):
        fallar("unreal.DomeMediaController no existe: compilar el modulo DomoVR (UnrealBuildTool DomoVREditor) antes.")

    # Remote Control necesita el buffer de transacciones del editor, que no
    # existe en -run=pythonscript: exponer una funcion ahi tumba el proceso
    # ("Cast of nullptr to TransBuffer failed", medido el 18 sep 2026). Por
    # eso el preset se arma en una segunda pasada con el editor completo
    # (crear_media_domo.ps1 -SoloRC, o este script pegado en la consola de
    # Python del editor abierto).
    solo_rc = os.environ.get("DOMO_SOLO_RC", "") == "1"
    en_commandlet = os.environ.get("DOMO_HEADLESS", "") == "1"

    if not solo_rc:
        unreal.EditorAssetLibrary.make_directory(CARPETA_MEDIA)
        mp, mt = crear_player_y_textura()
        _, mi = crear_material(mt)
        for nivel in NIVELES:
            colocar_en_nivel(nivel, mp, mt, mi)
        copiar_playlist_ejemplo()

    if en_commandlet:
        log("RC_Domo no se arma en modo commandlet: correr crear_media_domo.ps1 -SoloRC.")
    else:
        level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        if not level_subsystem.load_level(NIVEL_RC):
            fallar("No se pudo cargar {}".format(NIVEL_RC))
        actores = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
        ctrl = next((a for a in actores if isinstance(a, unreal.DomeMediaController)), None)
        if ctrl is None:
            fallar("{} no tiene DomeMediaController: correr primero crear_media_domo.ps1 sin -SoloRC.".format(NIVEL_RC))
        crear_preset_rc(ctrl)

    log("=== Fin crear_media_domo.py ===")
    if solo_rc and os.environ.get("DOMO_SALIR", "") == "1":
        unreal.SystemLibrary.quit_editor()


main()
