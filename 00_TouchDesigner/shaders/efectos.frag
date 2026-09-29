// ==========================================================================
// efectos.frag  ·  visualizaciones generativas para IN_FX
//
// Escribe DIRECTO el lienzo equirectangular 2:1 de DOMO (u 0.5 = frente,
// v 0.5 = horizonte, v 1 = cenit). Cada pixel calcula su direccion en la
// esfera y el efecto se evalua sobre esa direccion, no sobre (u, v): asi no
// hay costura atras (u = 0 / u = 1) ni un pellizco en el cenit, que es donde
// mas se mira en un domo. Los efectos que usan el azimut lo hacen con un
// numero entero de repeticiones por vuelta, por la misma razon.
//
// uniform vec4 uFx    : x = efecto (indice del menu), y = tiempo acumulado,
//                       z = giro acumulado (grados), w = intensidad
// uniform vec4 uCol1  : rgb = color A, w = escala
// uniform vec4 uCol2  : rgb = color B, w = detalle (0..1)
// uniform vec4 uAudio : nivel, graves, medios, agudos (0..1, ya multiplicados
//                       por la Reactividad; en cero el efecto no reacciona)
//
// Efectos: 0 tunel, 1 ondas, 2 estrellas, 3 caleidoscopio, 4 plasma,
//          5 flujo, 6 rejilla neon, 7 aurora
// ==========================================================================
uniform vec4 uFx;
uniform vec4 uCol1;
uniform vec4 uCol2;
uniform vec4 uAudio;

out vec4 fragColor;

const float PI = 3.14159265359;
const float TAU = 6.28318530718;

// ---------------------------------------------------------------- ruido
float hash13(vec3 p)
{
    p = fract(p * 0.1031);
    p += dot(p, p.zyx + 31.32);
    return fract((p.x + p.y) * p.z);
}

vec2 hash22(vec2 p)
{
    vec3 p3 = fract(vec3(p.xyx) * vec3(0.1031, 0.1030, 0.0973));
    p3 += dot(p3, p3.yzx + 33.33);
    return fract((p3.xx + p3.yz) * p3.zy);
}

float noise3(vec3 p)
{
    vec3 i = floor(p);
    vec3 f = fract(p);
    f = f * f * (3.0 - 2.0 * f);
    return mix(mix(mix(hash13(i), hash13(i + vec3(1, 0, 0)), f.x),
                   mix(hash13(i + vec3(0, 1, 0)), hash13(i + vec3(1, 1, 0)), f.x), f.y),
               mix(mix(hash13(i + vec3(0, 0, 1)), hash13(i + vec3(1, 0, 1)), f.x),
                   mix(hash13(i + vec3(0, 1, 1)), hash13(i + vec3(1, 1, 1)), f.x), f.y), f.z);
}

float fbm(vec3 p, int oct)
{
    float a = 0.5;
    float s = 0.0;
    for (int i = 0; i < 6; ++i) {
        if (i >= oct) break;
        s += a * noise3(p);
        p = p * 2.03 + vec3(1.7, 9.2, 3.1);
        a *= 0.5;
    }
    return s;
}

// linea suave y antialiasada sobre una coordenada que repite cada 1
float linea(float x, float grosor)
{
    float d = abs(fract(x - 0.5) - 0.5);
    float w = fwidth(x) * 1.2 + grosor;
    return 1.0 - smoothstep(grosor * 0.2, w, d);
}

// ---------------------------------------------------------------- efectos
vec3 tunel(vec3 d, float t, float esc, float det, vec3 a, vec3 b, vec4 au)
{
    // un tubo cuyo eje es la vertical: el publico vuela hacia el cenit.
    // z = altura a la que el rayo toca la pared de radio 1.
    float r = max(length(d.xy), 1e-3);
    float z = d.z / r;
    float ang = atan(d.x, d.y) / TAU;              // -0.5 .. 0.5, entero por vuelta
    float zz = z * esc + t;
    float n = floor(8.0 + det * 16.0);
    float l = max(linea(ang * n, 0.01), linea(zz * 2.0, 0.015));
    float fondo = 0.5 + 0.5 * sin(zz * 1.3 + ang * TAU * 2.0);
    vec3 col = mix(a, b, 0.5 + 0.5 * sin(zz * 0.45));
    float niebla = exp(-abs(z) * 0.12 / max(esc, 0.1));
    vec3 pared = mix(b, a, 0.5 + 0.5 * sin(zz * 0.9 + 1.0)) * (0.12 + 0.30 * fondo);
    return (pared + col * l * (1.6 + 1.5 * au.y)) * niebla;
}

vec3 ondas(vec3 d, float t, float esc, float det, vec3 a, vec3 b, vec4 au)
{
    // anillos que bajan del cenit mas dos focos que pasean: la interferencia
    // dibuja la figura
    float th = acos(clamp(d.z, -1.0, 1.0));
    vec3 p1 = normalize(vec3(sin(t * 0.23), cos(t * 0.17), 0.9));
    vec3 p2 = normalize(vec3(cos(t * 0.19 + 2.0), sin(t * 0.13 + 1.0), 0.6));
    float k = 14.0 * esc;
    float w = sin(th * k - t * 3.0)
            + sin(acos(clamp(dot(d, p1), -1.0, 1.0)) * k * 0.8 - t * 2.3) * det
            + sin(acos(clamp(dot(d, p2), -1.0, 1.0)) * k * 1.2 - t * 2.7) * det;
    w /= (1.0 + 2.0 * det);
    float cresta = pow(0.5 + 0.5 * w, 4.0 - 2.0 * au.y);
    float filo = smoothstep(0.93, 1.0, 0.5 + 0.5 * w);
    return mix(a, b, 0.5 + 0.5 * w) * (0.06 + 1.1 * cresta) + mix(b, vec3(1.0), 0.5) * filo * 0.6;
}

vec3 estrellas(vec3 d, float t, float esc, float det, vec3 a, vec3 b, vec4 au)
{
    // log-polar alrededor del cenit: acercarse es correr el radio logaritmico,
    // asi el campo de estrellas se abre desde el cenit hacia el borde sin fin
    float th = acos(clamp(d.z, -1.0, 1.0));
    float lr = log(max(tan(th * 0.5), 1e-4));
    float az = atan(d.x, d.y) / TAU;
    vec3 col = vec3(0.0);
    for (int k = 0; k < 4; ++k) {
        float fk = float(k);
        float N = floor(12.0 * esc * (1.0 + 0.6 * fk) * (0.6 + det));
        vec2 q = vec2(az * N, (lr + t * (0.25 + 0.12 * fk)) * N / TAU);
        vec2 id = floor(q);
        id.x = mod(id.x, N);
        vec2 f = fract(q) - 0.5;
        vec2 h = hash22(id + fk * 17.31);
        vec2 pos = (h - 0.5) * 0.6;
        vec2 dd = f - pos;
        dd.y *= 0.35 + 0.65 / (1.0 + 2.0 * au.x);     // con volumen se estiran
        float r = length(dd);
        float tam = 0.04 + 0.10 * h.x * h.x;
        float brillo = smoothstep(tam, 0.0, r) * 1.5 + 0.01 / (r * r + 0.01) * 0.12;
        float titila = 0.6 + 0.4 * sin(t * 6.0 + h.y * 40.0) * (0.5 + au.w);
        col += mix(a, b, h.y) * brillo * titila * step(0.35, h.x + 0.3);
    }
    return col * 1.6;
}

vec3 caleidoscopio(vec3 d, float t, float esc, float det, vec3 a, vec3 b, vec4 au, int oct)
{
    float th = acos(clamp(d.z, -1.0, 1.0));
    float az = atan(d.x, d.y);
    float n = floor(4.0 + det * 8.0);
    float seg = TAU / n;
    float aa = mod(az + t * 0.15, seg);
    aa = abs(aa - seg * 0.5);                       // espejo dentro de cada sector
    vec2 p = vec2(cos(aa), sin(aa)) * th * esc * 2.0;
    float v = fbm(vec3(p * 1.6, t * 0.2), oct);
    float v2 = fbm(vec3(p * 3.2 + v * 2.0, t * 0.27), oct);
    float borde = smoothstep(0.02, 0.0, abs(v2 - 0.5)) * (1.0 + au.z);
    vec3 col = mix(a, b, smoothstep(0.3, 0.7, v2));
    return col * (0.15 + 1.1 * smoothstep(0.35, 0.8, v2)) + borde * mix(b, vec3(1.0), 0.4);
}

vec3 plasma(vec3 d, float t, float esc, float det, vec3 a, vec3 b, vec4 au)
{
    vec3 p = d * esc * 3.0;
    float v = sin(p.x * 2.0 + t)
            + sin(p.y * 2.3 - t * 1.3)
            + sin(p.z * 1.7 + t * 0.7)
            + sin(length(p.xy + vec2(sin(t * 0.3), cos(t * 0.4))) * (3.0 + 4.0 * det) - t * 1.1);
    v = v * 0.25 + au.y * 0.3;
    vec3 col = mix(a, b, 0.5 + 0.5 * sin(v * TAU + t * 0.2));
    return col * (0.55 + 0.45 * sin(v * 6.0));
}

vec3 flujo(vec3 d, float t, float esc, float det, vec3 a, vec3 b, vec4 au, int oct)
{
    // ruido deformado por ruido sobre la esfera: se lee como tinta en agua
    vec3 p = d * esc * 2.5;
    vec3 q = vec3(fbm(p + vec3(0.0, 0.0, t * 0.15), oct),
                  fbm(p + vec3(5.2, 1.3, -t * 0.12), oct),
                  fbm(p + vec3(2.1, 7.7, t * 0.1), oct));
    float v = fbm(p + (2.0 + 1.5 * au.y) * q + vec3(t * 0.05), oct);
    vec3 col = mix(a, b, clamp(q.x * 1.6 - 0.2, 0.0, 1.0));
    return col * pow(clamp(v, 0.0, 1.0), 1.4) * 2.4;
}

vec3 rejilla(vec3 d, float t, float esc, float det, vec3 a, vec3 b, vec4 au)
{
    // techo y piso en perspectiva (estilo synthwave): la rejilla pasa por
    // encima del publico hacia el frente, con un sol en el horizonte
    float h = abs(d.z);
    vec2 pl = d.xy / max(h, 1e-3);
    vec2 g = pl * esc * 2.0 + vec2(0.0, -t);
    float grosor = 0.01 + 0.03 * det;
    float l = max(linea(g.x, grosor), linea(g.y, grosor));
    l *= smoothstep(0.015, 0.25, h);                // el horizonte se vuelve muare
    vec3 col = a * l * (1.2 + 2.0 * au.y);
    col += b * exp(-h * 10.0) * 0.8;                // resplandor del horizonte
    // sol al frente
    float el = asin(clamp(d.z, -1.0, 1.0));
    float az = atan(d.x, d.y);
    vec2 s = vec2(az, el - radians(10.0));
    float sol = smoothstep(0.30, 0.28, length(s));
    float franjas = step(0.5, fract(el * 40.0 - t * 0.5)) + step(radians(10.0), el);
    col += mix(b, vec3(1.0, 0.85, 0.3), clamp((el + 0.1) * 3.0, 0.0, 1.0)) * sol * min(franjas, 1.0) * (1.0 + au.x);
    return col;
}

vec3 aurora(vec3 d, float t, float esc, float det, vec3 a, vec3 b, vec4 au, int oct)
{
    float el = asin(clamp(d.z, -1.0, 1.0));
    float az = atan(d.x, d.y);
    float e = el / (PI * 0.5);
    vec3 col = vec3(0.0);
    for (int k = 0; k < 5; ++k) {
        float fk = float(k);
        float banda = 0.10 + 0.12 * fk
                    + 0.07 * sin(az * 3.0 + t * 0.3 + fk * 1.7)
                    + 0.05 * sin(az * 5.0 - t * 0.21 + fk);
        float dist = e - banda;
        // la cortina cuelga hacia arriba desde su borde de abajo
        float cortina = smoothstep(-0.015, 0.01, dist) * exp(-max(dist, 0.0) * (7.0 - 3.0 * au.y));
        vec3 pa = vec3(cos(az), sin(az), 0.0) * 18.0 * esc;
        float rayos = fbm(pa + vec3(0.0, 0.0, fk * 3.1 + t * 0.35), oct);
        rayos = pow(clamp(rayos * 1.4, 0.0, 1.0), 1.5 + det);
        col += mix(a, b, clamp(e * 1.4 + fk * 0.08, 0.0, 1.0)) * cortina * rayos * 0.55;
    }
    // un poco de cielo estrellado detras
    vec2 q = vec2(az / TAU * 400.0, e * 100.0);
    vec2 h = hash22(floor(q));
    float est = smoothstep(0.08, 0.0, length(fract(q) - 0.5 - (h - 0.5) * 0.6)) * step(0.85, h.x);
    col += vec3(est) * 0.5 * smoothstep(0.0, 0.1, e);
    return col * step(-0.02, e);
}

void main()
{
    vec2 uv = vUV.st;
    float az = (uv.x - 0.5) * TAU + radians(uFx.z);   // 0 = frente
    float el = (uv.y - 0.5) * PI;                      // 0 = horizonte
    vec3 d = vec3(sin(az) * cos(el), cos(az) * cos(el), sin(el));

    int fx = int(uFx.x + 0.5);
    float t = uFx.y;
    float esc = max(uCol1.w, 0.05);
    float det = clamp(uCol2.w, 0.0, 1.0);
    int oct = 2 + int(det * 4.0 + 0.5);
    vec3 a = uCol1.rgb;
    vec3 b = uCol2.rgb;
    vec4 au = clamp(uAudio, 0.0, 2.0);

    vec3 c;
    if (fx == 0)      c = tunel(d, t, esc, det, a, b, au);
    else if (fx == 1) c = ondas(d, t, esc, det, a, b, au);
    else if (fx == 2) c = estrellas(d, t, esc, det, a, b, au);
    else if (fx == 3) c = caleidoscopio(d, t, esc, det, a, b, au, oct);
    else if (fx == 4) c = plasma(d, t, esc, det, a, b, au);
    else if (fx == 5) c = flujo(d, t, esc, det, a, b, au, oct);
    else if (fx == 6) c = rejilla(d, t, esc, det, a, b, au);
    else              c = aurora(d, t, esc, det, a, b, au, oct);

    c *= uFx.w * (1.0 + 0.8 * au.x);
    fragColor = TDOutputSwizzle(vec4(max(c, 0.0), 1.0));
}
