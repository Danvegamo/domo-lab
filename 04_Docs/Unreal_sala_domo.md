# Sala de domo en Unreal Engine 5.8 para VR

Este documento explica cómo está armado el proyecto de Unreal que visualiza en
realidad virtual la sala de domo tipo planetario, qué hace cada script, cómo
se corre la importación de la geometría que genera el otro agente en Blender,
cómo se entra en VR desde este equipo, y cómo quedó armado (y qué falta a
mano) el puente en vivo con TouchDesigner por Spout.

## 0. Aviso operativo importante

El editor de `DomoVR` puede estar abierto con interfaz gráfica en este mismo
equipo. **Mientras el editor esté abierto, no correr `importar_sala.ps1` (ni
`UnrealEditor-Cmd.exe` a mano) contra el mismo `.uproject`**: dos procesos de
Unreal sobre el mismo proyecto se pelean por los mismos archivos de
`Saved/`/`Intermediate/` y por el `.umap`. Con el editor abierto, la
importación se corre desde dentro de él (por ejemplo desde la consola de
Python del editor, pegando el contenido de `importar_sala.py`, o con un botón
que la llame). El script está escrito para poder correrse así sin cambios: no
depende de nada que solo exista en modo headless.

## 1. Dónde está todo

```
Domo_VR_Unreal/
  01_Blender/          <- del otro agente, no se toca desde aquí
  02_Export/            <- del otro agente; aquí llegan sala_domo.fbx y texturas/
    texturas/            <- mapas PBR horneados (color, rugosidad, normal)
  03_Unreal/
    DomoVR/
      DomoVR.uproject
      Config/
        DefaultEngine.ini
        DefaultGame.ini
      Source/              <- modulo C++ minimo, vacio, solo para compilar plugins
        DomoVR.Target.cs
        DomoVREditor.Target.cs
        DomoVR/
          DomoVR.Build.cs, DomoVR.h, DomoVR.cpp
      Plugins/
        SpoutPlugin/        <- github.com/kessoning/Spout-UE5, rama 5.8_fix
      Content/
        Sala/
          Materials/    <- M_Domo, MI_Domo, M_Muro, M_Piso, M_Butaca,
                            M_Tarima, M_Control, M_Puerta
          Textures/      <- texturas horneadas ya importadas (T_<material>_<tipo>)
          BP_SpoutDomoReceiver  <- recibe Spout y alimenta MI_Domo (ver seccion 8)
        Maps/
          DomoVR.umap
    DomoVR_backup_preCpp/  <- copia de seguridad de antes de agregar C++/Spout
    importar_sala.py     <- script de Python de Unreal (geometria, materiales, nivel)
    conectar_spout.py     <- script hermano: puente Spout -> MI_Domo (ver seccion 8)
    abrir_proyecto.ps1    <- abre el editor grafico
    importar_sala.ps1     <- corre la importacion headless
  04_Docs/
    Unreal_sala_domo.md   <- este archivo
  05_Preview/            <- del otro agente, no se toca desde aquí
```

## 2. El proyecto (`DomoVR.uproject`)

El proyecto empezó **solo Blueprint** (sin módulos de código C++ propios).
Sigue siéndolo en cuanto a lógica de juego — toda la sala, sus materiales y
su nivel se arman por Python/datos, no por código — pero desde que se
agregó el puente de Spout (sección 8) sí tiene un módulo C++ mínimo
(`Source/DomoVR/`), con una sola clase propia (`ASpoutDomeReceiver`), y por
lo tanto necesita compilarse con Visual Studio/`UnrealBuildTool` antes de
poder abrirse — ya no alcanza con doble clic al `.uproject` la primera vez
o después de tocar el código; ver sección 8.3 para el comando exacto de
compilación.

Plugins habilitados en el `.uproject`:

- **PythonScriptPlugin** — para poder correr `importar_sala.py` y
  `conectar_spout.py`.
- **EditorScriptingUtilities** — subsistemas de edición por script
  (`EditorActorSubsystem`, `LevelEditorSubsystem`, etc.) que usan los
  scripts.
- **OpenXR** — la ruta de VR. En Unreal 5.8 ya no existe un plugin aparte
  "SteamVR": SteamVR actúa como *runtime* OpenXR del sistema, y Unreal habla
  con él a través del plugin OpenXR estándar del motor. No hace falta ni
  existe ningún plugin adicional de terceros que instalar.
- **SpoutPlugin** — el puente con TouchDesigner; ver sección 8.
- **ModelContextProtocol** y **EditorToolset** — control del editor por MCP
  para Claude Code; ver sección 9.

`EngineAssociation` queda en `"5.8"`. Como el motor está instalado en
`C:\Program Files\Epic Games\UE_5.8\` (misma convención que un install del
Launcher), esto alcanza para que `UnrealEditor(-Cmd).exe` de esa carpeta abra
el proyecto sin pedir conversión de versión.

### `Config/DefaultEngine.ini`

- `r.DynamicGlobalIlluminationMethod=1` y `r.ReflectionMethod=1` — Lumen para
  iluminación global y para reflejos (los valores del enum de Project
  Settings; `1` es Lumen en ambos casos).
- `r.GenerateMeshDistanceFields=True` — campos de distancia disponibles para
  Lumen.
- `r.Nanite.ProjectEnabled=True` — deja Nanite disponible a nivel de
  proyecto (necesario para poder activarlo algún día por malla). Hoy
  ninguna malla lo usa: ver la constante `USAR_NANITE` en
  `importar_sala.py` y el porqué más abajo.
- `r.DefaultFeature.AutoExposure=False` — la exposición automática queda
  apagada como valor por defecto del proyecto, coherente con el Post Process
  Volume de exposición fija que arma `importar_sala.py`.
- `DefaultGraphicsRHI=DefaultGraphicsRHI_DX12` bajo
  `[/Script/WindowsTargetPlatform.WindowsTargetSettings]` — DX12 como RHI por
  defecto, apto para Lumen con trazado por hardware en la RTX 3090.
- `bStartInVR=True` en `GeneralProjectSettings` — al lanzar el juego/PIE
  intenta arrancar directo en VR si hay un HMD disponible.
- `vr.InstancedStereo=1` en `[ConsoleVariables]` — estéreo instanciado
  (dibuja los dos ojos en menos passes), el ajuste estándar de rendimiento
  para HMDs binoculares como el Quest.

Al principio no se definió un mapa de inicio (`EditorStartupMap`/
`GameDefaultMap`) a propósito: así el proyecto abría limpio incluso antes de
que existiera `/Game/Maps/DomoVR`, que es lo que hacía falta para verificar
el proyecto antes de tener el FBX. Ahora que el nivel existe de verdad, se
puso:

```
[/Script/EngineSettings.GameMapsSettings]
EditorStartupMap=/Game/Maps/DomoVR.DomoVR
GameDefaultMap=/Game/Maps/DomoVR.DomoVR
```

Sin esto, un editor recién abierto (sobre todo si viene de una serie de
corridas headless, que no dejan "último nivel abierto" en el sentido en que
lo hace la interfaz gráfica) cae en un nivel `Untitled` vacío en vez de
mostrar la sala — se comprobó exactamente ese comportamiento antes de poner
esta configuración.

## 3. El contrato de geometría (versión final)

La sala es un **cilindro cerrado de 11.5 m de radio**, piso plano (sin
grada), sin ningún volumen exterior — todo lo que hace falta vive dentro de
ese cilindro:

- `SM_Domo` — cúpula, normales hacia adentro, UV con U = azimut y V =
  elevación. Emisivo, sin textura horneada (la imagen la pone TouchDesigner
  en vivo).
- `SM_Muro`, `SM_Piso` — el cilindro y el piso.
- `SM_Tarima` — cilindro central de 3 m de diámetro x 1 m de alto, en el
  origen. **El `PlayerStart` no puede coincidir con este volumen.**
- `SM_Control` — sector de 5 m de ancho contra el muro (lado −X), sin
  butacas: el piso marcado y el mobiliario (consola, mesa) de un puesto de
  operación dentro de la misma sala, flanqueado por dos de las cuatro
  puertas.
- `SM_Butacas_01`…`SM_Butacas_06` — 6 cuñas radiales (como porciones de
  pizza) alrededor de la tarima, 60 butacas reclinables cada una (360 en
  total), repartidas en unos 335° (no los 360° completos, por el sector de
  control). Los respaldos van muy reclinados: el espectador queda casi
  acostado mirando al cenit.
- `SM_Puerta_01`…`SM_Puerta_04` — cuatro puertas con hueco real en el muro
  cilíndrico.

Materiales: `M_Domo`, `M_Muro`, `M_Piso`, `M_Butaca`, `M_Tarima`, `M_Control`,
`M_Puerta`. Escala: 1 m de Blender = 100 uu de Unreal (el FBX ya viene así).

Texturas PBR horneadas en `02_Export/texturas/` (color base, rugosidad y
normal, 2048×2048) para `M_Piso`, `M_Muro`, `M_Butaca`, `M_Tarima` y
`M_Puerta`. **`M_Domo` y `M_Control` no llevan textura horneada** — el domo
porque es puramente emisivo/paramétrico para recibir la señal en vivo, y
`M_Control` porque no vino en la lista de mapas que se van a hornear (queda
con un color plano oscuro y mate, igual que antes).

## 4. `importar_sala.py`: qué hace y por qué

Se corre así (con el editor **cerrado**; ver aviso de la sección 0 si está
abierto):

```
UnrealEditor-Cmd.exe <ruta>\DomoVR.uproject -run=pythonscript -script=<ruta>\importar_sala.py -unattended -nosplash -nosound
```

(el script `importar_sala.ps1` arma ese comando con las rutas correctas; ver
sección 5).

Pasos que ejecuta, en orden:

1. **Importa `02_Export/sala_domo.fbx`** a `/Game/Sala/` usando el
   importador clásico de FBX (`unreal.FbxFactory` + `unreal.FbxImportUI`,
   no el framework Interchange), con `combine_meshes = False` para que cada
   objeto del FBX quede como su propio Static Mesh, con `build_nanite`
   controlado por la constante `USAR_NANITE` (hoy en `False`; ver el
   recuadro "Nanite: encendido o apagado" más abajo).

   **Si el archivo todavía no existe**, el script no falla: registra un
   aviso y sigue con el resto (materiales, nivel, iluminación, punto de
   partida). Esto es justamente lo que permitió verificar el proyecto y el
   script antes de que el otro agente terminara de generar la geometría. Si
   el archivo **sí** existe pero la importación no devuelve ningún Static
   Mesh, eso ya no se trata como "archivo faltante": el script para con una
   excepción, porque es un fallo real de importación que hay que mirar en el
   log de FBXImport.

   **Nombres reales de los assets importados — atención**: en una corrida
   real de prueba contra un `sala_domo.fbx` anterior, los Static Mesh
   quedaron nombrados `sala_domo_SM_Domo`, `sala_domo_SM_Muro`, etc. (con el
   nombre del archivo FBX antepuesto), no exactamente `SM_Domo` como dice el
   contrato al pie de la letra. Esto es un comportamiento del importador de
   FBX de Unreal cuando el nodo/objeto de origen no tiene un nombre único
   dentro de la escena; probablemente Blender está agrupando los objetos
   bajo un nodo o colección llamada `sala_domo`. Para no depender de que esto
   se corrija del lado de Blender, `importar_sala.py` resuelve los nombres
   **por sufijo** (`_nombre_canonico_de_malla`): acepta tanto `SM_Domo` como
   `algo_SM_Domo`. Lo mismo aplica a las variantes de butacas/puertas que no
   calcen con el patrón esperado: quedan registradas en los avisos en vez de
   perderse en silencio.

2. **Busca e importa las texturas PBR** de `02_Export/texturas/` para
   `M_Piso`, `M_Muro`, `M_Butaca`, `M_Tarima` y `M_Puerta`. Como todavía no
   se conoce la convención de nombres exacta que va a usar el otro agente,
   la búsqueda es flexible: para cada material, busca un archivo cuyo nombre
   contenga el nombre del material (sin el prefijo `M_`) y algún sinónimo
   del tipo de mapa (`basecolor`/`albedo`/`diffuse`/`color`,
   `roughness`/`rough`, `normal`/`nrm`). Si no encuentra alguno, ese material
   cae a un color plano de respaldo en vez de fallar. Al importar cada
   textura:
   - **Base color**: se deja con los valores por defecto (sRGB encendido):
     es una textura de color real.
   - **Rugosidad**: `compression_settings = TC_Masks` y `srgb = False` — es
     un mapa de datos, no de color; dejarle sRGB encendido es el error
     clásico que arruina los valores de rugosidad.
   - **Normal**: `compression_settings = TC_Normalmap` y `srgb = False` —
     así queda marcada como mapa de normales de verdad, no como una textura
     de color más.

3. **Crea los materiales** en `/Game/Sala/Materials/`:
   - **`M_Domo`**: shading model **Unlit** (no recibe ni reacciona a luces;
     solo muestra lo que se le ponga en el emisivo, que es exactamente lo
     que se necesita para una superficie de proyección). Tiene un nodo
     `TextureSampleParameter2D` con el parámetro **`SpoutTexture`** conectado
     a Emissive Color, con una textura de grilla del propio motor
     (`/Engine/EngineMaterials/T_Default_Material_Grid_M`) como marcador de
     posición — útil además para comprobar a ojo el mapeo UV azimut/elevación
     del domo apenas se vea en el visor. No usa ningún mapa horneado. Se crea
     también **`MI_Domo`**, una Material Instance con `M_Domo` como padre,
     que es la que de verdad se asigna a la malla del domo (ver sección 8,
     pendientes de Spout).
   - **`M_Muro`, `M_Piso`, `M_Butaca`, `M_Tarima`, `M_Puerta`**: Default Lit;
     si hay textura horneada la usan (color base → Base Color, rugosidad →
     Roughness por el canal R, normal → Normal), y si no, caen a un color
     plano oscuro y mate (parámetros `Color`/`Roughness` expuestos, para
     poder variarlos por Material Instance sin duplicar el material). El
     metálico siempre queda en una constante 0: no hay mapas metálicos en el
     contrato.
   - **`M_Control`**: mismo esquema que los anteriores, pero como no vino en
     la lista de mapas a hornear, siempre cae al color plano de respaldo
     (gris oscuro neutro, algo menos mate que las paredes — es un puesto de
     trabajo, no la superficie de proyección).

4. **Arma el nivel `/Game/Maps/DomoVR`**:
   - Coloca un actor por cada malla reconocida usando la transformación que
     ya trae el FBX.
   - Quita cualquier `SkyLight`, `DirectionalLight`, `ExponentialHeightFog` o
     `SkyAtmosphere` que el nivel pudiera traer: la única fuente de luz
     relevante en la sala debe ser la emisión de `M_Domo`.
   - Crea un `PostProcessVolume` con extensión infinita (`Unbound`) y
     exposición **manual y fija**: método de auto-exposición en `Manual` con
     los overrides de bias/brillo mínimo/máximo activados. Con exposición
     automática, la cámara reaccionaría a la propia imagen proyectada sobre
     la cúpula y arruinaría la lectura del contenido. Al ser `Unbound` no
     depende del tamaño de la sala ni de que haya o no un volumen exterior.
   - Coloca un `PlayerStart` a **400 cm del centro** (fuera del radio de 150
     cm de `SM_Tarima`, hacia +X, es decir del lado opuesto al sector de
     control que está en −X) y a **70 cm de altura** sobre el piso. Ambos
     números son una aproximación de trabajo, no datos medidos: con el piso
     plano y los respaldos casi acostado mirando al cenit, la altura de ojo
     es bastante más baja que la de alguien sentado erguido (~120 cm) o
     incluso que la de alguien apenas reclinado (~105 cm, la estimación de
     una versión anterior de este mismo script, de cuando los respaldos
     todavía no eran tan extremos). Hay que ajustar la posición y la altura
     con las coordenadas reales de las butacas apenas lleguen.

5. **Guarda todo**: las texturas, los materiales, el contenido de
   `/Game/Sala/` y el mapa.

6. **Imprime un resumen** al final (mallas importadas, mallas que faltaron,
   texturas importadas, materiales creados, actores colocados, avisos). Los
   mensajes de progreso del script salen como `Warning` en el log (con el
   prefijo `[importar_sala]`), no como `Display`: en las corridas de prueba,
   los mensajes `Display` de la categoría `LogPython` no siempre llegaban a
   la consola en modo `-run=pythonscript -unattended`, mientras que los
   `Warning` sí, siempre. Por eso se usó ese nivel a propósito para
   garantizar que el resumen se vea.

### Idempotencia: se puede correr las veces que haga falta

El script es la fuente de verdad de sus propios assets. Cada material,
textura e instancia de material se crea con un helper (`crear_asset`) que
primero borra el asset si ya existía en esa ruta, y nunca sigue adelante con
un `None`: si `create_asset` (o `load_asset`, o `spawn_actor_from_class`,
etc.) devuelve algo vacío, el script para de inmediato con una excepción que
dice qué asset y qué ruta fallaron. El nivel se trata distinto: si
`/Game/Maps/DomoVR` ya existe, no se borra ni se recrea (es más delicado si
el editor lo tiene abierto); se **carga** y se **limpia de actores**
(`destroy_actors` sobre todo lo que haya) antes de reconstruirlo desde cero.
La importación del FBX ya traía esto resuelto con `replace_existing = True`.

Esto se descubrió en la práctica, no en el papel: una corrida de prueba
sobre materiales que ya existían hizo que `create_asset` devolviera `None`
para `M_Domo`, y el script siguió una línea más abajo llamando
`material.set_editor_property(...)` sobre ese `None`, reventando con un
`AttributeError` en vez de un error claro. El punto exacto era
`_material_domo_emisivo()` (hoy reescrito para usar `crear_asset`, que
falla en el sitio correcto con el mensaje correcto).

### La colocación de la geometría en el nivel (y por qué falló una vez)

Una corrida headless real (con las 15 mallas y las texturas ya importadas
correctamente) dejó el mapa `/Game/Maps/DomoVR` sin geometría: las 15
llamadas a colocar una malla devolvieron `None`, y el script las registró
como aviso y siguió, terminando con código de salida `0` como si hubiera
salido bien. Eso era justamente el problema — un import que no coloca nada
no debería reportar éxito — y además había que entender la causa de raíz en
vez de tantear a ciegas.

**Causa, confirmada leyendo el motor** (no adivinada): la función que se
usaba, `EditorActorSubsystem.spawn_actor_from_object(mesh, ...)` (y su
equivalente viejo `EditorLevelLibrary.spawn_actor_from_object`, que llama
literalmente a la misma subrutina), resuelve qué actor crear a través del
sistema de **colocación de assets de la interfaz del editor**
(`FLevelEditorViewportClient::TryPlacingActorFromObject` →
`TryPlacingAssetObject`, en
`Engine/Source/Editor/UnrealEd/Private/LevelEditorViewport.cpp`). Ese
sistema es el que usa el editor cuando arrastrás un asset del Content
Browser a un viewport, y necesita un **viewport de Level Editor activo**
para decidir dónde y cómo colocarlo. Un commandlet lanzado con
`-run=pythonscript` **no abre esa interfaz** (no hay ventana, no hay
viewport): la función interna llega a `Actors.Num() == 0` y devuelve un
array vacío con solo un `Warning` en el log (`"No actor was spawned"`), no
una excepción — de ahí que Python reciba `None` en silencio, 15 veces
seguidas, sin que nada "explote".

La prueba de que el diagnóstico es correcto está en la misma corrida: el
`PostProcessVolume` y el `PlayerStart` **sí** se colocaron bien, y esos dos
se crean con `spawn_actor_from_class` (instanciar una *clase* de actor), no
con `spawn_actor_from_object` (colocar un *asset*). Instanciar una clase es
un camino más simple, dentro de la misma subrutina interna, que no necesita
resolver "qué factory de colocación le corresponde a este asset" — y esa
resolución es justo la parte que depende del viewport.

**Arreglo**: `colocar_geometria()` ya no llama a `spawn_actor_from_object`.
En su lugar, por cada malla:

1. Crea un `AStaticMeshActor` vacío con `spawn_actor_from_class` (el camino
   que ya se demostró que funciona headless).
2. Le asigna la malla a mano: `actor.static_mesh_component.set_static_mesh(mesh)`
   (`UStaticMeshComponent.SetStaticMesh` es una función normal, sin ninguna
   dependencia de interfaz — solo cambia qué malla renderiza el componente).

Con esto el resultado final es el mismo (un `AStaticMeshActor` por cada
pieza, en la posición que ya trae horneada el FBX), pero sin pasar por el
sistema de colocación interactivo. Además, ahora `colocar_geometria()`
junta cualquier malla que falle en cualquiera de esos dos pasos y, si la
lista no queda vacía, **para el script con una excepción** que nombra las
mallas afectadas — igual que se hizo con `create_asset` para los materiales:
ya no hay forma de que "no se colocó nada" termine reportado como éxito.

**Esto último no se pudo volver a correr contra el proyecto real** (el
editor gráfico estaba abierto — ver aviso de la sección 0 — y no se podía
lanzar un commandlet headless encima sin pelearse con él). El diagnóstico y
la firma de cada función (`AStaticMeshActor.static_mesh_component`,
`UStaticMeshComponent.set_static_mesh`, y el propio código de
`TryPlacingActorFromObject`) están confirmados leyendo
`C:\Program Files\Epic Games\UE_5.8\Engine\Source\` directamente, no
supuestos; pero la corrida real que demuestra que el arreglo coloca las 15
mallas de verdad queda pendiente del próximo ciclo headless.

### Nanite: encendido o apagado (y el bug del indicador de uso)

El encargo original pedía cuidar que 360 butacas repetidas no queden como
"una malla monolítica absurda". Se evaluó armar un esquema de
`InstancedStaticMeshComponent` para las butacas, pero no aporta nada en este
caso concreto: el contrato con Blender entrega 6 assets de malla para
butacas (uno por cuña, cada uno ya con sus 60 butacas fusionadas). Ahí no
hay 360 instancias que agrupar a nivel de actor: ya son solo 6 draw calls,
tan barato como puede ser sin tocar la geometría — la palanca real para
absorber densidad de geometría en Unreal 5 es Nanite, no el instanciado
manual.

**Se probó primero con Nanite encendido** (`build_nanite = True` en la
importación, para las 15 mallas de la sala). Eso trajo un problema real,
encontrado en una corrida de "Verificación de mapa" del editor: 0 errores,
pero 6 advertencias, una por cada material de la sala (`M_Muro`, `M_Piso`,
`M_Butaca`, `M_Tarima`, `M_Control`, `M_Puerta` — `M_Domo` no, porque es
Unlit y esa comprobación no aplica igual sobre materiales sin iluminación):

```
Al material /Game/Sala/Materials/M_Butaca.M_Butaca le faltaba el indicador de uso Nanite.
Si el recurso material no se vuelve a guardar, es posible que no se renderice correctamente
cuando se ejecuta fuera del editor.
```

Causa: las mallas se importaban con Nanite activo, pero
`importar_sala.py` creaba los materiales sin poner el indicador de uso
correspondiente en el asset. El editor lo activa al vuelo en memoria (por
eso se ve bien mientras se está trabajando ahí), pero como el `.uasset` del
material nunca se vuelve a guardar con ese indicador puesto, una
compilación empaquetada (donde no hay editor arreglando las cosas al vuelo)
podía rendirizar mal esos materiales sobre las mallas Nanite.

**La decisión final fue apagar Nanite** (`USAR_NANITE = False`, una única
constante en `importar_sala.py`), no arreglar el indicador y dejarlo
prendido. Razón: la sala completa, hoy, son **43 294 triángulos** en total.
Nanite existe para absorber densidades de millones de triángulos;  a este
conteo no aporta nada — solo agrega costo (streaming de clusters, DDC más
pesada, y el propio mantenimiento del indicador de uso que causó el bug de
arriba). Apagarlo es lo proporcionado y correcto para la geometría de hoy.

Eso sí quedó dejado listo para el día que el usuario escanee el planetario
real por fotogrametría con RealityCapture y entre geometría de verdad
pesada (potencialmente millones de triángulos, ahí Nanite sí se justifica):
**`USAR_NANITE` es la única constante que hay que voltear a `True`**. Tanto
`build_nanite` en la importación del FBX como el indicador de uso en cada
material (`marcar_uso_nanite()`, que llama a
`MaterialEditingLibrary.set_base_material_usage(material,
unreal.MaterialUsage.MATUSAGE_NANITE, USAR_NANITE)` — la función no
deprecada; existe `SetMaterialUsage` pero el propio motor la marca
`DeprecatedFunction` a favor de esta) se derivan de esa misma constante, así
que no pueden volver a quedar desincronizados como la primera vez. Después
de poner el indicador, el script también comprueba con
`has_material_usage()` que haya quedado puesto de verdad, y deja un aviso
en el log si no.

Si en el futuro el FBX llega con una malla de butaca por asiento en vez de
por cuña (más instancias reales que agrupar), `importar_sala.py` ya deja
una advertencia explícita en el log para retomar ahí la decisión de usar
instanciado manual además de (o en vez de) Nanite.

## 5. Los scripts de PowerShell

- **`abrir_proyecto.ps1`**: abre `DomoVR.uproject` con `UnrealEditor.exe`
  (interfaz gráfica completa). Rutas absolutas, corre desde cualquier
  directorio. La primera apertura compila shaders y deriva datos: puede
  tardar varios minutos con la GPU al 100%, es normal.

- **`importar_sala.ps1`**: corre `importar_sala.py` de forma headless con
  `UnrealEditor-Cmd.exe -run=pythonscript`, escribiendo un log en
  `03_Unreal\Saved_Logs\importar_sala.log` (crea la carpeta si hace falta) y
  devolviendo el código de salida real del proceso. **No correr este script
  mientras el editor gráfico tenga el proyecto abierto** (ver sección 0).

## 6. Cómo se verificó que el proyecto abre limpio

Se corrió `UnrealEditor-Cmd.exe DomoVR.uproject -run=pythonscript
-script=<script mínimo>` (imprime la versión del motor y sale) de forma
headless. Resultado: **`Success - 0 error(s), 1 warning(s)`**, código de
salida `0`. El único warning que se dejó pasar:

```
LogTemp: Warning: Existing value for UEditorPerformanceSettings::MaxViewportRenderingResolution will be overriden for OpenXR.
```

Es el propio plugin OpenXR avisando que va a pisar un ajuste de resolución
de viewport del editor para preparar el modo VR; no indica ningún problema
de configuración del proyecto.

Después se corrió una versión anterior de `importar_sala.py` completa (con
el FBX todavía sin llegar, apuntando a una ruta forzada a no existir para no
tocar el archivo real mientras el otro agente lo regeneraba) y también
terminó con **`Success - 0 error(s)`**. Quedaron creados de verdad `M_Domo`,
`MI_Domo`, `M_Muro`, `M_Piso`, `M_Butaca` y el mapa `/Game/Maps/DomoVR` (sin
geometría, porque el FBX no estaba disponible en esa corrida). Esa misma
sesión de pruebas también encontró y permitió corregir el problema de
idempotencia de la sección anterior.

**El contrato de geometría cambió varias veces después de esa última
verificación** (piso plano en vez de grada, cuñas radiales, tarima central,
sector de control, puertas, texturas PBR) y **el editor gráfico quedó
abierto con el proyecto cargado** para que se pudiera revisar en vivo. Por
las dos razones a la vez — no pelearse con el editor abierto, y no dejar
sin probar código nuevo que además tuvo que reescribirse por el hallazgo de
idempotencia — **la versión final de `importar_sala.py` (la que incluye
`SM_Tarima`, `SM_Control`, `SM_Puerta_01..04`, las texturas PBR y los
arreglos de idempotencia) no se volvió a correr contra el proyecto real**.
Cada pieza de API que usa (creación de texturas con `TextureFactory` +
`AssetImportTask`, `compression_settings`/`srgb`, los nombres de canal de
salida `RGB`/`R`/`G`/`B`/`A` de un `TextureSampleParameter2D`, los nombres
de propiedad de `PostProcessVolume`/`AutoExposure`) se verificó leyendo el
código fuente del motor en
`C:\Program Files\Epic Games\UE_5.8\Engine\Source\`, no adivinando — pero
recién se ejecuta de verdad la primera vez que alguien corra
`importar_sala.py` (por consola de Python dentro del editor abierto, o con
`importar_sala.ps1` una vez que el editor se cierre). Si algo de eso truena,
el mensaje de error va a decir exactamente qué asset y qué línea, gracias al
propio trabajo de idempotencia — no debería hacer falta ir a ciegas.

Aparte de eso, en el log de arranque aparece esta línea, impresa por la
propia librería de OpenXR (no por Unreal, por eso no tiene marca de tiempo
de `LogInit`) y que **no** cuenta en el resumen de errores del motor:

```
Error [GENERAL | xrCreateInstance | OpenXR-Loader] : xrCreateInstance called with invalid API version 1.1.  Max supported version is 1.0
```

Ocurre en cada arranque en cuanto el plugin OpenXR intenta negociar una
instancia con el *runtime* OpenXR activo del sistema, haya o no un visor
conectado en ese momento. No impidió que el editor terminara de cargar ni
que el script corriera (el proceso salió con código `0` en todas las
corridas). Es un candidato claro a molestar cuando se intente entrar en VR
de verdad: si al ponerse el visor la sesión de OpenXR no arranca, revisar
primero que SteamVR esté corriendo y que su runtime OpenXR esté seleccionado
como activo (`vrmonitor` → Configuración → Desarrollador → "Set SteamVR as
OpenXR runtime"), antes de sospechar del proyecto.

## 7. Cómo entrar en VR (OpenXR + SteamVR + Virtual Desktop)

1. Encender el Quest y conectarlo por **Virtual Desktop Streamer** al PC
   (streaming por red, no por cable — la ruta que ya está probada en este
   equipo).
2. Arrancar **SteamVR** en el PC. Confirmar en su configuración que el
   runtime OpenXR activo del sistema es el de SteamVR (es el que se instala
   por defecto al abrirlo, pero vale la pena confirmarlo si hay otro
   software de VR instalado que también se registre como runtime OpenXR,
   como el propio Oculus/Meta).
3. Abrir el proyecto con `abrir_proyecto.ps1` (o directamente
   `UnrealEditor.exe DomoVR.uproject`) — o usar el editor que ya esté abierto.
4. Abrir el mapa `/Game/Maps/DomoVR` (una vez que exista: hace falta haber
   corrido `importar_sala.py` primero).
5. Play → **VR Preview** (no el Play normal en viewport). Unreal debe
   detectar el HMD a través de OpenXR y arrancar la sesión estéreo. Si no
   arranca, el primer sospechoso es la línea de `xrCreateInstance` de la
   sección 6: revisar que SteamVR esté corriendo y con su runtime OpenXR
   activo antes de tocar nada del proyecto.

## 8. El puente Spout con TouchDesigner

### 8.1 Por qué Spout y no NDI (y por qué esto ya no es "solo Blueprint")

UE 5.8 trae de fábrica un plugin `NDIMedia` (Epic, con `NDIMediaSource` y
`NDIMediaOutput`, binarios ya compilados) y se evaluó usarlo primero: no
exige tocar C++ ni compilar nada. Pero la decisión del usuario fue ir por
**Spout**, así que NDI se dejó donde estaba — no se llegó a habilitar en el
`.uproject` ni a tocar `DefaultEngine.ini` para él, así que no queda ningún
resto suyo en el proyecto. Si en algún momento se prefiere volver a la ruta
sin compilar, `NDIMedia` sigue disponible en el motor sin instalar nada.

Ir por Spout significa que `DomoVR` **deja de ser un proyecto puramente de
contenido**: un plugin con código C++ (`SpoutPlugin`) obliga a que el
proyecto tenga su propio módulo de C++ para que `UnrealBuildTool` tenga
contra qué compilar. Se agregó lo mínimo posible para eso — ver 8.3 — pero
sigue sin haber ninguna lógica de juego en C++: todo el comportamiento en
tiempo de ejecución sigue viviendo en Blueprints, tal como pedía el encargo
original.

### 8.2 El plugin: cuál, de dónde, y con qué licencia

- Repositorio: **https://github.com/kessoning/Spout-UE5**, rama **`5.8_fix`**
  (commit `ac7f9fb`, "Added 5.8 support"), no la rama `main`. El
  `CHANGELOG.md` del propio repo confirma el motivo: la versión `0.0.5`
  corrige justo la compatibilidad con UE 5.8 (`FSlateRenderer::OnBackBufferReadyToPresent`
  cambió de firma en 5.8; el código está resguardado con
  `ENGINE_MAJOR_VERSION`/`ENGINE_MINOR_VERSION` para no romper 5.3–5.7). Es
  un fork del repositorio original de `zuyi53`; el autor actual (Kesson) lo
  mantiene y lo aclara en su propio README.
- **Licencia**: el `README.md` del repositorio dice explícitamente "This
  project is licensed under the MIT License. See the LICENSE file for
  details." — pero la rama `5.8_fix` clonada **no trae un archivo
  `LICENSE`** en su raíz (se buscó explícitamente y no está). Vale la pena
  confirmar con el autor o revisar otra rama/tag antes de usar esto en
  trabajo de cliente, ya que ahora mismo la única evidencia de la licencia
  es esa frase en el README, no un archivo de licencia versionado.
- Alternativas reales si esto se vuelve un problema (mencionadas también
  por el propio README del plugin): el **NDI de fábrica** de UE 5.8 (sección
  8.1), o el **kit comercial de Off World Live** (Fab), que trae binarios
  precompilados y cubre tanto Spout como NDI sin tener que compilar nada.

### 8.3 Qué se agregó al proyecto y cómo quedó compilando

- `03_Unreal/DomoVR/Plugins/SpoutPlugin/` — el plugin clonado completo
  (`Source/`, `ThirdParty/Spout/{include,lib}` con `Spout.dll`/`Spout.lib`
  ya incluidos, `Content/` con Blueprints de ejemplo). Habilitado en
  `DomoVR.uproject`.
- `03_Unreal/DomoVR/Source/` — módulo de proyecto mínimo, agregado solo
  para que `UnrealBuildTool` tenga un target de `DomoVR` contra el cual
  compilar el plugin:
  - `DomoVR.Target.cs` / `DomoVREditor.Target.cs` — targets de juego y de
    editor, `BuildSettingsVersion.Latest`.
  - `Source/DomoVR/DomoVR.Build.cs`, `DomoVR.h`, `DomoVR.cpp` — módulo
    vacío (`IMPLEMENT_PRIMARY_GAME_MODULE` sin una sola clase de juego
    propia). No hay Actors, Components ni lógica en C++ del lado de
    `DomoVR`; ese módulo existe únicamente para que el proyecto **tenga**
    módulo, requisito de `UnrealBuildTool` para compilar cualquier plugin
    con código.
  - `DomoVR.uproject` ahora declara `"Modules": [{"Name": "DomoVR", ...}]`.
- **Copia de seguridad**: antes de tocar nada de esto se copió el proyecto
  completo (tal como estaba, con el nivel de 17 actores ya armado) a
  `03_Unreal/DomoVR_backup_preCpp/`. No hizo falta usarla — la conversión no
  rompió el nivel (se verificó después: los 17 actores originales siguen
  ahí, ver 8.5) — pero queda disponible por si acaso.

**Compilación real, verificada**: se cerró el editor gráfico (obligatorio
para compilar) y se corrió

```
UnrealBuildTool.exe DomoVREditor Win64 Development -Project="<ruta>\DomoVR.uproject" -WaitMutex
```

con el toolchain de esta máquina (Visual Studio 2022 Community, MSVC
**14.44.35207**). Resultado: **`Result: Succeeded`**, código de salida `0`,
20/20 acciones completadas, ~40 segundos. Quedaron generados
`UnrealEditor-DomoVR.dll`, `UnrealEditor-SpoutPlugin.dll` y `Spout.dll`
(este último calzado junto al módulo del plugin, en
`Plugins/SpoutPlugin/Binaries/Win64/`, tal como pide el propio plugin).

Únicos avisos del compilador, dos veces el mismo, en `SpoutReceiver.cpp`
líneas 375 y 386:

```
warning C4996: 'RHIUpdateTexture2D': RHIUpdateTexture2D with an implied immediate command list is deprecated - Please update your code to the new API before upgrading to the next release, otherwise your project will no longer compile.
```

Es una función de la RHI marcada como obsoleta en 5.8 pero todavía
funcional; no bloquea la compilación de esta versión del motor. Si en algún
futuro upgrade de motor (5.9+) esto sí rompe la compilación, el punto exacto
a mirar es ese archivo del plugin, no nada de `DomoVR`.

Después de compilar se verificó, **headless, con el editor todavía
cerrado** (no se reabrió la interfaz gráfica hasta terminar todo esto), que
el plugin efectivamente **carga** en tiempo de ejecución — compilar y
cargar no son lo mismo — con
`hasattr(unreal, "SpoutBPFunctionLibrary")`, que dio `True`.

### 8.4 El puente se resolvió en C++, no en Blueprint

La primera versión de este documento dejaba el puente a medio armar a
propósito: un Blueprint en blanco (`BP_SpoutDomoReceiver`) con instrucciones
de qué 3 nodos cablear a mano en su Event Graph. El usuario pidió sacar el
Blueprint de la ecuación — no quería cablear nada — y en el camino
aparecieron dos razones **técnicas**, no solo de comodidad, para resolverlo
en C++:

1. **La firma real de `SpoutReceiver`** (`SpoutBPFunctionLibrary.h:110-116`):

   ```cpp
   static bool SpoutReceiver(FName SpoutName, UMaterialInterface* InputMaterial,
       FName TextureParameterName, UMaterialInstanceDynamic*& OutMat,
       UTexture2D*& OutTexture, UTextureRenderTarget2D* OptionalOutputRenderTarget = nullptr);
   ```

   recibe `OutMat` **por referencia**, y `SpoutReceiver.cpp:436` solo crea
   una Dynamic Material Instance nueva `if (!OutMat && InputMaterial)`.
   Cableado desde Blueprint, ese pin de salida no tiene memoria entre
   llamadas — llega `null` en cada `Tick` salvo que se promueva a variable
   Y ADEMÁS se vuelva a pasar esa misma variable como entrada, un detalle
   fácil de pasar por alto wireando a mano. El resultado real de no hacerlo
   bien: **una Dynamic Material Instance nueva por frame**, filtrándose sin
   que el recolector de basura se entere a tiempo. En C++
   (`ASpoutDomeReceiver`), `OutMat` se respalda en un miembro `UPROPERTY()`
   y se le pasa de vuelta en cada llamada: `SpoutReceiver` ve el puntero no
   nulo después de la primera vez y reutiliza la misma instancia.
2. **`OptionalOutputRenderTarget` sí se usa de verdad.** El comentario en
   `SpoutBPFunctionLibrary.cpp` dice "reserved for future GPU-side copy
   paths", pero `SpoutReceiver.cpp:457-466` lo redimensiona, captura su
   recurso, y se lo pasa tanto a `ReceiveOnRenderThread_GPU` como a
   `ReceiveOnRenderThread_CPU` — el comentario está desactualizado respecto
   de la implementación real. `ASpoutDomeReceiver` no lo termina usando (no
   hace falta un render target aparte para alimentar `MI_Domo`
   directamente), pero queda anotado en el propio código para quien lo
   retome después no se guíe por ese comentario viejo.

`BP_SpoutDomoReceiver` (Blueprint y su instancia en el nivel) **se borró**:
ya no hace falta y dejarlo solo confunde.

### 8.5 `ASpoutDomeReceiver`: la clase en C++

Vive en `03_Unreal/DomoVR/Source/DomoVR/SpoutDomeReceiver.{h,cpp}` — la
única clase de juego que tiene el módulo `DomoVR` (el resto del proyecto
sigue siendo Blueprint). Propiedades editables desde el panel de detalles,
sin tocar código ni recompilar para cambiarlas:

- `Spout Sender Name` (`FName`, por defecto `TDSyphonSpoutOut`) — el nombre
  del sender de TouchDesigner. Si TD cambia de nombre de sender, esto es lo
  único que hay que actualizar.
- `Target Material` — el material base (`MI_Domo`) del que `SpoutReceiver`
  saca la Dynamic Material Instance.
- `Texture Parameter Name` (por defecto `SpoutTexture`).
- `Target Mesh Component` — el `StaticMeshComponent` al que se le aplica el
  material recibido (el de `Domo_Actor`).
- `Target Material Slot` (por defecto `0`).

Comportamiento, verificado por lectura del propio código (no solo
supuesto):

- **`Tick()`** llama `SpoutReceiver` pasando el material/textura guardados
  como miembros (la razón 1 de arriba), y solo llama `SetMaterial` sobre la
  malla la primera vez que `OutMat` cambia de puntero — no en cada frame,
  tal como se pidió.
- **Tolerante a que el sender no exista todavía**: si `SpoutReceiver`
  devuelve `false` (TouchDesigner cerrado o el nivel se abrió primero), no
  hace nada más que un aviso en el log cada 5 segundos como mucho — no 90
  por segundo.
- **Tickea también en el editor, sin darle a Play.** Esto se resolvió
  sobreescribiendo `AActor::ShouldTickIfViewportsOnly()` para que devuelva
  `true`. Verificado en `Actor.cpp:376`
  (`FActorTickFunction::ExecuteTick`): cuando el tipo de tick es
  `LEVELTICK_ViewportsOnly` (el que usa el editor sin Play), un actor solo
  tickea si esa función devuelve `true`; por defecto en `AActor` devuelve
  `false`. Este es el mecanismo real de UE 5.8 para esto — **no**
  `bRunConstructionScriptOnDrag` (eso es para el Construction Script, que
  corre una vez al soltar el actor, no cada frame) ni ponerle
  `bTickInEditor` a un `UActorComponent` (eso tickea el componente, no el
  `Tick()` del propio Actor).

### 8.6 `conectar_spout.py`: qué deja montado, sin intervención manual

Se corre igual que `importar_sala.py` (headless, con el editor cerrado, ver
sección 0), **después** de `importar_sala.py`. Verificado con una corrida
real (`Success - 0 error(s)`):

1. Confirma que `SpoutPlugin` cargó (`unreal.SpoutBPFunctionLibrary`).
2. Borra `BP_SpoutDomoReceiver` — la instancia del nivel si quedaba alguna,
   y el asset del proyecto.
3. Confirma que `Domo_Actor` tenga `MI_Domo` en el slot de material 0 (lo
   pone si no).
4. Coloca (idempotente: borra cualquier instancia previa antes) una
   instancia de `ASpoutDomeReceiver` en `/Game/Maps/DomoVR`, con
   `Target Material = MI_Domo`, `Texture Parameter Name = SpoutTexture` y
   `Target Mesh Component` apuntando al `StaticMeshComponent` de
   `Domo_Actor`.
5. Vuelve a pasar el arreglo del indicador de uso Nanite (sección
   "Nanite: encendido o apagado") sobre los materiales de la sala, por si
   el script se corre suelto después de un reimport manual.
6. Genera la configuración de MCP para Claude Code y guarda nivel y assets
   (ver sección 9).

Con esto: al abrir el editor, sin tocar un solo nodo, `ASpoutDomeReceiver`
empieza a pedir el frame de `TDSyphonSpoutOut` cada Tick (en el editor y en
Play por igual) y lo aplica a la cúpula en cuanto llega. Lumen, al ver la
cúpula emitiendo esa luz, la rebota sobre las butacas — el efecto que se
buscaba.

### 8.7 Espacio de color: qué entra y qué hay que cuidar

Verificado leyendo `SpoutTextureUtils.cpp`: la textura que arma el receptor
(`UTexture2D::CreateTransient`) **no toca la bandera `SRGB`**, así que queda
en el valor por defecto de cualquier `UTexture` nueva en Unreal, que es
`SRGB = true` (confirmado en el constructor de `UTexture`,
`Texture.cpp:155`). Eso es lo correcto para esta señal: TouchDesigner emite
contenido de video/gráficos convencional, codificado en gamma sRGB (de
hecho el propio README del plugin recomienda del lado del *sender*
`RTF RGBA8 sRGB` como el formato de render target más confiable). Con
`SRGB = true`, la GPU decodifica la textura a espacio lineal al muestrearla
antes de que el material la use — que es lo que espera el pin de Emissive
Color, ya en espacio lineal.

En criollo: **no hay que tocar nada de espacio de color a propósito**. Si en
la práctica la cúpula se ve lavada (muy clara, sin contraste) o al revés,
apagada/oscura, el diagnóstico no es "cambiarle el sRGB a la textura" —
es sospechar de la cadena de TouchDesigner: revisar con qué *Capture
Source* o formato interno está saliendo `syphonspoutout1`, no del lado de
Unreal. El propio README del plugin señala un caso conocido en la punta
contraria (el *sender* hacia afuera): si un `SceneCapture2D` usa `Scene
Color (HDR)` en vez de `Final Color (HDR) en espacio lineal de trabajo`,
la imagen puede salir directamente negra del otro lado.

### 8.8 Cómo comprobar que la fuente se ve

1. Confirmar que TouchDesigner sigue con `syphonspoutout1` activo y
   `sendername = 'TDSyphonSpoutOut'` (¡ojo!: si TD se reinicia o se cambia
   el nombre del sender, hay que actualizar el nodo Spout Receiver).
2. Abrir `DomoVR.uproject`, entrar al mapa `/Game/Maps/DomoVR` (ya trae
   colocado `SpoutDomeReceiver`, no hace falta armar nada a mano — ver
   8.4-8.6).
3. Poner el viewport en **Realtime** (el botón o `Ctrl+R`) o entrar en Play:
   `ASpoutDomeReceiver::Tick()` solo corre si el viewport está en tiempo
   real o hay una sesión de Play/PIE corriendo — un viewport en pausa (el
   estado por defecto al abrir el editor) no tickea ningún actor, Spout
   incluido, y eso no es un fallo de `ASpoutDomeReceiver` sino de cómo
   Unreal tickea el mundo del editor en general.
4. La cúpula debería mostrar la imagen de TouchDesigner en vivo, con el
   mapeo azimut/elevación ya resuelto por Blender. Si se ve la grilla de
   `T_Default_Material_Grid_M` en vez del video, revisar en
   `Saved/Logs/DomoVR.log` la categoría `LogTemp` por avisos de
   `ASpoutDomeReceiver` (sender no disponible, o Spout deshabilitado — ver
   8.9) y `LogSpoutPlugin` por el motivo real.
5. Para confirmar visualmente el efecto de iluminación indirecta: con
   Lumen activo (ya configurado en `DefaultEngine.ini`), las butacas
   deberían cambiar de tono junto con lo que se proyecta en la cúpula —
   es la prueba de que la luz de la sala está viniendo de verdad de la
   emisión del domo y no de ninguna otra fuente.

### 8.9 El crash de `ERROR_MOD_NOT_FOUND` (`0xC06D007E`) y su arreglo

**Esto es un fallo real del plugin original** (`kessoning/Spout-UE5`, rama
`5.8_fix`), no de la integración de este proyecto — vale la pena
reportárselo al autor.

**Síntoma**: el editor se cerraba solo, de forma repetible, con volcados en
`Saved/Crashes/`. Pila del fallo (`Saved/Logs/DomoVR.log`):

```
Unhandled Exception: 0xc06d007e
[Callstack] UnrealEditor-SpoutPlugin.dll!__delayLoadHelper2() [delayhlp.cpp:346]
[Callstack] UnrealEditor-SpoutPlugin.dll!_tailMerge_spout_dll()
[Callstack] UnrealEditor-SpoutPlugin.dll!FSpoutD3DContext::Initialize() [SpoutD3DContext.cpp:90]
[Callstack] UnrealEditor-SpoutPlugin.dll!FSpoutReceiver::Receive() [SpoutReceiver.cpp:405]
[Callstack] UnrealEditor-DomoVR.dll!ASpoutDomeReceiver::Tick() [SpoutDomeReceiver.cpp:81]
```

**Causa raíz**: `0xC06D007E` es `ERROR_MOD_NOT_FOUND` envuelto por el
ayudante de carga diferida del CRT. `SpoutPlugin.Build.cs` declara
`PublicDelayLoadDLLs.Add("Spout.dll")` y lo copia a
`Plugins/SpoutPlugin/Binaries/Win64/Spout.dll` con `RuntimeDependencies` —
el archivo sí está ahí, 284.160 bytes. Pero `FSpoutModule::StartupModule()`
(`SpoutModule.cpp`, versión original) solo **comprobaba que el archivo
existiera** y lo dejaba escrito en el log — nunca lo cargaba de verdad. Con
carga diferida, la primera llamada real a una función de `Spout.dll`
(`SpoutDirectX`/`spoutSenderNames`, dentro de `FSpoutD3DContext::Initialize()`,
línea 90: `SpoutDirectX = MakeUnique<spoutDirectX>();`) dispara el ayudante
de carga diferida, que busca el módulo por su nombre pelado ("Spout.dll")
con el orden de búsqueda normal de Windows — que **no incluye** la carpeta
de binarios de este plugin. Falla, y como es una excepción estructurada de
Windows (no una excepción de C++), un `catch(...)` normal no la detiene:
tumba el proceso entero.

**Arreglo, en el propio `SpoutPlugin` vendorizado de este proyecto**
(`Plugins/SpoutPlugin/Source/SpoutPlugin/{Public/SpoutModule.h,Private/SpoutModule.cpp,Private/SpoutD3DContext.cpp}`):

1. `FSpoutModule::StartupModule()` ahora carga `Spout.dll` explícitamente
   con `FPlatformProcess::GetDllHandle()` desde la ruta absoluta (la misma
   que ya calculaba el diagnóstico original), guarda el handle en un
   miembro del módulo, y lo libera con `FreeDllHandle()` en
   `ShutdownModule()`. Con el módulo ya cargado en el proceso bajo ese
   nombre, el ayudante de carga diferida lo resuelve sin buscar en ningún
   lado.
2. **Blindaje** (para que un fallo de Spout no vuelva a tumbar el editor,
   pase lo que pase): `FSpoutModule::IsSpoutRuntimeAvailable()` (estático)
   queda en `false` si `GetDllHandle` devuelve null, con un error **una
   sola vez** en el log. `FSpoutD3DContext::Initialize()` comprueba ese
   estado de primero y corta ahí (con su propio aviso, también una sola
   vez) antes de tocar `SpoutDirectX`/`spoutSenderNames`. Y
   `ASpoutDomeReceiver::Tick()` comprueba lo mismo antes de llamar a
   `SpoutReceiver`: si Spout no está disponible, **se apaga solo**
   (`SetActorTickEnabled(false)`) y lo dice una vez — cúpula sin señal en
   vez de arriesgar el editor.

No se agregó manejo de excepciones estructuradas (SEH, `__try/__except`)
además de esto: con la carga explícita puesta primero, y las dos capas de
blindaje cortando el camino antes de tocar la biblioteca cuando no está
disponible, ningún código de este proyecto llega a tocar una función
delay-loaded de `Spout.dll` sin haber comprobado antes que el módulo cargó
— el escenario que el SEH cubriría (un fallo del *loader* a mitad de una
llamada ya en curso) no debería poder ocurrir más. Mezclar `__try/__except`
con objetos C++ con destructor en el mismo alcance tiene restricciones
reales del compilador (C2712) que hubieran complicado el cambio para una
cobertura que ya dan las dos comprobaciones explícitas.

**Verificación real** (no solo lectura de código):

- Se recompiló (`UnrealBuildTool.exe DomoVREditor Win64 Development`,
  `Result: Succeeded`, mismos dos warnings de `RHIUpdateTexture2D` ya
  conocidos, nada nuevo).
- **Reproducción directa del camino exacto del crash, sin depender de si el
  actor tickea o no**: con `Spout.dll` renombrado fuera de las dos rutas
  donde el plugin lo busca (`Binaries/Win64` y
  `ThirdParty/Spout/lib/amd64`), una llamada headless a
  `unreal.SpoutBPFunctionLibrary.spout_receiver(...)` — la misma función
  que corre `ASpoutDomeReceiver::Tick()` — completó sin crashear, y el log
  mostró exactamente el aviso nuevo:
  `LogSpoutPlugin: Error: Spout.dll no esta disponible en este proceso: se
  omite toda inicializacion de D3D/Spout.` Proceso salió con código `0`.
- Con los dos `Spout.dll` repuestos, la misma llamada volvió a pasar del
  aviso de "no disponible" (no aparece) al siguiente chequeo real del
  código (`SpoutPlugin requires DX12 RHI` — esperable en un commandlet
  headless, que no trae un dispositivo D3D12 real; no es un problema, es el
  mismo comportamiento que ya tenía el plugin antes de este cambio).
- Con el editor gráfico real (RTX 3090, RHI D3D12 confirmado en el log) y
  los dos escenarios — `Spout.dll` ausente y `Spout.dll` presente con
  TouchDesigner corriendo — el editor quedó abierto y estable en ambos
  casos, sin generar ningún volcado nuevo en `Saved/Crashes/` (se quedó
  exactamente en los 3 volcados previos a este arreglo, los que motivaron
  el reporte).
- Un matiz encontrado en el camino, sin relación con Spout: un editor recién
  abierto por `Start-Process` (sin la ventana en foco ni el viewport en
  modo *Realtime*) no tickea ningún actor del nivel hasta que se activa
  *Realtime* o arranca una sesión de Play — de ahí que la reproducción por
  Python directo a `spout_receiver` haya sido necesaria para probar el
  arreglo sin depender de eso.

## 9. Control del editor por MCP (Claude Code)

UE 5.8 trae de fábrica un servidor MCP (Model Context Protocol) de Epic
Games — no hay que instalar nada de terceros. Se habilitó para que el
usuario pueda seguir trabajando sobre este proyecto (y otros) controlando
el editor desde Claude Code.

### 9.1 Qué se habilitó, y por qué esa selección

- **`ModelContextProtocol`** (`Engine/Plugins/Experimental/ModelContextProtocol`) —
  el servidor en sí. Trae consigo, como dependencias declaradas en su
  propio `.uplugin`, `EngineAssetDefinitions` y `ToolsetRegistry` (se
  habilitan solos, no hace falta listarlos aparte).
- **`EditorToolset`** (`Engine/Plugins/Experimental/Toolsets/EditorToolset`) —
  el toolset de "Blueprints, Actors, Properties, etc." (así lo describe su
  propio `.uplugin`). Es el que de verdad importa para este proyecto:
  cubre edición de actores, propiedades y assets — materiales incluidos,
  como cualquier otro asset con propiedades — que es exactamente lo que
  hace falta para seguir iterando sobre `DomoVR` desde un agente.

**Lo que NO se habilitó, a propósito**: `AllToolsets` (el agregador que
prende todos los toolsets de golpe) y toolsets puntuales como
`UMGToolSet` o `SequencerAnimMixerToolset`, que el mensaje original
mencionaba como ejemplo. Criterio: este proyecto no tiene ni un solo widget
de UMG ni una sola Level Sequence — son capacidades reales del motor, pero
cero relevancia para `DomoVR` hoy, y cada toolset que se prende es un
módulo más cargando en el arranque del editor (se ve en el log,
`LogToolsetRegistry: Display: Registering Toolset ...`, una línea por cada
herramienta individual dentro de cada toolset — `EditorToolset` solo ya
registra una decena). Si en el futuro hace falta controlar Sequencer o UMG
desde MCP, son plugins que ya están en el disco del motor: alcanza con
agregarlos al `.uproject`, no hay que instalar nada.

Ambos plugins son `IsExperimentalVersion: true` en su descriptor, pero eso
solo afecta a un ícono de advertencia en el Plugin Browser del editor — no
hizo falta ninguna otra bandera para que cargaran. Se comprobó habilitando
los dos, recompilando, y abriendo el editor: cargaron limpio, sin errores
propios (ver 9.3 sobre el único error real que sí apareció, y que no tenía
que ver con esto).

### 9.2 Cómo se arranca, se para, y dónde escucha

- **Puerto real: `8090`, no el `8000` de fábrica.** Se armó
  `Config/DefaultEditorPerProjectUserSettings.ini` (la categoría de config
  que usa `UModelContextProtocolSettings`,
  `config=EditorPerProjectUserSettings`) con:

  ```
  [/Script/ModelContextProtocolEngine.ModelContextProtocolSettings]
  bAutoStartServer=True
  ServerPortNumber=8090
  ServerUrlPath=/mcp
  ```

  El `8000` de fábrica **no liga en esta máquina**: se comprobó primero en
  el log (`LogHttpListener: Error: HttpListener unable to bind to
  127.0.0.1:8000`, repetido en tres corridas distintas, headless y con
  interfaz gráfica) y después por fuera de Unreal, con un bind manual
  (`System.Net.Sockets.TcpListener` desde PowerShell), que falló igual con
  `WSAEACCES` ("Intento de acceso a un socket no permitido por sus permisos
  de acceso"). La causa: `netsh int ipv4 show excludedportrange
  protocol=tcp` muestra el rango **7929–8028 reservado por Windows** en esta
  máquina (casi seguro por el NAT de Hyper-V que usan WSL2/Docker Desktop),
  y el 8000 cae justo adentro. El 8090 sí liga (comprobado igual, a mano y
  después con el editor real: `LogHttpListener: Created new HttpListener on
  127.0.0.1:8090`). Si esto se mueve a otra máquina donde el 8000 sí esté
  libre, no hay ningún problema en volver a ese valor — o dejarlo en 8090,
  da igual mientras `.mcp.json` tenga el mismo puerto.
- **`bAutoStartServer=True`**: el servidor arranca solo al abrir el editor,
  sin tener que escribir nada en la consola. Si se prefiere arrancarlo a
  mano: `ModelContextProtocol.StartServer` (opcionalmente con un puerto:
  `ModelContextProtocol.StartServer 8090`). Para pararlo:
  `ModelContextProtocol.StopServer`. Ambos son comandos de consola del
  editor (la consola de Unreal, no una terminal de Windows).
- **Sin autenticación**: se revisó `ModelContextProtocolServer.cpp` buscando
  algo de auth/token/bearer y no hay nada — es un servidor HTTP en
  `127.0.0.1` sin más, pensado para uso local de un solo desarrollador.
  Cualquier proceso en esta misma máquina puede hablarle. No es un problema
  para este uso (dev, localhost), pero vale saberlo antes de pensar en
  exponerlo más allá de `127.0.0.1`.
- **Si cambia el puerto** (a mano, o porque en otra máquina el 8090
  tampoco esté libre): cambiar `ServerPortNumber` en
  `DefaultEditorPerProjectUserSettings.ini` (o en Project Settings > Model
  Context Protocol dentro del editor, que es lo mismo pero por UI) y volver
  a generar la configuración del cliente (siguiente punto) para que
  `.mcp.json` quede con la URL correcta.

### 9.3 La configuración de Claude Code: dónde quedó, y cómo se generó

Comando: `ModelContextProtocol.GenerateClientConfig ClaudeCode`. Leyendo
`ModelContextProtocolClientConfig.cpp`: para `ClaudeCode` escribe
`.mcp.json` (clave raíz `mcpServers`, con `"type": "http"` y el campo
`url`) en `FPaths::ProjectDir()` cuando el motor es un install (no de
fuente) — que es el caso de este engine en `Program Files` — y no en
`FPaths::RootDir()`. Es decir, en la raíz del proyecto, no del motor.

**Ruta real, confirmada en disco**:

```
C:\Users\Danvegamo\Documents\Domo_VR_Unreal\03_Unreal\DomoVR\.mcp.json
```

Contenido real, generado por el propio comando (no escrito a mano):

```json
{
	"mcpServers":
	{
		"unreal-mcp":
		{
			"type": "http",
			"url": "http://127.0.0.1:8090/mcp"
		}
	}
}
```

**Sí se pudo disparar sin interfaz.** `conectar_spout.py` (sección 8.6),
corrido headless, llama:

```python
unreal_editor_subsystem = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
world = unreal_editor_subsystem.get_editor_world()
unreal.SystemLibrary.execute_console_command(world, "ModelContextProtocol.GenerateClientConfig ClaudeCode")
```

y se confirmó en el log de esa misma corrida:
`LogModelContextProtocol: Display: MCP client configuration written to:
.../DomoVR/.mcp.json`, y leyendo el archivo después con Python, con el
contenido de arriba. No hizo falta el editor abierto para generarlo — sí
hace falta tenerlo abierto (con el servidor corriendo, puerto 8090) para
que Claude Code se pueda conectar de verdad a esa URL.

**No se tocó** `~/.claude.json` ni `~/.claude/mcp.json`: eso queda del lado
de quien registre el servidor en Claude Code, no de este proyecto.

### 9.4 El único error real que sí apareció (y no tiene que ver con MCP)

Al revisar el log completo de estas corridas aparecen bloques
`LogAutomationTest: Error: Condition failed` junto a líneas como
`LogTemp: Error test: UE::UnifiedErrorTest::Empty: [Error vacío]`. Esto
viene de los módulos de test que trae el propio plugin
(`ModelContextProtocolTests`, `ModelContextProtocolEngineTests`,
`ModelContextProtocolEditorTests`, declarados en su `.uplugin` con
`LoadingPhase: Default`): son pruebas automáticas del propio framework de
logging de errores, que **a propósito** generan un error falso para
comprobar que el sistema de reporte de errores lo captura bien — el nombre
`UnifiedErrorTest` lo deja bastante claro. No es un fallo de `DomoVR` ni
del MCP en sí; se deja anotado aquí para que si alguien ve esas líneas en
el log no las confunda con un problema real.

## 10. El bug de escala de importación (factor 100 faltante)

### 10.1 Qué pasaba y cómo se encontró

La sala se veía negra y en un principio se sospechó de Spout. La causa real
era otra, encontrada midiendo con `get_actor_bounds` por MCP: `Domo_Actor`
medía `min (-11.5, -11.5, 3)` a `max (11.5, 11.5, 14.5)` — esas cifras son
centímetros (uu de Unreal), o sea que la sala entera medía **23 cm de
diámetro, no 23 m**. Con la cámara dentro de una maqueta de 23 cm, la
superficie más cercana queda a unos 7 uu, dentro del plano de recorte
cercano por defecto — de ahí el negro total, no de Spout.

### 10.2 Causa raíz y por qué se corrigió del lado de Unreal

Verificado leyendo el motor, no supuesto: el constructor de
`UFbxAssetImportData` (`FbxAssetImportData.cpp`) trae
**`bConvertSceneUnit(false)`** de fábrica. Esa es la bandera "Convert the
scene from FBX unit to UE unit (centimeter)" — sin ella en `True`, el
importador toma los números del FBX tal cual, sin aplicar el factor 100 que
hace falta para pasar de metros (la unidad de Blender) a centímetros (la
unidad de Unreal). `importar_sala.py` nunca la tocaba, así que se quedaba
en `False`.

Se decidió arreglarlo en `importar_sala.py`
(`sm_data.set_editor_property("convert_scene_unit", True)`), no en el
export de Blender, por lo mismo que se advertía en el encargo: el mismo
`.fbx` también genera el `.glb` de `02_Export/` y podría tener otros
consumidores futuros — cambiar la escala en el origen los afectaría a
todos. `bConvertSceneUnit` además es más robusto que un
`ImportUniformScale = 100` a mano: usa la unidad que el propio FBX declara
en vez de asumir un factor fijo, así que sigue funcionando igual si el otro
agente cambia la escala de export de Blender el día de mañana.

### 10.3 Verificación real, con números

Se reimportó (`importar_sala.py` completo, headless) y se volvió a medir
con `get_actor_bounds` (por Python directo, no por MCP, en esa corrida
headless) contra `Domo_Actor`, `Muro_Actor`, `Piso_Actor` y `Tarima_Actor`:

```
Domo_Actor:  min (-1150.0, -1150.0,  300.0)  max (1150.0, 1150.0, 1450.0)
Muro_Actor:  min (-1150.0, -1150.0,    0.0)  max (1150.0, 1150.0,  300.0)
Piso_Actor:  min (-1150.0, -1150.0,    0.0)  max (1150.0, 1150.0,    0.0)
Tarima_Actor:min ( -150.0,  -150.0,    0.0)  max ( 150.0,  150.0,  100.0)
```

Exactamente lo esperado: domo de 11.5 m de radio arrancando a 3 m de altura
(300 a 1450 uu), muro de 0 a 3 m, piso plano, tarima de 3 m de diámetro x 1 m
de alto. **No hizo falta tocar `PlayerStart` ni el Post Process Volume**:
sus posiciones (`PLAYER_START_RADIO_CM`, `PLAYER_EYE_HEIGHT_CM`,
`TARIMA_RADIO_CM`) ya estaban escritas en centímetros de mundo real
correctos desde el principio — el bug estaba solo en cómo se importaba la
malla, no en dónde se colocaban las cosas después. El PPV sigue `Unbound`
(infinito), así que tampoco depende de la escala. Se volvió a correr
`conectar_spout.py` después para recolocar `ASpoutDomeReceiver` (el
reimport reconstruye el nivel desde cero, así que lo había borrado).

### 10.4 El intento de verificación visual por MCP — quedó inconcluso, y por qué

Se probó `CaptureViewport` (`EditorToolset.EditorAppToolset`) tal como pedía
el encargo. Notas prácticas sobre la herramienta, para quien la use después:

- **`captureTransform` y `annotations` son técnicamente opcionales según su
  JSON schema, pero la implementación los exige igual** — sin ellos, la
  llamada falla con "needs a default value". Con `annotations: []` (no un
  objeto, un arreglo vacío) alcanza para desactivar la superposición de
  cuadrícula/etiquetas.
- Varias herramientas piden parámetros que su schema no marca como
  `required` (`get_property_input` pedía `material` aunque solo
  `material_property` aparecía como obligatorio; `find_actors` pedía `tag`
  y `collision_channels`). Conviene pasar el objeto completo con valores
  vacíos (`""`, `[]`) en vez de confiar en el `required` del schema.

Con eso funcionando, se pudo confirmar independientemente del renderizado:

- El grafo de `M_Domo` está bien armado de verdad, no solo a ojo:
  `get_property_input` confirmó `MP_EmissiveColor` conectado a un
  `MaterialExpressionMultiply`, y `get_expression_inputs` confirmó sus dos
  entradas — `A` = `TextureSampleParameter2D.RGB`, `B` =
  `ScalarParameter` (`EmissiveIntensity`) — exactamente como lo armó
  `importar_sala.py`.
- La malla del domo (`Domo_Actor` = `StaticMeshActor_15`) tiene aplicado
  `/Engine/Transient.MID_MI_Domo_0`, una Dynamic Material Instance real, con
  su parámetro `SpoutTexture` apuntando a `/Engine/Transient.Texture2D_6` —
  **una textura viva, no la de marcador de posición**. Capturada con
  `CaptureAssetImage`, esa textura mostró una imagen real de domemaster
  (colores verdes, rojos, amarillos, formato fisheye circular): **la señal
  de Spout llega de verdad, con contenido, hasta el material**.

Lo que **no** se pudo confirmar fue que esa imagen se vea así de verdad
sobre la cúpula en un render final. Capturas repetidas con `CaptureViewport`
apuntando a la cúpula desde varios ángulos, con `EmissiveIntensity` en 20,
300 y hasta 50000, dieron resultados o bien negros o bien de un gris
plano uniforme — sin ninguna variación de color pese a que la textura de
origen sí la tiene, y sin ninguna diferencia perceptible entre 20 y 50000
(una diferencia de 2500 veces que debería notarse en cualquier render real,
así la exposición estuviera mal calibrada). Esa falta total de variación,
más que el negro en sí, es la señal de que **la captura no estaba mostrando
el material real de la cúpula**, sino algún tipo de vista de reemplazo: se
sospecha del modo de vista de depuración del viewport del editor
(la propia interfaz mostraba literalmente "Sin iluminación" en el selector
de modo de vista durante varias de estas pruebas), que en Unreal muestra un
gris plano de reemplazo para materiales con shading model Unlit en vez de
su emisión real — pero no se encontró, entre las herramientas de MCP
disponibles (`EditorToolset.EditorAppToolset` y compañía), una forma de
cambiar ese modo de vista a "Iluminado" para descartarlo con certeza. Se
probó también con sesiones de Play In Editor (en viewport y en ventana
flotante tipo Standalone, que no deberían heredar el modo de vista de
depuración del editor) apuntando la cámara hacia la cúpula con
`startTransform`, sin mejor resultado — aunque tampoco hay certeza de que el
pawn por defecto respetara el pitch de esa transformación de aparición.

**En criollo**: quedó demostrado con datos duros que la tubería completa
funciona hasta el material (textura de Spout viva y correcta, grafo del
material bien armado, parámetro de intensidad ajustable) pero **no quedó
confirmado a ojo, en esta sesión, que la cúpula se vea encendida en un
render final**. La forma más directa de comprobarlo — y la que se
recomienda antes de dar esto por cerrado — es que el usuario mismo entre a
`DomoVR.uproject`, confirme que el viewport esté en modo **Lit**
("Iluminado", no "Sin iluminación", ícono de la esfera junto al selector de
modo de vista) y en **Realtime**, y mire la cúpula con TouchDesigner
corriendo. Si ahí tampoco se ve, `EmissiveIntensity` (parámetro de
`MI_Domo`, hoy en **100**, subible sin recompilar) es el primer lugar para
seguir probando.
