# Cambios

Bitácora de cambios de domo-lab, de lo más reciente a lo más antiguo. Cada entrada
dice qué cambió y por qué; el detalle técnico y las mediciones están en
[04_Docs](04_Docs/). El estado futuro está en la [hoja de ruta](README.md#hoja-de-ruta).

## 29 de septiembre de 2026 · Regenerar TouchDesigner sin perder la disposición

- **La disposición de la red ya no se pierde al regenerar por MCP.** `build_domo.py` (versión 1.5) guarda la posición,
  el tamaño y el color de cada nodo y la caja de cada nota antes de destruir `/project1/DOMO`, y los devuelve al
  terminar (`00_TouchDesigner/conservar_layout.py`). La disposición queda en `layout_domo.json`, un nodo por línea.
- **Los nodos borrados a mano no vuelven.** Se guardan en la lista `omitidos` (hoy, `IN_169/VIDEO_DOME/spout_in`) y el
  constructor los borra al terminar.
- **Copia de seguridad antes de destruir:** `00_TouchDesigner/respaldo/DOMO_AAAAMMDD_HHMMSS.tox`, las últimas ocho,
  fuera de git. El constructor lista lo que había en la red anterior y ya no crea.
- **`domo_lab.toe` con el orden nuevo de la red** (136 nodos movidos y notas redimensionadas). Se le quitaron las rutas
  de video de esta máquina y `Fuente` queda en el patrón de prueba. Los DATs `moments_exec` y `watcher` de
  VIDEO_DOME ya no escriben la ruta absoluta del repositorio: usan `project.folder`.
- Verificado con una prueba de la lógica contra una red simulada. Sin verificar dentro de TouchDesigner: la
  primera regeneración real por MCP.
- Sin actualizar: `DOMO.tox` sigue siendo el del 29 de septiembre a mediodía (sin el orden nuevo); se vuelve a guardar
  desde TouchDesigner.

## 29 de septiembre de 2026 · README nuevo en tres idiomas, capturas del build y hoja de ruta

- **README rehecho** con cabecera, insignias, novedades, galería, secciones desplegables, diagramas Mermaid (arquitectura
  e historia), una animación de los montajes 16:9, la tabla de compatibilidad por fabricante de tarjeta y una hoja de
  ruta en tres columnas (ahora, después, más adelante).
- **Inglés y portugués:** `README.en.md` y `README.pt-BR.md`, traducidos por completo, con un selector de idioma en
  los tres. Los documentos de `04_Docs/` siguen solo en español y eso se dice en cada README.
- **Blender 5:** el README decía Blender 4; el generador se corre con Blender 5.2 LTS. Corregido en la insignia y en
  los requisitos.
- **Capturas nuevas del ejecutable** (`05_Preview/renders/`): la sala 180 con las paredes negras y el velo de la
  cúpula, las salas 45 y 90, seis montajes 16:9 y el menú. Se sacaron con el build empaquetado y un video propio.
- `04_Docs/build_docs.py` ahora traduce el HTML y el Mermaid de los README a Markdown simple y suma las páginas en
  inglés y portugués a `docs/index.html`.

## 29 de septiembre de 2026 · TouchDesigner: montajes 16:9, efectos, 3D y panel de Unreal

- **Montajes 16:9 arreglados.** Tres fallas de `dome_map.frag` (no solo los valores): el cilindro desaparecía a los
  ~20 s con el desplazamiento encendido, el túnel salía en forma de ojo con una costura dura, y un recorte negativo
  metía una muesca del borde del cuadro. Se corrigieron y se llevaron también al HLSL de Unreal. Se ajustaron los
  valores de `cine`, `grande`, `bajo`, `cenital`, `sala_6`, `sala_6_mosaico`, `sala_corona_panorama`, `tres`, `espejo`,
  `cilindro_doble` y `fragmentos`. Nuevo **brillo por pantalla** (columna `spare`).
- **Valores en vivo:** página *Ajuste* en VIDEO_DOME y 34 parámetros con rango en la página 16:9 de DOMO (ancho, alto,
  elevación, separación, copias, solape, borde, opacidad, brillo).
- **Módulos nuevos en TouchDesigner:** `IN_FX` (8 efectos GLSL reactivos al audio), `IN_3D` (objetos 3D animados con
  cámara orbital, sin importar modelos; ranura `modelo` para uno propio), un **master** de brillo, contraste, gamma y negro,
  y un **panel de control de Unreal por UDP** (`127.0.0.1:7000`, líneas `domo.*`).
- **Unreal sigue a TouchDesigner:** las plantillas del ejecutable se generan desde
  `00_TouchDesigner/video_dome/plantillas_ue.json` con `03_Unreal/generar_plantillas.py`, así que las cifras no divergen;
  hay un deslizador de brillo por pantalla en el menú.
- Verificado con capturas de cada módulo, 60 fps con la salida a 4096 y 9 comandos UDP recibidos por un receptor de
  prueba. Sin verificar: el panel contra el ejecutable abierto y `estudio_pantallas.html`, que no tiene los arreglos del shader.

## 29 de septiembre de 2026 · Sala, fondo desenfocado, perfiles de render y ajustes guardados

- **Paredes negras.** En el ejecutable las paredes de la sala 180 salían con la textura de
  madera. Ahora son negras por defecto y el menú permite volver a la madera (`domo.Paredes 0|1`).
- **Piso con menos reflejo.** Nuevo control «Rugosidad del piso»; el piso pulido de la sala 180
  refleja ahora bastante menos (por defecto 1,8 veces su rugosidad original).
- **Fondo desenfocado en los montajes 16:9.** El ejecutable no tenía la capa de fondo de
  VIDEO_DOME (solo había pantallas sobre negro). Se portó al material de la cúpula: modos
  sin fondo, lavado y envolvente, con desenfoque, brillo, saturación, zoom, repeticiones y giro,
  guardados por cue en `playlist.json`. El desenfoque usa los mips de la textura del video.
- **Perfiles de render según la pantalla y la tarjeta:** automático, visor VR, monitor, proyector o
  domo, y ligero. El porcentaje de pantalla se calcula con la resolución real de la ventana.
  `domo.Perfil`, y el menú muestra el fabricante, la memoria de video y la resolución interna.
- **`ajustes.json`:** el perfil, las paredes, el piso, el velo, las luces y el decodificador se guardan
  solos y se aplican al abrir. `empaquetar.ps1` lo conserva.
- **AMD e Intel:** investigación y decisiones en [07_GPUs_AMD_e_Intel.md](04_Docs/07_GPUs_AMD_e_Intel.md).
  El decodificador D3D12 Video de Electra, apagado de fábrica en el motor, se enciende al arrancar (es el camino
  de GPU para HEVC en AMD e Intel); **Optimizar video** usa NVENC, AMF o Quick Sync según la tarjeta. Solo se
  probó en NVIDIA: lo demás está por verificar con la tarjeta en la mano.

## 29 de septiembre de 2026 · Decodificación de video en la GPU

- **El video ya no se traba.** El ejecutable reproduce ahora con **Electra**, el
  reproductor de Unreal, en lugar de Windows Media Foundation. Con el video de
  prueba (HEVC de 4096 × 4096, 60 Mb/s) el proceso pasó de 6,5 a 1,5 núcleos de CPU
  y el decodificador de la GPU trabaja al 15 %. No se cambió de DirectX 12.
- Decodificadores habilitados en `DomoVR.uproject`: `D3D12VideoDecodersElectra`
  (D3D12 Video, cualquier fabricante; el motor lo trae apagado y el controlador lo enciende)
  y `NVDECElectra` (NVIDIA, tiene prioridad). Los dos abren HEVC de 4096 × 4096 nivel 6 en la RTX 3090.
- Si Electra no acepta un archivo, el ejecutable lo reintenta por etapas (Electra con el decodificador de
  Media Foundation y, por último, `WmfMedia` en CPU) y lo deja escrito en el log.
- Menú **Fuente y video > Decodificador de video** y comando
  `domo.Reproductor auto|electra|protron|wmf` para elegir el reproductor.
- **Optimizar video** (copia H.264 de 2048 con NVENC) sigue disponible para los
  casos que caen a `WmfMedia`; el aviso de «video pesado» solo sale con ese reproductor.
- `empaquetar.ps1` ya no pisa la `playlist.json` ni los `controles.json` del build
  con los del proyecto: los guarda y los devuelve al terminar.
- Documentado con las opciones que existen en UE 5.8 para decodificar en GPU con DX12
  ([06_Unreal_standalone.md](04_Docs/06_Unreal_standalone.md), sección 5).

## 29 de septiembre de 2026 · Optimizar video, sala 45 y 90

- `domo.Optimizar` y el botón del menú: copia liviana H.264 con ffmpeg (ruta de GPU
  completa con NVENC y respaldos por CPU y x264), avance visible y alta automática en la lista.
- `domo.Estado` escribe los cuadros por segundo y el cuadro más lento.
- **Arreglo de las salas 45 y 90 en el ejecutable:** no aparecía jugador ni cámara
  porque el motor descartaba el único `PlayerStart`. El modo de juego ahora siempre usa
  el primero, el jugador nace parado en el primer pasillo, y las mallas macizas
  (cúpula, muros) ya no expulsan al jugador. La gradería, la tarima y las barandas
  tienen colisión por su forma real.

## 29 de septiembre de 2026 · Jugador, teclas y montajes de pantallas

- **Jugador que camina** (`ADomePawn`, un `Character`): modos Caminar (gravedad y
  colisiones), Volar y Fantasma; velocidades, altura de ojos, gravedad y sensibilidad
  se ajustan en vivo y se guardan.
- **Teclas remapeables** desde el menú (`controles.json`, junto a la playlist).
- **Montajes de pantallas 16:9** editables en vivo, con 21 plantillas (corona, 2 y 4
  pantallas, túnel, anillo, cilindro…) portadas del sistema de TouchDesigner al
  material de la cúpula; submenús para cada pantalla y guardado en la playlist.
- **Velo de la cúpula** al encender las luces: un degradé tenue de blanco a morado
  sobre la proyección, con intensidad ajustable, para reforzar la sensación de que
  el espacio se encendió.

## 29 de septiembre de 2026 · Menú y control por UDP

- **Menú desplegable en pantalla** dentro del ejecutable (F2 o M): fuente, videos,
  formato, imagen en la cúpula, luces, puntos de vista, calidad, sala, sin teclado ni
  consola y sin TouchDesigner.
- **Control por UDP** en `127.0.0.1:7000` con los comandos `domo.*` (TouchDesigner,
  Resolume, QLab o un script pueden mandar cue, luces, abrir video…).
- La cabina de control de la sala 180 baja a 1,3 m de altura y hay puntos de vista
  para verla desde el espacio.

## 28 de septiembre de 2026 · Sala 180 más fiel

- Sala 180 más cercana al Planetario de Bogotá: cabina cerrada, tarima de 3 m, sin
  anillo de LED y sillas más atrás.
- El importador actualiza el nivel **sin borrar** los ajustes hechos en el editor;
  las luces de la sala se apagan solas cuando hay señal.

## 18 de septiembre de 2026 · Sala standalone y salas 45 y 90

- La sala reproduce videos sin TouchDesigner (`ADomeMediaController`, playlist en
  JSON) y se empaqueta como programa suelto para Windows.
- Salas de 45 grados (tipo Maloka, público sentado) y de 90 (de pie, con barandas).
- Materiales PBR, Nanite, Lumen con trazado de rayos por hardware y TSR.
- Módulo 16:9 editable desde la raíz de TouchDesigner; audio que sigue a la fuente al aire;
  giro esférico para sacar la costura de un 360 de la cúpula.
- README nuevo con licencias MIT (código) y CC BY 4.0 (contenido).

## 17 de septiembre de 2026 · Primera versión

- Sala de domo VR en Unreal 5.8 con el puente Spout desde TouchDesigner.
- Sistema de señal en TouchDesigner (360, 180, patrón de prueba), documentación del
  proceso y la matemática, y las fichas de los domos de Colombia.
