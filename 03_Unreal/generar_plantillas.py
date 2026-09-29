"""Regenera ArmarPlantilla() de DomeMediaController.cpp desde 00_TouchDesigner/video_dome/plantillas_ue.json.

Las plantillas de pantallas 16:9 se definen en TouchDesigner (video_dome/screens_module.py). TouchDesigner
escribe plantillas_ue.json con la tabla final; este script la convierte en el codigo C++ del ejecutable,
para que los montajes de Unreal tengan las mismas cifras. Correr despues de cambiar plantillas y antes de
empaquetar:  python 03_Unreal/generar_plantillas.py
"""
import json
import os

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(RAIZ, "03_Unreal", "DomoVR", "Source", "DomoVR")
plant = json.load(open(os.path.join(RAIZ, "00_TouchDesigner", "video_dome", "plantillas_ue.json"), encoding="utf-8"))["plantillas"]

def f(x):
    v = float(x)
    if v == int(v):
        return "%d.f" % int(v)
    return ("%.4f" % v).rstrip("0") + "f"


lineas = []
lineas.append("\t/** Las plantillas de video_dome/screens_module.py (TouchDesigner), a las mismas cifras.")
lineas.append("\t *  GENERADO por 03_Unreal/generar_plantillas.py desde 00_TouchDesigner/video_dome/plantillas_ue.json: no editar a mano. */")
lineas.append("\tTArray<FDomePantallaFila> ArmarPlantilla(const FString& Id)")
lineas.append("\t{")
lineas.append("\t\tTArray<FDomePantallaFila> R;")
primero = True
for pid, filas in plant.items():
    lineas.append("\t\t%s (Id == TEXT(\"%s\"))" % ("if" if primero else "else if", pid))
    primero = False
    lineas.append("\t\t{")
    for i, r in enumerate(filas):
        v = "F%d" % i
        lineas.append("\t\t\t{")
        lineas.append("\t\t\t\tFDomePantallaFila F = Fila(TEXT(\"%s\"), %s, %s, %s, %s, %d);" % (r["name"], f(r["yaw"]), f(r["pitch"]), f(r["hfov"]), f(r["vfov"]), int(r["mode"])))
        campos = [
            ("Roll", r["roll"], 0), ("Espejo", int(r["mirror"]), 0), ("Opacidad", r["opacity"], 1),
            ("CropX", r["cropx"], 0), ("CropY", r["cropy"], 0), ("CropW", r["cropw"], 1), ("CropH", r["croph"], 1),
            ("Borde", r["feather"], 0.04), ("Repeticion", r["tile"], 1), ("Solape", r["blend"], 0),
            ("Copias", int(r["rep"]), 1), ("Arco", r["repspan"], 360), ("Corrimiento", r["repofs"], 0),
            ("Recorrido", r["travel"], 0), ("Giro", r["spin"], 0), ("Bordes", int(r["edges"]), 0), ("Brillo", r["spare"], 0),
        ]
        sets = []
        for nombre, val, defecto in campos:
            if abs(float(val) - float(defecto)) > 1e-9:
                if nombre in ("Espejo", "Copias", "Bordes"):
                    sets.append("F.%s = %d;" % (nombre, int(val)))
                else:
                    sets.append("F.%s = %s;" % (nombre, f(val)))
        if int(r["repmir"]):
            sets.append("F.bEspejoAlterno = true;")
        if int(r["on"]) == 0:
            sets.append("F.bEncendida = false;")
        for s_ in sets:
            lineas.append("\t\t\t\t" + s_)
        lineas.append("\t\t\t\tR.Add(F);")
        lineas.append("\t\t\t}")
    lineas.append("\t\t}")
lineas.append("\t\telse { R.Add(Fila(TEXT(\"cine\"), 0, 45, 70, 39)); }")
lineas.append("\t\treturn R;")
lineas.append("\t}")
lineas.append("")
bloque = "\n".join(lineas) + "\n"


ruta = os.path.join(D, "DomeMediaController.cpp")
c = open(ruta, encoding="utf-8").read()
i = c.index("	/** Las plantillas de video_dome/screens_module.py (TouchDesigner), a las mismas cifras.")
j = c.index("	/** Una fila desde la vieja \"pantalla\" unica de la playlist. */")
c = c[:i] + bloque + c[j:]
open(ruta, "w", encoding="utf-8").write(c)
print("ArmarPlantilla regenerada con", len(plant), "plantillas")
