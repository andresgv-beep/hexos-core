# Instalar y quitar programas con plan, aprobación y comprobación

2026-11-03. Helios puede instalar y quitar programas en este PC, pero solo con tu aprobación
explícita, paso a paso y comprobado al final. Antes solo podía mirar (`terminal.read`) y darte
el comando para que lo ejecutaras tú.

## La cadena

1. **Planificar**, con la herramienta `system.package_plan` del modelo. Solo lee y simula:
   - averigua con qué gestor está el programa (apt, flatpak o snap) y su estado;
   - simula la operación: `apt-get -s remove|install` da los paquetes que saldrían o entrarían
     de verdad, dependencias incluidas;
   - rechaza en este paso lo que el ayudante no va a hacer: paquetes protegidos o una
     desinstalación que arrastra demasiado.
   El plan queda pendiente en la sesión y el modelo dice que espera tu aprobación, nunca que
   está hecho.
2. **Aprobar**, en la interfaz. La tarjeta enseña el plan y lo que entra o sale según la
   simulación, con dos botones: Cancelar y Aprobar. La aprobación llega por `/api/system`,
   fuera de la conversación.
3. **Ejecutar.** HexOS lanza `sudo -n /usr/local/libexec/hexos-paquetes GESTOR ACCIÓN PAQUETE`.
4. **Comprobar.** Una lectura independiente (`dpkg-query`, `flatpak info`, `snap list`) dice si
   el estado final es el esperado. «Hecho y comprobado» solo sale si las dos cosas cuadran.
5. **Anotar.** El resultado entra en la conversación como nota, para que Helios lo sepa en el
   turno siguiente.

## Por qué así

- **El modelo no tiene herramienta para aplicar.** Lo que lea en la web o en un documento puede
  hacer que proponga un plan, nunca que se ejecute: la ejecución solo llega por tu clic.
- **El ayudante es la puerta y se defiende solo** (`runtime/hexos-paquetes`, Python, sin shell):
  - lista cerrada: apt, flatpak (flathub, sistema) y snap; instalar o quitar; un paquete;
  - nombres validados con la gramática de cada gestor;
  - paquetes protegidos que nunca se quitan: núcleo, arranque, sudo, systemd, escritorio,
    NetworkManager, SSH, Tailscale, controladores y CUDA de NVIDIA, Python, snapd y flatpak;
  - una desinstalación de apt que arrastra un protegido o más de 15 paquetes se rechaza
    mirando su simulación, antes de ejecutar nada.
  - una instalación de apt que para entrar quitaría algún paquete (apt resuelve así los
    conflictos) se rechaza igual, desde su simulación.
  El plan usa esas mismas reglas, leídas del mismo fichero: hay una sola lista.
- **Un plan se ejecuta una vez.** Se retira de la sesión antes de lanzarlo, con un cerrojo
  propio. La interfaz se ve a la vez en el monitor y en el móvil: si dos pantallas aprueban a la
  vez, solo una lo toma y la otra recibe «lo decidió otra pantalla».
- **De uno en uno, y el modelo sabe que espera.** Solo hay una tarjeta. Mientras un plan está
  pendiente, cada turno se lo dice al modelo como dato («sigue esperando, no se ha aprobado ni
  rechazado»); pedir el mismo plan otra vez no crea uno nuevo, y pedir otro distinto devuelve
  que hay que decidir el primero. Sin esto, a «ya está, lo he aprobado» el E4B volvía a
  planificar y el 26B contaba que la aprobación se había procesado y algo había fallado.
- **Instalar exige decir el gestor.** De dónde sale el programa (apt, flatpak o snap) lo
  decides tú, no se adivina.

## Instalación (una vez, con sudo)

```
sudo runtime/instalar-ayudante-paquetes.sh
```

Copia el ayudante a `/usr/local/libexec/hexos-paquetes` (de root, 755) y añade
`/etc/sudoers.d/hexos-paquetes`, comprobado antes con `visudo`. La regla deja a tu usuario
ejecutar solo ese fichero sin contraseña. Para retirarlo:
`sudo rm /usr/local/libexec/hexos-paquetes /etc/sudoers.d/hexos-paquetes`.

Si el ayudante no está instalado, aprobar no rompe nada: la tarjeta dice que no se ejecutó y
por qué.

## Pruebas

`tools/system_packages_test.py` (21 pruebas, sin tocar el sistema): planes, rechazos, el
ayudante con su lista cerrada y sus protecciones, la aprobación y el rechazo, y dos pantallas
aprobando a la vez.
