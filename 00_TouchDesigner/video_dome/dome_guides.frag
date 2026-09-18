// ==========================================================================
// dome_guides.frag  ·  rejilla del domo + campos visibles + marco de cada pantalla
// Se dibuja ENCIMA del domemaster, solo para ubicar. Se apaga con el par Guides
// antes de proyectar o grabar.
//
// El domemaster es un circulo y sin referencias todo parece estar "en el
// medio". Los anillos de elevacion, los radios de azimut, el horizonte y el
// meridiano del frente dicen donde esta cada cosa.
//
// Los circulos blancos son los campos de mirada del publico: uno por punto de
// vista (uSeats.x). Con 4 o 6 puestos se ve de una si el montaje deja a algun
// sector de la sala sin nada enfrente, que es lo que pasa cuando se disena
// pensando en una sola persona.
//
// uniform vec4 uView  : x = fov del domo  y = aspecto  z = pantallas  w = giro global
// uniform vec4 uGuide : x = grosor  y = alpha  z = paso de anillos  w = paso de radios
// uniform vec4 uField : x = campo visible  y = elevacion de la mirada  z = azimut
//                       w = pantalla seleccionada en la UI
// uniform vec4 uSeats : x = cuantos puntos de vista
// uniform vec4 uAnim  : x = desplazamiento acumulado  y = giro acumulado
// Arrays: uPos / uSize / uOpt / uRep / uAnm igual que en dome_map.frag
// ==========================================================================
#define MAXSCREENS 16
#define MAXCOPIES 12

uniform vec4 uView;
uniform vec4 uGuide;
uniform vec4 uField;
uniform vec4 uSeats;
uniform vec4 uAnim;

uniform vec4 uPos[MAXSCREENS];
uniform vec4 uSize[MAXSCREENS];
uniform vec4 uOpt[MAXSCREENS];
uniform vec4 uRep[MAXSCREENS];
uniform vec4 uAnm[MAXSCREENS];

const float EL_MAX = 1.5551;

out vec4 fragColor;

const float PI = 3.14159265359;

vec3 dirFrom(float az, float el)
{
    return vec3(sin(az) * cos(el), cos(az) * cos(el), sin(el));
}

float copyYaw(int k, int n, float span)
{
    if (n <= 1) return 0.0;
    bool completa = span >= radians(359.0);
    float paso = completa ? span / float(n) : span / float(n - 1);
    return completa ? float(k) * paso
                    : (float(k) - (float(n) - 1.0) * 0.5) * paso;
}

// linea de ancho constante en pantalla. Sin el fwidth las lineas cerca del
// borde del circulo salen gordisimas y en el centro desaparecen.
float gridLine(float value, float step, float width)
{
    float d = abs(fract(value / step - 0.5) - 0.5) * step;
    return 1.0 - smoothstep(0.0, width * fwidth(value), d);
}

bool frameUV(vec3 P, float yaw, float pitch, float roll,
             float hf, float vf, int modo, out vec2 uv)
{
    uv = vec2(0.0);
    if (modo == 2) {
        float az = atan(P.x, P.y);
        float el = asin(clamp(P.z, -1.0, 1.0));
        float da = atan(sin(az - yaw), cos(az - yaw));
        uv = vec2(0.5 + da / hf, 0.5 + (el - pitch) / vf);
        return true;
    }
    if (modo == 4) {
        // cilindro: la altura del impacto en la pared es tan(elevacion)
        float az = atan(P.x, P.y);
        float el = asin(clamp(P.z, -1.0, 1.0));
        if (el <= 0.0005) return false;
        float da = atan(sin(az - yaw), cos(az - yaw));
        if (abs(da) > hf * 0.5) return false;
        float h  = tan(min(el, EL_MAX));
        float h0 = tan(clamp(pitch, 0.0, EL_MAX));
        float h1 = tan(clamp(pitch + vf, 0.001, EL_MAX));
        if (h1 <= h0) return false;
        uv = vec2(0.5 + da / hf, (h - h0) / (h1 - h0));
        return true;
    }
    vec3 C  = dirFrom(yaw, pitch);
    vec3 Rv = vec3(cos(yaw), -sin(yaw), 0.0);
    vec3 Uv = vec3(-sin(yaw) * sin(pitch), -cos(yaw) * sin(pitch), cos(pitch));
    if (abs(roll) > 1e-6) {
        vec3 r2 = Rv * cos(roll) + Uv * sin(roll);
        Uv = Uv * cos(roll) - Rv * sin(roll);
        Rv = r2;
    }
    float x = dot(P, Rv);
    float y = dot(P, Uv);
    float z = dot(P, C);
    if (z <= 0.001) return false;
    if (modo == 3) {
        vec2 q = vec2(atan(x, z) / (hf * 0.5), asin(clamp(y, -1.0, 1.0)) / (vf * 0.5));
        // (el cilindro se resuelve antes, junto con la banda)
        float rad = length(q);
        // el marco del tunel es su circulo exterior
        uv = vec2(0.5, 1.0 - rad);
        return (rad <= 1.2);
    }
    if (modo == 0) {
        uv = vec2(0.5 + (x / z) / (2.0 * tan(hf * 0.5)),
                  0.5 + (y / z) / (2.0 * tan(vf * 0.5)));
    } else {
        uv = vec2(0.5 + atan(x, z) / hf,
                  0.5 + asin(clamp(y, -1.0, 1.0)) / vf);
    }
    return true;
}

void main()
{
    vec2 nc = vUV.st * 2.0 - 1.0;
    float r = length(nc);
    if (r > 1.0) {
        fragColor = TDOutputSwizzle(vec4(0.0));
        return;
    }

    float half_dome = radians(uView.x * 0.5);
    float theta = r * half_dome;
    float phi   = atan(nc.x, -nc.y);

    float elev = 90.0 - degrees(theta);
    float az = degrees(phi);

    float w = max(uGuide.x, 0.5);
    float rings = gridLine(elev, max(uGuide.z, 1.0), w);
    float rays  = gridLine(az, max(uGuide.w, 1.0), w);
    float horizon = 1.0 - smoothstep(0.0, w * 2.0 * fwidth(elev), abs(elev));
    float front   = 1.0 - smoothstep(0.0, w * 2.0 * fwidth(az), abs(az));

    vec3 col = vec3(0.35, 0.75, 1.0) * max(rings, rays) * 0.5;
    col += vec3(1.0, 0.85, 0.3) * horizon;
    col += vec3(0.4, 1.0, 0.6) * front;

    vec3 P = vec3(sin(theta) * sin(phi), sin(theta) * cos(phi), cos(theta));

    // campos de mirada del publico, uno por punto de vista
    int puestos = clamp(int(uSeats.x + 0.5), 1, 8);
    for (int s = 0; s < puestos; ++s) {
        float ay = radians(uField.z) + float(s) * 2.0 * PI / float(puestos);
        vec3 look = dirFrom(ay, radians(uField.y));
        float ang = degrees(acos(clamp(dot(P, look), -1.0, 1.0)));
        float borde = 1.0 - smoothstep(0.0, w * 1.5 * fwidth(ang),
                                       abs(ang - max(uField.x, 1.0) * 0.5));
        // el primero mas fuerte: es el que manda en la pagina Espacio
        col += vec3(1.0) * borde * (s == 0 ? 0.9 : 0.45);
    }

    // marco de cada pantalla encendida, incluidas sus copias del anillo
    float giro = radians(uView.w);
    int count = clamp(int(uView.z + 0.5), 0, MAXSCREENS);
    for (int i = 0; i < count; ++i) {
        if (uOpt[i].x < 0.5) continue;
        int modo = int(uPos[i].w + 0.5);
        int copias = clamp(int(uRep[i].x + 0.5), 1, MAXCOPIES);
        float span = radians(uRep[i].y <= 0.0 ? 360.0 : uRep[i].y);
        // el marco tiene que dibujar el ancho REAL, con el solape incluido, o
        // no sirve para ver donde se cosen dos copias
        float hf_c = radians(max(uSize[i].x, 0.1))
                     + (copias > 1 ? radians(max(uOpt[i].w, 0.0)) : 0.0);
        for (int k = 0; k < copias; ++k) {
            vec2 uv;
            // el marco acompana el giro animado de la fila
            if (!frameUV(P, radians(uPos[i].x + uAnim.y * uAnm[i].y) + giro
                            + copyYaw(k, copias, span),
                         radians(uPos[i].y), radians(uPos[i].z),
                         hf_c,
                         radians(max(uSize[i].y, 0.1)), modo, uv)) continue;
            if (uv.x < -0.05 || uv.x > 1.05 || uv.y < -0.05 || uv.y > 1.05) continue;

            float edge = min(min(uv.x, 1.0 - uv.x), min(uv.y, 1.0 - uv.y));
            float dw = max(fwidth(uv.x), fwidth(uv.y)) * w * 1.5;
            float frame = 1.0 - smoothstep(0.0, dw, abs(edge));
            float cruz = max(1.0 - smoothstep(0.0, fwidth(uv.x) * w * 1.5, abs(uv.x - 0.5)),
                             1.0 - smoothstep(0.0, fwidth(uv.y) * w * 1.5, abs(uv.y - 0.5)));
            cruz *= step(0.0, edge);
            // la pantalla seleccionada en rojo, las demas en naranja; las
            // copias del anillo mas apagadas que la copia original
            vec3 tint = (abs(float(i) - uField.w) < 0.5)
                        ? vec3(1.0, 0.25, 0.25) : vec3(1.0, 0.65, 0.2);
            col += tint * max(frame, cruz * 0.3) * (k == 0 ? 1.0 : 0.5);
        }
    }

    float a = clamp(max(max(col.r, col.g), col.b), 0.0, 1.0) * clamp(uGuide.y, 0.0, 1.0);
    fragColor = TDOutputSwizzle(vec4(col, a));
}
