# La sala sin TouchDesigner: Unreal reproduce los videos

Hasta aquí la cúpula de la sala VR mostraba lo que TouchDesigner le mandaba
por Spout ([03_Puente_Spout.md](03_Puente_Spout.md)). Esta página describe la
otra forma de usarla, pensada para producción virtual y para llevar la sala a
otra máquina: **Unreal abre los videos él mismo**, los pone en la cúpula con
la misma matemática que usa TouchDesigner y se empaqueta como un programa
suelto (`DomoVR.exe`) que no necesita ni el editor ni TouchDesigner. Las dos
formas conviven en los mismos niveles: un parámetro, `Fuente`, elige entre
`Spout` y `Media`.

## 1. Qué es

| Pieza | Dónde | Qué hace |
|---|---|---|
| `MP_Domo` | `/Game/Media` | el reproductor de Media Framework; abre los archivos con Windows Media Foundation (`WmfMedia`) |
| `MT_Domo` | `/Game/Media` | la textura donde cae cada cuadro: sRGB, sin mips, salida *new style* (se lee como una textura 2D común) |
| `M_DomoMedia` / `MI_DomoMedia` | `/Game/Media` | el material de la cúpula para video. `M_Domo`, el de Spout, no se toca |
| `ADomeMediaController` | `Source/DomoVR/DomeMediaController.{h,cpp}` | lee la playlist, abre cada cue, pasa sus parámetros al material, maneja el audio, el fundido a negro, el teclado y los comandos `domo.*` |
| `DomeMediaController` | un actor en `DomoVR`, `DomoVR_45` y `DomoVR_90` | la instancia de esa clase en cada nivel, ya cableada a la cúpula y al `SpoutDomeReceiver` |
| `RC_Domo` | `/Game/Media` | preset de Remote Control con las funciones del controlador (nivel `DomoVR`) |
| `Movies/playlist.json` | `03_Unreal/DomoVR/Content/Movies/` | la lista de cues; los videos van en la misma carpeta |

El material hace por píxel, al revés, la misma cadena que en TouchDesigner
llevaba el video al lienzo de la sala ([04_Senal_TouchDesigner.md](04_Senal_TouchDesigner.md),
sección 6). Cada píxel de la cúpula:

1. Calcula su punto en el domemaster de la sala con el FOV de la sala
   (`domo_mapping.frag`, modo 1, lo que antes hacía `para_unreal`).
2. Deshace el mapping (`CentroX`, `CentroY`, `Escala`, `Rotar`) y pasa por el
   fisheye del contenido con el FOV del contenido (`FovContenido`; 0 es el de
   la sala, como `Fovauto`).
3. Aplica `Horizonte` y `Curva` con el cénit fijo y el giro esférico inverso
   `Yaw`, `Pitch`, `Roll` (`orientar.frag`).
4. Lee el video según su formato: 360 equirectangular, domemaster fisheye de
   180, VR180 (mono o lado a lado, el ojo izquierdo) o un video plano sobre
   una pantalla en la cúpula (`pantalla169.frag`, una pantalla).

Todo va en un nodo Custom de HLSL que escribe `03_Unreal/crear_media_domo.py`
(constante `HLSL`); el material no se arma a mano. La lectura usa
`Tex.SampleLevel(TexSampler, uv, 0)`: sin derivadas, el salto de `u` de 1 a 0
en la costura del 360 no dispara un mip chico ni deja una línea gris, el mismo
cuidado que tienen los shaders de TouchDesigner con `textureLod`.

La UV de la cúpula es la de siempre (canal 0, `U = azimut/360 + 0,5`,
`V = 0,5 + elevación/180`, frente en +X; ver [05_Modelos_de_sala.md](05_Modelos_de_sala.md),
sección 5), así que el mismo material sirve para las tres salas.

**El espejo de la U.** Con el contador de cuadros del patrón a la vista, la
primera prueba mostró el número al revés: la U de la cúpula crece hacia la
izquierda de quien mira desde adentro (azimut antihorario visto desde arriba),
y en TouchDesigner `u` crece hacia la derecha (`x = sin(az)`). El frente
(`u = 0,5`) y la costura (`u = 0 = 1`) caen bien, por eso el patrón simétrico
no lo delataba. `M_DomoMedia` lo corrige con el parámetro `EspejoU` (1 por
defecto). El camino de Spout tenía el mismo espejo: se comprobó el 18 de
septiembre de 2026 con un lienzo con texto mandado desde TouchDesigner, y
`M_Domo` lleva desde entonces su propio `EspejoU` ([02_Sala_Unreal.md](02_Sala_Unreal.md),
sección 13).

## 2. Cómo se arma

Con el editor cerrado, después de `importar_sala.ps1` y de conectar Spout para
cada modelo (reimportar un nivel lo vacía y se lleva el controlador):

```
03_Unreal\crear_media_domo.ps1            # assets, material y controlador en los tres niveles
03_Unreal\crear_media_domo.ps1 -SoloRC    # el preset de Remote Control
```

La primera línea genera los videos de prueba si faltan (sección 3), corre
`crear_media_domo.py` sin interfaz y copia la playlist de ejemplo
(`03_Unreal/Movies_ejemplo/playlist.json`) a `Content/Movies/` si ahí no hay
una; nunca pisa la que exista. Es idempotente: reutiliza `MP_Domo` y `MT_Domo`,
rehace el grafo de `M_DomoMedia` y cambia el controlador de cada nivel por uno
nuevo. Log en `03_Unreal/Saved_Logs/crear_media_domo.log`.

El preset va aparte porque exponer una función en Remote Control necesita el
buffer de transacciones del editor, que no existe en `-run=pythonscript`: ahí
el proceso se cae con `Cast of nullptr to TransBuffer failed`. `-SoloRC` abre
el editor completo sin render en pantalla (`-RenderOffscreen`), arma el preset
y lo cierra. El 18 de septiembre de 2026 dejó `RC_Domo` guardado con 16 campos
y luego el editor terminó con un acceso inválido *después* de `LogExit:
Exiting` (código `-1073741819`); el asset ya estaba escrito, así que no tiene
consecuencias, pero el código de salida no es 0.

El módulo C++ tiene que estar compilado (`UnrealBuildTool DomoVREditor Win64
Development`, [02_Sala_Unreal.md](02_Sala_Unreal.md), sección 8). La clase
depende de `MediaAssets`, `AudioMixer` y `Json`, y el proyecto habilita los
plugins `RemoteControl` y `RemoteControlWebInterface`.

## 3. Cómo preparar los videos

Media Framework en Windows abre los `.mp4` con Media Foundation, que decodifica
por hardware. Lo que funciona sin sorpresas:

| Dato | Valor |
|---|---|
| Contenedor | `.mp4` con `faststart` |
| Video | H.264 High o Main, `yuv420p` (8 bits), nivel 5.1 |
| Tamaño | 4096 × 2048 para 360 (2:1); 2048 × 2048 para domemaster o VR180; el ancho no pasa de 4096 |
| Cuadros | hasta 30 por segundo a 4096 × 2048 (el techo del nivel 5.1) |
| Audio | AAC estéreo, 48 kHz |

Un 360 cualquiera, a esa receta:

```
ffmpeg -i entrada.mov -vf "scale=4096:2048:flags=lanczos,format=yuv420p" ^
  -c:v libx264 -profile:v high -level:v 5.1 -preset slow -crf 18 -g 30 ^
  -c:a aac -b:a 192k -ac 2 -ar 48000 -movflags +faststart salida.mp4
```

Para un domemaster o un VR180 cambia solo el `scale` (`2048:2048`). Si el
original viene a 60 cuadros, `-r 30`; H.264 a 4096 × 2048 y 60 cuadros pide
nivel 5.2, que queda fuera de lo verificado. Con NVENC (`-c:v h264_nvenc
-preset p5 -cq 19 -profile:v high`) el encode es mucho más rápido; no se probó en la cúpula.

Lo que no conviene: HAP y ProRes (Media Foundation no los abre), cualquier
cosa de 10 bits (la textura es de 8 bits por canal, como el receptor de Spout),
anchos de 8192 y HEVC. HEVC puede funcionar con las *HEVC Video Extensions* de
Microsoft instaladas, pero no se probó.

**Videos de prueba.** `python 03_Unreal/generar_video_patron.py` escribe el
patrón de `shaders/patron.frag` como H.264 de 4096 × 2048, con un contador de
cuadros al frente (para ver que el video corre y que no está espejado) y un
pitido por segundo (para ver que el audio sigue al cue). Con `--formato
domemaster` sale el mismo patrón como domemaster de 2048 (la cuenta de
`domo_mapping.frag` en su modo 0) y con `--formato vr180` la mitad del frente.
En la cúpula los tres tienen que verse iguales (el VR180, solo la mitad del
frente): así se prueban los formatos. No van al repositorio; se regeneran.

**Derechos.** Los videos de `Content/Movies/` están fuera de git
(`.gitignore`). *3gracias* tiene todos los derechos reservados: se prueba desde
su carpeta original o desde una copia fuera del repositorio, nunca desde
`Content/Movies/` si se va a publicar un build.

## 4. La playlist

`Content/Movies/playlist.json`. Las rutas de `archivo` son relativas a la
carpeta de la playlist (o absolutas, solo para probar en una máquina). Un
ejemplo con todos los campos:

```json
{
  "cues": [
    { "nombre": "Apertura", "archivo": "apertura_360.mp4", "formato": "360",
      "yaw": 0, "pitch": -8, "roll": 0, "horizonte": 35, "curva": 1,
      "volumen": 1, "loop": false },
    { "nombre": "Cielo", "archivo": "cielo_domemaster.mp4", "formato": "domemaster",
      "fovContenido": 230, "mapping": { "centroX": 0, "centroY": 0.05, "escala": 1, "rotar": 0 } },
    { "nombre": "Créditos", "archivo": "creditos_16x9.mp4", "formato": "169",
      "pantalla": { "azimut": 0, "elevacion": 30, "ancho": 100, "alto": 56, "curva": false, "borde": 0.02 } }
  ]
}
```

| Campo | Por defecto | Qué es |
|---|---|---|
| `nombre` | el nombre del archivo | lo que se muestra al cambiar de cue |
| `archivo` | (obligatorio) | el video |
| `formato` | `"360"` | `"360"`, `"domemaster"`, `"vr180"`, `"vr180sbs"` o `"169"`; también el número 0 a 4 |
| `yaw`, `pitch`, `roll` | 0 | giro esférico, grados. `pitch` positivo lleva el frente hacia el cénit; 90 saca la costura de un 360 |
| `horizonte`, `curva` | 0, 1 | la altura del horizonte con el cénit fijo (máximo 80) y el reparto de la compresión; igual que `Rhorizonte` y `Rcurva` |
| `fovContenido` | 0 | FOV del contenido; 0 es el de la sala. 230 mete 25 grados de piso en una cúpula de 180 |
| `mapping` | 0, 0, 1, 0 | `centroX`, `centroY`, `escala`, `rotar`: la página Mapping de TouchDesigner |
| `pantalla` | 0, 30, 100, 56, false, 0,02 | solo para `"169"`: azimut y elevación del centro, ancho y alto en grados, curva (ángulos iguales) o plana, borde suave |
| `volumen` | 1 | volumen del audio del video |
| `loop` | true | con `false`, al terminar pasa solo al siguiente cue |

Un `"carpeta"` en la raíz del JSON cambia la carpeta base de los archivos. Los
valores de TouchDesigner se copian tal cual: por ejemplo *3gracias*, que en
TouchDesigner iba con `Rhorizonte` 35 y `Rpitch` −8, aquí es `"horizonte": 35,
"pitch": -8`.

Qué playlist se carga, en este orden: `-DomoPlaylist=<ruta>` en la línea de
comandos; en el editor, `RutaPlaylistEditor` si está puesta
(`[/Script/DomoVR.DomeMediaController]` en `Config/DefaultGame.ini` o en el
`Game.ini` del usuario, ruta absoluta); y si no, `PlaylistPath` del actor,
relativa a `Content/` (`Movies/playlist.json`), que en el build es
`<build>/DomoVR/Content/Movies/playlist.json`.

## 5. Operación

**Teclado**, en Play, en `-game` y en el build:

| Tecla | Acción |
|---|---|
| → o Av Pág | siguiente cue |
| ← o Re Pág | cue anterior |
| 1 a 9 | ir a ese cue |
| B o punto | fundido a negro (imagen y audio) y de vuelta |
| Espacio | pausa y play |
| Inicio | volver al principio del cue |
| F3 | alternar la fuente entre Media y Spout (antes era S) |
| F1 | ayuda y estado en pantalla |
| F2 o M | mostrar u ocultar el menú en pantalla (ver abajo) |
| W A S D | moverse; **Q / E** bajan y suben en vuelo, **Mayús** corre |
| F | alterna Caminar, Volar y Fantasma |

Todas estas teclas se pueden **cambiar desde el menú** (sección *Teclas*) y se
guardan en `controles.json`, junto a `playlist.json`. Los números 1 a 9 van
siempre al video 1 a 9.

Av Pág, Re Pág, B y punto son las teclas que mandan los presentadores
inalámbricos, así que uno de esos sirve de control de cabina. El controlador
habilita su entrada sobre el `PlayerController`, que la procesa antes que la
del `DefaultPawn`, así que las flechas deberían cambiar de cue sin mover al
jugador. **El teclado no se probó con teclas reales**: las pruebas del 18 de
septiembre de 2026 fueron por consola (sección 7), porque no se podían mandar
pulsaciones a la máquina mientras se usaba para otra cosa.

**Consola** (tecla `~`; en el build Development está disponible):
`domo.Cue N`, `domo.Siguiente`, `domo.Anterior`, `domo.Negro [0|1]`,
`domo.Pausa`, `domo.Param Nombre Valor` (cualquier campo del cue, más
`Brillo`, `FovSala` y `EspejoU`), `domo.Fuente Spout|Media`, `domo.Recargar`
(vuelve a leer la playlist), `domo.Estado` (escribe en el log el reproductor,
el tiempo, el tamaño de la textura, las pistas de audio y el nivel del audio) y
`domo.Camara X Y Z Pitch Yaw [FOV]` (mueve al jugador; para capturas) y
`domo.Preset VR|Render` (calidad de imagen; [02_Sala_Unreal.md](02_Sala_Unreal.md),
sección 14).

**Remote Control.** `RC_Domo` expone `Play`, `Pause`, `TogglePause`, `Next`,
`Prev`, `GoToCue`, `Reiniciar`, `SetParam`, `Blackout`, `ToggleBlackout`,
`SetFuente`, `ToggleFuente`, `RecargarPlaylist` y las propiedades `Fuente`,
`Brillo` y `bNegro` del controlador del nivel `DomoVR`. Con el editor abierto,
la API HTTP escucha en el puerto 30010 y el WebSocket en el 30020, por ejemplo
`PUT http://localhost:30010/remote/preset/RC_Domo/function/Next`. La interfaz
web (puerto 30000) se construye sola con Node la primera vez que se abre el
editor con conexión a internet y tarda unos minutos; en la corrida de `-SoloRC`
no llegó a terminar porque el editor se cierra enseguida (`Failed to Launch the
Remote Control Web Interface - WebApp exited` en el log, esperable). En un
build empaquetado Remote Control se enciende con `-RCWebControlEnable`; no se
probó.

**En el editor**, sin Play, el controlador también corre (como el receptor de
Spout): el viewport en *Realtime* muestra el video en la cúpula, sin sonido. El
audio solo suena en Play, `-game` o el build, para que el editor no suene
mientras se trabaja. `bReproducirEnEditor` lo apaga. Durante una sesión de
Play manda la copia de juego; al salir, la del editor vuelve a abrir el cue.

**Spout o Media.** Desde el 18 de septiembre de 2026 los tres niveles se
guardan en `Spout` (`FUENTE_INICIAL` en `crear_media_domo.py`): el editor, y
Play dentro del editor, arrancan con TouchDesigner en vivo, como antes de la
versión standalone. Fuera del editor (el build empaquetado y `-game`) el
controlador arranca en `Media`: lo decide `FuenteFueraDelEditor`, una
propiedad de configuración del controlador (`Media` por defecto; se cambia con
`[/Script/DomoVR.DomeMediaController]` `FuenteFueraDelEditor=Spout` en
`Config/DefaultGame.ini` o en el `Game.ini` del build). `-DomoFuente=Spout` o
`-DomoFuente=Media` en la línea de comandos pisa a las dos. El log lo dice al
arrancar: `Fuente al arrancar: Media`. Para cambiar en vivo: `Fuente` en el
panel de detalles del actor `DomeMediaController`, `domo.Fuente Spout|Media`
en la consola, o la tecla S en Play. Con `Media`, el controlador apaga el tick del
`SpoutDomeReceiver` (así no le devuelve su material a la cúpula ni llena el log
de "no disponible todavia"); con `Spout`, cierra el video y el receptor vuelve
a poner su material (`ASpoutDomeReceiver::ReaplicarMaterial`, que se agregó
para esto).

**Audio.** Sale del mismo reproductor que la imagen, por un
`MediaSoundComponent` no espacial (suena igual en toda la sala), así que cambia
con el cue sin nada más. El fundido a negro también baja el audio.

### Menú en pantalla (sin teclado ni consola)

Desde el 29 de septiembre de 2026 el ejecutable trae un menú en pantalla para
operar la cúpula con el mouse, sin TouchDesigner. Sale del código
(`DomeMenu.cpp`, Slate), no de un asset, así que viaja dentro del build sin
pasos manuales. En el ejecutable arranca visible; **F2 o M** lo muestran y lo
ocultan (también el botón *Ocultar*). En el editor arranca oculto
(`-DomoMenu=0|1` pisa las dos cosas). Con el menú abierto aparece el cursor.

| Sección | Qué hace |
|---|---|
| Fuente y video | Desplegable de fuente (Spout o Media); nombre del sender de Spout (Enter para aplicar); desplegable con los videos de la lista; anterior, play/pausa, reiniciar, siguiente; barra de tiempo; **Abrir video…** (diálogo de Windows, uno o varios archivos de cualquier carpeta), **Traer la carpeta** (agrega los videos de la carpeta de la lista que no estén), **Recargar lista**, **Guardar lista** (escribe `playlist.json`, con una copia `.bak` la primera vez); Repetir, Pasar al siguiente, Negro |
| Imagen en la cúpula | Formato del video (360, domemaster, VR180, VR180 lado a lado, plano 16:9) y deslizadores de Brillo, Volumen, Giro, Inclinar, Rodar, Horizonte, Curva, FOV del contenido y el mapping del domemaster (Centro X e Y, Escala, Rotar). Valen para el cue actual y se guardan con *Guardar lista* |
| Pantalla 16:9 | Azimut, elevación, ancho, alto, borde y curvatura de la pantalla del formato plano |
| Pantallas 16:9 (montajes) | Los montajes de pantallas de TouchDesigner: una pantalla, grande, baja, cenital, **2 pantallas que ocupan el domo**, **4 pantallas**, 6, espejadas, mosaico, **corona**, corona panorámica, tres, **anillo**, anillo doble, **túnel**, túnel con pantallas, cilindro (pared que sube), cilindro doble y fragmentos. Hasta 3 filas; cada una se elige (Pantalla 1, 2, 3), se agrega o se quita y se ajusta en submenús: *Forma y tamaño* (forma plana, curva, banda, túnel o cilindro; azimut, elevación, rodar, ancho, alto, opacidad, borde), *Copias en anillo* (copias, arco, solape, espejar de a una, corrimiento del recorte, repeticiones), *Recorte, espejo y bordes* y *Movimiento del montaje* (girar todo, giro continuo, recorrido continuo). Se guardan con cada video en `playlist.json` |
| Sala, luces y vista | Luces (automáticas, encendidas, apagadas), **velo de la cúpula con luces**, punto de vista (espectador, cabina mirando la cúpula o las pantallas, tarima, cada pasillo hacia su salida), calidad (VR o Render), sala (180, 90, 45) y salir |
| Movimiento | Modo (caminar, volar, fantasma), velocidades, correr, altura de ojos, sensibilidad del mouse, gravedad, volver al inicio |
| Teclas | Cada acción con dos teclas: clic, pulsar la tecla nueva (Esc cancela, Supr borra) |

Un video que se agrega desde el menú toma el formato del nombre del archivo
(`domemaster`, `360`, `vr180`, `16x9`…) o, si el nombre no dice nada, de sus
proporciones al abrirlo (cuadrado = domemaster, 2:1 = 360, lo demás = plano).
Se puede cambiar en la sección de imagen. Los puntos de vista son actores
`TargetPoint` con la etiqueta `domo_vista` que crea `realismo_sala.py` a partir
del manifiesto, así que siguen a la planta si Blender la cambia.

**Verificación.** El menú se dibujó en un PNG dentro del build empaquetado con
`domo.MenuFoto <ruta.png> [ancho alto]` (con `-DomoMenuTodo` salen abiertas
todas las secciones). **Los clics del mouse no se probaron con un mouse real**:
los desplegables, el diálogo de archivos y los deslizadores se revisaron por
construcción y por sus efectos (los mismos métodos que los comandos `domo.*`,
que sí se probaron), no pulsándolos.

### El jugador: caminar, volar o atravesar

El jugador es un `Character` (`ADomePawn`, con `ADomeGameMode` como modo de
juego del proyecto) y no el `DefaultPawn` del motor, que volaba en la dirección
de la mirada y sin colisiones: al mirar abajo y avanzar se caía uno del piso.
Aparece de pie en el pasillo 1, mirando a la tarima. Tres modos (tecla F o el
menú): **Caminar** (gravedad y colisiones con el piso, la tarima, el muro y la
cabina; las butacas no chocan, para no quedar atorado), **Volar** (sin gravedad,
con colisiones) y **Fantasma** (atraviesa todo). Los puntos de vista del menú
ponen los *ojos* en el lugar de la butaca (o la cabina) y pasan a Volar, para
que la gravedad no lo baje de ahí; F vuelve a Caminar. Con el menú abierto el
mouse solo gira la vista con el clic derecho apretado (se puede cambiar).
Consola: `domo.Modo caminar|volar|fantasma`, `domo.Inicio`, `domo.Posicion`.

La colisión sale de mallas con `Use Complex Collision As Simple`
(`realismo_sala.ajustar_colision`, que corre en cada importación): el importador
de FBX les generaba un casco convexo sólido a la cúpula y al muro, y eso
expulsaba al jugador por el techo.

### El velo de la cúpula al encender las luces

Con las luces de la sala encendidas (sin señal, o a mano) la cúpula recibe un
velo tenue de blanco en el cenit a morado en el borde, que acompaña a las luces
de las paredes. Es una copia de la cúpula un poco más chica con un material
aditivo (`M_DomoResplandor`, actor `Resplandor_Domo` con la etiqueta
`domo_resplandor`) que el controlador sube y baja con el mismo fundido de las
luces. Se regula en el menú (*Velo de la cúpula con luces*), con `domo.Param
Resplandor 0.5` o `IntensidadResplandor` en la config; 0 lo apaga.

### Control por UDP (TouchDesigner, Resolume, QLab, un script)

El ejecutable escucha líneas de texto en `127.0.0.1:7000`. Cada línea es un
comando de consola `domo.*`; cualquier otra cosa se ignora (no se puede mandar
`quit` ni otros comandos del motor). Ejemplos: `domo.Cue 2`, `domo.Luces 0`,
`domo.Negro 1`, `domo.Param Yaw 45`, `domo.Sender TD_Domo_Lab`,
`domo.Abrir C:/videos/domemaster.mp4` (lo agrega a la lista y lo pone),
`domo.Guardar`, `domo.Menu 0`, `domo.Plantilla sala_corona` (o `sala_2`,
`sala_4`, `tunel`, `anillo`, `cilindro`…), `domo.Param S_Yaw 45` (cualquier campo
de la pantalla elegida con el prefijo `S_`), `domo.Modo volar`. Un mensaje puede
traer varias líneas.

- El puerto se cambia con `PuertoUdp` (config del controlador) o
  `-DomoUdp=<puerto>`; `0` lo apaga.
- Por defecto solo escucha en este equipo. Para recibir desde otro
  computador de la red: `bUdpEnRed=True` o `-DomoUdpRed`. **No hay
  autenticación**: úsese en una red de confianza.
- El menú muestra en qué puerto escucha. Se probó mandando un datagrama desde
  PowerShell (`domo.Luces 0`, `domo.Cue 3`, `domo.Abrir …` se ejecutaron y `quit` se
  rechazó).

## 6. Empaquetado

```
03_Unreal\empaquetar.ps1
```

Corre `RunUAT BuildCookRun` (Win64, Development, `-build -cook -stage -pak
-archive`) con los tres niveles y deja el build en `03_Unreal\Build\Windows\`
(fuera de git). `Config/DefaultGame.ini` agrega `+DirectoriesToAlwaysStageAsNonUFS=(Path="Movies")`:
los videos y la playlist no entran al `.pak`, porque Media Foundation necesita
un archivo real, y quedan sueltos en `Build\Windows\DomoVR\Content\Movies\`,
donde se pueden cambiar sin volver a empaquetar. También agrega los tres mapas
a `MapsToCook` y `/Game/Media` a `DirectoriesToAlwaysCook` (el preset no lo
referencia ningún nivel). Al final el script comprueba que estén la playlist y
cada video que nombra, y copia lo que falte. Log en
`03_Unreal/Saved_Logs/empaquetar.log`.

Medido el 18 de septiembre de 2026: la primera corrida tardó 6,2 minutos
(cocina completa con los shaders ya en caché del editor) y la segunda 1,1; el
build pesa 1,1 GB. `Spout.dll` se copia junto al `.exe`
(`Binaries/Win64/`, por el `RuntimeDependencies` del plugin), no a la carpeta
del plugin, y el plugin no la buscaba ahí: el primer build arrancó con
`Spout.dll not found` y Spout apagado. Se agregó esa ruta a `FindSpoutDllPath()`
en `Plugins/SpoutPlugin/Source/SpoutPlugin/Private/SpoutModule.cpp`, otro
cambio local sobre el plugin vendorizado (ver [03_Puente_Spout.md](03_Puente_Spout.md),
sección 2). Con eso el build carga Spout y la tecla S sirve también ahí.

Para abrirlo:

```
Build\Windows\DomoVR.exe                          sala 180 (el mapa por defecto)
Build\Windows\DomoVR.exe /Game/Maps/DomoVR_45     sala 45
Build\Windows\DomoVR.exe /Game/Maps/DomoVR_90     sala 90
```

El proyecto arranca en VR (`bStartInVR`): con SteamVR o Virtual Desktop
corriendo entra directo al visor; sin visor conviene `-nohmd -windowed
-ResX=1920 -ResY=1080`. Para llevarlo a otra máquina basta la carpeta
`Build\Windows` entera (con el instalador de prerequisitos incluido por
`-prereqs`).

## 7. Cómo se verificó

Todo con `-RenderOffscreen` (sin ventana ni foco) y un guion de prueba: el
controlador lee `-DomoGuion=<archivo>`, un comando de consola por línea con
`esperar N` para las pausas, y los ejecuta en orden. Las capturas salen con
`HighResShot 1600x900 filename=<ruta>` después de `domo.Camara 0 0 300 …` (el
centro de la esfera en la sala 180). Ejemplo de guion:

```
esperar 6
domo.Estado
domo.Camara 0 0 300 35 0 100
esperar 1
HighResShot 1600x900 filename=C:/tmp/frente.png
esperar 1.5
domo.Cue 2
esperar 4
domo.Estado
quit
```

```
UnrealEditor.exe <ruta>\DomoVR.uproject /Game/Maps/DomoVR -game -RenderOffscreen -nohmd ^
  -ResX=1600 -ResY=900 -DomoPlaylist=<playlist> -DomoGuion=<guion> -abslog=<log>
```

Resultados del 18 de septiembre de 2026, en `-game` con los binarios del editor:

| Prueba | Resultado |
|---|---|
| Patrón 360, frente (`Yaw` 0 de la cámara, +X) | cuadro blanco al frente a 45°, verde abajo, cian arriba, sin rojo ni amarillo |
| Cénit | disco cian con los ocho meridianos y la marca magenta junto al centro, hacia el frente |
| Atrás | la columna negra gruesa de la costura |
| `pitch` 90 | la costura no aparece en la cúpula; atrás, cerca del horizonte, queda el cénit del video |
| `horizonte` 20 | la banda amarilla entra por el borde de la cúpula |
| domemaster y VR180 del mismo patrón | el frente idéntico al del 360 (con el contador legible) |
| `"169"` | el patrón entero como pantalla plana al frente, negro alrededor |
| *3gracias* (`test roto pintura.mp4`, H.264 Main 4096 × 2048, 76 Mb/s, nivel 5.1) | abre con `WmfMedia` sin transcodificar; textura 4096 × 2048, `tasa=1.00` |
| Sala 45 (`DomoVR_45`) | desde el ojo del `PlayerStart`, el patrón y *3gracias* sobre la pantalla inclinada, frente al público |
| Audio | `pistas_audio=1` y nivel 0,077 con el patrón (el pitido); 0,000 con *3gracias*, cuya pista de audio es silencio (−91 dB medido con ffmpeg); de vuelta al patrón, 0,077 otra vez |
| Negro | cúpula negra y nivel del audio a cero; al quitarlo vuelve |
| Fuente Spout y de vuelta | el receptor toma la cúpula; al volver a Media se reabre el cue actual |
| Cue sin `loop` | al terminar pasa solo al siguiente |
| Log | sin errores de `LogWmfMedia` ni de `LogMediaUtils` |
| Build empaquetado (`DomoVR.exe -RenderOffscreen -nohmd`) | las mismas capturas que en `-game` (frente, cénit, atrás, `pitch` 90, `horizonte` 20, `"169"`, *3gracias*), los videos leídos desde `Build\Windows\DomoVR\Content\Movies\`, Spout cargado y el cambio Media → Spout → Media funcionando |

El build escribe al arrancar seis `LogD3D12RHI: Error: Failed to create
pipeline state ... error 80070057`, antes de cargar el nivel y sin efecto
visible en las capturas; no se investigaron (probablemente estados de trazado
de rayos del motor, no del material de la cúpula). También sale una vez el
aviso "no disponible todavia" del receptor de Spout: tickea en el primer cuadro,
antes de que el controlador lo apague.

En `-game` con los binarios del editor aparecen dos errores de Python de los
plugins del motor `EditorToolset` y `ToolsetRegistry`
(`module 'unreal' has no attribute 'AgentSkill'`): son del modo `-game`, no de
este proyecto, y no existen en el build empaquetado.

## 8. Límites

- **8 bits.** `MT_Domo` es de 8 bits por canal, igual que el receptor de
  Spout. Un video de 10 bits no mejora nada (y con Media Foundation
  probablemente no abre).
- **Códecs.** H.264 hasta 4096 de ancho y 30 cuadros por segundo es lo
  verificado. HAP, ProRes, 8K y 60 cuadros a 4096 × 2048 quedan fuera.
- **Una pantalla.** El formato `"169"` es una sola pantalla
  (`pantalla169.frag`). Los montajes de muchas pantallas, templates y
  recorridos de `VIDEO_DOME` siguen siendo cosa de TouchDesigner.
- **Sin fundido entre cues.** El cambio de cue es un corte; para una
  transición suave, `B` (negro), cambiar y `B` otra vez.
- **Sin costura fundida.** El fundido de `costura.frag` no está en el
  material; para sacar la costura de un 360 queda el giro esférico (`pitch`,
  `roll`).
- **Un reproductor.** Hay un solo `MP_Domo`: no se pueden mezclar dos videos.

## 9. Pendiente de confirmar

- **Espejo en el camino de Spout: resuelto** el 18 de septiembre de 2026
  (`EspejoU` en `M_Domo`; [02_Sala_Unreal.md](02_Sala_Unreal.md), sección 13).
- **El build en el visor.** Se probó sin visor (`-nohmd`); falta abrirlo con
  SteamVR o Virtual Desktop y mirar la cúpula en VR.
- **Los `Failed to create pipeline state` del arranque del build** (sección 7).
- **Remote Control en el build** con `-RCWebControlEnable`: no probado.
- **HEVC y 60 cuadros**: no probados.
- **Indicador de uso Nanite: resuelto** el 18 de septiembre de 2026. Las
  superficies de la sala son instancias de `M_SalaPBR`, que lleva el
  indicador; el aviso ya no sale en `-game` ([02_Sala_Unreal.md](02_Sala_Unreal.md),
  sección 11). El build no se volvió a empaquetar después de ese cambio.
