"""Recuperación explícita: historial literal y perfil confirmado por HERA."""
import os
from pathlib import Path
import re
import subprocess


class HeraProfile:
    def __init__(self, binary, home):
        self.binary = str(Path(binary).resolve())
        self.home = str(Path(home).resolve())
        # Ids de hechos que la última lectura no pudo interpretar. Vacío no
        # significa que no existan: significa que se leyeron todos.
        self.unreadable = []

    def read(self):
        result = subprocess.run([self.binary, 'perfil-agente'],
            env=dict(os.environ, HELIOS_HOME=self.home), capture_output=True,
            text=True, timeout=10)
        if result.returncode:
            raise RuntimeError('No se pudo recuperar HERA; no se continúa con un perfil vacío')
        value = result.stdout.strip()
        return '' if value == '(perfil vacío: nada confirmado todavía)' else value

    def say(self, text):
        """Registra un enunciado de la persona y devuelve su id. HERA solo acepta
        como evidencia un dicho suyo ya registrado, no una cita suelta."""
        result = subprocess.run([self.binary, 'dijo', text],
            env=dict(os.environ, HELIOS_HOME=self.home), capture_output=True,
            text=True, timeout=10)
        identifier = (result.stdout or '').strip()
        if result.returncode or not identifier:
            raise ValueError('HERA no registró el mensaje como evidencia')
        return identifier

    # Respaldo para un HERA anterior a `lista --bruto`: sus columnas son
    # "%-5s %-11s %-28s %s", y ese ancho es MÍNIMO, no máximo.
    CLAVE_DESDE, CLAVE_HASTA = 18, 46

    def keys(self):
        """Claves confirmadas. Devuelve solo las que se han podido leer.

        `unreadable` lista las que no. La diferencia importa: una clave ilegible no
        es una clave ausente, y confundirlas hace creer que un dato guardado no
        está —y entonces se vuelve a guardar en vez de corregirlo.
        """
        claves, ilegibles = self._listar()
        self.unreadable = ilegibles
        return claves

    def _listar(self):
        bruto = subprocess.run([self.binary, 'lista', '--bruto'],
            env=dict(os.environ, HELIOS_HOME=self.home), capture_output=True,
            text=True, timeout=10)
        if not bruto.returncode and '\t' in (bruto.stdout or ''):
            # Campos separados por tabulador: no hay columnas que desbordar.
            claves = {}
            for line in bruto.stdout.splitlines():
                campos = line.split('\t')
                if len(campos) >= 4 and campos[1] == 'confirmado':
                    claves[campos[2]] = campos[3]
            return claves, []
        result = subprocess.run([self.binary, 'lista'],
            env=dict(os.environ, HELIOS_HOME=self.home), capture_output=True,
            text=True, timeout=10)
        if result.returncode:
            raise ValueError('HERA no devolvió la lista de hechos')
        claves, ilegibles = {}, []
        for line in (result.stdout or '').splitlines():
            campos = line.split(None, 2)
            if len(campos) < 3 or campos[1] != 'confirmado':
                continue
            if len(line) <= self.CLAVE_HASTA or line[self.CLAVE_HASTA - 1] != ' ':
                # Clave desbordada: no se puede separar sin adivinar. Se anota como
                # ilegible, no como inexistente.
                ilegibles.append(campos[0])
                continue
            clave = line[self.CLAVE_DESDE:self.CLAVE_HASTA].strip()
            valor = re.split(r'\s+->\s|\s{2,}\[', line[self.CLAVE_HASTA:])[0].strip()
            if clave:
                claves[clave] = valor
        return claves, ilegibles

    def correct(self, key, value, text, evidence):
        """Reemplaza un hecho vigente. HERA lo hace de forma atómica y conserva
        la cadena: `hera historial <clave>` la enseña entera."""
        dicho = self.say(evidence)
        return self._run(['corrige', key, value, text, dicho, dicho])

    def remember(self, key, value, text, evidence):
        """Confirma un hecho en el perfil. `guarda` y no `propon`: el agente solo
        lee confirmados, así que un candidato se quedaría invisible para siempre.

        `evidence` es el texto de la persona; aquí se registra con `dijo` para
        obtener el id que HERA exige. Y la clave lleva sujeto: `yo/nombre`, no
        `nombre`, o la rechaza por sujeto_ajeno.
        """
        return self._run(['guarda', key, value, text, self.say(evidence)])

    def _run(self, args):
        result = subprocess.run([self.binary] + args,
            env=dict(os.environ, HELIOS_HOME=self.home), capture_output=True,
            text=True, timeout=10)
        salida = (result.stdout or '').strip()
        # HERA rechaza con código de salida 0 y un "rechazado: <motivo>" en stdout.
        # Mirar solo returncode daba por guardado lo que nunca entró en el perfil.
        if result.returncode or salida.startswith('rechazado'):
            detalle = salida or (result.stderr or '').strip()
            raise ValueError('HERA no guardó el dato' + (': ' + detalle if detalle else ''))
        return salida


def history_tool(store, name, args):
    if name == 'history.recent':
        rows = store.db.execute('SELECT id,ts,role,text FROM conversation ORDER BY rowid DESC LIMIT 20').fetchall()[::-1]
        return {'messages': [dict(id=r['id'], ts=r['ts'], role=r['role'], excerpt=r['text'][:500])
                             for r in rows], 'historical_data': True, 'order':'oldest_to_newest'}
    if name == 'history.search':
        query = args['query']
        # LIKE literal: ni comodines ni SQL aportado por el modelo.
        query = query.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        rows = store.db.execute("SELECT id,ts,role,text FROM conversation "
            "WHERE text LIKE ? ESCAPE '\\' ORDER BY rowid DESC LIMIT 20",
            ('%' + query + '%',)).fetchall()[::-1]
        return {'matches': [dict(id=r['id'], ts=r['ts'], role=r['role'],
                                  excerpt=r['text'][:500]) for r in rows],
                'historical_data': True, 'limit': 20,
                'order': 'oldest_to_newest',
                'search_type': 'literal_substring',
                'note': 'Cero coincidencias no demuestra ausencia. Prueba una palabra más corta o history.recent.'}
    row = store.db.execute('SELECT id,ts,role,text FROM conversation WHERE id=?',
                           (args['id'],)).fetchone()
    if row is None:
        raise ValueError('mensaje inexistente')
    start = args.get('start', 0)
    if not 0 <= start <= len(row['text']):
        raise ValueError('posición fuera del mensaje')
    end = min(start + 6000, len(row['text']))
    return dict(id=row['id'], ts=row['ts'], role=row['role'], text=row['text'][start:end],
                next_start=end if end < len(row['text']) else None, historical_data=True)
