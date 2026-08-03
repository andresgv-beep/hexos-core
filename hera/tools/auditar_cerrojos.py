#!/usr/bin/env python3
"""
Audita que TODA puerta pública del almacén tome el cerrojo.

Existe por un fallo concreto: dos de las envolturas se aplicaron con un
reemplazo de texto que no encajó, el fichero compiló igual y las baterías
pasaron — porque ninguna ejercita esas dos funciones en paralelo.
`hera_store_registrar()`, que es la que usa `hera guarda`, se quedó escribiendo
sin cerrojo y podía repetir un id de hecho.

Un parche que no aplica es silencioso. Esto lo vuelve ruidoso: si mañana
alguien añade una función pública y olvida el cerrojo, la puerta falla y no
hace falta que a nadie se le ocurra la prueba de concurrencia adecuada.

Regla: toda función pública `hera_store_*` muta o lee el estado global, así que
tiene que llamar a `bloquear(`. Las exentas están listadas con su motivo — y
cada excepción hay que justificarla aquí, que es el punto.
"""

import re
import sys

EXENTAS = {
    "hera_veredicto_nombre": "función pura sobre un enum, no toca estado",
    "hera_estado_nombre": "función pura sobre un enum, no toca estado",
    "hera_store_ruta": "devuelve la ruta, fijada en abrir() y ya inmutable",
    "hera_store_cerrar": "suelta el descriptor del cerrojo; tomarlo aquí sería "
                         "cerrar la puerta con la llave dentro",
}


def main(ruta):
    with open(ruta, encoding="utf-8") as f:
        src = f.read()

    # Definiciones de nivel superior (no `static`): firma + cuerpo.
    patron = re.compile(
        r"^(?!static)(?:const char \*|bool|size_t|void|hera_veredicto_t|"
        r"hera_estado_t)\s*\**(\w+)\s*\([^;]*?\)\s*\{",
        re.MULTILINE | re.DOTALL)

    fallos = []
    revisadas = 0
    for m in patron.finditer(src):
        nombre = m.group(1)
        if nombre in EXENTAS:
            continue
        # Cuerpo por conteo de llaves desde la de apertura.
        i, prof = m.end() - 1, 0
        while i < len(src):
            if src[i] == "{":
                prof += 1
            elif src[i] == "}":
                prof -= 1
                if prof == 0:
                    break
            i += 1
        cuerpo = src[m.end():i]
        revisadas += 1
        if "bloquear(" not in cuerpo:
            fallos.append(nombre)

    for n in fallos:
        print(f"  \033[31m✗ {n}() no toma el cerrojo\033[0m")
    print(f"{revisadas} puertas públicas revisadas · {len(fallos)} sin cerrojo")
    if fallos:
        print("Si alguna debe quedar exenta, añádela a EXENTAS con su motivo.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "src/hera_store.c"))
