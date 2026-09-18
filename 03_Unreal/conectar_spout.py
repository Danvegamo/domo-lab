# -*- coding: utf-8 -*-
"""
conectar_spout.py
==================

Script hermano de importar_sala.py. Deja preparado, del lado de Unreal, el
puente Spout que trae la senal en vivo de TouchDesigner (sender
"TDSyphonSpoutOut", 4096x4096, mismo equipo) hasta el parametro de emision
de MI_Domo, y genera la configuracion de MCP para Claude Code.

Correr DESPUES de importar_sala.py (necesita que /Game/Maps/DomoVR y
MI_Domo ya existan) y con el editor CERRADO (headless).

Historial: la primera version de este script armaba un Blueprint en blanco
(BP_SpoutDomoReceiver) para que alguien terminara de cablear 3 nodos a mano
en el Event Graph. El usuario pidio sacar el Blueprint de la ecuacion: no
quiere cablear nada a mano. El puente se resolvio en C++
(ASpoutDomeReceiver, en Source/DomoVR/SpoutDomeReceiver.{h,cpp}) por dos
razones tecnicas, no solo de comodidad:

1. La firma real de SpoutReceiver (SpoutBPFunctionLibrary.h:110-116) recibe
   el material dinamico (OutMat) por referencia, y SpoutReceiver.cpp:436
   solo crea uno nuevo "if (!OutMat && InputMaterial)". Desde Blueprint, ese
   pin de salida no tiene memoria entre llamadas: se crearia una Dynamic
   Material Instance nueva CADA FRAME. En C++, OutMat se respalda en un
   UPROPERTY() del actor y se le pasa de vuelta cada Tick, asi que se crea
   una sola vez.
2. Verificado tambien: OptionalOutputRenderTarget si se usa de verdad en
   SpoutReceiver.cpp:457-466 (el comentario que dice "reserved for future"
   en SpoutBPFunctionLibrary.cpp esta desactualizado). No se termino
   usando en ASpoutDomeReceiver -- no hace falta un render target aparte
   para alimentar MI_Domo directamente -- pero queda anotado para quien lo
   retome.

Este script:
1. Borra BP_SpoutDomoReceiver (instancia del nivel y asset del proyecto):
   ya no hace falta, dejarlo solo confunde.
2. Asegura que Domo_Actor tenga MI_Domo en su slot de material 0.
3. Coloca (idempotente) una instancia de ASpoutDomeReceiver en el nivel,
   con sus propiedades apuntando a MI_Domo y a Domo_Actor.
4. Aplica el arreglo de Nanite (marcar_uso_nanite, reexportado desde
   importar_sala.py) sobre los materiales de la sala, por si este script se
   corre suelto despues de un reimport manual.
5. Genera la configuracion de MCP para Claude Code
   (ModelContextProtocol.GenerateClientConfig ClaudeCode) y confirma en
   donde quedo escrita.
6. Guarda nivel y assets.
"""

import os
import sys

import unreal

# Reusa la lista de materiales de la sala, el arreglo de Nanite y la
# resolucion del modelo de sala (DOMO_FOV) de importar_sala.py, para no
# duplicar esa logica.
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)
import importar_sala as sala  # noqa: E402

# Modelo de sala: sin DOMO_FOV (o 180) es /Game/Maps/DomoVR; con DOMO_FOV=90
# es /Game/Maps/DomoVR_90, etc. MI_Domo es compartido por todos los modelos:
# cada nivel tiene su propio SpoutDomeReceiver, que crea su instancia
# dinamica a partir del mismo MI_Domo. Ver 04_Docs/05_Modelos_de_sala.md.
MAP_PACKAGE_PATH = sala.MAP_PACKAGE_PATH
ES_MEDIA_ESFERA = sala.ES_MEDIA_ESFERA
MI_DOMO_PATH = "/Game/Sala/Materials/MI_Domo"
BP_SPOUT_RECEIVER_PATH = "/Game/Sala/BP_SpoutDomoReceiver"

# TD_Domo_Final = Pantallas (SPOUT_UNREAL). El de dosis.45 manda "TDSyphonSpoutOut".
SPOUT_SENDER_NAME = "TD_Domo_Lab"
PARAMETRO_TEXTURA_DOMO = "SpoutTexture"


def log(msg):
    unreal.log_warning("[conectar_spout] {}".format(msg))


def aviso(msg):
    unreal.log_warning("[conectar_spout] AVISO: {}".format(msg))


def fallar(msg):
    raise RuntimeError("[conectar_spout] {}".format(msg))


def cargar_nivel():
    level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    if not unreal.EditorAssetLibrary.does_asset_exist(MAP_PACKAGE_PATH):
        fallar(
            "No existe el mapa {}. Correr primero importar_sala.py.".format(MAP_PACKAGE_PATH)
        )
    ok = level_subsystem.load_level(MAP_PACKAGE_PATH)
    if not ok:
        fallar("No se pudo cargar el nivel {}.".format(MAP_PACKAGE_PATH))
    return level_subsystem


def borrar_blueprint_viejo(actor_subsystem):
    # 1) instancias en el nivel
    borrados = 0
    for actor in list(actor_subsystem.get_all_level_actors()):
        if actor.get_class().get_name().startswith("BP_SpoutDomoReceiver"):
            actor_subsystem.destroy_actor(actor)
            borrados += 1
    if borrados:
        log("Borradas {} instancias de BP_SpoutDomoReceiver del nivel.".format(borrados))

    # 2) el asset del Blueprint
    if unreal.EditorAssetLibrary.does_asset_exist(BP_SPOUT_RECEIVER_PATH):
        ok = unreal.EditorAssetLibrary.delete_asset(BP_SPOUT_RECEIVER_PATH)
        if not ok:
            fallar("No se pudo borrar el asset {} (ya no hace falta).".format(BP_SPOUT_RECEIVER_PATH))
        log("Asset {} borrado (el puente Spout ahora es C++).".format(BP_SPOUT_RECEIVER_PATH))


def encontrar_domo_actor(actor_subsystem):
    for actor in actor_subsystem.get_all_level_actors():
        if actor.get_actor_label() == "Domo_Actor":
            return actor
    fallar("No se encontro el actor 'Domo_Actor' en el nivel. Correr importar_sala.py primero.")


def asegurar_material_en_domo(domo_actor, mi_domo):
    mesh_comp = domo_actor.static_mesh_component
    if mesh_comp is None:
        fallar("Domo_Actor no tiene static_mesh_component (no deberia pasar en un AStaticMeshActor).")
    actual = mesh_comp.get_material(0)
    if actual != mi_domo:
        mesh_comp.set_material(0, mi_domo)
        log("Domo_Actor: material del slot 0 puesto en MI_Domo (antes: {}).".format(actual))
    else:
        log("Domo_Actor ya tenia MI_Domo en el slot 0.")
    return mesh_comp


def colocar_spout_dome_receiver(actor_subsystem, mi_domo, domo_mesh_comp):
    if not hasattr(unreal, "SpoutDomeReceiver"):
        fallar(
            "unreal.SpoutDomeReceiver no existe: el modulo DomoVR no cargo o no "
            "se recompilo despues de agregar la clase. Revisar "
            "Saved/Logs/DomoVR.log."
        )

    # Idempotente: se borra cualquier instancia previa antes de colocar la nueva.
    existentes = [
        a for a in actor_subsystem.get_all_level_actors()
        if a.get_class() == unreal.SpoutDomeReceiver
    ]
    if existentes:
        actor_subsystem.destroy_actors(existentes)
        log("Se borraron {} instancias previas de ASpoutDomeReceiver.".format(len(existentes)))

    actor = actor_subsystem.spawn_actor_from_class(
        unreal.SpoutDomeReceiver, unreal.Vector(0.0, 0.0, 0.0), unreal.Rotator(0.0, 0.0, 0.0)
    )
    if actor is None:
        fallar("spawn_actor_from_class devolvio None para SpoutDomeReceiver.")

    actor.set_actor_label("SpoutDomeReceiver")
    actor.set_editor_property("spout_sender_name", SPOUT_SENDER_NAME)
    actor.set_editor_property("target_material", mi_domo)
    actor.set_editor_property("texture_parameter_name", PARAMETRO_TEXTURA_DOMO)
    actor.set_editor_property("target_mesh_component", domo_mesh_comp)
    actor.set_editor_property("target_material_slot", 0)

    log(
        "SpoutDomeReceiver colocado: sender='{}', target_material=MI_Domo, "
        "parametro='{}', malla=Domo_Actor.".format(SPOUT_SENDER_NAME, PARAMETRO_TEXTURA_DOMO)
    )
    return actor


def re_marcar_nanite_en_materiales():
    """Vuelve a pasar marcar_uso_nanite (de importar_sala.py) sobre los
    materiales de la sala, por si este script se corre suelto despues de
    tocar algo a mano."""
    # Desde el 18 sep 2026 las superficies son instancias; el indicador vive
    # en los materiales base.
    nombres = ["M_Domo", "M_SalaPBR", "M_SalaEmisivo"]
    for nombre in nombres:
        ruta = sala._ruta_completa(sala.CONTENT_MATERIALS, nombre)
        material = unreal.EditorAssetLibrary.load_asset(ruta)
        if material is None:
            aviso("{} no existe todavia; no se puede marcar su uso Nanite.".format(ruta))
            continue
        sala.marcar_uso_nanite(material, nombre)
    log("Indicador de uso Nanite revisado en los materiales de la sala (USAR_NANITE={}).".format(sala.USAR_NANITE))
    unreal.EditorAssetLibrary.save_directory(sala.CONTENT_MATERIALS, False, True)


def generar_config_mcp(level_subsystem):
    if not hasattr(unreal, "UnrealEditorSubsystem"):
        aviso("unreal.UnrealEditorSubsystem no existe; se omite la generacion de config MCP.")
        return

    unreal_editor_subsystem = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    world = unreal_editor_subsystem.get_editor_world()
    if world is None:
        aviso("No se pudo obtener el mundo del editor; se omite la generacion de config MCP.")
        return

    # ExecuteConsoleCommand no devuelve nada (es void en KismetSystemLibrary.h);
    # la confirmacion real es que el archivo aparezca en disco, mas abajo.
    unreal.SystemLibrary.execute_console_command(world, "ModelContextProtocol.GenerateClientConfig ClaudeCode")
    log("Comando ejecutado: ModelContextProtocol.GenerateClientConfig ClaudeCode")

    # ModelContextProtocolClientConfig.cpp: para ClaudeCode escribe en
    # <ProjectDir>/.mcp.json cuando el motor esta instalado (no es build de
    # fuente), que es el caso de este engine en Program Files.
    ruta_esperada = os.path.join(
        unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir()), ".mcp.json"
    )
    if os.path.isfile(ruta_esperada):
        log("Configuracion de MCP para Claude Code escrita en: {}".format(ruta_esperada))
        with open(ruta_esperada, "r", encoding="utf-8") as f:
            log("Contenido de .mcp.json: {}".format(f.read()))
    else:
        aviso(
            "No aparecio {} despues de correr GenerateClientConfig. Revisar "
            "el log de arranque por 'LogModelContextProtocol'.".format(ruta_esperada)
        )


def main():
    log("=== Conectar Spout en C++ (TouchDesigner -> MI_Domo) + MCP ===")
    log("Modelo de sala: FOV {:g} -> nivel {}".format(sala.FOV_DOMO, MAP_PACKAGE_PATH))

    if not hasattr(unreal, "SpoutBPFunctionLibrary"):
        fallar("SpoutPlugin no cargo (unreal.SpoutBPFunctionLibrary no existe).")

    mi_domo = unreal.EditorAssetLibrary.load_asset(MI_DOMO_PATH)
    if mi_domo is None:
        fallar("No se encontro {}. Correr importar_sala.py primero.".format(MI_DOMO_PATH))

    level_subsystem = cargar_nivel()
    actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

    borrar_blueprint_viejo(actor_subsystem)

    domo_actor = encontrar_domo_actor(actor_subsystem)
    domo_mesh_comp = asegurar_material_en_domo(domo_actor, mi_domo)

    colocar_spout_dome_receiver(actor_subsystem, mi_domo, domo_mesh_comp)

    if ES_MEDIA_ESFERA:
        # Solo en el modelo base: los materiales son compartidos y ya estan
        # marcados; en los casquetes no se resalvan assets del 180.
        re_marcar_nanite_en_materiales()

    ok = level_subsystem.save_current_level()
    if not ok:
        aviso("save_current_level devolvio False.")
    if ES_MEDIA_ESFERA:
        unreal.EditorAssetLibrary.save_directory("/Game/Sala", False, True)
        generar_config_mcp(level_subsystem)
    else:
        log("Casquete: se guarda solo el nivel; .mcp.json y materiales quedan como los dejo el 180.")

    log("=== Fin conectar_spout.py ===")


main()
