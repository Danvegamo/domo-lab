// Rotacion esferica de un lienzo equirectangular (equirect -> equirect).
//
// Gira la esfera entera antes de pasarla a domemaster: Yaw alrededor del eje
// vertical, Pitch alrededor del eje izquierda-derecha (positivo lleva el
// frente hacia el cenit, igual que DOMO.Pitch) y Roll alrededor del eje del
// frente. No es un corrimiento en u: cada pixel de salida calcula su
// direccion, la devuelve con la rotacion inversa y lee el lienzo de entrada
// en esa direccion. Asi la costura de un 360 (la columna u = 0, un meridiano
// de polo a polo) se puede sacar de la cupula: con Pitch 90 queda entera bajo
// el horizonte.
//
// Convencion del lienzo (la de todo DOMO): u = 0.5 es el frente, v = 0.5 el
// horizonte, v = 1 el cenit. Direccion: x a la derecha, y arriba, z al frente.
//
// uniform vec4 uRot  : x = yaw, y = pitch, z = roll (grados), w = pintar la costura (0/1)
// uniform vec4 uSeam : x = posicion de la costura en u de la ENTRADA (0..1),
//                      y = ancho de la guia (fraccion del ancho)
//                      z = elevacion minima valida de la ENTRADA (grados; -90 = toda).
//                          IN_169 la usa: bajo 90 - Domefov/2 el lienzo que sale
//                          del domemaster de VIDEO_DOME no tiene imagen, y el
//                          Projection TOP estira ahi el borde del circulo en rayas.
// uniform vec4 uElev : x = Horizonte: elevacion (grados) a la que queda el horizonte
//                          del video, con el cenit fijo. Positivo lo sube y mete
//                          en la cupula lo que estaba bajo el horizonte (el piso);
//                          negativo lo baja y deja fuera la parte baja del cielo.
//                      y = Curva (1 = compresion pareja). Mayor que 1 aprieta el
//                          piso contra el borde y deja el cielo mas natural; menor
//                          que 1 hace lo contrario. Con Horizonte 0 solo reparte
//                          el cielo entre el horizonte y el cenit.
//
// El remapeo de elevacion va DESPUES del giro (en el sentido de la imagen): se
// gira la esfera del video y luego se comprime la elevacion respecto de la
// cupula. Con t = (90 - e) / 90 la distancia al cenit de la salida (0 en el
// cenit, 1 en el borde de la cupula) y th = (90 - Horizonte) / 90, la
// elevacion que se lee es 90 - 90 (t / th)^Curva. En el borde de la cupula
// entra hasta 90 (th^-Curva - 1) grados bajo el horizonte.
//
// Se lee con textureLod nivel 0: con mipmaps, el salto de u de 1 a 0 en la
// costura dispara el nivel de mip y deja una linea gris de un pixel.

uniform vec4 uRot;
uniform vec4 uSeam;
uniform vec4 uElev;

out vec4 fragColor;

const float PI = 3.14159265358979;

vec3 dir_de_uv(vec2 uv)
{
    float az = (uv.x - 0.5) * 2.0 * PI;
    float el = (uv.y - 0.5) * PI;
    return vec3(cos(el) * sin(az), sin(el), cos(el) * cos(az));
}

vec2 uv_de_dir(vec3 d)
{
    float az = atan(d.x, d.z);
    float el = asin(clamp(d.y, -1.0, 1.0));
    return vec2(fract(az / (2.0 * PI) + 0.5), el / PI + 0.5);
}

// rotaciones inversas (traspuestas), en el orden inverso al directo:
// directo = Yaw * Pitch * Roll, inverso = Roll^T * Pitch^T * Yaw^T
vec3 yaw_inv(vec3 d, float a)
{
    float c = cos(a), s = sin(a);
    return vec3(c * d.x - s * d.z, d.y, s * d.x + c * d.z);
}

vec3 pitch_inv(vec3 d, float a)
{
    float c = cos(a), s = sin(a);
    return vec3(d.x, c * d.y - s * d.z, s * d.y + c * d.z);
}

vec3 roll_inv(vec3 d, float a)
{
    float c = cos(a), s = sin(a);
    return vec3(c * d.x + s * d.y, -s * d.x + c * d.y, d.z);
}

void main()
{
    vec2 uv = vUV.st;
    float H = min(uElev.x, 80.0);
    float g = max(uElev.y, 0.05);
    if (abs(H) > 1e-4 || abs(g - 1.0) > 1e-4) {
        float t = (0.5 - (uv.y - 0.5)) * 2.0;        // 0 cenit, 1 horizonte de la sala, 2 nadir
        float el = 90.0 - 90.0 * pow(t / ((90.0 - H) / 90.0), g);
        if (el < -90.0) {
            fragColor = TDOutputSwizzle(vec4(0.0, 0.0, 0.0, 1.0));
            return;
        }
        uv.y = el / 180.0 + 0.5;
    }
    vec3 d = dir_de_uv(uv);
    d = yaw_inv(d, radians(uRot.x));
    d = pitch_inv(d, radians(uRot.y));
    d = roll_inv(d, radians(uRot.z));
    vec2 src = uv_de_dir(d);

    vec4 c = textureLod(sTD2DInputs[0], src, 0.0);
    if ((src.y - 0.5) * 180.0 < uSeam.z)
        c = vec4(0.0, 0.0, 0.0, 1.0);

    if (uRot.w > 0.5) {
        // distancia en u a la costura de la entrada, dando la vuelta
        float du = abs(fract(src.x - uSeam.x + 0.5) - 0.5);
        if (du < max(uSeam.y, 0.001))
            c = vec4(1.0, 0.0, 0.0, 1.0);
    }
    fragColor = TDOutputSwizzle(c);
}
