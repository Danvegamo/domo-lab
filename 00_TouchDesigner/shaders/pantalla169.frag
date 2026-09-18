// Pantalla plana (16:9 o cualquier aspecto) colocada sobre la cupula.
// Sale un lienzo equirectangular 2:1: para cada pixel del lienzo se calcula
// la direccion en la esfera y se pregunta si esa direccion cae dentro de la
// pantalla. Si cae, se lee el video; si no, se lee el fondo difuso (entrada 1)
// o negro. No hay geometria ni camara: el mapeo se resuelve por pixel.
//
// Convencion del lienzo: u = 0.5 es el frente (azimut 0), v = 0.5 es el
// horizonte y v = 1 el cenit. La mitad superior del lienzo es la cupula.
//
// uScreen: x = azimut del centro (grados, 0 al frente, + a la derecha)
//          y = elevacion del centro (grados, 0 horizonte, 90 cenit)
//          z = ancho angular (grados)
//          w = alto angular (grados)
// uMode:   x = forma: 0 plana (gnomonica, rectas rectas), 1 curva (angulos iguales)
//          y = fondo: 1 usa la entrada 1 como fondo, 0 deja negro
//          z = borde suave (fraccion del ancho de la pantalla)
//          w = sin uso

uniform vec4 uScreen;
uniform vec4 uMode;
out vec4 fragColor;

const float PI = 3.14159265358979;

void main() {
    vec2 uv = vUV.st;
    float lon = (uv.x - 0.5) * 2.0 * PI;
    float lat = (uv.y - 0.5) * PI;
    vec3 d = vec3(cos(lat) * sin(lon), sin(lat), cos(lat) * cos(lon));

    float az = radians(uScreen.x);
    float el = radians(uScreen.y);
    vec3 C = vec3(cos(el) * sin(az), sin(el), cos(el) * cos(az));
    vec3 R = normalize(cross(vec3(0.0, 1.0, 0.0), C));
    vec3 U = cross(C, R);

    float hh = radians(max(uScreen.z, 1.0)) * 0.5;
    float hv = radians(max(uScreen.w, 1.0)) * 0.5;
    float t = dot(d, C);
    float x, y;
    bool ok;
    if (uMode.x < 0.5) {
        ok = t > 0.001;
        float tt = max(t, 0.001);
        x = dot(d, R) / tt / tan(hh);
        y = dot(d, U) / tt / tan(hv);
    } else {
        ok = t > -0.999;
        x = atan(dot(d, R), t) / hh;
        y = asin(clamp(dot(d, U), -1.0, 1.0)) / hv;
    }
    vec2 suv = vec2(x, y) * 0.5 + 0.5;
    float b = max(uMode.z, 1e-4);
    float m = 0.0;
    if (ok) {
        m = smoothstep(0.0, b, suv.x) * smoothstep(0.0, b, 1.0 - suv.x)
          * smoothstep(0.0, b, suv.y) * smoothstep(0.0, b, 1.0 - suv.y);
    }
    vec4 col = texture(sTD2DInputs[0], clamp(suv, 0.0, 1.0));
    vec4 bg = (uMode.y > 0.5) ? texture(sTD2DInputs[1], uv) : vec4(0.0, 0.0, 0.0, 1.0);
    vec4 c = mix(bg, col, m);
    c.a = 1.0;
    fragColor = TDOutputSwizzle(c);
}
