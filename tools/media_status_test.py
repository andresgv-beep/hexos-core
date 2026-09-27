"""La tarjeta viva de la cola de vídeo: campos cerrados, progreso y controles."""
import json
from pathlib import Path
import tempfile
import unittest

from hexos.agent.chat_backend import media_http
from hexos.agent.media_jobs.store import JobStore
from hexos.agent.media_jobs.profiles import freeze


def source(i, folder='Parque Jurásico 3 [BDremux 1080 px]'):
    return dict(device='nas-fixture', path=f'/peliculas/{folder}/pelicula{i}.mkv',
                library_root='/peliculas', kind='movie',
                identity=dict(size_bytes=21_900_000_000, mtime_ns=1, inode=i, filesystem_id='1'))


def profile():
    return freeze('fixture-rf19', dict(PresetName='fixture', VideoEncoder='x264', FileFormat='av_mkv',
                                       VideoQualitySlider=19, VideoPreset='fast', AudioList=[]))


class MediaStatusTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = JobStore(self.root); self.addCleanup(self.store.close)

    def put(self, job_id, **changes):
        job = self.store.get(job_id)
        job.update(changes)
        with self.store.transaction():
            self.store._save(job)

    def test_no_queue_is_an_empty_list(self):
        self.assertEqual(media_http.summary(self.root/'otro'), dict(jobs=[]))

    def test_running_job_shows_progress_estimate_and_nothing_else(self):
        batch = self.store.create([source(1)], profile(), 'encoder', 'r1', 1000)
        job_id = batch['jobs'][0]['id']
        self.put(job_id, state='running', observation=dict(
            status='running', percent=64.0, eta_seconds=720, output_bytes=4_544_000_000, pid=7))
        card, = media_http.summary(self.root, now=1100)['jobs']
        self.assertEqual(card['title'], 'Parque Jurásico 3')
        self.assertEqual((card['label'], card['percent'], card['eta_seconds']), ('Convirtiendo', 64.0, 720))
        self.assertEqual((card['size_before_gb'], card['estimated_gb']), (21.9, 7.1))
        # La ruta, el perfil y los recibos no salen hacia la pantalla.
        self.assertNotIn('/peliculas', json.dumps(card))
        self.assertFalse({'source', 'profile', 'observation', 'pid'} & set(card))

    def test_early_progress_gives_no_size_estimate(self):
        job_id = self.store.create([source(1)], profile(), 'encoder', 'r1', 1000)['jobs'][0]['id']
        self.put(job_id, state='running', observation=dict(status='running', percent=2.0, output_bytes=10))
        card, = media_http.summary(self.root, now=1100)['jobs']
        self.assertNotIn('estimated_gb', card)

    def test_finished_jobs_stay_a_few_hours_then_leave_the_card(self):
        job_id = self.store.create([source(1)], profile(), 'encoder', 'r1', 1000)['jobs'][0]['id']
        self.put(job_id, state='completed', publication=dict(identity=dict(size_bytes=7_200_000_000)))
        self.store.event(job_id, 2000, 'transition', {})
        card, = media_http.summary(self.root, now=2000 + 3600)['jobs']
        self.assertEqual((card['label'], card['percent'], card['size_after_gb']), ('Terminada', 100.0, 7.2))
        self.assertEqual(media_http.summary(self.root, now=2000 + 7*3600)['jobs'], [])

    def test_controls_pause_and_cancel_the_batch(self):
        batch = self.store.create([source(1), source(2)], profile(), 'encoder', 'r1', 1000)
        paused = media_http.control(self.root, dict(batch_id=batch['id'], operation='pause'), now=1001)
        self.assertTrue(all(card['paused'] for card in paused['jobs']))
        cancelled = media_http.control(self.root, dict(batch_id=batch['id'], operation='cancel'), now=1002)
        self.assertEqual({card['state'] for card in cancelled['jobs']}, {'cancelled'})

    def test_controls_reject_anything_else(self):
        batch = self.store.create([source(1)], profile(), 'encoder', 'r1', 1000)
        for payload in (dict(batch_id=batch['id'], operation='delete'), dict(batch_id=batch['id']),
                        dict(batch_id=batch['id'], operation='pause', extra=1), dict(batch_id='', operation='pause')):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                media_http.control(self.root, payload, now=1001)


if __name__ == '__main__':
    unittest.main()
