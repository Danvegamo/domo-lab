// Costura de un video 360 equirectangular.
// Un video 360 mal cosido deja una linea vertical visible donde el borde
// izquierdo se encuentra con el derecho (u = 0 / u = 1), o en cualquier otro
// azimut si la costura del stitching quedo dentro del cuadro. Este shader
// funde una franja alrededor de esa columna: desenfoca en horizontal con un
// nucleo triangular y, si hace falta, corrige un salto vertical y de brillo
// entre los dos lados.
//
// uSeam: x = posicion de la costura en u (0..1)
//        y = ancho de la franja fundida (fraccion del ancho)
//        z = radio del desenfoque horizontal (fraccion del ancho)
//        w = guia: > 0.5 pinta la costura en rojo para encontrarla
// uFix:  x = corrimiento vertical del lado derecho (fraccion del alto)
//        y = ganancia del lado derecho (1 = sin cambio)

uniform vec4 uSeam;
uniform vec4 uFix;
out vec4 fragColor;

vec4 tex(vec2 p) {
    return texture(sTD2DInputs[0], vec2(fract(p.x), clamp(p.y, 0.0, 1.0)));
}

void main() {
    vec2 uv = vUV.st;
    float d = uv.x - uSeam.x;
    d -= floor(d + 0.5);                       // distancia con vuelta (-0.5..0.5)
    float w = max(uSeam.y, 1e-5);
    float m = 1.0 - smoothstep(0.0, w, abs(d)); // peso de la franja
    float lado = step(0.0, d) * (1.0 - smoothstep(0.0, w * 3.0, abs(d)));
    vec2 p = uv + vec2(0.0, uFix.x * lado);
    vec4 c = tex(p);
    if (m > 0.0) {
        vec4 acc = vec4(0.0);
        float ws = 0.0;
        for (int i = -16; i <= 16; i++) {
            float t = float(i) / 16.0;
            float k = 1.0 - abs(t);
            acc += tex(p + vec2(t * uSeam.z * m, 0.0)) * k;
            ws += k;
        }
        c = mix(c, acc / ws, m);
    }
    c.rgb *= mix(1.0, uFix.y, lado);
    if (uSeam.w > 0.5 && abs(d) < 0.0006) c = vec4(1.0, 0.0, 0.0, 1.0);
    fragColor = TDOutputSwizzle(c);
}
