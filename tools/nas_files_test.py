"""Lector real sobre directorios temporales, catálogo y frontera del agente.

No conecta a ningún NAS ni certifica el comportamiento del modelo.
"""
import base64
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch, mock_open

from hexos.agent import catalog, hosts, nas_files, nas_files_remote
from hexos.agent.chat import Agent
from hexos.agent.chat_backend.state import AgentDependencies


class FilesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.workspace = self.base / 'workspace'
        self.first = self.base / 'disco uno'
        self.second = self.base / 'disco dos'
        self.first.mkdir()
        self.second.mkdir()
        self.file(self.first / 'vacío.mkv', 0)
        self.file(self.first / 'Árbol.mkv', 10_000_000_000)
        self.file(self.second / 'Árbol.mkv', 100_000_000_000)
        self.file(self.second / 'grande.mp4', 101_000_000_000)
        self.file(self.second / 'notas.txt', 20)

    def file(self, path, size):
        with path.open('wb') as handle:
            handle.truncate(size)

    def observe(self, workspace, device, request):
        return dict(nas_files_remote.collect(request), device=device or 'nas', observed_at='2026-09-20T12:00:00Z')

    def index(self, roots=None):
        with patch.object(nas_files, 'observe', side_effect=self.observe):
            return nas_files.index(self.workspace, roots=roots or [str(self.first), str(self.second)])

    def test_unlimited_inclusive_ranges_zero_and_two_roots(self):
        scan = self.index()
        self.assertTrue(scan['published'])
        all_files = nas_files.search(self.workspace, scan_id=scan['scan_id'])
        self.assertEqual(all_files['total_matches'], 5)
        films = nas_files.search(self.workspace, scan_id=scan['scan_id'], kind='video')
        self.assertEqual([item['size_bytes'] for item in films['items']],
                         [101_000_000_000, 100_000_000_000, 10_000_000_000, 0])
        bounded = nas_files.search(self.workspace, scan_id=scan['scan_id'], kind='video',
                                   min_bytes=10_000_000_000, max_bytes=100_000_000_000)
        self.assertEqual(bounded['total_matches'], 2)
        self.assertEqual(len(bounded['totals']), 2)
        empty = nas_files.search(self.workspace, scan_id=scan['scan_id'], max_bytes=0)
        self.assertEqual([item['name'] for item in empty['items']], ['vacío.mkv'])
        self.assertEqual(nas_files.search(self.workspace, scan_id=scan['scan_id'],
                         min_bytes=101_000_000_001)['total_matches'], 0)

    def test_stable_pagination_and_refresh_do_not_mix_snapshots(self):
        scan = self.index()['scan_id']
        first = nas_files.search(self.workspace, scan_id=scan, limit=2)
        self.file(self.first / 'nuevo.mkv', 102_000_000_000)
        new_scan = self.index()['scan_id']
        second = nas_files.search(self.workspace, scan_id=scan, limit=2, offset=first['next_offset'])
        third = nas_files.search(self.workspace, scan_id=scan, limit=2, offset=second['next_offset'])
        self.assertIsNone(third['next_offset'])
        self.assertEqual(len({item['path'] for item in first['items'] + second['items'] + third['items']}), 5)
        self.assertEqual(nas_files.search(self.workspace, scan_id=new_scan)['total_matches'], 6)

    def test_remembers_directories_and_queries_without_network(self):
        folder = self.first / 'Multimedia' / 'peliculas'
        folder.mkdir(parents=True)
        self.file(folder / 'film.mkv', 12)
        self.index()
        with patch.object(nas_files, 'observe') as observe:
            result = nas_files.locations(self.workspace, query='MULTIMEDIA')
            observe.assert_not_called()
        self.assertEqual([item['path'] for item in result['items']], [str(folder.parent)])
        self.assertFalse(result['network_used'])
        self.assertEqual(result['items'][0]['observed_at'], '2026-09-20T12:00:00Z')
        # No devuelve cada descendiente al buscar el nombre de una biblioteca.
        self.assertEqual(result['total_matches'], 1)

    def test_empty_browsed_directory_is_remembered(self):
        folder = self.first / 'series'
        folder.mkdir()
        with patch.object(nas_files, 'observe', side_effect=self.observe):
            nas_files.browse(self.workspace, device='NAS', path=str(folder))
        result = nas_files.locations(self.workspace, device='nas', query='series')
        self.assertEqual(result['items'][0]['path'], str(folder))
        with patch.object(nas_files, 'observe', side_effect=self.observe):
            nas_files.browse(self.workspace, device='nas', path=str(self.first/'absent'))
        self.assertEqual(nas_files.locations(self.workspace, query='absent')['total_matches'], 0)

    def test_import_old_catalog_once_and_keep_separate_device_paths(self):
        self.index()
        db = nas_files.database(self.workspace)
        with db:
            db.execute('DELETE FROM directories')
            db.execute('DELETE FROM directory_imports')
        db.close()
        with patch.object(nas_files, 'observe') as observe:
            first = nas_files.locations(self.workspace, limit=1)
            second = nas_files.locations(self.workspace, limit=1, offset=first['next_offset'])
            observe.assert_not_called()
        self.assertNotEqual(first['items'][0]['path'], second['items'][0]['path'])
        db = nas_files.database(self.workspace)
        with db:
            nas_files.remember_directories(db, 'other', [str(self.first)], '2026-09-21')
        db.close()
        self.assertEqual(nas_files.locations(self.workspace, device='other')['total_matches'], 1)

    def test_long_paths_limit_page_size_without_losing_files(self):
        folder = self.first / ('pelicula con titulo largo ' * 7)
        folder.mkdir()
        for index in range(120):
            self.file(folder / (str(index) + ' titulo de película muy largo ' * 5 + '.mkv'), index)
        scan = self.index()['scan_id']
        offset, paths = 0, []
        while offset is not None:
            page = nas_files.search(self.workspace, scan_id=scan, limit=100, offset=offset)
            self.assertLess(len(json.dumps(page, ensure_ascii=False)), 7000)
            self.assertLess(page['returned_count'], 100)
            paths.extend(item['path'] for item in page['items'])
            self.assertEqual(page['returned_count'], len(page['items']))
            self.assertIn('catálogo filtrado: 125.', page['headline'])
            offset = page['next_offset']
        self.assertEqual(len(paths), 125)
        self.assertEqual(len(set(paths)), 125)

    def test_checkpoint_preserves_catalog_filters_and_next_page(self):
        from hexos.agent.chat_backend.ledger import checkpoint_messages
        page = dict(scan_id='real-id', device='nas', complete=False, total_matches=120,
                    filters=dict(extensions=['mkv'], min_bytes=8_000_000_000, max_bytes=50_000_000_000),
                    offset=0, next_offset=12, returned_count=12, items=['x'*40000])
        messages = checkpoint_messages([dict(tool='nas.find', arguments={'device':'nas'}, result=page)])
        result = messages[0]['tool_responses'][0]['response']
        self.assertEqual(result['filters'], page['filters'])
        self.assertEqual(result['next_offset'], 12)
        self.assertEqual(result['scan_id'], 'real-id')
        self.assertLess(len(json.dumps(messages)), 1500)

    def test_unicode_literal_query_root_and_same_names_remain_distinct(self):
        scan = self.index()['scan_id']
        self.assertEqual(nas_files.search(self.workspace, scan_id=scan, query='ÁRBOL')['total_matches'], 2)
        self.assertEqual(nas_files.search(self.workspace, scan_id=scan, query='%')['total_matches'], 0)
        result = nas_files.search(self.workspace, scan_id=scan, root=str(self.first), query='árbol')
        self.assertEqual(result['total_matches'], 1)
        self.assertEqual(result['items'][0]['size_bytes'], 10_000_000_000)

    def test_overlap_links_and_special_files(self):
        folder = self.first / 'nested'
        folder.mkdir()
        self.file(folder / 'film.MKV', 12)
        (self.first / 'loop').symlink_to(self.first, target_is_directory=True)
        (self.first / 'link.mkv').symlink_to(self.second / 'grande.mp4')
        scan = self.index([str(self.first), str(folder), str(self.first)])
        result = nas_files.search(self.workspace, scan_id=scan['scan_id'])
        self.assertEqual(result['total_matches'], 3)
        self.assertTrue(scan['coverage']['skipped']['symlinks'])
        self.assertEqual(next(item for item in result['items'] if item['name'] == 'film.MKV')['root'], str(folder))

    def test_incomplete_scan_does_not_publish_or_erase_previous(self):
        original = self.index()['scan_id']
        with patch.object(nas_files_remote, 'MAX_ENTRIES', 1):
            failure = self.index()
        self.assertFalse(failure['published'])
        self.assertNotIn('scan_id', failure)
        self.assertEqual(failure['coverage']['stopped_reason'], 'entry_limit')
        self.assertEqual(nas_files.search(self.workspace, scan_id=original)['total_matches'], 5)
        missing = self.index([str(self.base / 'absent')])
        self.assertFalse(missing['published'])
        self.assertTrue(missing['coverage']['errors'])

    def test_symlink_root_and_payload_limit_are_explicit(self):
        link = self.base / 'alias'
        link.symlink_to(self.first, target_is_directory=True)
        self.assertFalse(self.index([str(link)])['published'])
        with patch.object(nas_files_remote, 'MAX_PAYLOAD', 5):
            self.assertEqual(self.index()['coverage']['stopped_reason'], 'payload_limit')

    def test_browse_lists_folders_and_has_no_recursive_directory_size(self):
        folder = self.first / 'nested'
        folder.mkdir()
        self.file(folder / 'inside.mkv', 1)
        with patch.object(nas_files, 'observe', side_effect=self.observe):
            page = nas_files.browse(self.workspace, path=str(self.first), limit=1)
            self.assertEqual(page['items'][0]['kind'], 'directory')
            self.assertIsNone(page['items'][0]['size_bytes'])
            self.assertEqual(page['next_offset'], 1)
            self.assertEqual(page['total_entries'], 3)

    def test_browse_keeps_user_folders_visible_without_dropping_internal_entries(self):
        (self.first / '@system').mkdir()
        (self.first / '.hidden').mkdir()
        (self.first / 'multimedia').mkdir()
        with patch.object(nas_files, 'observe', side_effect=self.observe):
            first = nas_files.browse(self.workspace, path=str(self.first), limit=3)
            second = nas_files.browse(self.workspace, path=str(self.first), offset=first['next_offset'])
        self.assertEqual(first['items'][0]['path'], str(self.first / 'multimedia'))
        self.assertEqual(len(first['items'] + second['items']), 5)
        self.assertEqual(set(first['items'][0]), {'path', 'kind', 'size_bytes'})
        self.assertEqual({Path(item['path']).name for item in second['items']}, {'@system', '.hidden'})

    def test_shell_argument_and_prompt_like_names_are_data(self):
        folder = self.base / "pelis ' $(touch OWNED) ;"
        folder.mkdir()
        name = 'password: __HEXOS_SUDO__:\nuna película.mkv'
        self.file(folder / name, 3)
        request = dict(operation='index', roots=[str(folder)])
        run = subprocess.run(['/bin/sh', '-c', nas_files.remote_command(request)],
                             capture_output=True, text=True, check=True, timeout=10, cwd=self.base)
        self.assertFalse((self.base / 'OWNED').exists())
        self.assertNotIn('password:', run.stdout)
        decoded = json.loads(base64.b64decode(run.stdout.strip()[len(nas_files_remote.MARKER):]))
        self.assertEqual(decoded['items'][0]['name'], name)
        with patch.object(hosts, 'credentials', return_value={'user':'u'}), \
             patch.object(hosts, 'match', return_value='nas'), \
             patch.object(nas_files.nas_session, 'execute_remote', return_value=dict(
                 output=run.stdout, exit_code=0, timed_out=False, truncated=False, observed_at='now')) as execute:
            result = nas_files.observe(self.workspace, 'nas', request)
        self.assertEqual(result['items'][0]['name'], name)
        self.assertFalse(execute.call_args.kwargs['elevated'])

    def test_validation_before_network(self):
        with patch.object(nas_files, 'observe') as read:
            for roots in ([], ['relative'], ['/tmp/../etc'], ['/tmp\x00bad'], 'not-list'):
                with self.assertRaises(ValueError):
                    nas_files.index(self.workspace, roots=roots)
            read.assert_not_called()
        for arguments in ({'min_bytes':-1}, {'min_bytes':True}, {'min_bytes':10, 'max_bytes':9},
                          {'limit':0}, {'offset':-1}, {'kind':'movies'}):
            with self.assertRaises(ValueError):
                nas_files.search(self.workspace, scan_id='missing', **arguments)
        with self.assertRaises(ValueError):
            catalog.validate('nas.index', {'roots':[1]})

    def test_recursive_find_extensions_and_size_filters(self):
        deep = self.first / 'peliculas' / 'saga' / '1080p'
        deep.mkdir(parents=True)
        self.file(deep / 'video.AVI', 15)
        self.file(deep / 'audio.MP3', 10)
        self.file(deep / 'not-a-video.mkv.bak', 15)
        with patch.object(nas_files, 'observe', side_effect=self.observe) as observe:
            result = nas_files.find(self.workspace, roots=[str(self.first), str(self.second)],
                                    extensions=['.MKV', 'avi', 'mp3'], min_bytes=10, max_bytes=20)
        self.assertEqual(observe.call_count, 1)
        self.assertEqual([item['name'] for item in result['items']], ['video.AVI', 'audio.MP3'])
        self.assertTrue(result['complete'])
        self.assertTrue(result['total_is_exact'])
        # El recorrido filtra extensiones, no tamaños: ampliar el rango es local.
        wider = nas_files.search(self.workspace, scan_id=result['scan_id'], extensions=['MKV'])
        self.assertEqual(wider['total_matches'], 3)
        self.assertEqual(wider['items'][0]['size_bytes'], 100_000_000_000)
        with self.assertRaisesRegex(ValueError, 'solo incluye extensiones'):
            nas_files.search(self.workspace, scan_id=result['scan_id'], extensions=['MP4'])
        self.assertEqual(nas_files.search(self.workspace, scan_id=result['scan_id'])['filters']['extensions'],
                         ['avi', 'mkv', 'mp3'])

    def test_find_discovers_roots_and_pages_locally(self):
        roots = [str(self.first), str(self.second)]
        with patch.object(nas_files_remote, 'discover_data_roots', return_value=(roots, [])) as discover, \
             patch.object(nas_files, 'observe', side_effect=self.observe):
            first = nas_files.find(self.workspace, extensions=['MKV', 'mp4'], limit=2)
        discover.assert_called_once_with(include_hidden=False)
        self.assertTrue(first['coverage']['auto_discovered'])
        with patch.object(nas_files, 'observe') as observe:
            second = nas_files.search(self.workspace, scan_id=first['scan_id'], extensions=['mkv','mp4'],
                                      offset=first['next_offset'], limit=2)
            observe.assert_not_called()
        self.assertEqual(second['total_matches'], 4)
        self.assertIsNone(second['next_offset'])
        self.assertEqual(len({item['path'] for item in first['items'] + second['items']}), 4)

    def test_find_slash_means_all_data_volumes_not_system_partition(self):
        with patch.object(nas_files_remote, 'discover_data_roots', return_value=([str(self.first)], [])) as discover, \
             patch.object(nas_files, 'observe', side_effect=self.observe):
            result = nas_files.find(self.workspace, roots=['/'], extensions=['mkv'])
        discover.assert_called_once()
        self.assertEqual(result['total_matches'], 2)
        self.assertEqual(result['roots'], [str(self.first)])
        with patch.object(nas_files, 'observe') as observe:
            with self.assertRaises(ValueError):
                nas_files.index(self.workspace, roots=['/'])
            with self.assertRaises(ValueError):
                nas_files.find(self.workspace, roots=['/', str(self.first)])
            observe.assert_not_called()

    def test_find_exclusions_are_explicit_and_optional(self):
        internal = self.first / '@eaDir'
        internal.mkdir()
        self.file(internal / 'preview.mp4', 4)
        self.file(self.first / '.secret.mp4', 6)
        with patch.object(nas_files, 'observe', side_effect=self.observe):
            default = nas_files.find(self.workspace, roots=[str(self.first)], extensions=['mp4'])
            all_files = nas_files.find(self.workspace, roots=[str(self.first)], extensions=['mp4'], include_hidden=True)
        self.assertEqual(default['total_matches'], 0)
        self.assertTrue(default['coverage']['excludes_hidden'])
        self.assertEqual(default['coverage']['skipped']['hidden'], 2)
        self.assertEqual(all_files['total_matches'], 2)

    def test_find_partial_results_never_claim_complete_or_replace_full_index(self):
        original = self.index()['scan_id']
        with patch.object(nas_files, 'observe', side_effect=self.observe):
            partial = nas_files.find(self.workspace, roots=[str(self.first), str(self.base/'missing')], extensions=['mkv'])
        self.assertFalse(partial['complete'])
        self.assertFalse(partial['total_is_exact'])
        self.assertEqual(partial['total_matches'], 2)
        self.assertEqual(partial['coverage']['error_count'], 1)
        self.assertTrue(nas_files.search(self.workspace, scan_id=original)['complete'])
        self.assertFalse(nas_files.search(self.workspace, scan_id=partial['scan_id'])['complete'])

    def test_find_bounded_scan_remains_partial_on_every_page(self):
        with patch.object(nas_files, 'observe', side_effect=self.observe), \
             patch.object(nas_files_remote, 'MAX_FIND_ENTRIES', 1):
            result = nas_files.find(self.workspace, roots=[str(self.first)], extensions=['mkv'])
        self.assertFalse(result['complete'])
        self.assertEqual(result['coverage']['stopped_reason'], 'entry_limit')
        page = nas_files.search(self.workspace, scan_id=result['scan_id'])
        self.assertFalse(page['total_is_exact'])

    def test_model_has_one_entry_for_live_recursive_search(self):
        self.assertIn('nas.find', catalog.model_tools())
        self.assertNotIn('nas.index', catalog.model_tools())
        self.assertIn('nas.index', catalog.TOOLS)

    def test_no_automatic_volumes_is_not_an_empty_success(self):
        with patch.object(nas_files_remote, 'discover_data_roots', return_value=([], [])), \
             patch.object(nas_files, 'observe', side_effect=self.observe):
            result = nas_files.find(self.workspace, extensions=['mkv'])
        self.assertFalse(result['published'])
        self.assertNotIn('total_matches', result)
        self.assertFalse((self.workspace/'nas_files.sqlite').exists())

    def test_extension_validation_happens_before_ssh(self):
        with patch.object(nas_files, 'observe') as observe:
            for extensions in ('mkv', [], ['*.mkv'], ['mkv;touch foo'], ['a/b'], [1]):
                with self.assertRaises(ValueError):
                    nas_files.find(self.workspace, extensions=extensions)
            with self.assertRaises(ValueError):
                nas_files.find(self.workspace, extensions=['mkv'], min_bytes=20, max_bytes=10)
            with self.assertRaises(ValueError):
                nas_files.find(self.workspace, include_hidden='false')
            observe.assert_not_called()
        self.assertEqual(nas_files.extensions_argument(['MKV', '.mkv', 'mp3']), ['mkv','mp3'])

    def test_discovery_uses_only_observed_data_mounts(self):
        mounts = ('1 0 0:1 / / rw - ext4 /dev/root rw\n'
                  '2 1 0:2 / /volume1 rw - btrfs /dev/md2 rw\n'
                  '3 1 0:3 / /volumeUSB1/usbshare rw - ext4 /dev/sda1 rw\n'
                  '4 1 0:4 / /volume1/@docker rw - overlay overlay rw\n')
        mapping = {'/volume1':str(self.first), '/volumeUSB1/usbshare':str(self.second)}
        real_open = nas_files_remote.open_directory
        with patch('builtins.open', mock_open(read_data=mounts)), \
             patch.object(nas_files_remote, 'open_directory', side_effect=lambda path: real_open(mapping[path])):
            roots, errors = nas_files_remote.discover_data_roots()
        self.assertEqual(roots, ['/volume1', '/volumeUSB1/usbshare'])
        self.assertEqual(errors, [])

    def test_transport_failure_never_becomes_empty_catalog(self):
        request = dict(operation='index', roots=[str(self.first)])
        with patch.object(hosts, 'credentials', return_value={'user':'u'}), \
             patch.object(hosts, 'match', return_value='nas'):
            for raw in (dict(exit_code=127), dict(exit_code=0, timed_out=True),
                        dict(exit_code=0, truncated=True),
                        dict(exit_code=0, output='banner without payload'),
                        dict(exit_code=0, output=nas_files_remote.MARKER + 'broken')):
                with patch.object(nas_files.nas_session, 'execute_remote', return_value=raw):
                    with self.assertRaises(ValueError):
                        nas_files.observe(self.workspace, 'nas', request)
        self.assertFalse((self.workspace / 'nas_files.sqlite').exists())

    def test_permission_failure_and_timeout_are_not_complete(self):
        real_open = nas_files_remote.open_directory
        def denied(path):
            if path == str(self.second):
                raise PermissionError(13, 'denied')
            return real_open(path)
        with patch.object(nas_files_remote, 'open_directory', side_effect=denied):
            result = self.index()
        self.assertFalse(result['published'])
        self.assertEqual(result['coverage']['errors'][0]['errno'], 13)
        with patch.object(nas_files_remote, 'MAX_SECONDS', 0):
            self.assertEqual(self.index()['coverage']['stopped_reason'], 'time_limit')

    def test_structured_transport_does_not_corrupt_payload_with_short_password(self):
        payload = nas_files_remote.MARKER + base64.b64encode(b'{"items":[]}').decode()
        class Process:
            before = payload + '\r\n'
            exitstatus = 0
            def expect(self, patterns, timeout=None):
                return 2
            def close(self, force=False):
                pass
        with patch('pexpect.spawn', return_value=Process()):
            result = nas_files.nas_session._ssh([], 'e', 'nas', {'host':'fixture'}, 22,
                      'files', None, None, None, payload_marker=nas_files_remote.MARKER)
        self.assertEqual(result['output'], payload)


class DispatcherTest(unittest.TestCase):
    def test_missing_second_nas_keeps_file_search_in_recovery(self):
        class Runtime:
            def __init__(self):
                self.messages = []
                self.outputs = iter([
                    {'tool':'nas.find', 'arguments':{'device':'uno', 'extensions':['mkv']}},
                    {'reply':'Encontré películas en uno.', 'work':None},
                    {'tool':'nas.find', 'arguments':{'device':'dos', 'extensions':['mkv']}},
                    {'reply':'Películas consultadas en los dos.', 'work':None},
                ])
            def call(self, request):
                pass
            def generate(self, messages):
                self.messages.append(messages)
                return next(self.outputs)
        with tempfile.TemporaryDirectory() as workspace:
            hosts.save(workspace, 'uno', 'helios', 'fixture')
            hosts.save(workspace, 'dos', 'helios', 'fixture')
            runtime = Runtime()
            operations = []
            def files(workspace, *, operation, **kwargs):
                operations.append((operation, kwargs['device']))
                return dict(complete=True, total_matches=1, items=[])
            agent = Agent(workspace, runtime, dependencies=AgentDependencies(nas_files=files))
            result = agent.chat('Busca archivos mkv en uno y dos')
        self.assertEqual(operations, [('find','uno'), ('find','dos')])
        warning = json.dumps(runtime.messages[2], ensure_ascii=False)
        self.assertIn('nas_find para buscar', warning)
        self.assertNotIn('Léelo ahora con nas_read.', warning)
        self.assertEqual([step['tool'] for step in result['tools']], ['nas.find','nas.find'])

    def test_search_offline_and_missing_access_uses_existing_dialog(self):
        class Runtime:
            pass
        with tempfile.TemporaryDirectory() as workspace:
            def files(workspace, *, operation, **kwargs):
                if operation == 'search':
                    return dict(items=[], total_matches=0)
                raise hosts.AccessNeeded(kwargs['device'], {'host':'fixture'})
            agent = Agent(workspace, Runtime(), dependencies=AgentDependencies(nas_files=files))
            with agent.store() as store:
                self.assertEqual(agent.tool(store, 'nas.search', {'scan_id':'fixture'})['total_matches'], 0)
                result = agent.tool(store, 'nas.index', {'device':'nas', 'roots':['/films']})
            self.assertTrue(result['access_required'])
            self.assertEqual(agent.credential_request['pending_operation']['tool'], 'nas.index')
            self.assertEqual(agent.credential_request['pending_operation']['arguments']['roots'], ['/films'])


if __name__ == '__main__':
    unittest.main()
