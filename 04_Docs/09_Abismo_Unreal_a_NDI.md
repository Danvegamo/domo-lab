# El abismo: Unreal genera el domo y lo manda por NDI

Hasta ahora la señal iba de TouchDesigner a Unreal: el video se proyectaba en la cúpula de una sala virtual. Esta página
documenta el **sentido inverso**: Unreal es la fuente. Una escena en tiempo real, un fondo marino profundo con partículas
y brillo, criaturas que cruzan la Colombia actual con el mar del Cretácico de Villa de Leyva y basura plástica del
Antropoceno con la que dialogan, se renderiza como **domemaster** y sale por **NDI**, para que TouchDesigner (o un
proyector, o cualquier receptor NDI) la reciba. La cámara se mueve por el espacio; lo que se ve es lo que vería el público
dentro de la cúpula.

![El abismo como domemaster, en pleno diálogo: criaturas, basura plástica y el lecho](../05_Preview/renders/abismo_domemaster_dialogo.jpg)

Estado, el 29 de septiembre de 2026: **funciona de punta a punta en Unreal** (escena, domemaster y NDI, en el editor y en el
programa empaquetado, medido con un receptor propio). **Falta probarlo dentro de TouchDesigner** (sección 7).

## 1. Cómo se abre

```powershell
03_Unreal\crear_abismo.ps1                 # una vez, con el editor cerrado: materiales, mallas y el nivel /Game/Maps/Abismo
03_Unreal\empaquetar.ps1                   # el programa (ya incluye el nivel Abismo)
03_Unreal\Build\Windows\DomoVR.exe /Game/Maps/Abismo
```

Desde el editor: abrir `/Game/Maps/Abismo` y *Play*. La fuente NDI se llama `Unreal_Abismo` (`-AbismoNDI=Nombre` la
cambia). **F4** muestra u oculta el domemaster en la ventana. Antes de `crear_abismo.ps1` hay que haber corrido
`01_Blender/generar_criaturas.py` (las mallas están en `02_Export/criaturas/`, ver [08_Criaturas_abismo.md](08_Criaturas_abismo.md)).

Requisitos: los de siempre (Unreal 5.8 y el módulo C++ compilado). NDI no pide instalar nada: el plugin `NDIMedia` que trae
el motor lleva su propia `Processing.NDI.Lib.x64.dll`, y el empaquetado la copia al programa. *NDI® es una marca de Vizrt
NDI AB.*

## 2. Qué hace cada pieza

```
AAbismoEscena   lecho procedural, niebla, luz de la superficie, nieve marina y posproceso con brillo
AAbismoFauna    13 especies (InstancedStaticMesh), el dialogo con la basura y los encuentros con la camara
ADomeEmisorNDI  la camara: recorre un camino, captura un cubo, lo convierte en domemaster y lo manda por NDI
```

- **La captura.** `ADomeEmisorNDI` lleva un `SceneCaptureComponentCube` (`bCaptureRotation`, para que el cubo gire con la
  cámara). Cada cuadro captura las seis caras (1024 px cada una) y un material (`M_CuboADomemaster`) las convierte a un
  domemaster **equidistante** de 2048 × 2048: el radio de la imagen es proporcional al ángulo desde el cenit, el cenit queda
  al centro y el frente abajo, igual que el que saca TouchDesigner. Con 1024 por cara hay 11 px por grado, lo mismo que un
  domemaster de 2048 (`LadoCubo` y `LadoDomemaster` se cambian juntos: para 4096, cubo de 2048).
- **NDI.** `UNDIMediaOutput` del plugin de Epic captura la textura del domemaster (`CaptureTextureRenderTarget2D`) y la
  anuncia a 30 fps, en 8 bits. El motor la convierte a YUV antes de mandarla.
- **La cámara.** Un camino suave (una curva de Lissajous alrededor de `Centro`, de 240 s por vuelta) con el frente hacia donde
  avanza y un balanceo lento. `InclinacionDomo` (50° por defecto) inclina el cenit de la cúpula hacia adelante: una cúpula
  solo muestra lo que está sobre su horizonte, y con el cenit mirando al cielo el lecho quedaría fuera. Con 50°, el lecho
  entra por la parte baja del frente y el agua abierta queda arriba.
- **El lecho.** Un `ProceduralMeshComponent` de 120 m de lado (dunas, colinas y afloramientos, sacados de una semilla; la
  misma semilla da el mismo lecho). Niebla exponencial volumétrica azul verdosa, una luz direccional fría y un posproceso con
  brillo (bloom). Sin Lumen: la escena es emisiva y de niebla, y seis vistas de Lumen por cuadro no caben.
- **La nieve marina.** 9 000 esferas pequeñas en un `InstancedStaticMesh`. Un material aditivo las **envuelve alrededor de la
  cámara** en el vértice (así son siempre las mismas 9 000, con paralaje real) y las desvanece en el borde de la caja.
- **La fauna.** Cada especie es un `InstancedStaticMesh`. Los cuerpos **nadan con un shader**, sin esqueleto: una onda viaja
  por el cuerpo y mueve los vértices según el alfa del color por vertice (0 rígido, 1 en cola, aletas, tentáculos y alas).
  El código solo mueve los cuerpos enteros (rumbo, altura sobre el lecho, quedarse en el área, no pasar sobre la cámara).
  Las belemnitas van en cardumen; las amonitas, las bolsas, las botellas, los anillos y las redes van a la deriva con una
  corriente común; las rocas, los corales y las algas se plantan en el lecho.

## 3. El diálogo con el Antropoceno

Un ciclo de 75 segundos (`DuracionDialogo`), cinco momentos:

| Momento | Qué pasa |
|---|---|
| Calma (0–25 %) | Las criaturas nadan; la basura deriva; poca luz propia. |
| Llamada (25–42 %) | Las criaturas laten con luz bioluminiscente y las tres más cercanas a la cámara sueltan ondas de luz que se expanden. |
| Respuesta (38–65 %) | La basura responde con una luz **sintética** (magenta y verde ácido) en vez del azul orgánico. |
| Acercamiento (42–88 %) | Las criaturas giran hacia la basura más cercana y la rodean a distancia. |
| Calma otra vez | Todo se apaga y vuelve el ciclo. |

Además, cada 18 s una criatura grande **cruza por delante de la cámara** a unos 6 a 12 m, para que se la vea entera.
`Curiosidad` (0 a 2) dice cuánto se acercan; `Densidad` multiplica la cantidad de todas las especies.

## 4. Parámetros, línea de comandos y consola

| Cómo | Qué |
|---|---|
| `-AbismoNDI=Nombre` | nombre de la fuente NDI |
| `-AbismoLado=2048` · `-AbismoCubo=1024` | domemaster y cara del cubo |
| `-AbismoSinNDI` | dibuja el domemaster pero no lo manda |
| `-AbismoExposicion=0.9` | brillo fijo de la exposición (más alto = más oscuro) |
| `-AbismoSemilla=N` · `-AbismoDensidad=X` | lecho y cantidad de fauna |
| `-AbismoSegundo=S` · `-AbismoDialogo=S` | empezar en el segundo S del recorrido o del diálogo |
| `-AbismoFoto=a.png;b.png -AbismoFotoCada=8 -AbismoSalir` | guardar el domemaster y salir |
| `-AbismoSinTope` | no limitar los cuadros (ver la trampa de la sección 6) |
| consola `abismo.Foto ruta.png` · `abismo.Segundo S` · `abismo.Velocidad V` · `abismo.Inclinacion G` · `abismo.Dialogo S` | lo mismo, en vivo |

## 5. Medido

En la RTX 3090, el domemaster de 2048 con cubo de 1024:

| Configuración | Cuadros por segundo |
|---|---|
| Cubo de 1024, escena completa, sin tope | 40 a 55 |
| Cubo de 1536 | 25 a 30 (baja con el tiempo) |
| Con NDI y tope de 30 fps (lo que se entrega) | **29,8 recibidos durante 60 s** (100 s en el editor), sin caídas |

El receptor de esta medida es `03_Unreal/herramientas/ndi_recibir.py`, que busca la fuente por nombre, recibe unos segundos,
cuenta los cuadros y guarda el último como PNG; usa la DLL de NDI del motor por `ctypes` y no necesita TouchDesigner ni NDI
Tools. Sirve para comprobar a distancia que Unreal está anunciando y a qué cadencia:

```
python 03_Unreal\herramientas\ndi_recibir.py Unreal_Abismo salida.png --segundos 10
```

## 6. Trampas medidas

- **El motor se caía a los ~50 s** con `Too many residency sets are open concurrently` (D3D12). Sin vsync y sin pantalla el
  juego corría a lo que diera la GPU y las listas de comandos se acumulaban. Con `t.MaxFPS` igual a los fps de NDI (30) no se
  cae en 100 s; `ADomeEmisorNDI` lo pone solo. Apagar la gestión de residencia (`D3D12.ResidencyManagement=0`) **no sirve**: en
  lugar de la caída, la GPU dio fallos de página al leer el cubo.
- **El domemaster salía negro** aunque el dibujo funcionaba (un degradado de prueba se veía bien). No era la captura: la
  exposición. El modo de exposición *Manual* usa la cámara física (ISO, diafragma, obturador) y deja a oscuras una escena
  tenue. Se usa *Histogram* con el mínimo y el máximo iguales, que da un brillo fijo (`Exposicion`; **más alto es más
  oscuro**). En `ADomeEmisorNDI` hay un modo de diagnóstico (`ModoDepuracion`: 1 degradado, 2 la dirección como color,
  3 el cubo amplificado) que permite separar esa causa de una captura vacía.
- **El cubo de render por defecto del material** (`RTC_Default`) tiene tamaño 0 al crearse. Se le da tamaño real.
- **`CaptureScene()` de un cubo** se llama a mano cada cuadro, justo antes de dibujar el material; con `bCaptureRotation` el
  cubo gira con el actor y el material muestrea con la dirección local (X adelante, Y a la derecha, Z arriba), sin cambiar
  ejes.
- **Nada referencia** las mallas y los materiales del abismo (se cargan por ruta con `LoadObject`), así que el cocinado los
  dejaba fuera del programa. `DefaultGame.ini` los cocina a la fuerza con `DirectoriesToAlwaysCook=/Game/Abismo`.
- En Python de Unreal: el pin de coordenadas de `TextureSampleParameterCube` se llama `UVs`; el color por vertice se conecta
  con el pin vacío (RGB) o `A`; `PerInstanceCustomData` usa `const_default_value`.
- Un script suelto llamado `enum.py` en la carpeta temporal del usuario tapa a la biblioteca estándar de Python cuando los
  scripts se corren desde ahí: correr los parches desde otra carpeta.

## 7. Recibirlo en TouchDesigner (pendiente de probar)

TouchDesigner trae `NDI In TOP`. La fuente aparece como `<equipo> (Unreal_Abismo)`, 2048 × 2048, y es un domemaster, no
un equirectangular. Hay dos usos:

1. **Al proyector de la cúpula real:** el domemaster de Unreal ya es lo que el proyector espera; se puede mandar tal cual a las
   salidas (`out_domo`, Spout, NDI o a disco) sin pasar por el lienzo equirectangular. Es lo mejor: no hay conversión de ida y
   vuelta.
2. **A la sala virtual de Unreal o al resto del sistema:** hay que llevarlo al lienzo equirectangular común (un `Projection TOP`
   de fisheye a equirectangular, como hace `IN_180`). Se pierde algo de nitidez en el borde.

El módulo de TouchDesigner que haría esto (`IN_UE`, con su página en `DOMO`, el mismo Activo y la misma orientación que los
demás) no está escrito: hace falta TouchDesigner abierto para probarlo por MCP sin arriesgar `build_domo.py`.

## 8. Lo que falta

- Módulo `IN_UE` en TouchDesigner y prueba real de NDI hacia él.
- Audio: el plugin puede mandar audio por NDI (`bOutputAudio`), la escena todavía no tiene sonido.
- Control por UDP (`domo.*`) para el abismo: velocidad, densidad, dialogo, inclinación.
- Verlo dentro de la sala virtual: poner el domemaster como textura de la cúpula de la sala 180, en lugar de un video.
- Probarlo en un proyector y un visor reales; en AMD e Intel, igual que el resto (ver [07_GPUs_AMD_e_Intel.md](07_GPUs_AMD_e_Intel.md)).
- Un recorrido dirigido (cue a cue, con puntos y tiempos) además del camino automático.
