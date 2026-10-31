"""Cobertura y cierres con runtime simulado, sin modelo ni acceso al NAS."""
import json
import tempfile
import unittest
from hexos.agent.chat import Agent
from hexos.agent.chat_backend.document_reading import coverage, enrich, progress, check_completion
from hexos.agent.chat_backend.state import TurnState
from hexos.agent.file_catalog import file_copies, file_access


class Runtime:
    def call(self, request):
        pass

    def generate(self, messages):
        return dict(reply='Sí, he leído todo el documento.', work=None)


class DocumentReadingTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.agent = Agent(self.tmp.name, Runtime())

    def tearDown(self):
        self.tmp.cleanup()

    def event(self, store, offset, count, file_id='a', failed=False):
        result = dict(file_id=file_id, name='Documento.md', offset=offset,
                      text='x'*count, total_characters=66978)
        result = enrich(store, 'nas.file_read', result)
        store.db.execute('INSERT INTO tool_events(turn_id,ts,body) VALUES (?,?,?)',
                         ('turn', 'now', json.dumps(dict(tool='nas.file_read', failed=failed, result=result))))
        store.db.commit()
        return result

    def test_union_duplicates_overlaps_gaps_and_eof(self):
        p = coverage(100, [(0, 10), (0, 10), (5, 20), (90, 100), (200, 200)])
        self.assertEqual(p['read_characters'], 30)
        self.assertEqual(p['continue_from'], 20)
        self.assertFalse(p['document_complete'])
        self.assertTrue(coverage(100, [(90, 100), (0, 90)])['document_complete'])
        self.assertTrue(coverage(0, [(0, 0)])['document_complete'])

    def test_reported_two_reads_and_restart(self):
        with self.agent.store() as store:
            self.event(store, 0, 4000)
            p = self.event(store, 4000, 4000)['reading_progress']
            self.assertEqual(p['read_characters'], 8000)
            self.assertEqual(p['remaining_characters'], 58978)
            self.assertEqual(p['percent'], 11.9)
            self.assertEqual(p['continue_from'], 8000)
            self.event(store, 0, 4000)
            self.event(store, 8000, 4000, failed=True)
            self.event(store, 0, 6000, file_id='different-copy')
        with Agent(self.tmp.name, Runtime()).store() as store:
            self.assertEqual(progress(store, 'a'), p)

    def test_viewer_read_does_not_count_for_model(self):
        item = file_copies.save(self.tmp.name, dict(name='x', text_available=True, observed_at='now'), '😀abc'.encode())
        file_access.read(self.tmp.name, file_id=item['file_id'])
        with self.agent.store() as store:
            self.assertIsNone(progress(store, item['file_id']))

    def test_retry_then_replaces_false_closure_without_progress(self):
        with self.agent.store() as store:
            self.event(store, 0, 8000)
            turn = TurnState('¿Lo has leído todo?')
            output = dict(reply='Sí, he leído todo.', work=None)
            self.assertTrue(check_completion(store, turn, output))
            self.assertIn('8000', turn.messages[0]['content'])
            self.assertFalse(check_completion(store, turn, output))
            self.assertIn('Documento completo: NO', output['reply'])
            self.assertNotIn('Sí, he leído todo', output['reply'])

    def test_partial_question_and_other_document_do_not_force_reads(self):
        with self.agent.store() as store:
            result = self.event(store, 0, 4000)
            turn = TurnState('Resume ese fragmento', trace=[dict(tool='nas.file_read', result=result)])
            output = dict(reply='Resumen parcial.', work=None)
            self.assertFalse(check_completion(store, turn, output))
            self.assertIn('Resumen parcial.', output['reply'])
            self.assertIn('Documento completo: NO', output['reply'])
            other = dict(reply='Buscaré otro archivo.', work=None)
            self.assertFalse(check_completion(store, TurnState('Lee completo otro documento'), other))
            self.assertEqual(other['reply'], 'Buscaré otro archivo.')

    def test_unicode_offsets_and_line_boundaries_reconstruct_exact_text(self):
        original = ('Español: escríbeme, piñón, acción 😀.\n' * 400) + 'fin 🚀'
        item = file_copies.save(self.tmp.name, dict(name='x', text_available=True, observed_at='now'),
                                original.encode('utf-8-sig'))
        offset, pieces = 0, []
        with self.agent.store() as store:
            while True:
                result = file_access.read(self.tmp.name, file_id=item['file_id'], offset=offset, count=333)
                self.assertEqual(result['offset_unit'], 'unicode_code_points')
                self.assertEqual(result['end_offset'], offset+len(result['text']))
                self.assertEqual(result['text'], original[offset:result['end_offset']])
                enriched = enrich(store, 'nas.file_read', result)
                store.db.execute('INSERT INTO tool_events(turn_id,ts,body) VALUES (?,?,?)',
                    ('unicode', 'now', json.dumps(dict(tool='nas.file_read', result=enriched))))
                pieces.append(result['text'])
                if result['next_offset'] is None:
                    break
                self.assertTrue(result['text'].endswith('\n'))
                self.assertGreater(result['next_offset'], offset)
                offset = result['next_offset']
            p = progress(store, item['file_id'])
            self.assertEqual(p['covered_ranges'], [[0, len(original)]])
            self.assertTrue(p['document_complete'])
            self.assertEqual(''.join(pieces), original)
        with self.assertRaises(ValueError):
            file_access.read(self.tmp.name, file_id=item['file_id'], offset=len(original)+1)

    def test_partial_response_is_preserved_with_backend_coverage(self):
        with self.agent.store() as store:
            result = self.event(store, 0, 4000)
            turn = TurnState('Cuéntame', trace=[dict(tool='nas.file_read', result=result)])
            output = dict(reply='En este fragmento aparece el registro de tensores.', work=None)
            self.assertFalse(check_completion(store, turn, output))
            self.assertIn('registro de tensores', output['reply'])
            self.assertIn('Documento completo: NO', output['reply'])

    def test_tool_budget_closes_honestly(self):
        with self.agent.store() as store:
            result = self.event(store, 0, 8000)
            turn = TurnState('Lee todo el documento', trace=[dict(tool='nas.file_read', result=result)]*48)
            output = dict(reply='He leído todo.', work=None)
            self.assertFalse(check_completion(store, turn, output))
            self.assertIn('58,978', output['reply'])

    def test_full_document_continues_past_six_calls_without_user_turn(self):
        item = file_copies.save(self.tmp.name, dict(name='Documento.md', text_available=True, observed_at='now'),
                                ('ñ'*66978).encode())
        class ReadingRuntime(Runtime):
            offset = 0
            results = []
            def generate(self, messages):
                if self.offset is None:
                    return dict(reply='He leído todo el documento.', work=None)
                return dict(tool='nas.file_read', arguments=dict(file_id=item['file_id'], offset=self.offset, count=4000))
            def tool_result(self, result):
                self.results.append(result)
                self.offset = result['next_offset']
        runtime = ReadingRuntime()
        agent = Agent(self.tmp.name, runtime)
        result = agent.chat('Lee todo el documento')
        self.assertEqual(len(result['tools']), 17)
        self.assertIn('Documento completo: SÍ', result['reply'])
        self.assertEqual(runtime.results[-1]['reading_progress']['continue_from'], None)
        with agent.store() as store:
            self.assertEqual(progress(store, item['file_id'])['read_characters'], 66978)
            events = [json.loads(row[0]) for row in store.db.execute('SELECT body FROM tool_events')]
            self.assertTrue(all(e['delivered_to_model'] for e in events))

    def test_reading_budget_does_not_expand_other_tools(self):
        from hexos.agent.chat_backend.reading_budget import exhausted
        turn = TurnState('Lee', trace=[dict(tool='nas.file_read')]*20)
        self.assertFalse(exhausted(turn, 'nas.file_read'))
        self.assertFalse(exhausted(turn, 'nas.find'))
        turn.trace.extend([dict(tool='nas.find')]*12)
        self.assertTrue(exhausted(turn, 'media.start'))
        self.assertFalse(exhausted(turn, 'nas.file_read'))
        turn.trace.extend([dict(tool='nas.file_read')]*28)
        self.assertTrue(exhausted(turn, 'nas.file_read'))

    def test_repeated_reads_stop_without_counting_duplicate_coverage(self):
        from hexos.agent.chat_backend.reading_budget import exhausted
        with self.agent.store() as store:
            turn = TurnState('Lee')
            for _ in range(3):
                result = self.event(store, 0, 4000)
                turn.trace.append(dict(tool='nas.file_read', result=result))
            self.assertTrue(exhausted(turn, 'nas.file_read'))
            self.assertEqual(progress(store, 'a')['read_characters'], 4000)

    def test_reading_time_budget(self):
        import time
        from hexos.agent.chat_backend.reading_budget import exhausted, MAX_READING_SECONDS
        turn = TurnState('Lee', reading_started=time.monotonic()-MAX_READING_SECONDS-1)
        self.assertTrue(exhausted(turn, 'nas.file_read'))

    def test_continuations_follow_progress_not_two_retry_limit(self):
        with self.agent.store() as store:
            turn = TurnState('Lee todo el documento')
            for offset in range(0, 20000, 4000):
                result = self.event(store, offset, 4000)
                turn.trace.append(dict(tool='nas.file_read', result=result))
                self.assertTrue(check_completion(store, turn, dict(reply='He leído todo.', work=None)))
            output = dict(reply='No puedo avanzar.', work=None)
            self.assertFalse(check_completion(store, turn, output))
            self.assertIn('No puedo avanzar.', output['reply'])
            self.assertIn('Documento completo: NO', output['reply'])

    def test_failed_delivery_does_not_count(self):
        with self.agent.store() as store:
            result = dict(file_id='x', name='x', text='abc', offset=0, total_characters=3)
            store.db.execute('INSERT INTO tool_events(turn_id,ts,body) VALUES (?,?,?)',
                ('delivery', 'now', json.dumps(dict(tool='nas.file_read', result=result, delivered_to_model=False))))
            self.assertIsNone(progress(store, 'x'))

    def test_chat_false_reassurance_is_not_saved(self):
        with self.agent.store() as store:
            self.event(store, 0, 4000)
            self.event(store, 4000, 4000)
        result = self.agent.chat('¿Lo has leído todo?')
        self.assertIn('Documento completo: NO', result['reply'])
        with self.agent.store() as store:
            saved = store.db.execute("SELECT text FROM conversation WHERE role='assistant' ORDER BY rowid DESC LIMIT 1").fetchone()[0]
            self.assertEqual(saved, result['reply'])


if __name__ == '__main__':
    unittest.main()
