# Modelos de sala: domo 180, domo 90 y domo 45

La sala de domo existe en tres variantes que comparten todo (piso, butacas,
tarima, zona de control, puertas, listones, materiales, señal de Spout) y solo
cambian en la cúpula y en la altura del muro. Cada variante es un FBX propio en
`02_Export/` y un nivel propio en `03_Unreal/DomoVR/Content/Maps/`. Los tres
salen del mismo generador (`01_Blender/generar_sala_domo.py`) y del mismo
importador (`03_Unreal/importar_sala.py`), parametrizados por el FOV de la
cúpula. La geometría de base está en [02_Sala_Unreal.md](02_Sala_Unreal.md) y
la señal que llega a la cúpula en [04_Senal_TouchDesigner.md](04_Senal_TouchDesigner.md).

## 1. Qué es cada modelo

| Modelo | Cúpula | Elevación que cubre | Modelo en TouchDesigner |
|---|---|---|---|
| **Domo 180** | media esfera (planetario clásico) | de 0° (horizonte) a 90° (cénit) | `domo180` |
| **Domo 90** | casquete esférico | de 45° a 90° | `domo90` |
| **Domo 45** | casquete esférico | de 67,5° a 90° | `domo45` |

El FOV es el ángulo total que abarca la cúpula vista desde el centro de su
esfera; el borde del casquete queda a `90 − FOV/2` grados de elevación. Los
casquetes representan salas donde la proyección cubre solo la parte alta del
cielo: el muro es más alto y el público mira más arriba.

## 2. Geometría

Todo se deriva de dos constantes del generador, `RADIO_DOMO = 11,5 m` (radio del
muro) y `ALTURA_ARRANQUE = 3 m` (altura a la que arranca la media esfera), más
`FOV_DOMO`. Las reglas:

- El borde de la cúpula tiene siempre el radio del muro (11,5 m), de modo que
  el muro cilíndrico sube hasta él y la sala cierra sin ningún anillo plano.
  Por eso la esfera de la que se recorta el casquete es más grande que la del
  domo 180: `RADIO_ESFERA = RADIO_DOMO / cos(elev_min)`.
- La altura del cénit es la misma en los tres modelos:
  `ALTURA_CENIT = ALTURA_ARRANQUE + RADIO_DOMO = 14,5 m`. La sala no cambia de
  envolvente; cambia cuánto de esa altura es muro y cuánto es cúpula.
- La altura del casquete (sagita) es `RADIO_ESFERA · (1 − sin(elev_min))` y el
  muro mide lo que queda: `ALTURA_PARED = ALTURA_CENIT − SAGITA`.
- El centro de la esfera queda en `ALTURA_CENIT − RADIO_ESFERA`. En los
  casquetes cae por debajo del piso: es un punto virtual, desde el que se
  definen la elevación y la UV, no una cota construible.

| | Domo 180 | Domo 90 | Domo 45 |
|---|---|---|---|
| Radio del muro y del borde de cúpula | 11,50 m | 11,50 m | 11,50 m |
| Borde de cúpula (elevación mínima) | 0° | 45° | 67,5° |
| Radio de la esfera | 11,50 m | 16,26 m | 30,05 m |
| Altura del muro (`ALTURA_PARED`) | 3,00 m | 9,74 m | 12,21 m |
| Altura de la cúpula (sagita) | 11,50 m | 4,76 m | 2,29 m |
| Cénit sobre el piso | 14,50 m | 14,50 m | 14,50 m |
| Centro de la esfera (z) | +3,00 m | −1,76 m | −15,55 m |
| Triángulos de la escena | 49 090 | 49 090 | 49 090 |
| FBX | `02_Export/sala_domo.fbx` | `02_Export/sala_domo_90.fbx` | `02_Export/sala_domo_45.fbx` |
| Blend | `01_Blender/sala_domo.blend` | `01_Blender/sala_domo_90.blend` | `01_Blender/sala_domo_45.blend` |
| Previews | `05_Preview/vista_*.png` | `05_Preview/vista_*_90.png` | `05_Preview/vista_*_45.png` |
| Nivel de Unreal | `/Game/Maps/DomoVR` | `/Game/Maps/DomoVR_90` | `/Game/Maps/DomoVR_45` |
| Mallas en Unreal | `/Game/Sala/sala_domo_SM_*` | `/Game/Sala/Domo_90/sala_domo_90_SM_*` | `/Game/Sala/Domo_45/sala_domo_45_SM_*` |
| Materiales | `/Game/Sala/Materials/M_*`, `MI_Domo` | los mismos, reutilizados | los mismos, reutilizados |

Las cotas de muro y cúpula se verifican en cada corrida leyendo el FBX
exportado de vuelta (`verificar_export()` imprime `OK`/`DESAJUSTADO` para el
diámetro, la sagita, la altura del muro y el rango V de la UV).

Una consecuencia de medir la elevación desde el centro de la esfera y no desde
el ojo: desde el centro del piso el borde del casquete se ve a unos 40° en el
domo 90 (atan(9,74/11,5)) y a unos 47° en el domo 45, no a los 45° y 67,5°
nominales. Para el mapeo de la señal eso es irrelevante (la textura se pega por
elevación real sobre la esfera); para un estudio de visibilidad desde las
butacas habría que decidir otra regla de altura (ver la sección 6).

## 3. La UV de la cúpula y por qué el mismo lienzo sirve para los tres

TouchDesigner manda por Spout (`TD_Domo_Lab`) un lienzo equirectangular 2:1 con
la cúpula en la mitad superior: `u = 0,5` es el frente (+X), `u = 0/1` la parte
de atrás (−X), `v = 0,5` el horizonte y `v = 1` el cénit. La cúpula de los tres
modelos lleva **una sola capa UV** con esta fórmula, escrita a mano en
`uv_equirectangular()`:

```
U = azimut / 360 + 0,5        (módulo 1; costura en −X)
V = 0,5 + elevación / 180     (elevación desde el centro de la esfera)
```

V no se normaliza al casquete. Así la misma textura cae en el mismo punto del
cielo en los tres modelos: el domo 180 lee `v` de 0,5 a 1, el domo 90 de 0,75 a
1 y el domo 45 de 0,875 a 1. Con el patrón de prueba de TouchDesigner (verde
`v 0,5–0,75`, cian `v 0,75–1`, cuadro blanco del frente en `v 0,75`, marca
magenta en el cénit):

- domo 180: verde del horizonte a 45°, cian de 45° al cénit, cuadro blanco a
  media altura del frente;
- domo 90: solo cian; el cuadro blanco queda justo en el borde de la cúpula
  sobre el frente, el cénit magenta en el centro;
- domo 45: solo cian, sin cuadro blanco (queda bajo el borde); solo se ve la
  marca magenta y los meridianos.

**De dónde sale esta fórmula.** Hasta el 17 de septiembre de 2026 el generador
escribía `V = elevación / 90` y en Unreal se medía otra cosa (la cúpula leía la
mitad superior del lienzo, `v 0,5` en el horizonte), sin explicación en el
código. La explicación, encontrada leyendo el FBX de vuelta con Blender: la
cúpula se creaba con `primitive_uv_sphere_add`, que ya trae una capa `UVMap`
propia; el `bm.loops.layers.uv.new("UVMap")` del script creaba una **segunda**
capa (`UVMap.001`) y escribía ahí. Unreal muestrea el canal 0, que era la UV por
defecto de la esfera de Blender: costura en −X, V de 0 a 1 sobre la esfera
completa, es decir 0,5 a 1 en la mitad superior. Exactamente la fórmula de
arriba. Ahora la cúpula se construye a mano con `bmesh` (mismos vértices y
triángulos que antes en el 180), tiene una única capa y la fórmula es
explícita. `verificar_export()` imprime las capas del FBX para que no vuelva a
pasar. El FBX del domo 180 regenerado pierde la capa fantasma (`UVMap.001`) y
por eso es un poco más liviano que el anterior; el canal 0 no cambia.

## 4. Cómo regenerar

Blender (sin interfaz; el ejecutable está en
`C:\Program Files\Blender Foundation\Blender 5.2\blender.exe`):

```
blender.exe -b -P 01_Blender\generar_sala_domo.py                 # domo 180, hornea texturas (~10 min)
blender.exe -b -P 01_Blender\generar_sala_domo.py -- --fov 90     # domo 90 (~1 min)
blender.exe -b -P 01_Blender\generar_sala_domo.py -- --fov 45     # domo 45
```

El FOV también se puede dar con la variable de entorno `DOMO_FOV`; el argumento
manda si están los dos. Los casquetes no hornean texturas (son las mismas por
material y ya existen de la corrida del 180; `--hornear` las fuerza), pero sí
desenvuelven el UV de las mismas piezas para que el FBX salga igual de válido.

Unreal, headless, uno por modelo:

```
03_Unreal\importar_sala.ps1 -Fov 90
03_Unreal\importar_sala.ps1 -Fov 90 -ScriptName conectar_spout.py
03_Unreal\importar_sala.ps1 -Fov 45
03_Unreal\importar_sala.ps1 -Fov 45 -ScriptName conectar_spout.py
```

El `.ps1` fija `DOMO_FOV` y escribe el log en
`03_Unreal\Saved_Logs\<script>_<fov>.log`. Con `DOMO_FOV = 90` el importador
lee `sala_domo_90.fbx`, deja las mallas en `/Game/Sala/Domo_90`, reutiliza los
materiales de `/Game/Sala/Materials` (crea solo los que falten) e importa el
FBX sin materiales para no pisar los `M_*` sueltos que el 180 dejó en
`/Game/Sala`. Sin `DOMO_FOV` el comportamiento es el original y **no se toca**
nada del 180. `conectar_spout.py` coloca el `SpoutDomeReceiver` del nivel que
toque apuntando al mismo `MI_Domo` y al `Domo_Actor` de ese nivel; en los
casquetes no vuelve a marcar Nanite ni a escribir `.mcp.json`.

Sobre el editor abierto: la importación headless es otro proceso de Unreal
sobre el mismo proyecto. Es seguro solo para niveles que el editor no tiene
cargados (los casquetes se importaron el 17 de septiembre de 2026 con el
editor abierto en `DomoVR`, sin conflicto de archivos). Dos cosas que se ven en
ese caso y no son fallos:

- `UnrealEditor-Cmd.exe` termina con **código de salida 1** aunque el script
  haya corrido completo (`Python script executed successfully ... result 0`).
  El resumen del log dice `Failure - 1 error(s)` y el único error es
  `LogHttpListener: Error: HttpListener unable to bind to 127.0.0.1:8090`: el
  plugin de MCP del commandlet intenta abrir el mismo puerto que ya tiene el
  editor abierto. Con el editor cerrado el código vuelve a ser 0. Lo que vale
  es el bloque `[importar_sala] === Resumen ===` del log.
- El commandlet arranca con el mapa de inicio del proyecto (`/Game/Maps/DomoVR`)
  cargado. La primera versión del importador guardaba todo `/Game/Maps` sin
  mirar si estaba sucio y reescribió `DomoVR.umap` (mismo contenido
  reserializado, pero es el mapa que el editor tenía abierto); se restauró
  desde git y ahora el casquete guarda solo su propio mapa con `save_asset`.

Nunca reimportar el 180 con el editor abierto en `/Game/Maps/DomoVR`. Los
niveles nuevos aparecen en el Content Browser del editor abierto después de un
rescan (o al reiniciarlo). Cada importación de casquete tarda unos 9 minutos,
casi todo en compilar shaders y construir las 16 mallas.

Para verlos con señal: en TouchDesigner poner `Modelo = domo90` o `domo45`, para
que el domemaster y el lienzo de Unreal usen el mismo FOV que la cúpula; en
Unreal abrir el nivel y confirmar el viewport en Lit y Realtime.

## 5. Cómo agregar un modelo nuevo

Un modelo se define por el FOV. Para un casquete de otro ángulo basta con
`--fov N` (10 a 180): salen `sala_domo_N.fbx`, `/Game/Maps/DomoVR_N` y
`/Game/Sala/Domo_N` sin tocar nada más, y en TouchDesigner se usa
`Modelo = custom` con `Fovcustom = N`.

Para un domo real del catálogo `06_Modelos/domos_colombia.json` (campos
`diametro_m`, `inclinacion_deg`, `fov_vertical_deg`):

1. **FOV**: si el catálogo trae `fov_vertical_deg`, es el `--fov`. Si no,
   180 para una media esfera clásica.
2. **Diámetro**: `RADIO_DOMO = diametro_m / 2` en `generar_sala_domo.py`.
   Hoy es una constante, no un argumento; cambiarla afecta a todo lo que se
   deriva de ella (ancho angular del sector de control, reparto de butacas,
   puertas, listones). Con radios pequeños (Medellín 15 m, EMAVI 8 m, domos
   móviles de 5 m) las 360 butacas no caben: `calcular_filas()` sigue
   agregando filas hasta completar `BUTACAS_POR_MODULO` y las últimas
   quedarían fuera del muro. Habría que bajar `BUTACAS_POR_MODULO` (o
   calcularlo desde el radio) antes de generar.
3. **Inclinación** (`inclinacion_deg`, por ejemplo los 27° del Planetario de
   Medellín): **no está soportada** (ver la sección 6).
4. Sufijo: hoy el sufijo es el FOV (`_90`). Un modelo real con el mismo FOV
   que otro (dos salas de 180 con distinto diámetro) colisionaría en nombres;
   haría falta un argumento de nombre de modelo (`--modelo medellin`) que
   reemplace al sufijo numérico en el generador y en el importador.

Ejemplo con Medellín: `diametro_m = 15`, `fov_vertical_deg = 160`,
`inclinacion_deg = 27`. Con `RADIO_DOMO = 7,5` y `--fov 160` sale un casquete
de 10° a 90° de elevación (esfera de 7,62 m, muro de 3,52 m si se mantiene la
regla del cénit a `ALTURA_ARRANQUE + RADIO_DOMO`); la inclinación de 27° no.

## 6. Qué falta

- **Inclinación de la cúpula**: no soportada. Los tres modelos son
  simétricos respecto del eje vertical. Un domo inclinado (Medellín, 27°)
  requiere rotar la esfera alrededor del eje Y antes de recortar el casquete,
  recalcular la intersección con el muro (deja de ser un anillo horizontal:
  el muro tendría altura variable con el azimut) y decidir si la UV sigue la
  esfera inclinada (el cénit del contenido se mueve con la cúpula) o el cielo
  real. Del lado de TouchDesigner el `Pitch` ya existe para compensar.
- **Regla de altura del muro**: se eligió mantener el cénit a 14,5 m en los
  tres modelos. Es una convención, no un dato; si un domo real dicta otra
  altura de muro, hay que exponer `ALTURA_PARED` (o `ALTURA_CENIT`) como
  argumento en vez de derivarla.
- **Radio y aforo por argumento**: `RADIO_DOMO` y `BUTACAS_POR_MODULO` siguen
  siendo constantes; para el catálogo de domos reales tienen que ser
  parámetros (ver la sección 5).
- **Verificación visual del patrón en Unreal** para los niveles 90 y 45:
  pendiente con el editor abierto en esos niveles y TouchDesigner en
  `domo90` / `domo45`. La geometría y el rango V de la UV están verificados
  en el FBX; lo que se vería sobre la cúpula se describe en la sección 3.
- **PlayerStart**: igual que en el 180 (a 4 m del centro hacia +X, 70 cm de
  altura). En los casquetes el público mira mucho más arriba; la butaca tipo
  y la altura de ojo no se ajustaron.
- El FBX del domo 180 regenerado hoy tiene una sola capa UV (antes dos). El
  nivel `/Game/Maps/DomoVR` no se reimportó (el editor lo tenía abierto); el
  canal 0 es idéntico, así que reimportarlo cuando el editor esté cerrado no
  debería cambiar nada visible.
