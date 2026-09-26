"""Avisos de tareas en segundo plano: se cuentan una vez y caducan a los tres días."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from hexos.agent import task_notices
from hexos.agent.chat import Agent
from hexos.agent.work import WorkStore

MOVIE = '/volume1/peliculas/Parque Jurásico 2 [BDremux 1080 px][ES-EN]/ParqueJurasico2BDR1080.mkv'


class Runtime:
    def __init__(self, *replies):
        self.replies, self.inputs = iter(replies), []

    def generate(self, messages):
        self.inputs.append(repr(messages))
        return dict(reply=next(self.replies), work=None)

    def call(self, request):
        pass


def job(job_id, state, path=MOVIE, **extra):
    return dict(dict(id=job_id, state=state, source=dict(path=path, identity=dict(size_bytes=27_000_000_000)),
                     publication=dict(path=path.replace('.mkv', '.optimizada.mkv'),
                                      identity=dict(size_bytes=7_100_000_000)),
                     cleanup=dict(cleaned=True, original_removed=True)), **extra)


class Queue:
    def __init__(self, workspace):
        self.db = sqlite3.connect(Path(workspace)/'media_jobs.sqlite')
        self.db.execute('CREATE TABLE media_jobs (id TEXT PRIMARY KEY, state TEXT, revision INTEGER, body TEXT)')

    def put(self, value, revision=1):
        self.db.execute('INSERT OR REPLACE INTO media_jobs VALUES (?,?,?,?)',
                        (value['id'], value['state'], revision, json.dumps(value)))
        self.db.commit()


class TaskNoticesTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.workspace = self.temp.name
        self.queue = Queue(self.workspace)
        self.store = WorkStore(self.workspace)
        self.addCleanup(self.store.db.close)
        self.clock = [1000.0]

    def collect(self):
        task_notices.collect(self.store.db, self.workspace, clock=lambda: self.clock[0])

    def test_first_collection_counts_old_jobs_as_already_told(self):
        self.queue.put(job('old', 'completed'))
        self.collect()
        self.assertEqual(task_notices.pending(self.store.db), [])
        self.assertEqual(len(task_notices.recent(self.store.db)), 1)

    def test_new_endings_are_pending_once_and_skip_what_needs_no_telling(self):
        self.collect()
        self.queue.put(job('done', 'completed'))
        self.queue.put(job('gone', 'cancelled'))
        self.queue.put(job('internal', 'blocked', require_review=True))
        self.queue.put(job('broken', 'failed', path='/v/peliculas/Dune (2021)/dune.mkv', error='Salida vacía'))
        self.collect(); self.collect()
        pending = task_notices.pending(self.store.db)
        self.assertEqual([(n['title'], n['outcome']) for n in pending],
                         [('Parque Jurásico 2', 'terminada'), ('Dune', 'fallida')])
        done = pending[0]['body']
        self.assertEqual((done['size_before_gb'], done['size_after_gb'], done['original_replaced']), (27.0, 7.1, True))
        self.assertEqual(pending[1]['body']['error'], 'Salida vacía')

    def test_a_new_block_after_resuming_is_a_new_notice(self):
        self.collect()
        self.queue.put(job('j', 'blocked', require_review=False), revision=3)
        self.collect()
        task_notices.mark_reported(self.store.db, [n['key'] for n in task_notices.pending(self.store.db)], 't1')
        self.queue.put(job('j', 'blocked', require_review=False), revision=7)
        self.collect()
        self.assertEqual(len(task_notices.pending(self.store.db)), 1)

    def test_told_notices_leave_context_and_expire_after_three_days(self):
        self.collect()
        self.queue.put(job('done', 'completed'))
        self.collect()
        task_notices.mark_reported(self.store.db, ['media:done:completed'], 'turn', clock=lambda: self.clock[0])
        self.assertEqual(task_notices.pending(self.store.db), [])
        self.clock[0] += 3*24*3600 - 60
        self.collect()
        self.assertTrue(task_notices.recent(self.store.db)[0]['reported'])
        self.clock[0] += 120
        self.collect()
        self.assertEqual(task_notices.recent(self.store.db), [])

    def test_mention_ignores_accents_and_case(self):
        notices = [dict(title='Parque Jurásico 2', outcome='terminada', body={})]
        self.assertEqual(task_notices.unmentioned('Ya terminó parque jurasico 2, ocupa 7 GB.', notices), [])
        self.assertEqual(len(task_notices.unmentioned('¡Hola! ¿Qué tal?', notices)), 1)

    def test_history_request_is_recognised_and_greeting_is_not(self):
        for text in ('¿Qué tareas has terminado?', 'enséñame el historial de tareas',
                     '¿Ha terminado la película?', 'qué has hecho mientras dormía'):
            self.assertTrue(task_notices.HISTORY_REQUEST.search(text), text)
        self.assertIsNone(task_notices.HISTORY_REQUEST.search('Hola, buenos días'))


class TurnTest(unittest.TestCase):
    def test_greeting_hears_about_finished_job_and_only_once(self):
        with tempfile.TemporaryDirectory() as workspace:
            queue = Queue(workspace)
            WorkStore(workspace).db.close()
            agent = Agent(workspace, Runtime('¡Hola!', '¡Hola otra vez!', 'Hecho.'))
            first = agent.chat('Hola')          # siembra: nada que contar aún
            self.assertNotIn('segundo plano', first['reply'])
            queue.put(job('done', 'completed'))
            second = agent.chat('Hola de nuevo')
            self.assertIn('TAREAS EN SEGUNDO PLANO', agent.runtime.inputs[1])
            # El modelo no lo contó: lo añade HexOS y queda contado.
            self.assertIn('«Parque Jurásico 2»: terminada (27,0 → 7,1 GB)', second['reply'])
            third = agent.chat('¿Qué tareas has terminado?')
            self.assertNotIn('ACABARON DESDE TU ÚLTIMA', agent.runtime.inputs[2])
            self.assertIn('HISTORIAL DE TAREAS', agent.runtime.inputs[2])
            self.assertNotIn('segundo plano', third['reply'])


if __name__ == '__main__':
    unittest.main()
