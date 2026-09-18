// ==========================================================================
// dome_map.frag  ·  video 16:9 -> domemaster fisheye, con N pantallas
// Copia de referencia del shader que build_video_dome.py escribe adentro de
// /project1/VIDEO_DOME/dome_map (y de dome_map_b y bg_map, que son el mismo
// shader con otra tabla o en modo fondo). Si se edita aca, hay que volver a
// correr el build.
//
// Trabaja al reves que un render: por cada pixel del domemaster calcula la
// direccion en la cupula y pregunta que pantalla la cubre. Por eso no hace
// falta geometria, camara ni teselado.
//
// Las pantallas NO estan cableadas: vienen de la tabla `screens` convertida a
// CHOP, una fila por pantalla. Asi se agregan, se mueven y se guardan como
// template sin tocar la red.
//
// Cada fila puede REPETIRSE en anillo (uRep). Eso es lo que hace que el domo
// funcione para una sala repartida y no para una sola persona mirando al
// frente: con rep=4 la misma pantalla aparece enfrente de cada cuarto de la
// sala, y se sigue moviendo como una sola.
//
// Las copias de una fila se COSEN entre si: se juntan sus aportes y se dividen
// por el peso total, asi el solape queda parejo. Con la mezcla secuencial de
// antes dos bordes suaves encimados sumaban 0.75 de cobertura y se veia una
// banda oscura en cada costura. Filas distintas si se apilan una sobre otra,
// que es lo que uno espera al poner un tunel debajo de una pantalla.
//
// uniform vec4 uView : x = fov del domo   y = aspecto del video (ancho/alto)
//                      z = cuantas pantallas   w = giro global del conjunto
// uniform vec4 uBg   : x = zoom del lavado   y = repeticiones del envolvente
//                      z = giro del fondo    w = modo (0 pantallas, 4 wrap, 5 wash)
// uniform vec4 uAnim : x = desplazamiento acumulado   y = giro acumulado (grados)
//
// Arrays, una entrada por pantalla:
//   uPos[i]  = yaw, pitch, roll, modo
//              modo 0 plana / 1 curva / 2 banda / 3 tunel / 4 cilindro
//   uSize[i] = hfov, vfov, espejo, opacidad   espejo 0 no / 1 horiz / 2 vert / 3 ambos
//   uCrop[i] = x, y, ancho, alto           recorte del cuadro que usa esa pantalla
//   uOpt[i]  = encendida, feather, repeticiones adentro, solape entre copias (grados)
//   uRep[i]  = copias en anillo, arco que ocupan (grados), espejo alterno,
//              corrimiento del recorte por copia
//   uAnm[i]  = cuanto le afecta el desplazamiento, cuanto el giro,
//              bordes (0 los cuatro / 1 solo los costados / 2 solo arriba y abajo),
//              reservado
// ==========================================================================
#define MAXSCREENS 16
#define MAXCOPIES 12

uniform vec4 uView;
uniform vec4 uBg;
uniform vec4 uAnim;

uniform vec4 uPos[MAXSCREENS];
uniform vec4 uSize[MAXSCREENS];
uniform vec4 uCrop[MAXSCREENS];
uniform vec4 uOpt[MAXSCREENS];
uniform vec4 uRep[MAXSCREENS];
uniform vec4 uAnm[MAXSCREENS];

out vec4 fragColor;

const float PI = 3.14159265359;
// tan(89.1 grados): mas arriba el cilindro se va al infinito y aparecen
// artefactos de precision justo en el cenit
const float EL_MAX = 1.5551;

// direccion unitaria a partir de azimut y elevacion, en la base
// (derecha, frente, cenit). azimut 0 = frente del domo = ABAJO del domemaster.
vec3 dirFrom(float az, float el)
{
    return vec3(sin(az) * cos(el), cos(az) * cos(el), sin(el));
}

// Angulo que hay que sumarle al yaw para la copia k de un anillo de n copias
// repartidas sobre un arco de 'span' radianes.
//
// Con la vuelta entera las copias van 0, paso, 2*paso... asi la copia 0 se
// queda donde el usuario puso la pantalla y las demas se reparten alrededor.
// Con un arco parcial se centran sobre esa direccion, que es lo que uno espera
// al abrir un abanico.
float copyYaw(int k, int n, float span)
{
    if (n <= 1) return 0.0;
    bool completa = span >= radians(359.0);
    float paso = completa ? span / float(n) : span / float(n - 1);
    return completa ? float(k) * paso
                    : (float(k) - (float(n) - 1.0) * 0.5) * paso;
}

// Coordenada dentro de una pantalla. Devuelve false si la direccion cae fuera.
bool screenUV(vec3 P, float yaw, float pitch, float roll,
              float hf, float vf, int modo, float tile, float travel,
              out vec2 uv)
{
    uv = vec2(0.0);

    // banda: rectangulo en azimut/elevacion, sin marco propio. Puede dar la
    // vuelta entera al domo sin deformarse en los costados.
    if (modo == 2) {
        float az = atan(P.x, P.y);                    // 0 = frente
        float el = asin(clamp(P.z, -1.0, 1.0));
        float da = az - yaw;
        da = atan(sin(da), cos(da));                  // envolver a [-PI, PI]
        uv = vec2(0.5 + da / hf, 0.5 + (el - pitch) / vf);
        if (tile > 1.0) uv.x = fract(uv.x * tile);
        uv.y = uv.y - travel;
        return (uv.x >= 0.0 && uv.x <= 1.0 && uv.y >= 0.0 && uv.y <= 1.0);
    }

    // cilindro: el video envuelto en una pared cilindrica alrededor del
    // publico, no pegado a la cupula. La altura a la que un rayo golpea la
    // pared es tan(elevacion), asi que la imagen se comprime sola hacia el
    // cenit: eso es lo que da la sensacion de fuga y de estar adentro. El
    // tunel polar, en cambio, retuerce la imagen alrededor de un punto, y con
    // una textura de ciudad eso se lee como un remolino, no como espacio.
    if (modo == 4) {
        float az = atan(P.x, P.y);
        float el = asin(clamp(P.z, -1.0, 1.0));
        if (el <= 0.0005) return false;               // debajo del horizonte no hay pared
        float da = atan(sin(az - yaw), cos(az - yaw));
        if (abs(da) > hf * 0.5) return false;
        float h  = tan(min(el, EL_MAX));
        float h0 = tan(clamp(pitch, 0.0, EL_MAX));
        float h1 = tan(clamp(pitch + vf, 0.001, EL_MAX));
        if (h1 <= h0) return false;
        uv = vec2(0.5 + da / hf, (h - h0) / (h1 - h0));
        if (tile > 1.0) uv.x = fract(uv.x * tile);
        uv.y = uv.y - travel;                          // el cilindro se lleva
        return (uv.x >= 0.0 && uv.x <= 1.0 && uv.y >= 0.0 && uv.y <= 1.0);
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

    // tunel: coordenadas polares alrededor del centro de la pantalla. El video
    // se enrosca hacia el centro y con repeticiones da anillos que se alejan.
    if (modo == 3) {
        vec2 q = vec2(atan(x, z) / (hf * 0.5), asin(clamp(y, -1.0, 1.0)) / (vf * 0.5));
        float rad = length(q);
        if (rad > 1.0) return false;
        float ang = atan(q.y, q.x) / (2.0 * PI) + 0.5;
        float rep = max(tile, 1.0);
        uv = vec2(ang, fract((1.0 - rad) * rep - travel));
        return true;
    }

    if (modo == 0) {
        // plana (gnomonica): las rectas del video siguen rectas en el espacio
        uv = vec2(0.5 + (x / z) / (2.0 * tan(hf * 0.5)),
                  0.5 + (y / z) / (2.0 * tan(vf * 0.5)));
    } else {
        // curva: angulos iguales, para pantallas de mas de ~100 grados
        uv = vec2(0.5 + atan(x, z) / hf,
                  0.5 + asin(clamp(y, -1.0, 1.0)) / vf);
    }
    if (tile > 1.0) uv.x = fract(uv.x * tile);
    return (uv.x >= 0.0 && uv.x <= 1.0 && uv.y >= 0.0 && uv.y <= 1.0);
}

// Peso del pixel dentro del marco de la pantalla.
//
// bordes: 0 = los cuatro lados, 1 = solo los costados, 2 = solo arriba y abajo.
// En un anillo cosido interesa el 1: si el borde de arriba tambien se degrada,
// la corona se lee como una fila de manchas en vez de una banda continua.
float pesoBorde(vec2 uv, float fth, int bordes)
{
    fth = max(fth, 0.0001);
    float lados = smoothstep(0.0, fth, uv.x) * smoothstep(0.0, fth, 1.0 - uv.x);
    float arrab = smoothstep(0.0, fth, uv.y) * smoothstep(0.0, fth, 1.0 - uv.y);
    if (bordes == 1) return lados;
    if (bordes == 2) return arrab;
    return lados * arrab;
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
    float aspect = max(uView.y, 0.0001);
    float theta = r * half_dome;               // angulo desde el cenit
    float phi   = atan(nc.x, -nc.y);           // 0 = abajo = frente del domo
    int bgmode = int(uBg.w + 0.5);

    // ---------------- capa de fondo ----------------
    if (bgmode == 4) {
        // envolvente: el video da la vuelta al domo, espejado para que no se
        // vea la costura, del horizonte (abajo) al cenit (arriba)
        float a = (phi - radians(uBg.z)) / (2.0 * PI) + 0.5;
        float tile = max(uBg.y, 1.0);
        vec2 uvw = vec2(abs(mod(a * tile, 2.0) - 1.0),
                        clamp(1.0 - theta / half_dome, 0.0, 1.0));
        fragColor = TDOutputSwizzle(texture(sTD2DInputs[0], clamp(uvw, 0.0, 1.0)));
        return;
    }
    if (bgmode == 5) {
        // lavado: copia agrandada del propio cuadro llenando el circulo
        float zoom = max(uBg.x, 0.01);
        vec2 uvz = vec2(0.5 + nc.x * 0.5 / zoom,
                        0.5 + nc.y * 0.5 * aspect / zoom);
        fragColor = TDOutputSwizzle(texture(sTD2DInputs[0], clamp(uvz, 0.0, 1.0)));
        return;
    }

    // ---------------- pantallas ----------------
    vec3 P = vec3(sin(theta) * sin(phi), sin(theta) * cos(phi), cos(theta));
    float giro = radians(uView.w);
    int count = clamp(int(uView.z + 0.5), 0, MAXSCREENS);

    vec4 acc = vec4(0.0);

    for (int i = 0; i < count; ++i) {
        if (uOpt[i].x < 0.5) continue;                       // apagada

        int modo = int(uPos[i].w + 0.5);
        float hf = radians(max(uSize[i].x, 0.1));
        float vf = radians(max(uSize[i].y, 0.1));

        // la animacion global entra escalada por lo que diga cada fila
        float travel = uAnim.x * uAnm[i].x;
        float yaw0 = radians(uPos[i].x + uAnim.y * uAnm[i].y) + giro;
        int bordes = int(uAnm[i].z + 0.5);

        int copias = clamp(int(uRep[i].x + 0.5), 1, MAXCOPIES);
        float span = radians(uRep[i].y <= 0.0 ? 360.0 : uRep[i].y);
        bool alterna = uRep[i].z > 0.5;
        float paso_crop = uRep[i].w;

        // solape entre copias: el ancho de muestreo crece esos grados y el
        // borde suave ocupa exactamente el solape, asi dos copias vecinas se
        // reparten el mismo pixel y no queda ni raya ni banda oscura
        float solape = radians(max(uOpt[i].w, 0.0));
        float hf_c = (copias > 1) ? hf + solape : hf;
        float fth = (copias > 1 && solape > 0.0)
                    ? solape / hf_c
                    : max(uOpt[i].y, 0.0001);

        // los aportes de las copias de ESTA fila se suman y se normalizan
        vec4 suma = vec4(0.0);
        float peso = 0.0;

        for (int k = 0; k < copias; ++k) {
            vec2 uv;
            if (!screenUV(P, yaw0 + copyYaw(k, copias, span), radians(uPos[i].y),
                          radians(uPos[i].z), hf_c, vf, modo, uOpt[i].z, travel,
                          uv)) continue;

            float w = pesoBorde(uv, fth, bordes);
            if (w <= 0.0) continue;

            int esp = int(uSize[i].z + 0.5);
            bool flipx = (esp == 1 || esp == 3);
            bool flipy = (esp == 2 || esp == 3);
            // espejo alterno: copias vecinas se encuentran por el mismo borde
            // del cuadro, asi el anillo se lee como un objeto y no como cortes
            if (alterna && (k - (k / 2) * 2) == 1) flipx = !flipx;
            if (flipx) uv.x = 1.0 - uv.x;
            if (flipy) uv.y = 1.0 - uv.y;

            // recorte: que fragmento del cuadro usa esta copia
            vec2 c0 = uCrop[i].xy;
            c0.x = fract(c0.x + paso_crop * float(k));
            vec2 cs = max(uCrop[i].zw, vec2(0.0001));
            vec2 uvs = clamp(c0 + uv * cs, 0.0, 1.0);

            suma += texture(sTD2DInputs[0], uvs) * w;
            peso += w;
        }

        if (peso <= 0.0) continue;
        vec4 col = suma / peso;                       // la costura queda pareja
        float a = min(peso, 1.0) * clamp(uSize[i].w, 0.0, 1.0);
        // las filas se apilan en el orden de la tabla: la ultima queda arriba
        acc = mix(acc, col, a * col.a);
    }

    fragColor = TDOutputSwizzle(acc);
}
