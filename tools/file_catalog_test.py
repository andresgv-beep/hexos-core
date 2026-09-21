"""Contratos de la base de archivos, sin modelo, SSH ni NAS externo."""
import ast
import copy
from pathlib import Path
import tempfile
import unittest

from hexos.agent.file_catalog.service import FileCatalog
from hexos.agent.file_catalog.sqlite_repository import SQLiteCatalog, database
from hexos.agent.file_catalog.presentation import bounded_page
from hexos.agent import nas_files_remote


class CatalogContractTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.files = self.root / 'library'
        self.files.mkdir()
        self.workspace = self.root / 'catalog'
        self.reads = 0

        def reader(device, request):
            self.reads += 1
            return dict(nas_files_remote.collect(request), device=device or 'local-fixture',
                        observed_at='2026-09-20T12:00:00Z')

        self.service = FileCatalog(reader, SQLiteCatalog(self.workspace))

    def test_mixed_library_changes_and_offline_queries(self):
        for name in ('report.pdf', 'readme.md', 'song.mp3', 'film.mkv'):
            (self.files / name).write_bytes(b'fixture')
        first = self.service.find(roots=[str(self.files)])
        self.assertEqual(first['total_matches'], 4)
        old_id = first['scan_id']
        (self.files / 'readme.md').rename(self.files / 'guide.md')
        (self.files / 'film.mkv').write_bytes(b'new')
        (self.files / 'song.mp3').unlink()
        (self.files / 'another.pdf').write_bytes(b'new document')
        second = self.service.find(roots=[str(self.files)])
        self.assertNotEqual(old_id, second['scan_id'])
        self.assertEqual({i['name'] for i in second['items']}, {'report.pdf','guide.md','film.mkv','another.pdf'})
        self.assertEqual(next(i['size_bytes'] for i in second['items'] if i['name']=='film.mkv'), 3)

        def unavailable(device, request):
            self.fail('Una consulta local no debe usar el lector')

        restarted = FileCatalog(unavailable, SQLiteCatalog(self.workspace))
        pdfs = restarted.search(scan_id=second['scan_id'], extensions=['pdf'])
        self.assertEqual(pdfs['total_matches'], 2)
        old = restarted.search(scan_id=old_id)
        self.assertIn('song.mp3', {i['name'] for i in old['items']})
        self.assertIn('readme.md', {i['name'] for i in old['items']})
        self.assertGreater(restarted.locations()['total_matches'], 0)
        self.assertEqual(self.reads, 2)

    def test_failed_reader_does_not_replace_previous_catalog(self):
        (self.files / 'film.mkv').write_bytes(b'original')
        original = self.service.find(roots=[str(self.files)])
        def unavailable(device, request):
            raise OSError('fixture: NAS unavailable')
        service = FileCatalog(unavailable, SQLiteCatalog(self.workspace))
        with self.assertRaisesRegex(OSError, 'unavailable'):
            service.find(roots=[str(self.files)])
        self.assertEqual(service.search(scan_id=original['scan_id'])['total_matches'], 1)

    def test_publication_is_atomic_when_a_record_is_invalid(self):
        (self.files / 'a.pdf').write_bytes(b'pdf')
        observation = self.service.reader('fixture', {'operation':'index','roots':[str(self.files)]})
        observation['items'].append(dict(observation['items'][0], path=str(self.files/'bad.pdf'), size_bytes=None))
        import sqlite3
        with self.assertRaises(sqlite3.IntegrityError):
            SQLiteCatalog(self.workspace).publish(observation, [str(self.files)])
        db = database(self.workspace)
        try:
            for table in ('scans','files','directories','directory_imports'):
                self.assertEqual(db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0], 0)
        finally:
            db.close()

    def test_presentation_does_not_mutate_repository_records(self):
        (self.files / 'a.pdf').write_bytes(b'pdf')
        page = self.service.find(roots=[str(self.files)])
        raw = SQLiteCatalog(self.workspace).search(scan_id=page['scan_id'])
        expected = copy.deepcopy(raw)
        view = bounded_page(raw)
        self.assertEqual(raw, expected)
        self.assertIn('inode', raw['items'][0])
        self.assertNotIn('inode', view['items'][0])

    def test_service_accepts_store_without_sqlite(self):
        class MemoryStore:
            def locations(self, **kwargs):
                return dict(items=[], total_matches=0, offset=0, next_offset=None,
                            source='fixture', network_used=False)
        def reader(*args):
            raise AssertionError('No network for locations')
        self.assertEqual(FileCatalog(reader, MemoryStore()).locations()['total_matches'], 0)


class DependencyBoundaryTest(unittest.TestCase):
    def test_core_does_not_import_adapters_or_agent(self):
        base = Path(__file__).resolve().parents[1] / 'hexos/agent/file_catalog'
        for filename in ('service.py','ports.py','validation.py','presentation.py'):
            tree = ast.parse((base / filename).read_text())
            imports = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    imports.append(node.module or '')
            with self.subTest(module=filename):
                self.assertFalse(any(part in name for name in imports for part in
                    ('sqlite', 'ssh', 'hosts', 'nas_session', 'nas_files', 'chat', 'subprocess')))
        # Persistence must not know model-facing page budgets or remote access.
        tree = ast.parse((base / 'sqlite_repository.py').read_text())
        modules = [node.module or '' for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
        self.assertFalse(any(part in name for name in modules for part in ('presentation','ssh','hosts','chat')))


if __name__ == '__main__':
    unittest.main()
