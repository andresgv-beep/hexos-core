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

    def test_first_pass_without_output_gives_no_size_estimate(self):
        job_id = self.store.create([source(1)], profile(), 'encoder', 'r1', 1000)['jobs'][0]['id']
        self.put(job_id, state='running', observation=dict(status='running', percent=11.4, output_bytes=0))
        card, = media_http.summary(self.root, now=1100)['jobs']
        self.assertEqual(card['percent'], 11.4)
        self.assertNotIn('estimated_gb', card)

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

    def test_verified_film_waiting_to_publish_shows_its_final_size(self):
        job_id = self.store.create([source(1)], profile(), 'encoder', 'r1', 1000)['jobs'][0]['id']
        self.put(job_id, state='awaiting_review', review_kind='publication',
                 validation=dict(valid=True, identity=dict(size_bytes=6_073_919_068)))
        card, = media_http.summary(self.root, now=1100)['jobs']
        self.assertEqual((card['label'], card['percent'], card['size_after_gb']), ('Lista para publicar', 100.0, 6.1))

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


    def test_live_reading_replaces_the_stored_one(self):
        job_id = self.store.create([source(1)], profile(), 'encoder', 'r1', 1000, mode='live')['jobs'][0]['id']
        self.put(job_id, state='running', run_id='run-1', observation=dict(status='running', percent=2.4, eta_seconds=3917))
        class Fixed:
            def sample(self, job):
                return dict(run_id='run-1', status='running', percent=37.0, eta_seconds=2400, output_bytes=2_600_000_000)
        card, = media_http.summary(self.root, now=1100, progress=Fixed())['jobs']
        self.assertEqual((card['percent'], card['eta_seconds'], card['estimated_gb']), (37.0, 2400, 7.0))



class LiveProgressTest(unittest.TestCase):
    def setUp(self):
        self.now = [100.0]
        self.calls = []
        self.samples = [dict(run_id='r1', status='running', percent=41.5, eta_seconds=1800, output_bytes=3_000_000_000)]
        def observe(job):
            self.calls.append(job['id'])
            result = self.samples[0]
            if isinstance(result, Exception):
                raise result
            return result
        # spawn síncrono: la lectura «en segundo plano» ocurre en el acto.
        self.progress = media_http.LiveProgress(observe, clock=lambda: self.now[0], interval=20, spawn=lambda work: work())

    def test_reads_at_most_once_per_interval(self):
        job = dict(id='j1', run_id='r1')
        # La primera lectura arranca ahora; la respuesta de este momento aún no la tiene.
        self.assertIsNone(self.progress.sample(job))
        self.assertEqual(self.progress.sample(job)['percent'], 41.5)
        self.assertEqual(len(self.calls), 1)
        self.now[0] += 25
        self.progress.sample(job)
        self.assertEqual(len(self.calls), 2)

    def test_a_failed_read_keeps_the_last_one_and_retries_later(self):
        job = dict(id='j1', run_id='r1')
        self.progress.sample(job)
        self.samples[0] = media_http.UncertainEffect('SSH caído')
        self.now[0] += 25
        self.assertEqual(self.progress.sample(job)['percent'], 41.5)
        self.now[0] += 25
        self.progress.sample(job)
        self.assertEqual(len(self.calls), 3)

    def test_another_run_is_never_shown(self):
        self.progress.sample(dict(id='j1', run_id='r1'))
        self.assertIsNone(self.progress.sample(dict(id='j1', run_id='r2')))


if __name__ == '__main__':
    unittest.main()
