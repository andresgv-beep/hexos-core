import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest

from hexos.agent.hosts import credentials, forget, load, resolve, save, store_path


def inventory(workspace, devices):
    db = sqlite3.connect(str(Path(workspace) / 'work.sqlite'))
    db.execute('CREATE TABLE network_devices (id TEXT PRIMARY KEY, body TEXT)')
    for device in devices:
        db.execute('INSERT INTO network_devices VALUES (?,?)', (device['id'], json.dumps(device)))
    db.commit()
    db.close()


def device(id, name, ip, state=('REACHABLE',), at='2026-09-12T14:27:13+00:00', mac='aa:bb:cc:dd:ee:ff'):
    address = dict(ip=ip, state=list(state), observed_at=at)
    return dict(id=id, mac=mac, interface='wlp0', addresses=[address], latest_addresses=[address],
                identity=dict(name=name, kind=None, source='user_statement') if name else None)


class HostsTest(unittest.TestCase):
    def test_credentials_round_trip_with_private_permissions(self):
        with tempfile.TemporaryDirectory() as tmp:
            save(tmp, 'Synology', 'helios', 'secreta', 22)
            self.assertEqual(os.stat(store_path(tmp)).st_mode & 0o777, 0o600)
            # El nombre se normaliza para que synology y Synology sean el mismo equipo.
            self.assertEqual(credentials(tmp, 'synology')['user'], 'helios')
            self.assertEqual(credentials(tmp, 'SYNOLOGY')['password'], 'secreta')
            self.assertIsNone(credentials(tmp, 'otro'))

    def test_revoking_one_access_leaves_the_others_and_keeps_permissions(self):
        with tempfile.TemporaryDirectory() as tmp:
            save(tmp, 'synology', 'helios', 'a')
            save(tmp, 'nimos nas', 'root', 'b')
            self.assertEqual(forget(tmp, 'Synology')['remaining'], ['nimos nas'])
            self.assertIsNone(credentials(tmp, 'synology'))
            self.assertEqual(credentials(tmp, 'nimos nas')['user'], 'root')
            self.assertEqual(os.stat(store_path(tmp)).st_mode & 0o777, 0o600)

    def test_revoking_the_last_access_removes_the_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            save(tmp, 'synology', 'helios', 'a')
            forget(tmp, 'synology')
            self.assertFalse(store_path(tmp).exists())
            with self.assertRaises(ValueError) as caught:
                forget(tmp, 'synology')
            self.assertIn('ninguno', str(caught.exception))

    def test_readable_by_others_is_refused_instead_of_used(self):
        with tempfile.TemporaryDirectory() as tmp:
            save(tmp, 'nas', 'u', 'p')
            os.chmod(store_path(tmp), 0o644)
            with self.assertRaises(ValueError) as caught:
                load(tmp)
            self.assertIn('chmod 600', str(caught.exception))

    def test_rejects_names_that_could_reach_the_shell(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name, user, port in [('nas; rm -rf /', 'u', 22), ('nas', 'u$(id)', 22),
                                     ('nas', 'u', 0), ('nas', 'u', 70000), ('', 'u', 22)]:
                with self.assertRaises(ValueError):
                    save(tmp, name, user, 'p', port)

    def test_resolves_saved_name_to_its_current_address(self):
        with tempfile.TemporaryDirectory() as tmp:
            inventory(tmp, [device('a', 'synology', '192.168.1.243', mac='b4:2e:99:47:6d:15'),
                            device('b', 'nimos nas', '192.168.1.131'),
                            device('c', None, '192.168.1.249')])
            located = resolve(tmp, 'Synology')
            self.assertEqual(located['host'], '192.168.1.243')
            self.assertEqual(located['mac'], 'b4:2e:99:47:6d:15')
            self.assertTrue(located['reachable'])

    def test_unknown_name_lists_what_is_saved(self):
        with tempfile.TemporaryDirectory() as tmp:
            inventory(tmp, [device('a', 'synology', '192.168.1.243')])
            with self.assertRaises(ValueError) as caught:
                resolve(tmp, 'faro')
            self.assertIn('synology', str(caught.exception))

    def test_prefers_a_reachable_address_over_a_stale_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            stale = dict(ip='192.168.1.9', state=['STALE'], observed_at='2026-09-12T15:00:00+00:00')
            live = dict(ip='192.168.1.243', state=['REACHABLE'], observed_at='2026-09-12T14:00:00+00:00')
            entry = device('a', 'synology', '0.0.0.0')
            entry['latest_addresses'] = [stale, live]
            inventory(tmp, [entry])
            self.assertEqual(resolve(tmp, 'synology')['host'], '192.168.1.243')

    def test_ipv6_only_device_says_so_instead_of_guessing(self):
        with tempfile.TemporaryDirectory() as tmp:
            entry = device('a', 'synology', '0.0.0.0')
            entry['latest_addresses'] = [dict(ip='fe80::1', state=['REACHABLE'], observed_at='2026-09-12T14:00:00+00:00')]
            inventory(tmp, [entry])
            with self.assertRaises(ValueError) as caught:
                resolve(tmp, 'synology')
            self.assertIn('IPv4', str(caught.exception))

    def test_duplicate_names_refuse_to_pick_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            inventory(tmp, [device('a', 'nas', '192.168.1.2'), device('b', 'nas', '192.168.1.3')])
            with self.assertRaises(ValueError) as caught:
                resolve(tmp, 'nas')
            self.assertIn('no distingue', str(caught.exception))


if __name__ == '__main__':
    unittest.main()
