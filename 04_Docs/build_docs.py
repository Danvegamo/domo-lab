#!/usr/bin/env python3
"""Genera docs/index.html a partir de los .md del proyecto domo-lab.

Adaptado del generador de Domo_Pantallas (04_Docs/build_docs.py de ese otro
proyecto): se reutiliza tal cual su render de Markdown (titulos, listas,
tablas, citas, bloques de codigo con boton de copiar) y su plantilla HTML de
una sola pagina con barra lateral y buscador. Lo que cambia frente a aquel
script:

  - Lee otras paginas (ver PAGES) y no falla si 05_Modelos_de_sala.md no
    existe todavia: la salta con un aviso.
  - Sabe renderizar imagenes (`![alt](ruta)`), algo que el generador
    original no necesitaba. Cada imagen referenciada se copia a docs/img/,
    convertida a JPG de 400 KB o menos con Pillow si el archivo pesa mas que
    eso, o copiada tal cual si ya es un PNG liviano.
  - Sabe renderizar formulas en LaTeX (`$$...$$` en bloque, `$...$` en
    linea): como no hay CDN no se intenta KaTeX, se muestran como bloques o
    tramos de codigo monoespaciado con la clase "formula", legibles tal cual.
  - Resuelve los enlaces entre documentos del propio repo (por ejemplo
    "02_Sala_Unreal.md#seccion" o "../06_Modelos/Domos_de_Colombia.md") como
    anclas internas de esta misma pagina. Si el destino no quedo incluido en
    PAGES (caso de 05_Modelos_de_sala.md si no existe), el enlace cae a la
    version del archivo en GitHub para no quedar roto.
  - Agrega en la portada un enlace al estudio interactivo de pantallas
    (se copia tambien a docs/estudio_pantallas.html para que GitHub Pages lo
    sirva) y un enlace al repositorio.
  - Al terminar, verifica la propia pagina generada: cuenta imagenes rotas,
    anclas internas rotas y que las paginas esperadas esten presentes.

Uso (requiere Pillow para las imagenes; instalar con `pip install pillow`
si hace falta):

    python 04_Docs/build_docs.py

Se puede correr desde cualquier carpeta: las rutas se calculan a partir de
la ubicacion de este script. Publicar con GitHub Pages apuntando a la
carpeta docs/ de la rama principal. Hay que volver a correr el script cada
vez que cambie un .md o una imagen referenciada.
"""

from __future__ import annotations

import html
import io
import json
import re
from html.parser import HTMLParser
from pathlib import Path

try:
    from PIL import Image
except ImportError:  # pragma: no cover - aviso claro si falta la dependencia
    Image = None

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "04_Docs"
OUT_DIR = ROOT / "docs"
OUT = OUT_DIR / "index.html"
IMG_DIR = OUT_DIR / "img"
IMG_MAX_BYTES = 400 * 1024

REPO_URL = "https://github.com/Danvegamo/domo-lab"
ESTUDIO_SRC = ROOT / "00_TouchDesigner" / "video_dome" / "web" / "estudio_pantallas.html"
ESTUDIO_OUT_NAME = "estudio_pantallas.html"

# Orden de lectura: de la vision general a la bitacora cronologica.
# (ruta, titulo en la barra lateral, bajada de una linea)
PAGES = [
    (ROOT / "README.md", "Guia del proyecto",
     "Vision general, el proceso en cuatro pasos y como poner todo en marcha"),
    (DOCS / "01_Proceso_y_matematica.md", "El proceso y la matematica",
     "Que es esto, la matematica del domo paso a paso y las decisiones ya medidas"),
    (DOCS / "04_Senal_TouchDesigner.md", "La senal en TouchDesigner",
     "Como se arma la red que manda video 360, domemaster o pantallas planas a la cupula"),
    (DOCS / "02_Sala_Unreal.md", "La sala en Unreal",
     "La sala VR en Unreal Engine 5.8: geometria, materiales, VR y como regenerarla"),
    (DOCS / "03_Puente_Spout.md", "El puente Spout",
     "Como TouchDesigner le manda la senal a la cupula de Unreal por Spout"),
    (DOCS / "05_Modelos_de_sala.md", "Otros modelos de sala",
     "Domo de 90 y 45 grados"),
    (ROOT / "06_Modelos" / "Domos_de_Colombia.md", "Domos de Colombia",
     "Fichas de planetarios y cines domo reales, con sus datos y fuentes"),
    (DOCS / "Unreal_sala_domo.md", "Bitacora: sala de domo en Unreal",
     "El registro cronologico y completo de como se construyo la sala (bitacora larga)"),
]

CALLOUTS = {
    "BIEN": ("ok", "Bien"),
    "OJO": ("warn", "Ojo"),
    "AVISO": ("danger", "Aviso"),
}


# --------------------------------------------------------------------------
# Slugs: uno "bonito" en ascii para las anclas de la pagina, y uno que imita
# el algoritmo de GitHub (conserva acentos) para poder casar los enlaces que
# los .md ya traen escritos como "archivo.md#seccion-con-acentos".
# --------------------------------------------------------------------------

def slugify(text: str) -> str:
    text = re.sub(r"[`*_]", "", text).strip().lower()
    text = (text.replace("á", "a").replace("é", "e").replace("í", "i")
                .replace("ó", "o").replace("ú", "u").replace("ñ", "n"))
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text or "seccion"


def github_slug(text: str) -> str:
    text = re.sub(r"[`*_]", "", text).strip().lower()
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    text = re.sub(r"\s+", "-", text).strip("-")
    return text


# --------------------------------------------------------------------------
# Imagenes: cada referencia relativa de un .md se copia a docs/img/, con
# conversion a JPG <= 400 KB si el original pesa mas que eso.
# --------------------------------------------------------------------------

def compress_to_jpeg(src: Path, dst: Path, limit: int) -> None:
    if Image is None:
        raise RuntimeError(
            "Pillow no esta instalado (pip install pillow); hace falta para "
            "convertir %s a JPG" % src)
    img = Image.open(src)
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[-1])
        img = bg
    else:
        img = img.convert("RGB")

    quality = 88
    max_w = 1920
    data = b""
    while True:
        frame = img
        if frame.width > max_w:
            ratio = max_w / frame.width
            frame = frame.resize((max_w, max(1, int(frame.height * ratio))), Image.LANCZOS)
        buf = io.BytesIO()
        frame.save(buf, "JPEG", quality=quality, optimize=True)
        data = buf.getvalue()
        if len(data) <= limit or (quality <= 35 and max_w <= 640):
            break
        if quality > 35:
            quality -= 8
        else:
            max_w = int(max_w * 0.75)
    dst.write_bytes(data)


def process_image(src: Path, cache: dict) -> str | None:
    """Copia/convierte una imagen a docs/img/ y devuelve su nombre de archivo."""
    if src in cache:
        return cache[src]
    if not src.exists():
        cache[src] = None
        return None
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    data = src.read_bytes()
    if len(data) <= IMG_MAX_BYTES:
        out_name = src.name
        (IMG_DIR / out_name).write_bytes(data)
    else:
        out_name = src.stem + ".jpg"
        compress_to_jpeg(src, IMG_DIR / out_name, IMG_MAX_BYTES)
    cache[src] = out_name
    return out_name


IMG_MD_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")


def rewrite_images(md: str, current_dir: Path, cache: dict, doc_label: str) -> str:
    def repl(m: re.Match) -> str:
        alt, src = m.group(1), m.group(2)
        if src.startswith(("http://", "https://", "data:")):
            return m.group(0)
        abs_src = (current_dir / src).resolve()
        out_name = process_image(abs_src, cache)
        if out_name is None:
            print("  [AVISO] %s: imagen no encontrada: %s" % (doc_label, src))
            return m.group(0)
        return "![%s](img/%s)" % (alt, out_name)

    return IMG_MD_RE.sub(repl, md)


# --------------------------------------------------------------------------
# Enlaces entre documentos: "archivo.md" o "archivo.md#seccion" (relativos al
# .md que los contiene) se resuelven contra el mapa de paginas incluidas.
# --------------------------------------------------------------------------

MD_LINK_RE = re.compile(r"(?<!!)\[([^\]]+)\]\(([^)]+)\)")


def resolve_href(href: str, current_dir: Path, path_to_docid: dict,
                  headings_by_docid: dict) -> str:
    if href.startswith(("http://", "https://", "mailto:", "#")):
        return href
    base, frag = (href.split("#", 1) + [None])[:2] if "#" in href else (href, None)
    if not base:
        return href
    if base.replace("\\", "/").rstrip("/").endswith(ESTUDIO_OUT_NAME):
        return ESTUDIO_OUT_NAME + (("#" + frag) if frag else "")
    try:
        abs_path = (current_dir / base).resolve()
    except OSError:
        return href
    doc_id = path_to_docid.get(abs_path)
    if doc_id:
        if frag:
            frag_low = frag.lower()
            for gslug, anchor in headings_by_docid.get(doc_id, []):
                if gslug == frag_low:
                    return "#" + anchor
        return "#" + doc_id
    # No es una de las paginas incluidas (por ejemplo 05_Modelos_de_sala.md
    # si todavia no existe): que el enlace apunte al archivo en GitHub, para
    # no dejarlo roto en la pagina publicada.
    try:
        rel = abs_path.relative_to(ROOT).as_posix()
    except ValueError:
        return href
    return "%s/blob/main/%s" % (REPO_URL, rel)


def rewrite_links(md: str, current_dir: Path, path_to_docid: dict,
                   headings_by_docid: dict) -> str:
    def repl(m: re.Match) -> str:
        text, href = m.group(1), m.group(2)
        return "[%s](%s)" % (text, resolve_href(href, current_dir, path_to_docid, headings_by_docid))

    return MD_LINK_RE.sub(repl, md)


# --------------------------------------------------------------------------
# Markdown -> HTML (subconjunto suficiente para estos documentos)
# --------------------------------------------------------------------------

def inline(text: str) -> str:
    """Formato de linea: imagenes, formulas en linea, codigo, negrita,
    cursiva y enlaces.

    Imagenes, formulas y codigo se apartan con marcadores antes de escapar y
    de aplicar negrita/cursiva, para que su contenido nunca se interprete
    como formato ni quede escapado dos veces.
    """
    spans: list[str] = []

    def stash(built: str) -> str:
        spans.append(built)
        return "\x00%d\x00" % (len(spans) - 1)

    def stash_img(m: re.Match) -> str:
        alt, src = m.group(1), m.group(2)
        if src.startswith(("http://", "https://", "data:")):
            return stash('<img src="%s" alt="%s" loading="lazy">' % (html.escape(src), html.escape(alt)))
        return stash('<img src="%s" alt="%s" loading="lazy">' % (html.escape(src), html.escape(alt)))

    def stash_code(m: re.Match) -> str:
        return stash("<code>%s</code>" % html.escape(m.group(1)))

    def stash_formula(m: re.Match) -> str:
        return stash('<code class="formula-inline">%s</code>' % html.escape(m.group(1)))

    chunk = IMG_MD_RE.sub(stash_img, text)
    chunk = re.sub(r"`([^`]+)`", stash_code, chunk)
    chunk = re.sub(r"(?<!\$)\$([^$\n]+)\$(?!\$)", stash_formula, chunk)
    chunk = html.escape(chunk)
    chunk = chunk.replace(r"\|", "|")
    chunk = re.sub(r"\[([^\]]+)\]\(([^)]+)\)",
                   r'<a href="\2" target="_blank" rel="noopener">\1</a>', chunk)
    chunk = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", chunk, flags=re.S)
    chunk = re.sub(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])", r"<em>\1</em>", chunk)
    return re.sub(r"\x00(\d+)\x00", lambda m: spans[int(m.group(1))], chunk)


def render_table(rows: list[str]) -> str:
    cells = [[c.strip() for c in re.split(r"(?<!\\)\|", r.strip().strip("|"))] for r in rows]
    head, body = cells[0], cells[2:]  # cells[1] es la fila de guiones
    parts = ['<div class="tablewrap"><table><thead><tr>']
    parts += ["<th>%s</th>" % inline(c) for c in head]
    parts.append("</tr></thead><tbody>")
    for row in body:
        parts.append("<tr>" + "".join("<td>%s</td>" % inline(c) for c in row) + "</tr>")
    parts.append("</tbody></table></div>")
    return "".join(parts)


def render_quote(lines: list[str]) -> str:
    text = " ".join(l.lstrip("> ").rstrip() for l in lines).strip()
    kind, label = "note", "Nota"
    m = re.match(r"\*\*\[([A-Z]+)\]\*\*\s*(.*)", text, re.S)
    if m and m.group(1) in CALLOUTS:
        kind, label = CALLOUTS[m.group(1)]
        text = m.group(2)
    return ('<div class="callout %s"><span class="tag">%s</span><div>%s</div></div>'
            % (kind, html.escape(label), inline(text)))


IMG_LINE_RE = re.compile(r"^!\[([^\]]*)\]\(([^)]+)\)$")


def render_imgset(stripped_lines: list[str]) -> str:
    """Una o varias imagenes que forman su propio parrafo: figura con pie."""
    figs = []
    for s in stripped_lines:
        m = IMG_LINE_RE.match(s)
        alt, src = m.group(1), m.group(2)
        caption = "<figcaption>%s</figcaption>" % inline(alt) if alt else ""
        figs.append('<figure><img src="%s" alt="%s" loading="lazy">%s</figure>'
                    % (html.escape(src), html.escape(alt), caption))
    cls = "imgset" if len(figs) > 1 else "imgset one"
    return '<div class="%s">%s</div>' % (cls, "".join(figs))


def render_markdown(md: str, doc_id: str, headings: list[tuple[str, str, int]]) -> str:
    lines = md.split("\n")
    out: list[str] = []
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]

        # Bloque de formula LaTeX ($$ ... $$)
        if line.strip() == "$$":
            i += 1
            buf = []
            while i < n and lines[i].strip() != "$$":
                buf.append(lines[i])
                i += 1
            i += 1  # cierre $$
            formula = html.escape("\n".join(buf).strip())
            out.append('<div class="codeblock formula"><button class="copy" type="button">copiar</button>'
                       '<pre><code class="lang-formula">%s</code></pre></div>' % formula)
            continue

        # Bloque de codigo
        if line.startswith("```"):
            lang = line[3:].strip()
            i += 1
            buf = []
            while i < n and not lines[i].startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1
            code = html.escape("\n".join(buf))
            out.append('<div class="codeblock"><button class="copy" type="button">copiar</button>'
                       '<pre><code class="lang-%s">%s</code></pre></div>' % (html.escape(lang or "txt"), code))
            continue

        # Titulos
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            level = len(m.group(1))
            title = m.group(2).strip()
            anchor = "%s--%s" % (doc_id, slugify(title))
            if level in (2, 3):
                headings.append((anchor, re.sub(r"[`*]", "", title), level))
            out.append('<h%d id="%s"><a class="anchor" href="#%s">#</a>%s</h%d>'
                       % (level + 1, anchor, anchor, inline(title), level + 1))
            i += 1
            continue

        # Separador
        if re.match(r"^\s*---+\s*$", line):
            out.append("<hr>")
            i += 1
            continue

        # Tabla
        if line.lstrip().startswith("|") and i + 1 < n and re.match(r"^\s*\|[\s:|-]+\|\s*$", lines[i + 1]):
            buf = []
            while i < n and lines[i].lstrip().startswith("|"):
                buf.append(lines[i])
                i += 1
            out.append(render_table(buf))
            continue

        # Cita / nota
        if line.startswith(">"):
            buf = []
            while i < n and lines[i].startswith(">"):
                buf.append(lines[i])
                i += 1
            out.append(render_quote(buf))
            continue

        # Lista con vinetas
        if re.match(r"^\s*[-*]\s+", line):
            items: list[str] = []
            while i < n and (re.match(r"^\s*[-*]\s+", lines[i]) or (items and lines[i].startswith("  ") and lines[i].strip())):
                if re.match(r"^\s*[-*]\s+", lines[i]):
                    items.append(re.sub(r"^\s*[-*]\s+", "", lines[i]).rstrip())
                else:
                    items[-1] += " " + lines[i].strip()
                i += 1
            out.append("<ul>" + "".join("<li>%s</li>" % inline(x) for x in items) + "</ul>")
            continue

        # Lista numerada
        if re.match(r"^\s*\d+\.\s+", line):
            first_num = int(re.match(r"^\s*(\d+)\.\s+", line).group(1))
            items = []
            while i < n and (re.match(r"^\s*\d+\.\s+", lines[i]) or (items and lines[i].startswith("  ") and lines[i].strip())):
                if re.match(r"^\s*\d+\.\s+", lines[i]):
                    items.append(re.sub(r"^\s*\d+\.\s+", "", lines[i]).rstrip())
                else:
                    items[-1] += " " + lines[i].strip()
                i += 1
            out.append('<ol start="%d">' % first_num
                       + "".join("<li>%s</li>" % inline(x) for x in items) + "</ol>")
            continue

        # Parrafo (o un grupo de imagenes que forman su propio parrafo)
        if line.strip():
            buf = [line]
            i += 1
            while i < n and lines[i].strip() and not re.match(r"^(#{1,6}\s|```|\$\$\s*$|>|\s*[-*]\s|\s*\d+\.\s|\s*\|)", lines[i]):
                buf.append(lines[i])
                i += 1
            stripped_lines = [b.strip() for b in buf]
            if all(IMG_LINE_RE.match(s) for s in stripped_lines):
                out.append(render_imgset(stripped_lines))
                continue
            para = " ".join(x.strip() for x in buf)
            if re.match(r"^\*[^*].*\*$", para):  # linea entera en cursiva = subtitulo
                out.append('<p class="lead">%s</p>' % inline(para.strip("*")))
            else:
                out.append("<p>%s</p>" % inline(para))
            continue

        i += 1

    return "\n".join(out)


# --------------------------------------------------------------------------
# Plantilla
# --------------------------------------------------------------------------

CSS = """
*,*::before,*::after{box-sizing:border-box}
:root{
  --bg:#0e1116; --bg-soft:#161b22; --bg-code:#0a0d12; --line:#242c38;
  --fg:#dfe5ec; --fg-dim:#96a2b3; --accent:#5ec8f2; --accent-soft:#12303d;
  --ok:#4ec9a0; --warn:#e5b567; --danger:#ef6f6c;
  --mono:"JetBrains Mono",Consolas,"Cascadia Mono",monospace;
  --sans:"Inter",-apple-system,Segoe UI,system-ui,sans-serif;
}
html[data-theme=light]{
  --bg:#fbfcfd; --bg-soft:#f1f4f8; --bg-code:#f5f7fa; --line:#dde3ea;
  --fg:#1b2430; --fg-dim:#5b6878; --accent:#0c6f9c; --accent-soft:#e2f1f9;
}
html{scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.65 var(--sans);
  display:grid;grid-template-columns:290px 1fr}
a{color:var(--accent)}
/* ---- barra lateral ---- */
aside{position:sticky;top:0;height:100vh;overflow-y:auto;background:var(--bg-soft);
  border-right:1px solid var(--line);padding:20px 0 60px}
aside .brand{padding:0 20px 14px;border-bottom:1px solid var(--line);margin-bottom:14px}
aside .brand b{display:block;font-size:15px;letter-spacing:.02em}
aside .brand span{font-size:12px;color:var(--fg-dim)}
#q{width:calc(100% - 40px);margin:0 20px 14px;padding:8px 10px;border-radius:7px;
  border:1px solid var(--line);background:var(--bg);color:var(--fg);font:13px var(--sans)}
#q:focus{outline:none;border-color:var(--accent)}
nav a{display:block;text-decoration:none;color:var(--fg-dim);font-size:13.5px;
  padding:5px 20px 5px 22px;border-left:2px solid transparent}
nav a.doc{color:var(--fg);font-weight:600;font-size:14px;margin-top:14px}
nav a.h3{padding-left:38px;font-size:12.5px}
nav a:hover{color:var(--accent);background:var(--accent-soft)}
nav a.active{color:var(--accent);border-left-color:var(--accent);background:var(--accent-soft)}
/* ---- contenido ---- */
main{padding:46px 56px 140px;max-width:1000px}
section{scroll-margin-top:20px}
section+section{margin-top:90px;padding-top:44px;border-top:1px solid var(--line)}
.src{font:12px var(--mono);color:var(--fg-dim)}
h2{font-size:30px;line-height:1.25;margin:.2em 0 .5em;letter-spacing:-.01em}
h3{font-size:23px;margin:1.9em 0 .5em;padding-bottom:6px;border-bottom:1px solid var(--line)}
h4{font-size:18px;margin:1.6em 0 .4em}
h5{font-size:15px;margin:1.4em 0 .3em;color:var(--fg-dim);text-transform:uppercase;letter-spacing:.06em}
.anchor{float:left;margin-left:-1.1em;padding-right:.35em;color:var(--line);
  text-decoration:none;opacity:0;transition:opacity .15s}
h3:hover .anchor,h4:hover .anchor{opacity:1}
p.lead{color:var(--fg-dim);font-size:14px}
hr{border:0;border-top:1px solid var(--line);margin:34px 0}
code{font:.88em var(--mono);background:var(--bg-soft);border:1px solid var(--line);
  border-radius:5px;padding:1px 5px}
code.formula-inline{color:var(--accent)}
.codeblock{position:relative;margin:18px 0}
.codeblock pre{margin:0;background:var(--bg-code);border:1px solid var(--line);
  border-radius:9px;padding:16px 18px;overflow-x:auto}
.codeblock code{background:none;border:0;padding:0;font-size:13px;line-height:1.55;white-space:pre}
.codeblock.formula pre{border-left:3px solid var(--accent)}
.codeblock.formula code{font-size:14px;letter-spacing:.01em}
.copy{position:absolute;top:9px;right:9px;background:var(--bg-soft);color:var(--fg-dim);
  border:1px solid var(--line);border-radius:6px;font:11px var(--sans);padding:3px 9px;
  cursor:pointer;opacity:0;transition:opacity .15s}
.codeblock:hover .copy{opacity:1}
.copy:hover{color:var(--accent);border-color:var(--accent)}
.tablewrap{overflow-x:auto;margin:18px 0;border:1px solid var(--line);border-radius:9px}
table{border-collapse:collapse;width:100%;font-size:14px}
th,td{padding:9px 13px;text-align:left;border-bottom:1px solid var(--line);vertical-align:top}
th{background:var(--bg-soft);font-size:12.5px;text-transform:uppercase;letter-spacing:.04em;
  color:var(--fg-dim);white-space:nowrap}
tbody tr:last-child td{border-bottom:0}
tbody tr:hover{background:var(--bg-soft)}
ul,ol{padding-left:22px}
li{margin:.35em 0}
.callout{display:flex;gap:12px;margin:18px 0;padding:13px 16px;border-radius:9px;
  border:1px solid var(--line);border-left:3px solid var(--fg-dim);background:var(--bg-soft)}
.callout .tag{font:11px var(--sans);font-weight:700;text-transform:uppercase;
  letter-spacing:.06em;padding-top:3px;white-space:nowrap}
.callout>div>*:first-child{margin-top:0}
.callout.ok{border-left-color:var(--ok)} .callout.ok .tag{color:var(--ok)}
.callout.warn{border-left-color:var(--warn)} .callout.warn .tag{color:var(--warn)}
.callout.danger{border-left-color:var(--danger)} .callout.danger .tag{color:var(--danger)}
#theme{position:fixed;top:16px;right:20px;z-index:9;background:var(--bg-soft);color:var(--fg-dim);
  border:1px solid var(--line);border-radius:7px;padding:6px 12px;font:12px var(--sans);cursor:pointer}
#theme:hover{color:var(--accent);border-color:var(--accent)}
kbd{font:11px var(--mono);background:var(--bg-soft);border:1px solid var(--line);
  border-bottom-width:2px;border-radius:5px;padding:1px 5px}
/* ---- portada de atajos ---- */
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(215px,1fr));gap:12px;margin:26px 0}
.card{display:block;text-decoration:none;padding:15px 16px;border-radius:11px;
  border:1px solid var(--line);background:var(--bg-soft);transition:border-color .15s,transform .15s}
.card:hover{border-color:var(--accent);transform:translateY(-2px)}
.card b{display:block;color:var(--fg);font-size:15px;margin-bottom:4px}
.card span{color:var(--fg-dim);font-size:12.5px;line-height:1.45}
/* ---- imagenes de los documentos ---- */
img{max-width:100%;height:auto;border-radius:9px;border:1px solid var(--line);display:block}
.imgset{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:14px;margin:18px 0}
.imgset.one{grid-template-columns:1fr;max-width:640px}
.imgset figure{margin:0}
.imgset figcaption{margin-top:6px;font-size:12.5px;color:var(--fg-dim);text-align:center}
/* ---- resultados del buscador ---- */
#results{margin:0 20px 10px;max-height:52vh;overflow-y:auto}
#results:empty{display:none}
#results a{display:block;padding:8px 10px;border-radius:8px;text-decoration:none;
  border:1px solid transparent;border-left:0}
#results a:hover,#results a.sel{background:var(--accent-soft);border-color:var(--line)}
#results b{display:block;color:var(--fg);font-size:13px}
#results i{display:block;color:var(--accent);font-size:10.5px;font-style:normal;
  text-transform:uppercase;letter-spacing:.05em;margin-bottom:2px}
#results em{display:block;color:var(--fg-dim);font-size:12px;font-style:normal;line-height:1.4;
  margin-top:2px;overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}
#results mark{background:var(--accent-soft);color:var(--accent);border-radius:3px;padding:0 1px}
#empty{margin:0 20px 12px;color:var(--fg-dim);font-size:12.5px}
:target{animation:flash 1.4s ease-out}
@keyframes flash{from{background:var(--accent-soft)}to{background:transparent}}
@media print{aside,#theme,.copy,.cards{display:none}body{display:block;background:#fff;color:#000}}
@media (max-width:900px){body{grid-template-columns:1fr}
  aside{position:static;height:auto;border-right:0;border-bottom:1px solid var(--line)}
  main{padding:28px 20px 90px}}
"""

JS = """
document.querySelectorAll('.copy').forEach(b=>b.onclick=()=>{
  navigator.clipboard.writeText(b.parentElement.querySelector('code').innerText);
  b.textContent='copiado'; setTimeout(()=>b.textContent='copiar',1400);
});
const links=[...document.querySelectorAll('nav a')];
const io=new IntersectionObserver(es=>{
  es.forEach(e=>{ if(!e.isIntersecting) return;
    links.forEach(l=>l.classList.toggle('active', l.getAttribute('href')==='#'+e.target.id)); });
},{rootMargin:'-10% 0px -80% 0px'});
document.querySelectorAll('section,h3[id],h4[id]').forEach(el=>io.observe(el));
/* ---- buscador de texto completo ---- */
const q=document.getElementById('q'), box=document.getElementById('results'),
      nav=document.querySelector('nav'), empty=document.getElementById('empty');
const norm=s=>s.toLowerCase().normalize('NFD').replace(/[\\u0300-\\u036f]/g,'');
const IDX=DOCS_INDEX.map(e=>({...e, nt:norm(e.t), nx:norm(e.x), nd:norm(e.d)}));
let sel=-1;

function snippet(text, raw, term){
  const i = text.indexOf(term); if(i<0) return raw.slice(0,140);
  const a = Math.max(0, i-50), b = Math.min(raw.length, i+term.length+90);
  const pre = a>0?'…':'', post = b<raw.length?'…':'';
  const before = raw.slice(a,i), hit = raw.slice(i,i+term.length), after = raw.slice(i+term.length,b);
  const esc = s => s.replace(/[&<>]/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
  return pre+esc(before)+'<mark>'+esc(hit)+'</mark>'+esc(after)+post;
}

function search(){
  const raw=q.value.trim(), t=norm(raw);
  sel=-1;
  if(!t){ box.innerHTML=''; empty.textContent=''; nav.style.display=''; return; }
  nav.style.display='none';
  const hits=[];
  for(const e of IDX){
    let score=0;
    if(e.nt.includes(t)) score+=100;
    if(e.nd.includes(t)) score+=20;
    const at=e.nx.indexOf(t);
    if(at>=0) score+=40-Math.min(30, at/40);
    if(score) hits.push({e, score, at});
  }
  hits.sort((a,b)=>b.score-a.score);
  if(!hits.length){ box.innerHTML=''; empty.textContent='Nada con «'+raw+'».'; return; }
  empty.textContent=hits.length+' resultado'+(hits.length>1?'s':'');
  box.innerHTML=hits.slice(0,25).map(h=>
    '<a href="#'+h.e.a+'"><i>'+h.e.d+'</i><b>'+h.e.t+'</b><em>'+snippet(h.e.nx,h.e.x,t)+'</em></a>'
  ).join('');
}

q.oninput=search;
q.onkeydown=ev=>{
  const opts=[...box.querySelectorAll('a')];
  if(ev.key==='Escape'){ q.value=''; search(); q.blur(); return; }
  if(!opts.length) return;
  if(ev.key==='ArrowDown'||ev.key==='ArrowUp'){
    ev.preventDefault();
    sel=(sel+(ev.key==='ArrowDown'?1:-1)+opts.length)%opts.length;
    opts.forEach((o,i)=>o.classList.toggle('sel',i===sel));
    opts[sel].scrollIntoView({block:'nearest'});
  }
  if(ev.key==='Enter'&&sel>=0){ ev.preventDefault(); opts[sel].click(); }
};
box.onclick=ev=>{ if(ev.target.closest('a')){ q.value=''; search(); } };
document.addEventListener('keydown',ev=>{
  if(ev.target===q) return;
  if(ev.key==='/'||((ev.ctrlKey||ev.metaKey)&&ev.key==='k')){ ev.preventDefault(); q.focus(); q.select(); }
});
const root=document.documentElement, btn=document.getElementById('theme');
const saved=localStorage.getItem('domolab-theme'); if(saved) root.dataset.theme=saved;
const paint=()=>btn.textContent = root.dataset.theme==='light' ? 'modo oscuro' : 'modo claro';
btn.onclick=()=>{ root.dataset.theme = root.dataset.theme==='light' ? 'dark':'light';
  localStorage.setItem('domolab-theme',root.dataset.theme); paint(); };
paint();
"""


def plain(md: str) -> str:
    """Markdown -> texto pelado, para el buscador."""
    md = re.sub(r"```.*?```", " ", md, flags=re.S)
    md = re.sub(r"\$\$.*?\$\$", " ", md, flags=re.S)
    md = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", md)
    md = re.sub(r"[`*_>#|$]", " ", md)
    md = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", md)
    return re.sub(r"\s+", " ", md).strip()


def index_entries(md: str, doc_id: str, doc_title: str) -> list[dict]:
    """Un registro del buscador por cada apartado de nivel 2 o 3."""
    entries: list[dict] = []
    cur = {"a": doc_id, "t": doc_title, "d": doc_title, "x": []}
    for line in md.split("\n"):
        m = re.match(r"^(#{2,3})\s+(.*)$", line)
        if m:
            entries.append(cur)
            title = re.sub(r"[`*]", "", m.group(2).strip())
            cur = {"a": "%s--%s" % (doc_id, slugify(m.group(2))), "t": title,
                   "d": doc_title, "x": []}
        else:
            cur["x"].append(line)
    entries.append(cur)
    out = []
    for e in entries:
        text = plain("\n".join(e["x"]))
        out.append({"a": e["a"], "t": e["t"], "d": e["d"], "x": text[:600]})
    return out


def collect_headings(md: str, doc_id: str) -> list[tuple[str, str]]:
    """(slug estilo GitHub, ancla interna) de cada titulo de nivel 2 o 3."""
    out = []
    for line in md.split("\n"):
        m = re.match(r"^(#{2,3})\s+(.*)$", line)
        if m:
            title = m.group(2).strip()
            out.append((github_slug(title), "%s--%s" % (doc_id, slugify(title))))
    return out


def strip_first_heading(md: str) -> str:
    return re.sub(r"\A#\s+.*\n", "", md, count=1)


def build() -> Path:
    existing_pages = [(p, t, b) for p, t, b in PAGES if p.exists()]
    for p, t, b in PAGES:
        if not p.exists():
            print("  falta %s, lo salto" % p)

    # --- Paso 1: mapa de rutas -> doc_id y titulos de cada apartado, para
    # poder resolver los enlaces entre documentos antes de renderizar nada.
    path_to_docid: dict[Path, str] = {}
    raw_by_docid: dict[str, str] = {}
    headings_by_docid: dict[str, list[tuple[str, str]]] = {}
    for path, title, _ in existing_pages:
        doc_id = slugify(title)
        md = strip_first_heading(path.read_text(encoding="utf-8"))
        path_to_docid[path.resolve()] = doc_id
        raw_by_docid[doc_id] = md
        headings_by_docid[doc_id] = collect_headings(md, doc_id)

    # --- Paso 2: imagenes, enlaces y render de cada pagina.
    img_cache: dict[Path, str | None] = {}
    sections, nav, index = [], [], []

    intro = (
        '<section id="inicio">\n'
        '<h2>domo-lab</h2>\n'
        '<p class="lead">Documentacion completa del proyecto: el proceso, la '
        'matematica, la sala en Unreal, el puente Spout, la senal en '
        'TouchDesigner y las fichas de domos reales. El buscador (tecla '
        '<kbd>/</kbd>) busca dentro del texto, no solo en los titulos.</p>\n'
        '<div class="cards">'
        '<a class="card" href="%s"><b>Estudio interactivo</b>'
        '<span>Probar montajes de pantallas en el navegador, sin TouchDesigner.</span></a>'
        '<a class="card" href="%s" target="_blank" rel="noopener"><b>Repositorio</b>'
        '<span>Codigo y scripts en GitHub: %s</span></a>'
        '</div>\n</section>' % (ESTUDIO_OUT_NAME, REPO_URL, REPO_URL))
    sections.append(intro)
    nav.append('<a class="doc" href="#inicio">Inicio</a>')

    for path, title, blurb in existing_pages:
        doc_id = slugify(title)
        md = rewrite_images(raw_by_docid[doc_id], path.parent, img_cache, title)
        md = rewrite_links(md, path.parent, path_to_docid, headings_by_docid)

        headings: list[tuple[str, str, int]] = []
        body = render_markdown(md, doc_id, headings)
        index.extend(index_entries(md, doc_id, title))

        rel = path.relative_to(ROOT).as_posix()
        sections.append(
            '<section id="%s">\n<p class="src">%s</p>\n<h2>%s</h2>\n<p class="lead">%s</p>\n%s\n</section>'
            % (doc_id, html.escape(rel), html.escape(title), html.escape(blurb), body))

        nav.append('<a class="doc" href="#%s">%s</a>' % (doc_id, html.escape(title)))
        for anchor, text, level in headings:
            nav.append('<a class="h%d" href="#%s">%s</a>' % (level + 1, anchor, html.escape(text)))
        print("  %-28s %2d apartados" % (path.name, len(headings)))

    # --- Estudio interactivo: se copia junto a index.html para que Pages lo sirva.
    if ESTUDIO_SRC.exists():
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        (OUT_DIR / ESTUDIO_OUT_NAME).write_bytes(ESTUDIO_SRC.read_bytes())
        print("  copiado %s -> docs/%s" % (ESTUDIO_SRC.relative_to(ROOT).as_posix(), ESTUDIO_OUT_NAME))
    else:
        print("  [AVISO] no existe %s, no se copia el estudio interactivo" % ESTUDIO_SRC)

    page = """<!DOCTYPE html>
<html lang="es" data-theme="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>domo-lab · documentación</title>
<style>%s</style>
</head>
<body>
<button id="theme" type="button">modo claro</button>
<aside>
  <div class="brand"><b>domo-lab</b><span>Documentacion del laboratorio de domo</span></div>
  <input id="q" type="search" placeholder="Buscar en todo el texto  ( / )" autocomplete="off">
  <p id="empty"></p>
  <div id="results"></div>
  <nav>%s</nav>
</aside>
<main>%s</main>
<script>const DOCS_INDEX=%s;</script>
<script>%s</script>
</body>
</html>
""" % (CSS, "\n".join(nav), "\n".join(sections), json.dumps(index, ensure_ascii=False), JS)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT.write_text(page, encoding="utf-8")
    return OUT


# --------------------------------------------------------------------------
# Verificacion: se corre sola al final de build(). No depende de BeautifulSoup,
# solo de html.parser (libreria estandar), asi el build no gana dependencias
# nuevas ademas de Pillow.
# --------------------------------------------------------------------------

class _PageAudit(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()
        self.hrefs: list[str] = []
        self.img_srcs: list[str] = []
        self.section_ids: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        d = dict(attrs)
        if d.get("id"):
            self.ids.add(d["id"])
            if tag == "section":
                self.section_ids.append(d["id"])
        if tag == "a" and d.get("href"):
            self.hrefs.append(d["href"])
        if tag == "img" and d.get("src"):
            self.img_srcs.append(d["src"])


def verify(out_path: Path) -> None:
    audit = _PageAudit()
    audit.feed(out_path.read_text(encoding="utf-8"))

    broken_links = [h for h in audit.hrefs if h.startswith("#") and h[1:] not in audit.ids]
    broken_images = []
    for src in audit.img_srcs:
        if src.startswith(("http://", "https://", "data:")):
            continue
        if not (OUT_DIR / src).exists():
            broken_images.append(src)

    expected_ids = {slugify(t) for p, t, _ in PAGES if p.exists()}
    missing_pages = expected_ids - set(audit.section_ids)

    print("\nVerificacion de %s" % out_path)
    print("  tamano: %d KB" % (out_path.stat().st_size // 1024))
    print("  paginas presentes: %d/%d" % (len(expected_ids & set(audit.section_ids)), len(expected_ids)))
    print("  imagenes referenciadas: %d" % len(audit.img_srcs))
    print("  imagenes rotas: %d%s" % (len(broken_images), (" -> %s" % broken_images) if broken_images else ""))
    print("  enlaces internos: %d" % len([h for h in audit.hrefs if h.startswith("#")]))
    print("  enlaces internos rotos: %d%s" % (len(broken_links), (" -> %s" % broken_links) if broken_links else ""))
    if missing_pages:
        print("  [AVISO] paginas esperadas ausentes del HTML: %s" % missing_pages)


if __name__ == "__main__":
    print("Generando documentacion de domo-lab…")
    out = build()
    print("Listo: %s (%d KB)" % (out, out.stat().st_size // 1024))
    verify(out)
