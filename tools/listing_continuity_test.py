"""Regresión de búsqueda → muéstrame todas, sin depender de otra generación."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from hexos.agent import nas_files, nas_files_remote
from hexos.agent.chat import Agent
from hexos.agent.chat_backend.listing_followups import listing_followup
from hexos.agent.chat_backend.history_archive import history_page


class NoGeneration:
    def __init__(self): self.resets=0
    def call(self, request): self.resets += 1
    def generate(self, messages): raise AssertionError('No hace falta inferencia para mostrar todas las páginas')
    def announce(self, *args): raise AssertionError('Tampoco hace falta generar un anuncio')


class ContinuityTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.workspace=self.root/'work'
        self.folder=self.root/'Compartido'
        self.folder.mkdir()
        for n in range(39):
            (self.folder/('hnf-'+str(n).zfill(2)+'-'+'x'*80)).mkdir()
        self.runtime=NoGeneration()
        self.agent=Agent(self.workspace,self.runtime)

    def observe(self, workspace, device, request):
        return dict(nas_files_remote.collect(request),device=device,observed_at='2026-09-20')

    def seed(self, legacy=False):
        args=dict(device='nas', query='hnf', roots=[str(self.folder)],limit=2)
        with patch.object(nas_files,'observe',side_effect=self.observe):
            result=nas_files.directories(self.workspace,**args)
        if legacy: result.pop('snapshot_id')
        with self.agent.store() as store:
            store.db.execute('INSERT INTO conversation VALUES (?,?,?,?,?)',
                ('search','2026-09-20','user','hay algo similar llamado hnf dentro de compartido?','hnf'))
            store.db.execute('INSERT INTO tool_events(turn_id,ts,body) VALUES (?,?,?)',
                ('search','2026-09-20',json.dumps(dict(tool='nas.directories',arguments=args,result=result))))
            store.db.commit()
        return result

    def test_all_pages_without_network_or_model_and_restart(self):
        original=self.seed()
        self.agent=Agent(self.workspace,self.runtime)  # persisted trace and snapshot
        with patch.object(nas_files,'observe',side_effect=AssertionError('No debe reconectar')):
            result=self.agent.chat('muestrame todas')
        self.assertGreater(len(result['tools']),1)
        paths=[i['path'] for step in result['tools'] for i in step['result']['items']]
        self.assertEqual(len(paths),39)
        self.assertEqual(len(set(paths)),39)
        self.assertTrue(all(Path(p).name in result['reply'] for p in paths))
        self.assertEqual(result['tools'][0]['arguments']['snapshot_id'],original['snapshot_id'])
        self.assertIn('hnf',result['reply'])
        self.assertGreater(self.runtime.resets,0)

    def test_scoped_correction_does_not_switch_to_share_inventory(self):
        self.seed(legacy=True)
        with self.agent.store() as store:
            store.db.execute('INSERT INTO conversation VALUES (?,?,?,?,?)',
                ('wrong','2026-09-20','user','muestrame todas','muestrame todas'))
            store.db.execute('INSERT INTO tool_events(turn_id,ts,body) VALUES (?,?,?)',
                ('wrong','2026-09-20',json.dumps(dict(tool='nas.shares',arguments={'device':'nas'},
                    result=dict(items=[],device='nas',roots=[])))))
            store.db.commit()
        with patch.object(nas_files,'observe',side_effect=self.observe) as reader:
            result=self.agent.chat('todas las que estan en compartido macho no te enteras')
        self.assertEqual(reader.call_count,1)
        self.assertEqual(result['tools'][0]['tool'],'nas.directories')
        self.assertEqual(result['tools'][0]['arguments']['query'],'hnf')
        self.assertIn('(39)',result['reply'])

    def test_unrelated_topic_does_not_resurrect_search(self):
        self.seed()
        with self.agent.store() as store:
            for uid,text in [('topic','qué tiempo hace'),('now','muestrame todas')]:
                store.db.execute('INSERT INTO conversation VALUES (?,?,?,?,?)',(uid,'2026-09-20','user',text,text))
            store.db.commit()
            self.assertIsNone(listing_followup(store,'now','muestrame todas'))

    def test_tras_limpiar_el_chat_empieza_vacio_y_lo_anterior_queda_detras(self):
        # 18/11: «limpias contexto pero la conversación sigue en el chat» al recargar.
        from hexos.agent.chat_backend.context import LIMPIEZA
        from hexos.agent.chat_backend.persistence import clave
        with self.agent.store() as store:
            for n in range(6):
                store.db.execute('INSERT INTO conversation VALUES (?,?,?,?,?)',
                    ('a%d' % n,'2026-11-18','user' if n%2==0 else 'assistant','a','a'))
            corte = store.db.execute('SELECT MAX(rowid) FROM esta_ventana').fetchone()[0]
            store.db.execute('INSERT INTO agent_state VALUES (?,?)', (clave(store, LIMPIEZA), str(corte)))
            store.db.commit()
            vacia = history_page(store)
            self.assertEqual(vacia['messages'], [])
            self.assertTrue(vacia['has_more'])
            antes = history_page(store, before=vacia['next_before'])
            self.assertEqual([r['id'] for r in antes['messages']], ['a%d' % n for n in range(6)])
            for n in range(2):
                store.db.execute('INSERT INTO conversation VALUES (?,?,?,?,?)',
                    ('b%d' % n,'2026-11-18','user' if n%2==0 else 'assistant','b','b'))
            store.db.commit()
            nueva = history_page(store)
            self.assertEqual([r['id'] for r in nueva['messages']], ['b0', 'b1'])
            self.assertEqual([r['id'] for r in history_page(store, before=nueva['next_before'])['messages']],
                             ['a%d' % n for n in range(6)])

    def test_history_cursor_survives_new_messages_without_gaps(self):
        with self.agent.store() as store:
            for n in range(245):
                store.db.execute('INSERT INTO conversation VALUES (?,?,?,?,?)',
                    (str(n),'2026-09-20','user' if n%2==0 else 'assistant',str(n),str(n)))
            store.db.commit()
            first=history_page(store)
            store.db.execute('INSERT INTO conversation VALUES (?,?,?,?,?)',('new','2026-09-20','user','new','new'))
            store.db.commit()
            second=history_page(store,before=first['next_before'])
            third=history_page(store,before=second['next_before'])
            self.assertIsNone(third['next_before'])
            self.assertEqual([r['id'] for r in third['messages']+second['messages']+first['messages']],list(map(str,range(245))))
            for kwargs in ({'before':-1},{'limit':0},{'limit':101}):
                with self.assertRaises(ValueError): history_page(store,**kwargs)


if __name__=='__main__': unittest.main()
