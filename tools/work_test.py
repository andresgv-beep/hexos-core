"""Prueba del registro en un workspace temporal, sin GPU ni perfil personal."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tempfile
import unittest
from hexos.agent.work import WorkStore, strict_json


class WorkTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='hexos-work-')
        self.store = WorkStore(self.tmp.name)
        self.job = self.store.dispatch(dict(op='create', title='Disco del NAS',
            request='Comprueba cuánto espacio queda', source_ref='turn:1'), actor='user')

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def classify(self, actor, scope='NAS'):
        job = self.store.get(self.job['id'])
        return self.store.dispatch(dict(op='classify', id=job['id'], revision=job['revision'],
            kind='diagnostico', scope=scope, reason='Petición de espacio en disco',
            tags=['disco']), actor=actor)

    def test_proposal_and_user_correction_survive_restart(self):
        job = self.classify('model')
        self.assertIsNone(job['kind'])
        self.assertEqual(job['classification_proposal']['scope'], 'NAS')
        job = self.classify('user', 'Servidor de copias')
        job = self.classify('model', 'NAS')
        self.assertEqual(job['scope'], 'Servidor de copias')
        self.store.close()
        self.store = WorkStore(self.tmp.name)
        self.assertEqual(self.store.get(job['id']), job)
        history = self.store.dispatch(dict(op='history', id=job['id']), actor='user')
        self.assertEqual([e['actor'] for e in history], ['user', 'model', 'user', 'model'])

    def test_search_dates_and_pending_state(self):
        job = self.classify('user')
        job = self.store.dispatch(dict(op='update', id=job['id'], revision=job['revision'],
            state='bloqueado', next_step='Esperar conexión SSH', refs=['report:1']), actor='system')
        day = job['updated_at'][:10]
        found = self.store.listing(scope='NAS', query='conexión', since=day, until=day)
        self.assertEqual(found[0]['id'], job['id'])
        self.assertEqual(self.store.listing(scope='Casa'), [])
        self.assertEqual(self.store.listing(until='2000-01-01'), [])

    def test_rejects_stale_updates_without_partial_writes(self):
        other = WorkStore(self.tmp.name)
        try:
            self.classify('user')
            with self.assertRaises(ValueError):
                other.dispatch(dict(op='update', id=self.job['id'], revision=1,
                                    state='en_curso'), actor='system')
            self.assertEqual(other.get(self.job['id'])['state'], 'pendiente')
        finally:
            other.close()

    def test_invalid_calls_do_not_change_revision(self):
        calls = [
            (dict(op='classify', kind='destruir', scope='NAS', reason='x'), 'model'),
            (dict(op='update', state='terminado'), 'model'),
            (dict(op='update', state='terminado'), 'user'),
            (dict(op='update', command='reboot'), 'user'),
        ]
        for call, actor in calls:
            with self.assertRaises(ValueError):
                self.store.dispatch(call | dict(id=self.job['id'], revision=1), actor=actor)
        self.assertEqual(self.store.get(self.job['id']), self.job)

    def test_duplicate_json_key_rejected(self):
        with self.assertRaises(ValueError):
            strict_json('{"op":"list","op":"update"}')


if __name__ == '__main__':
    unittest.main()
