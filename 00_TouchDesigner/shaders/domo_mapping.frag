// Domemaster con mapping, directo desde el lienzo equirectangular.
//
// Reemplaza a la pareja Projection TOP (equirect -> fisheye) + Transform TOP
// (mapping) que habia antes. Esa pareja cortaba: el Projection TOP solo
// dibujaba los grados del FOV del contenido y todo lo demas quedaba negro, asi
// que Escala, Centrox y Centroy movian un circulo ya recortado y lo que
// aparecia en el borde era negro, nunca el piso del video. Aqui cada pixel de
// salida deshace el mapping y va a buscar su direccion al lienzo completo: al
// encoger (Escala < 1) o correr el cenit entra contenido de verdad, incluido
// el que esta bajo el horizonte.
//
// Dos modos de salida (uFov.w):
//   0 = domemaster: el cuadro es el fisheye de la sala, cenit en el centro,
//       frente ABAJO del cuadro (la convencion de siempre). Fuera del circulo
//       de la sala queda negro.
//   1 = equirectangular de la sala VR: el lienzo que lee la cupula de Unreal
//       (u 0.5 frente, v 0.5 horizonte, v 1 cenit). Cada pixel de la mitad
//       superior busca su punto en el domemaster y sigue el mismo camino, asi
//       que Unreal ve exactamente lo que veria el domo, sin pasar por un
//       domemaster intermedio de 2048 (mas nitido).
//
// Convencion de direcciones (la de todo DOMO): x a la derecha, y arriba,
// z al frente. En el lienzo: u = 0.5 el frente, v = 0.5 el horizonte.
//
// uniform vec4 uMap : x = Centrox, y = Centroy (fraccion del domemaster),
//                     z = Escala, w = Rotar (grados)
// uniform vec4 uFov : x = FOV del contenido (grados), y = FOV de la sala (grados),
//                     z = Pitch de la pagina Domo (grados), w = modo de salida
//
// Se lee con textureLod nivel 0: con mipmaps, el salto de u de 1 a 0 en la
// costura del lienzo dispara el nivel de mip y deja una linea gris.

uniform vec4 uMap;
uniform vec4 uFov;

out vec4 fragColor;

const float PI = 3.14159265358979;

vec2 uv_de_dir(vec3 d)
{
    float az = atan(d.x, d.z);
    float el = asin(clamp(d.y, -1.0, 1.0));
    return vec2(fract(az / (2.0 * PI) + 0.5), el / PI + 0.5);
}

// La misma inclinacion que orientar.frag: Pitch positivo lleva el frente
// del contenido hacia el cenit.
vec3 pitch_inv(vec3 d, float a)
{
    float c = cos(a), s = sin(a);
    return vec3(d.x, c * d.y - s * d.z, s * d.y + c * d.z);
}

// Color del punto p del domemaster de la sala (p en -1..1, y arriba; el
// circulo de radio 1 es la cupula).
vec4 color_en(vec2 p)
{
    // deshacer el mapping: trasladar, rotar, escalar (inverso de S, R, T)
    vec2 q = p - 2.0 * uMap.xy;
    float a = radians(-uMap.w);                       // Rotar positivo = antihorario
    q = vec2(cos(a) * q.x - sin(a) * q.y, sin(a) * q.x + cos(a) * q.y);
    q /= max(uMap.z, 1e-4);

    // fisheye equidistante del contenido: radio 1 = FOV del contenido / 2
    float th = length(q) * radians(uFov.x) * 0.5;   // angulo desde el cenit
    if (th > PI)
        return vec4(0.0, 0.0, 0.0, 1.0);             // mas alla del nadir
    float az = atan(q.x, -q.y);                       // 0 = frente (abajo del cuadro)
    vec3 d = vec3(sin(th) * sin(az), cos(th), sin(th) * cos(az));
    d = pitch_inv(d, radians(uFov.z));
    return textureLod(sTD2DInputs[0], uv_de_dir(d), 0.0);
}

void main()
{
    vec2 uv = vUV.st;
    vec2 p;
    float borde;
    if (uFov.w < 0.5) {
        // domemaster
        p = uv * 2.0 - 1.0;
        float px = fwidth(p.x);                       // ~un pixel de salida
        borde = 1.0 - smoothstep(1.0 - px, 1.0 + px, length(p));
    } else {
        // equirectangular de la sala VR: direccion del pixel -> punto del domemaster
        float azs = (uv.x - 0.5) * 2.0 * PI;
        float el = (uv.y - 0.5) * PI;
        float th = 0.5 * PI - el;                     // angulo desde el cenit
        float r = th / (radians(uFov.y) * 0.5);
        p = r * vec2(sin(azs), -cos(azs));
        borde = r <= 1.0 ? 1.0 : 0.0;
    }
    vec4 c = borde > 0.0 ? color_en(p) : vec4(0.0);
    c.rgb *= borde;
    c.a = 1.0;
    fragColor = TDOutputSwizzle(c);
}
