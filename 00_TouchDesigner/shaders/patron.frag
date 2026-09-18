// Patron de prueba del lienzo equirectangular. Sirve para saber, en la sala
// real o en la sala VR, donde cae cada parte del lienzo:
//   rojo     v 0.00-0.25   bajo el horizonte, lejos: no deberia verse en un domo 180
//   amarillo v 0.25-0.50   justo bajo el horizonte: tampoco deberia verse
//   verde    v 0.50-0.75   la cupula, del horizonte a 45 grados de elevacion
//   cian     v 0.75-1.00   la cupula, de 45 grados al cenit
//   negro    meridianos cada 45 grados de azimut (u cada 0.125); el de u = 0
//            es mas grueso: la costura del lienzo, azimut 180, detras
//   blanco   cuadro en u 0.5, v 0.75: el frente, a 45 grados de elevacion
//   magenta  marca en u 0.5, v 0.97: casi el cenit
// Con este patron se midio el 17 sep 2026 que en la sala VR el frente (u 0.5)
// cae en +X, que la cupula lee solo la mitad superior (verde abajo, cian
// arriba, nada de rojo ni amarillo) y que el cenit queda en el centro del
// domemaster. Las capturas estan en 05_Preview/pruebas/.
out vec4 fragColor;
void main() {
    vec2 uv = vUV.st;
    vec4 c;
    if (uv.y < 0.25)      c = vec4(1.0, 0.0, 0.0, 1.0);
    else if (uv.y < 0.5)  c = vec4(1.0, 1.0, 0.0, 1.0);
    else if (uv.y < 0.75) c = vec4(0.0, 1.0, 0.0, 1.0);
    else                  c = vec4(0.0, 1.0, 1.0, 1.0);
    if (mod(uv.x, 0.125) < 0.003) c = vec4(0.0, 0.0, 0.0, 1.0);
    if (uv.x < 0.012) c = vec4(0.0, 0.0, 0.0, 1.0);
    if (abs(uv.x - 0.5) < 0.03 && abs(uv.y - 0.75) < 0.06) c = vec4(1.0, 1.0, 1.0, 1.0);
    if (abs(uv.x - 0.5) < 0.015 && abs(uv.y - 0.97) < 0.03) c = vec4(1.0, 0.0, 1.0, 1.0);
    fragColor = TDOutputSwizzle(c);
}
