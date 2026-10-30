"""Directorios y recursos compartidos: lectura actual distinta de archivos y memoria."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from hexos.agent import nas_files, nas_files_remote, nas_shares_remote
from hexos.agent.chat_backend.state import default_nas_files, AgentDependencies
from hexos.agent.chat import Agent
from hexos.agent.chat_backend.file_requests import validate_file_request, explicit_directory_read, explicit_share_read
from hexos.agent.chat_backend.file_responses import file_listing_reply


class DirectoryTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / 'volume'
        self.root.mkdir()
        self.workspace = self.base / 'workspace'

    def observe(self, workspace, device, request):
        module = nas_shares_remote if request['operation'] == 'shares' else nas_files_remote
        return dict(module.collect(request), device=device or 'nas', observed_at='2026-09-20T20:00:00Z')

    def search(self, **kwargs):
        with patch.object(nas_files, 'observe', side_effect=self.observe):
            return default_nas_files(self.workspace, operation='directories', device='nas',
                                     roots=[str(self.root)], **kwargs)

    def test_empty_directories_case_and_literal_name_are_not_files(self):
        (self.root / 'HNF9').mkdir()
        (self.root / 'HNFV9').mkdir()
        (self.root / 'hnf9.pdf').write_text('file')
        result = self.search(query='hnf9', exact=True)
        self.assertEqual([i['name'] for i in result['items']], ['HNF9'])
        self.assertEqual(self.search(query='HNF9', exact=True)['items'], result['items'])
        self.assertEqual(nas_files.locations(self.workspace, query='hnf9')['total_matches'], 1)
        self.assertTrue(result['network_used'])

    def test_saved_locations_ignore_accents_and_case(self):
        (self.root / 'peliculas').mkdir()
        (self.root / 'Películas antiguas').mkdir()
        self.search(query='')
        for q in ('películas', 'PELICULAS', 'peliculas'):
            self.assertEqual(nas_files.locations(self.workspace, query=q)['total_matches'], 2, q)

    def test_nested_roots_empty_folder_and_pagination(self):
        for index in range(4):
            (self.root / ('folder'+str(index))).mkdir()
        first = self.search(limit=2)
        second = self.search(limit=2, offset=first['next_offset'])
        self.assertEqual(first['total_matches'], 5)  # includes the observed root
        self.assertEqual(len({i['path'] for i in first['items'] + second['items']}), 4)
        with patch.object(nas_files_remote, 'discover_data_roots', return_value=([str(self.root)], [])), \
             patch.object(nas_files, 'observe', side_effect=self.observe):
            result = nas_files.directories(self.workspace, query='folder3')
        self.assertEqual(result['total_matches'], 1)

    def test_failure_is_partial_and_symlink_is_not_traversed(self):
        (self.root / 'link').symlink_to(self.base, target_is_directory=True)
        (self.root / 'private').mkdir()
        original = nas_files_remote.open_directory
        def opened(path):
            if path.endswith('/private'):
                raise PermissionError(13, 'fixture')
            return original(path)
        with patch.object(nas_files_remote, 'open_directory', side_effect=opened):
            result = self.search(query='missing')
        self.assertFalse(result['complete'])
        self.assertFalse(result['total_is_exact'])
        self.assertEqual(result['total_matches'], 0)
        self.assertEqual(result['skipped']['symlinks'], 1)
        self.assertGreater(result['error_count'], 0)

    def test_live_search_observes_renames_instead_of_saved_locations(self):
        (self.root / 'HNF9').mkdir()
        self.assertEqual(self.search(query='HNF9')['total_matches'], 1)
        (self.root / 'HNF9').rename(self.root / 'changed')
        self.assertEqual(self.search(query='HNF9')['total_matches'], 0)
        self.assertEqual(nas_files.locations(self.workspace, query='HNF9')['total_matches'], 1)

    def test_share_configuration_is_distinct_from_arbitrary_folders(self):
        config = self.base / 'shares.conf'
        config.write_text('[Photos]\npath='+str(self.root)+'\n[Unavailable]\npath='+str(self.base/'absent')+'\n')
        (self.root / 'not a share').mkdir()
        with patch.object(nas_shares_remote, 'CONFIG_PATH', str(config)), \
             patch.object(nas_files, 'observe', side_effect=self.observe):
            result = default_nas_files(self.workspace, operation='shares', device='nas')
        self.assertTrue(result['complete'])
        self.assertEqual({i['name'] for i in result['items']}, {'Photos', 'Unavailable'})
        self.assertIn('Sin acceso', next(i['access'] for i in result['items'] if i['name']=='Unavailable'))

    def test_unavailable_or_included_configuration_does_not_claim_full_listing(self):
        with patch.object(nas_shares_remote, 'CONFIG_PATH', str(self.base/'missing')):
            self.assertFalse(nas_shares_remote.collect({})['complete'])
        config = self.base/'shares.conf'
        config.write_text('[global]\ninclude=/unread.conf\n')
        with patch.object(nas_shares_remote, 'CONFIG_PATH', str(config)):
            self.assertFalse(nas_shares_remote.collect({})['complete'])

    def test_remote_shares_script_runs_without_package_installed(self):
        command = nas_files.remote_command({'operation':'shares'})
        raw = subprocess.check_output(command, shell=True, cwd=self.base, text=True)
        self.assertIn(nas_files_remote.MARKER, raw)

    def test_dispatch_passes_device_and_directory_operation(self):
        calls=[]
        def files(workspace, **kwargs):
            calls.append(kwargs)
            return dict(items=[], complete=True)
        agent = Agent(self.workspace, runtime=None, dependencies=AgentDependencies(nas_files=files))
        with agent.store() as store:
            result = agent.dispatcher.dispatch(store, 'nas.directories', {'device':'nas','query':'HNF9'})
        self.assertTrue(result['complete'])
        self.assertEqual(calls[0]['operation'], 'directories')
        self.assertEqual(calls[0]['query'], 'HNF9')

    def test_current_literal_cannot_be_replaced_with_historical_name(self):
        text = 'Busca por todo el Synology 1 una carpeta llamada HNF9.'
        with self.assertRaisesRegex(ValueError, 'HNF9'):
            validate_file_request(text, 'nas.directories', {'query':'HNFV9'})
        validate_file_request(text, 'nas.directories', {'query':'hnf9'})
        with self.assertRaisesRegex(ValueError, 'nas.directories'):
            validate_file_request(text, 'nas.find', {'query':'HNF9'})

    def test_quoted_names_and_approximate_requests(self):
        with self.assertRaises(ValueError):
            validate_file_request('Busca la carpeta llamada "Mis fotos"', 'nas.directories', {'query':'fotos'})
        validate_file_request('Busca una carpeta parecida a HNF9', 'nas.directories', {'query':'HNF'})
        validate_file_request('Busca una carpeta llamada HNF9 o similar', 'nas.directories', {'query':'HNF'})

    def test_dispatch_blocks_mismatched_literal_before_io(self):
        def files(*args, **kwargs):
            self.fail('No debe ejecutar una búsqueda con otro nombre')
        agent = Agent(self.workspace, runtime=None, dependencies=AgentDependencies(nas_files=files))
        with agent.store() as store:
            store.db.execute('INSERT INTO conversation VALUES (?,?,?,?,?)',
                             ('turn','2026-09-20','user','Busca una carpeta llamada HNF9',''))
            with self.assertRaisesRegex(ValueError, 'HNF9'):
                agent.dispatcher.dispatch(store, 'nas.directories',
                                          {'device':'nas','query':'HNFV9'}, turn_id='turn')

    def test_explicit_directory_read_is_narrow_and_preserves_literal(self):
        text = 'Busca por todo el Synology 1 una carpeta llamada HNF9.'
        call = explicit_directory_read(text, ['synology 1'])
        self.assertEqual(call['arguments'], {'device':'synology 1','query':'HNF9','exact':True})
        for other in ('No busques una carpeta llamada HNF9 en synology 1',
                      '¿Puedes explicar cómo buscar una carpeta llamada HNF9 en synology 1?',
                      'Busca una carpeta llamada HNF9 en /volume1 del synology 1',
                      'Busca una carpeta llamada HNF9 o similar en synology 1'):
            self.assertIsNone(explicit_directory_read(other, ['synology 1']))
        self.assertIsNone(explicit_directory_read(text, ['synology 1','synology 2']))

    def test_directory_reply_preserves_partial_coverage_without_internal_fields(self):
        trace = [dict(tool='nas.directories', result=dict(device='synology 1', query='HNF9',
                      items=[], complete=False, error_count=10, excludes_hidden=True))]
        reply = file_listing_reply('Busca por todo el Synology 1 una carpeta llamada HNF9.', trace)
        self.assertIn('HNF9', reply)
        self.assertIn('10 incidencias', reply)
        self.assertIn('parcial', reply)
        self.assertNotIn('nas.directories', reply)
        self.assertNotIn('exact', reply)

    def test_share_reply_names_paths_and_access_without_raw_flags(self):
        trace = [dict(tool='nas.shares', result=dict(device='synology 1', complete=True,
                      items=[dict(name='Fotos',path='/volume1/photos', access='Sin acceso de lectura por SSH')]))]
        reply = file_listing_reply('Que carpetas compartidas puedes ver en el Synology 1? Listame todas.', trace)
        self.assertEqual(explicit_share_read('Listame todas las carpetas compartidas en el synology 1', ['synology 1'])['tool'], 'nas.shares')
        self.assertIsNone(explicit_share_read('No listes las carpetas compartidas', ['synology 1']))
        self.assertIn('Fotos:', reply)
        self.assertIn('/volume1/photos', reply)
        self.assertIn('Sin acceso', reply)
        self.assertNotIn('readable', reply)

    def test_listing_does_not_override_complex_requests(self):
        trace = [dict(tool='nas.shares', result=dict(device='nas',complete=True,items=[]))]
        self.assertIsNone(file_listing_reply('Compara las carpetas compartidas y propón cómo organizarlas',trace))


if __name__ == '__main__':
    unittest.main()
