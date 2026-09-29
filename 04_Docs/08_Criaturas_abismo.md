# Criaturas y objetos del abismo

La escena submarina del domo (fondo marino profundo con partículas y glow) tiene
13 mallas procedurales: cinco animales que cruzan la Colombia actual con el mar
epicontinental de Villa de Leyva (Boyacá, Cretácico Inferior, hace unos 130
millones de años), una belemnita que se instancia en cardumen, cuatro piezas de
basura plástica y tres piezas de decorado del lecho. La idea es un diálogo del
Antropoceno: criaturas orgánicas y bioluminiscentes frente a plástico que flota.
Todo sale de un solo script, sin descargar assets y sin texturas externas.

```
blender.exe -b -P 01_Blender\generar_criaturas.py                       # todo (unos 15 s)
blender.exe -b -P 01_Blender\generar_criaturas.py -- --solo kelp_tira   # solo algunos ids
blender.exe -b -P 01_Blender\generar_criaturas.py -- --vistas C:\carpeta  # vistas de depuración
```

Escribe `02_Export/criaturas/<id>.fbx` (uno por objeto), `manifiesto_criaturas.json`
(ids, triángulos, cajas en m y cm, islas UV) en la misma carpeta, y en
`05_Preview/pruebas/` la hoja de contacto `criaturas_hoja.jpg` y
`criaturas_hoja_mov.jpg` (la misma hoja con el peso de movimiento como mapa de
calor: azul rígido, rojo móvil). Cada FBX se reimporta en Blender al terminar y
el script se detiene con error si la caja, los triángulos, las UV, la capa de
color, el alfa, la orientación de las normales o la unidad de la cabecera no
coinciden con lo construido.

## 1. Tabla de criaturas y objetos

Dimensiones medidas reimportando el FBX (X largo, Y ancho, Z alto). Los
triángulos son los del FBX. Total de la escena: 41 006.

| id | Qué cruza | Dato real | Triángulos | Dimensiones (m) |
|---|---|---|---:|---|
| `kronos_jaguar` | pliosaurio de cabeza grande y mandíbula con dientes, cuatro aletas y piel de rosetas | *Kronosaurus boyacensis*: pliosaurio de Villa de Leyva, Boyacá (Cretácico Inferior). Longitud real sin confirmar. Del jaguar, las rosetas (anillos oscuros con manchas en el centro) | 7 838 | 7,00 × 3,10 × 1,15 |
| `amonita_rana` | concha de amonita en espiral con tentáculos y colores de rana venenosa | amonitas del Cretácico Inferior de Villa de Leyva; los géneros exactos, sin confirmar. De *Phyllobates* / *Oophaga* (ranas de Colombia), el color de advertencia; el patrón amarillo, azul y negro es una elección de diseño | 5 228 | 1,20 × 0,30 × 0,81 |
| `calla_manati` | plesiosaurio de cuello largo con hocico ancho y bigotes de manatí | *Callawayasaurus colombiensis*: plesiosaurio elasmosáurido de Villa de Leyva (cuello largo, cuatro aletas). Longitud real sin confirmar. De *Trichechus manatus*, el hocico romo con vibrisas (bigotes) | 5 334 | 5,00 × 3,04 × 1,42 |
| `desma_orquidea` | tortuga marina grande con orquídeas y corales hechos de geometría | *Desmatochelys padillai*: tortuga marina de Villa de Leyva (Cretácico Inferior). Autoría, año y tamaño real, sin confirmar. Las orquídeas y corales son invención del diseño | 9 042 | 3,00 × 3,19 × 0,82 |
| `kyhy_inia` | ictiosaurio esbelto con el melón y el hocico largo del delfín rosado | *Kyhytysuka sachicarum*: ictiosaurio de Sáchica, Boyacá (Cretácico Inferior). Tamaño real sin confirmar. *Inia geoffrensis*: delfín rosado del Amazonas, de hocico largo y melón prominente | 5 388 | 3,50 × 1,47 × 1,26 |
| `belemnita_morpho` | belemnita con alas de mariposa Morpho que aletean | las belemnitas son cefalópodos extintos con un rostro (guarda) en forma de bala; su presencia en Villa de Leyva, sin confirmar. En *Morpho*, el azul intenso viene del color estructural de las escamas, no de un pigmento | 364 | 0,40 × 0,43 × 0,11 |
| `bolsa_plastica` | bolsa que flota como medusa | plástico de un solo uso; la campana arrugada y las cintas por atrás son la asociación visual con una medusa | 1 108 | 0,60 × 0,41 × 0,25 |
| `botella_pet` | botella con tapa y etiqueta | botella PET estándar de agua o gaseosa (cuello y tapa aproximados, no una marca) | 1 078 | 0,30 × 0,07 × 0,07 |
| `red_fantasma` | fragmento de red de pesca rasgada con cuerda de flotación y boyas | las redes abandonadas se llaman "redes fantasma" | 1 098 | 2,00 × 1,26 × 0,32 |
| `anillo_lata` | portalatas de seis anillos | plástico de un solo uso | 1 092 | 0,15 × 0,10 × 0,01 |
| `roca_lecho` | roca irregular con musgo y líquenes | decorado | 816 | 1,00 × 0,74 × 0,50 |
| `coral_abanico` | abanico de coral de un solo plano | decorado (gorgonia) | 1 854 | 0,80 × 0,07 × 0,68 |
| `kelp_tira` | tira de alga con 60 cortes a lo largo | decorado | 766 | 3,00 × 0,21 × 0,15 |

La bioluminiscencia es de diseño en los cinco animales: son los vértices de
color cian o azul claro de la capa `Col`. Nada de eso se toma de los fósiles.
Tampoco lo son las proporciones: son estilizadas (por ejemplo, la cabeza del
pliosaurio es una interpretación, no una reconstrucción).

Topes de triángulos del encargo: criaturas grandes 12 000, `belemnita_morpho`
400, decorado 3 000, el resto 1 500. Se contó `amonita_rana` como criatura (tope
de 12 000). Ningún objeto pasa su tope.

## 2. Convenciones de malla

- **Orientación.** Nariz o frente hacia +X, Z arriba, el largo a lo largo de X.
  Transformaciones aplicadas (rotación cero y escala uno). Origen en el centro del
  cuerpo: el torso en los animales de cola o cuello largos (Z = 0 es el eje del
  cuerpo), y el centro de la caja en los objetos flotantes y en el decorado
  (`kelp_tira` queda con su base en X = -1,5 m, y `roca_lecho` con la base plana
  hacia abajo).
- **Unidades.** Se construye en metros. El FBX sale con la geometría ya en
  centímetros y la cabecera declarando centímetros (`UnitScaleFactor = 1`). Ver
  la trampa 1.
- **Normales.** Todas las caras son suaves. Cada primitiva se orienta hacia
  afuera por volumen con signo, y el script comprueba que no queden aristas
  abiertas ni mal orientadas y que el volumen del FBX reimportado sea positivo.
- **UV0.** Una sola capa (`UVMap`). Cada parte (cuerpo, cabeza, aletas, dientes,
  ojos...) es una isla en su propia celda de una cuadrícula 0-1, con margen;
  `manifiesto_criaturas.json` dice qué partes hay en cada objeto y en qué orden
  ocupan las celdas. Por dentro de la isla, U va alrededor y V a lo largo. Los
  dientes, ojos y boyas comparten celda a propósito (se solapan entre sí, porque
  son iguales). La etiqueta de `botella_pet` es una isla propia con U alrededor
  y V a lo largo, para pegarle una imagen.
- **Color por vértice.** Una sola capa, `Col`, porque Unreal solo importa una:
  **RGB** = patrón y colores base, **A** = peso de movimiento (antes pensado como
  capa `Mov`). A = 0 en el cuerpo rígido y sube hacia 1 en las puntas móviles
  (cola, aletas, tentáculos, alas, cintas, tira de alga, ramas de coral,
  bigotes). En la reimportación en Blender el alfa se conserva (cuantizado a 8
  bits: 0,3 vuelve como 0,302).
- **Cortes.** El cuerpo principal de las criaturas grandes tiene entre 44 y 104
  cortes a lo largo (`kelp_tira`, 60). Excepciones por presupuesto:
  `belemnita_morpho` tiene 10 cortes, y sus alas 6, porque el tope es 400
  triángulos y se instancia cientos de veces.
- **Materiales.** Un solo slot por malla, con nombre por familia: `M_Criatura`,
  `M_Plastico`, `M_Decorado`. Los materiales del FBX son vacíos; el material de
  Unreal se hace aparte. La translucidez de la bolsa, la botella, la red y el
  anillo la pone ese material (el alfa de `Col` NO es opacidad).

Convención esperada del shader (no está horneada): el peso A escala el
desplazamiento. Ondulación de cola y de cuerpo en Y, aleteo de aletas y alas en Z,
oscilación de tentáculos y de la tira de alga en Y y Z, con una fase que dependa
de la posición en X.

## 3. Trampas

1. **La unidad del FBX.** La sala usa `global_scale=1` con `apply_unit_scale=True`
   y `FBX_SCALE_ALL`: la geometría queda en metros y el 100 viaja en la unidad del
   archivo, por lo que `importar_sala.py` fuerza `convert_scene_unit=True`. Para
   piezas sueltas se probó otra cosa (medido en Blender 5.2 con un cubo de 1 m).
   `apply_unit_scale=False` con `FBX_SCALE_NONE` y `global_scale=1` escribe los
   vértices en centímetros (±50 para un cubo de 1 m), declara centímetros en la
   cabecera y deja el nodo con escala uno. Es lo que usan las criaturas: el
   tamaño es correcto con `convert_scene_unit` activo o no. Con
   `global_scale=100` y la unidad sin aplicar, la geometría salía 100 veces más
   grande (±5 000). Hay que evitar ese ajuste.
2. **La escala 0,01 al reimportar.** Blender importa un FBX en centímetros con
   el objeto a escala 0,01 y la malla en cm. Para medir en metros hay que aplicar
   la escala primero (el script lo hace).
3. **Ejes.** Se exporta con `axis_forward='Y'` y `axis_up='Z'`, igual que el FBX
   de piezas de la sala, para que una malla local no pase por la conversión de
   ejes. La comparación de la caja reimportada contra la construida verifica que
   la nariz siga en +X. Unreal es de mano izquierda e invierte Y (como con la sala), pero la nariz
   sigue en +X.
4. **Color en modo `LINEAR`.** Los números que escribe el script en `Col` son los
   del archivo. Con `SRGB` (el valor por defecto de Blender) el exportador los
   convertiría y el alfa no. Cómo interpreta Unreal esos números al importar
   (crudos o con conversión sRGB) **no está verificado** (el servidor MCP de
   Unreal estaba caído): los valores se eligieron como colores "de pantalla".
5. **La resolución del patrón la da la densidad de vértices.** Las rosetas del
   jaguar miden unos 0,5 m (celdas de Voronoi de 0,85 m) porque el cuerpo tiene
   un vértice cada 0,07 m a lo largo y cada 0,13 m alrededor. Un patrón más fino
   sale como ruido. El detalle fino va por UV en el shader. Los puntos
   bioluminiscentes se ven como cuadros por lo mismo: es esperado.
6. **Un solo barrido para cuerpo y cabeza.** Con la cabeza como pieza aparte
   (`kronos_jaguar`, `kyhy_inia`) quedaba un escalón visible en la junta. Ahora
   cuerpo y cráneo son un solo barrido; la mandíbula sí es pieza aparte.
7. **Curvas de posición con valores negativos.** La función `perfil()` recorta a
   cero (sirve para radios). Para la altura de un eje se pasa `negativos=True`.
   Sin eso, la mandíbula de `kronos_jaguar` quedaba metida dentro del cráneo.
8. **Mallas abiertas o mal orientadas.** El script cuenta las aristas
   dirigidas de la malla y falla si hay una abierta o repetida.
9. **Etiquetas de la hoja.** La hoja escala cada objeto para caber en su celda:
   el tamaño real va en la etiqueta, no en la imagen.
10. **Sin confirmar todavía.** Ningún FBX se importó aún en Unreal 5.8:
    interpretación del alfa y del color, colisión, y si el nombre del slot
    (`M_Criatura`, ...) llega bien. Los datos de fósiles marcados "sin
    confirmar" arriba no se verificaron contra una fuente.
