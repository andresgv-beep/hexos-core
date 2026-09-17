"""Aceptación conversacional real, con almacenes temporales y snapshot opcional.

Requiere GPU libre. El informe de salida contiene conversación privada.
"""
import argparse
import json
import re
from pathlib import Path
import sqlite3
import sys
import tempfile
import unicodedata
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hexos.agent.chat import Agent
from hexos.agent.native import NativeRuntime


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--runtime', required=True)
    p.add_argument('--model', required=True)
    p.add_argument('--template', required=True)
    p.add_argument('--source')
    p.add_argument('--rows', type=int, nargs='+', default=[54, 56])
    p.add_argument('--social', action='store_true', help='También probar charla con trabajo antiguo guardado')
    p.add_argument('--thinking', action='store_true')
    p.add_argument('--output', required=True)
    a = p.parse_args()
    output = Path(a.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    records = []
    with tempfile.TemporaryDirectory(prefix='hexos-conversation-live-') as tmp:
        root = Path(tmp)
        runtime = NativeRuntime(a.runtime, a.model, 8192, root, a.template, thinking=a.thinking)
        def turn(agent, label, request, expected=None):
            try:
                result = agent.chat(request)
                normalized = ''.join(c for c in unicodedata.normalize('NFD', result['reply'].lower())
                                     if not unicodedata.combining(c))
                row = dict(case=label, request=request, result=result,
                           expected_name=expected, name_present=expected in normalized if expected else None)
                if label in ('replay_60','replay_62','replay_64') or label.startswith('social_'):
                    row['internal_details'] = bool(re.search(r'\b[a-f0-9]{32}\b|result_id|encargo persistente|perfil confirmado|petici[oó]n actual', result['reply'], re.I))
                if label == 'resume_old_work':
                    row['recovered_result'] = (any(t['tool']=='result.get' and isinstance(t['result'],dict) and 'text' in t['result'] for t in result['tools']) or
                        any(s['tool']=='result.get' and s.get('text') and 'error' not in s for s in result.get('context_sources', [])))
                    row['recovered_result'] = row['recovered_result'] and 'nas' in normalized
                if label == 'change_topic':
                    row['ideas_provided'] = 'herramientas para generar ideas' not in normalized and len(result['reply']) > 50
                if label in ('network', 'network_colloquial'):
                    row['network_read'] = any(t['tool']=='network.local' and
                        t.get('result', {}).get('passive') is True for t in result['tools'])
            except Exception as exc:
                row = dict(case=label, request=request, error=str(exc))
            with agent.store() as store:
                uid = store.db.execute("SELECT id FROM conversation WHERE role='user' ORDER BY rowid DESC LIMIT 1").fetchone()[0]
                row['generations'] = [json.loads(r[0]) for r in store.db.execute(
                    'SELECT body FROM generation_events WHERE turn_id=? ORDER BY seq', (uid,))]
            records.append(row)
            output.write_text(json.dumps(records, ensure_ascii=False, indent=2))
            print(json.dumps({k:v for k,v in row.items() if k!='generations'}, ensure_ascii=False), flush=True)
            return row
        try:
            if a.source:
                src = sqlite3.connect(Path(a.source).resolve().as_uri()+'?mode=ro', uri=True)
                for target in a.rows:
                    folder = root / str(target)
                    folder.mkdir()
                    db = sqlite3.connect(folder / 'work.sqlite')
                    src.backup(db)
                    request = db.execute('SELECT text FROM conversation WHERE rowid=?', (target,)).fetchone()[0]
                    db.execute('DELETE FROM tool_events WHERE turn_id IN (SELECT id FROM conversation WHERE rowid>=?)', (target,))
                    db.execute('DELETE FROM conversation WHERE rowid>=?', (target,))
                    db.commit()
                    db.close()
                    turn(Agent(folder, runtime), f'replay_{target}', request, 'andres' if target in (54,56) else None)
                if a.social:
                    folder = root / 'social'
                    folder.mkdir()
                    db = sqlite3.connect(folder / 'work.sqlite')
                    src.backup(db)
                    db.execute('DELETE FROM tool_events WHERE turn_id IN (SELECT id FROM conversation WHERE rowid>=58)')
                    db.execute('DELETE FROM conversation WHERE rowid>=58')
                    db.commit()
                    db.close()
                    social = Agent(folder, runtime)
                    for i, request in enumerate(['hola helios','que tal va todo?','y que quiere decir eso?','vale.']):
                        turn(social, f'social_{i}', request)
                    turn(social, 'resume_old_work', 'Volvamos al resumen de trabajos que preparaste antes. Recupera el resultado y dime qué había pendiente.')
                    # Recorrido real: la ficha del NAS no equivale a una revisión del dispositivo.
                    social.clear_context()
                    for i, request in enumerate(['hola socio', 'como estan los sistemas?', 'mi nas',
                                                 'si revisalo', 'si']):
                        turn(social, f'device_{i}', request)
                src.close()
            agent = Agent(root / 'clean', runtime)
            for label, request, expected in [
                ('introduce','Me llamo Marta.',None),
                ('recall','¿Cómo me llamo?','marta'),
                ('correct','Corrijo mi nombre: soy Elena.',None),
                ('change_topic','Dame dos ideas para organizar un inventario.',None),
                ('return','Volviendo a lo de antes, ¿cómo me llamo?','elena'),
                ('tool','Consulta los procedimientos disponibles y dime cuáles hay.',None),
            ]:
                turn(agent, label, request, expected)
            agent.clear_context()
            runtime.close()
            runtime = NativeRuntime(a.runtime, a.model, 8192, root, a.template, thinking=a.thinking)
            agent = Agent(root / 'clean', runtime)
            turn(agent, 'reset_restart', '¿Cómo me llamo?', 'elena')
            turn(agent, 'unknown', '¿En qué ciudad vivo? No te lo he dicho.', None)
            turn(agent, 'network', 'Consulta las IP que conoce este equipo en la red local y dime cuáles ves. Distingue entradas antiguas de vecinos alcanzables recientemente.')
            agent.clear_context()
            turn(agent, 'network_colloquial', 'socio busca ip en toda la red')
            turn(agent, 'network_accept', 'eso te queria decir')
            turn(agent, 'network_insist', 'pues hazlo')
            inventory = Agent(root / 'inventory', runtime)
            fake = dict(observed_at='2026-09-12T12:00:00Z', truncated=False, note='Simulación de laboratorio',
                        neighbors=[dict(ip='192.168.1.10', mac='aa:bb:cc:dd:ee:ff', interface='eth0', state=['STALE'])])
            with patch('hexos.agent.devices.snapshot', return_value=fake):
                turn(inventory, 'inventory_save', 'Guarda los dispositivos de la red en el inventario.')
                turn(inventory, 'inventory_identify', 'Recuerda: 192.168.1.10 es mi NAS Faro.')
                turn(inventory, 'inventory_correct', 'Corrige el nombre: 192.168.1.10 es mi NAS Puerto.')
            inventory.clear_context()
            turn(inventory, 'inventory_recall', 'Consulta el inventario y dime qué IP tiene mi NAS Puerto.')
            with inventory.store() as s:
                saved = inventory.tool(s, 'device.list', {'scope': 'unidentified'})['items']
                if len(saved) != 1 or not saved[0]['identity'] or 'Puerto' not in saved[0]['identity']['name']:
                    records.append(dict(case='inventory_persistence', error='Identificación o corrección no persistida'))
                    output.write_text(json.dumps(records, ensure_ascii=False, indent=2))
            suffix_agent = Agent(root / 'suffix_inventory', runtime)
            suffix_data = dict(fake, neighbors=[dict(ip='192.168.1.'+str(n), mac=f'aa:bb:cc:dd:ee:{n:02x}',
                                interface='eth0',state=['STALE']) for n in (243,131,249)])
            with suffix_agent.store() as s, patch('hexos.agent.devices.snapshot', return_value=suffix_data):
                suffix_agent.tool(s,'device.refresh',{})
            turn(suffix_agent, 'inventory_suffix', 'guara el que termina en 243 como synology, el 131 como nimos nas')
            turn(suffix_agent, 'inventory_saved_names', 'Consulta las guardadas: ¿tienes synology o nimos nas?')
            with patch('hexos.agent.chat.network_snapshot', return_value=suffix_data):
                identified = turn(suffix_agent, 'network_identified', 'vuelve a buscar ips y identificalas')
            result=identified.get('result',{})
            reply=result.get('reply','').casefold()
            if ('synology' not in reply or 'nimos' not in reply or
                not any(t['tool']=='network.local' for t in result.get('tools',[])) or
                any(t['tool']=='device.identify' for t in result.get('tools',[]))):
                records.append(dict(case='network_identity_read',error='No recuperó nombres mediante lectura'))
                output.write_text(json.dumps(records, ensure_ascii=False, indent=2))
            with suffix_agent.store() as s:
                saved = suffix_agent.tool(s, 'device.list', {'scope': 'unidentified'})['items']
                names = {d['latest_addresses'][0]['ip']:d['identity']['name'].casefold() if d['identity'] else None for d in saved}
                if names != {'192.168.1.243':'synology','192.168.1.131':'nimos nas','192.168.1.249':None}:
                    records.append(dict(case='suffix_persistence',error='Nombres o direcciones incorrectos', names=names))
                    output.write_text(json.dumps(records, ensure_ascii=False, indent=2))
        finally:
            runtime.close()
    failures = [r['case'] for r in records if 'error' in r or r.get('name_present') is False or r.get('internal_details')
                or r.get('recovered_result') is False or r.get('ideas_provided') is False
                or r.get('network_read') is False]
    if failures:
        raise SystemExit('Revisar: ' + ', '.join(failures))


if __name__ == '__main__':
    main()
