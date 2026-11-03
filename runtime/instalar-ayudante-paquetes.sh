#!/usr/bin/env bash
# Instala el ayudante de paquetes de HexOS (runtime/hexos-paquetes) y la única regla de sudo
# que necesita. Lo ejecuta la persona, una vez, con sudo:
#
#   sudo runtime/instalar-ayudante-paquetes.sh [usuario]
#
# usuario: la cuenta que corre HexOS (por defecto, la que llamó a sudo). La regla le deja
# ejecutar SOLO /usr/local/libexec/hexos-paquetes sin contraseña; el ayudante decide qué se
# admite. Para retirarlo: sudo rm /usr/local/libexec/hexos-paquetes /etc/sudoers.d/hexos-paquetes
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo 'Ejecútalo con sudo.' >&2; exit 1; }
usuario=${1:-${SUDO_USER:-}}
[[ -n $usuario ]] && id "$usuario" >/dev/null || { echo 'Indica el usuario que corre HexOS.' >&2; exit 1; }
origen=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/hexos-paquetes
destino=/usr/local/libexec/hexos-paquetes
regla=/etc/sudoers.d/hexos-paquetes

install -d -m 755 -o root -g root /usr/local/libexec
install -m 755 -o root -g root "$origen" "$destino"
temporal=$(mktemp)
printf '%s ALL=(root) NOPASSWD: %s\n' "$usuario" "$destino" > "$temporal"
visudo -cf "$temporal" >/dev/null
install -m 440 -o root -g root "$temporal" "$regla"
rm -f "$temporal"
echo "Instalado $destino; $usuario puede ejecutarlo con sudo -n."
