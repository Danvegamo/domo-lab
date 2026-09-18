# Domos de Colombia (planetarios y cines domo)

Investigación web de partida sobre las salas de domo (planetarios y cines domo) que existen o están en construcción en Colombia, hecha para alimentar el proyecto `Domo_VR_Unreal`. Los datos numéricos que no tienen fuente confiable quedan como `null` en el JSON y están listados en el campo `pendiente` de cada sala. **Nada de esto reemplaza una medición en sitio.**

Fuente de datos completa (estructurada, para código/scripts): [`domos_colombia.json`](./domos_colombia.json).

Fecha de esta investigación: 17 de septiembre de 2026.

## Tabla resumen

| Sala | Ciudad | Operador | Diámetro (m) | Inclinación (°) | FOV vertical (°) | Aforo | Proyección | Año | Señal en vivo |
|---|---|---|---|---|---|---|---|---|---|
| Planetario de Bogotá | Bogotá | Idartes | 23 | ? | ? | 375 | Digistar 7 + 2× Christie Griffyn 4K32-RGB, 4K | 1969 / renov. 2021 | Sí (Domo Vivo) |
| Planetario de Medellín "Jesús Emilio Ramírez" | Medellín | Parque Explora | 15 | 27 | 160 | 110 | Sky-Skan Definiti (Uniview), 4K | 1984 / renov. 2004-2012 | ? |
| Cine Domo de Maloka | Bogotá | Corporación Maloka | 22 | ? | 180 | 314 | 5 proyectores 4K, 30.000 lúmenes | fin. de los 90 / renov. 2017-2024 | ? |
| Planetario Combarranquilla | Barranquilla | Combarranquilla | ? | ? | ? | ? | Digitarium Zeta (sin confirmar en cuál sala) | 1995 | ? |
| MIMAS (domo móvil Combarranquilla) | Barranquilla (itinerante) | Combarranquilla | 5 | ? | ? | ? | digital, marca sin confirmar | 2025 | ? |
| Planetario del Centro de Ciencia, Arte y Tecnología (San Fernando) | Cali | U. Antonio José Camacho | 15 | ? | ? | 120 | 5 proyectores láser 4K | 2024/2025 | ? |
| Planetario de EMAVI | Cali | EMAVI / FAC | 8 | ? | ? | 60 | proyector óptico-mecánico Zeiss (1967) | 1967/1972 | ? |
| Planetario y Observatorio UTP | Pereira | Universidad Tecnológica de Pereira | ? | ? | ? | 76 | fulldome, marca sin confirmar | ~1988 (sin confirmar) | ? |
| Planetario del Centro de Ciencias U. de Nariño | Pasto | Universidad de Nariño | ? | ? | ? | ? | sin definir | EN CONSTRUCCIÓN | ? |
| Planetario Móvil OAM (Samoga) | Manizales | U. Nacional sede Manizales | 4,8 | ? | ? | 25 | video, marca sin confirmar | ? | ? |

`?` en la tabla significa dato sin fuente confiable (`null` en el JSON); ver el campo `pendiente` de cada sala para el detalle exacto de qué falta.

## Fichas por sala

### Planetario de Bogotá
- Cúpula de 23 m, aforo reportado de 375 personas (una fuente dice 376).
- Sistema de proyección Digistar 7 (Evans & Sutherland) con dos proyectores láser Christie Griffyn 4K32-RGB de 34.000 lúmenes cada uno, resolución 4K nativa. Reemplazó en 2021 un proyector óptico-mecánico Zeiss de 52 años.
- Pantalla Nanoseam (sin costuras visibles) de 420 paneles.
- Tiene un programa "Domo Vivo" con conciertos y shows en vivo en formato fulldome 4K, lo que confirma capacidad de señal en vivo (protocolo exacto sin publicar).
- Desde 2025 Idartes anunció una transformación del domo para subir el aforo a 700 personas y dejar el esquema circular tradicional de butacas; hay que verificar en qué quedó esa obra.
- Fuentes: [Historia — Planetario de Bogotá](https://planetariodebogota.gov.co/historia), [Digital AV Magazine, renovación Christie 2021](https://www.digitalavmagazine.com/en/2021/12/07/el-planetario-de-bogota-renueva-su-sistema-de-proyeccion-con-christie/), [Idartes, inauguración nuevo sistema](https://www.idartes.gov.co/es/noticias/el-planetario-de-bogota-inaugura-su-nuevo-sistema-de-proyeccion), [Idartes, transformación del domo](https://www.idartes.gov.co/es/noticias/el-planetario-de-bogota-transforma-su-domo), [Pulzo, 2026](https://www.pulzo.com/nacion/planetario-de-bogota-ciencia-cine-y-astronomia-hasta-2026-con-experiencia-sobre-materia-oscura-PP5128535A).

### Planetario de Medellín "Jesús Emilio Ramírez" (Parque Explora)
- Cúpula de 15 m de diámetro, inclinada 27°, en paneles de aluminio microperforado.
- Aforo de 110 personas por función.
- Sistema Sky-Skan Definiti sobre software Uniview, 4K, sonido 7.1.
- Abrió en 1984; las fuentes no coinciden si la renovación digital fue en 2004 o en 2012.
- Tiene además un domo móvil itinerante (unidad separada, sin sala fija) para experiencias fuera de sede.
- Fuentes: [Wikipedia, Planetario de Medellín](https://es.wikipedia.org/wiki/Planetario_de_Medell%C3%ADn), [sitio oficial, domo planetario](https://www.planetariomedellin.org/visitanos/domo-planetario), [El Colombiano, domo móvil](https://www.elcolombiano.com/tecnologia/ciencia/planetario-medellin-nuevo-domo-movil-en-el-tesoro-CD34047401).

### Cine Domo de Maloka
- Cúpula/pantalla de 22 m de diámetro, 16 m de altura, pantalla curva de 180° (fov vertical confirmado).
- Aforo de 314 personas (una fuente de 2017 dice 309; se usó 314 por ser el dato más reciente, de la reapertura de junio de 2024).
- 5 proyectores de alta definición, 30.000 lúmenes, resolución reportada como 4K en 2024, aunque una renovación de 2017 hablaba de proyectores Christie Mirage 304K y 8K; no se pudo resolver la contradicción con fuentes abiertas.
- Es el primer teatro de formato gigante de Suramérica (tecnología Iwerks original).
- Fuentes: [Cine Domo — Maloka](https://maloka.org/cine-domo/), [Regresa el Cine Domo, 2024](https://maloka.org/noticias/regresa-el-cine-domo-de-maloka/), [AVI Latinoamérica, renovación 8K 2017](https://www.avilatinoamerica.com/201704114557/noticias/empresas/maloka-renovo-domo-con-3d-en-resolucion-8k.html), [El Tiempo, reinauguración](https://www.eltiempo.com/bogota/maloka-reinaugura-su-domo-39920).

### Planetario Combarranquilla
- Abrió el 25 de mayo de 1995 (primera función pública el 7 de junio de ese año), con ampliación de sala museográfica interactiva en 2014.
- No se encontraron especificaciones técnicas públicas confiables del domo fijo (diámetro, aforo, inclinación, pantalla). Se menciona un proyector estelar digital Digitarium Zeta, pero no queda claro si corresponde a la sala principal o a otra sala.
- Cuenta con un domo móvil inflable propio llamado MIMAS (ficha separada abajo).
- Fuentes: [Tu Guía Combarranquilla, 30 años](https://tuguia.combarranquilla.co/Revista/?p=6444), [Combarranquilla, Ciencia y Cultura](https://www.combarranquilla.co/ciencia-y-cultura/).

### MIMAS (domo móvil de Combarranquilla)
- Domo inflable portátil de 5 m de diámetro, itinerante por la región Caribe, lanzado en 2025.
- No es sala fija; no se encontraron datos de aforo ni de marca de proyección.
- Fuentes: [Rueda la Economía, 2025](https://www.ruedalaeconomia.com/2025/06/14/desde-el-planetario-combarranquilla-mimas-el-domo-inflable-para-explorar-el-universo/), [Tu Guía Combarranquilla, MIMAS](https://tuguia.combarranquilla.co/Revista/?p=6654).

### Planetario del Centro de Ciencia, Arte y Tecnología (Parque Tecnológico de Innovación San Fernando, Cali)
- Domo de 15 m, aforo de 120 personas, 5 proyectores láser 4K con sonido envolvente (marca sin confirmar).
- Abrió para colegios en octubre de 2024 y al público general en abril de 2025.
- Operado inicialmente por la Universidad Antonio José Camacho, con planes de pasar a un ente mixto público-privado.
- Es un proyecto distinto y mucho más nuevo que el histórico Planetario de EMAVI (ver siguiente ficha); ambos están en Cali pero no son la misma sala.
- Fuentes: [El País, fotos del centro](https://www.elpais.com.co/cali/en-imagenes-los-detalles-ineditos-de-como-es-el-centro-de-ciencia-arte-y-tecnologia-inaugurado-en-cali-0212.html), [Alcaldía de Cali, llegada del domo](https://www.cali.gov.co/infraestructura/publicaciones/179992/llego-el-domo-para-el-planetario-del-parque-tecnologico-de-innovacion-san-fernando/), [Alcaldía de Cali, Petronio bajo el planetario](https://www.cali.gov.co/boletines/publicaciones/188383/por-primera-vez-en-cali-petronio-se-gozara-bajo-un-planetario-en-cali/).

### Planetario de EMAVI (Escuela Militar de Aviación "Marco Fidel Suárez", Cali)
- Considerado el primer planetario de Colombia: proyector óptico-mecánico Carl Zeiss adquirido en 1967, abierto al público general en octubre de 1972.
- Cúpula de 8 m de diámetro, aforo máximo de 60 personas por función.
- Declarado Bien de Interés Cultural por el Concejo de Cali.
- Al estar dentro de una instalación militar, no quedó claro en fuentes abiertas si sigue programando funciones públicas regulares; se recomienda confirmar directamente con EMAVI.
- Fuentes: [EMAVI, patrimonio arquitectónico](https://www.emavi.edu.co/es/noticias/el-planetario-de-emavi-patrimonio-arquitectonico-y-urbanistico-de-cali), [Fuerza Aeroespacial Colombiana](https://www.fac.mil.co/es/noticias/primer-planetario-de-colombia-en-la-escuela-militar-de-aviacion), [Colombia.com](https://www.colombia.com/turismo/sitios-turisticos/cali/atractivos-turisticos/sdi212/53289/el-planetario).

### Planetario y Observatorio Astronómico UTP (Pereira)
- Aforo de 76 personas; diámetro de cúpula, inclinación y marca de proyección sin confirmar en fuentes públicas.
- Ofrece experiencias fulldome (ej. "Colombia Tierra de Gigantes") y visita al observatorio del grupo Alfa Orión.
- Una fuente de 2008 dice que el planetario llevaba entonces 20 años, lo que ubicaría la apertura hacia 1988, sin confirmar.
- Fuentes: [Comunicaciones UTP, agosto](https://comunicaciones.utp.edu.co/68160/vicerrectorias/vicerrectorias-vicerrectorias-3/el-planetario-de-la-universidad-tecnologica-de-pereira-presenta-pereira-bajo-las-estrellas-en-agosto/), [Gonzalo Duque, 2008](https://godues.wordpress.com/2008/02/29/la-universidad-tecnologica-de-pereira-y-su-planetario-u-t-p-ed-rac-457/), [Planetario UTP, Parque de Ciencia](https://planetario.utp.edu.co/parque-de-ciencia/).

### Planetario del Centro de Ciencias de la Universidad de Nariño (Pasto)
- **Todavía no está abierto al público.** Es un planetario digital dentro del Centro de Ciencias de la Universidad de Nariño (6.403 m², junto a un telescopio de 1 m de apertura), en construcción.
- Según fuentes de 2025, se esperaba terminar el edificio en año y medio, con 2027 como el año en que empezaría el equipamiento tecnológico y la curaduría de contenidos (donde entraría el domo).
- No tiene todavía diámetro, aforo ni sistema de proyección definidos en fuentes públicas.
- Fuentes: [Impacto TIC](https://impactotic.co/ciencia/centro-de-ciencias-de-la-universidad-de-narino/), [Diario del Sur](https://www.diariodelsur.com.co/la-universidad-de-narino-arranca-la-construccion-del-centro-de-ciencias/), [Universidad de Nariño](https://www.udenar.edu.co/centro-de-ciencias-universidad-de-narino/).

### Planetario Móvil OAM (Observatorio Astronómico de Manizales / Museo Samoga, Universidad Nacional sede Manizales)
- Domo hemisférico portátil e inflable, oscuro, de 3,2 m de alto por 4,8 m de diámetro, aforo de 25 personas.
- No es sala fija: según las fuentes consultadas, Manizales no tiene un planetario de domo fijo construido; un planetario fijo en Samoga aparece solo mencionado como proyecto, sin evidencia de haberse ejecutado.
- Requiere un espacio cubierto de 3,5 m de alto por 6 m por 7 m para instalarse.
- Fuentes: [OAM, planetario móvil](https://oam.manizales.unal.edu.co/planetario-movil/planetario-movil/), [Museo Samoga](http://samoga.manizales.unal.edu.co/).

## Salas descartadas o sin confirmar como reales

- **"Planetario de Cali" genérico**: el nombre puede confundirse con dos salas distintas y reales que sí se documentaron aquí: el histórico Planetario de EMAVI (1967/1972, dentro de la Escuela Militar de Aviación) y el nuevo planetario del Centro de Ciencia, Arte y Tecnología en el Parque Tecnológico San Fernando (2024/2025). No hay una tercera sala separada con ese nombre genérico confirmada.
- **Domo Digital del Museo de Ciencias de la Universidad Nacional (sede Bogotá)**: no se encontró evidencia de que exista una sala de domo fija con ese nombre en la sede Bogotá de la Universidad Nacional; toda la evidencia encontrada sobre "domo" y "Universidad Nacional" apunta al planetario móvil OAM de la sede Manizales (incluido arriba). Queda como no confirmado; si existe, falta encontrar la fuente.
- **Planetario de Manizales (sala fija)**: no se encontró evidencia de que exista, más allá del planetario móvil OAM y de una mención a un planetario fijo "proyectado" para el Museo Samoga que no se pudo confirmar como construido.

## Cómo corregir o agregar una sala

Este documento y el archivo [`domos_colombia.json`](./domos_colombia.json) están pensados para corregirse por pull request, con estas reglas simples:

1. **Edita el JSON**, no solo esta tabla. La tabla y las fichas de este Markdown deben quedar consistentes con `domos_colombia.json`, que es la fuente de verdad para cualquier script o modelo 3D que consuma estos datos.
2. **Un PR por sala.** Si vas a corregir o agregar datos de una sala, hazlo en un pull request separado del resto, para que sea fácil de revisar.
3. **Todo dato numérico necesita fuente o una nota explícita de medida en sala.** Si agregas o cambias un campo como `diametro_m`, `inclinacion_deg`, `fov_vertical_deg` o `aforo`:
   - agrega la URL de la fuente en la lista `fuentes` de esa sala, o
   - si lo mediste tú mismo en el sitio, dilo explícitamente en `notas` (por ejemplo: "diámetro medido en sitio el 2026-10-01 con cinta métrica, no hay fuente pública") y marca `verificado_en_sala: true`.
   - Nunca dejes un número sin fuente ni nota: si no tienes ninguna de las dos, dejá el campo en `null` y agrégalo a la lista `pendiente`.
4. **Quita el campo de `pendiente`** cuando ya tenga fuente o verificación en sala.
5. **Valida el JSON antes de mandar el PR:**
   ```bash
   python -m json.tool 06_Modelos/domos_colombia.json
   ```
   Si este comando falla, el PR no se puede aceptar.
6. Si una sala cerró, cambió de operador, o descubres que una sala listada aquí en realidad no existe (como pasó con "Planetario de Cali" genérico), dilo en `notas` en vez de borrar la entrada sin explicación, para que quede el rastro de la corrección.
