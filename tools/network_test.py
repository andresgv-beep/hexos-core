import json
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from hexos.agent.network import snapshot
from hexos.agent import catalog


class NetworkTest(unittest.TestCase):
    @patch('hexos.agent.network.shutil.which', return_value='/usr/sbin/ip')
    @patch('hexos.agent.network.subprocess.run')
    def test_passive_states_and_fixed_commands(self, run, which):
        fixtures = [[], [], [], [
            dict(dst='192.168.1.2', dev='eth0', lladdr='aa:bb', state=['REACHABLE']),
            dict(dst='192.168.1.3', dev='eth0', lladdr='cc:dd', state=['STALE']),
            dict(dst='192.168.1.4', dev='eth0', state=['FAILED'])]]
        run.side_effect = [SimpleNamespace(stdout=json.dumps(x)) for x in fixtures]
        result = snapshot()
        self.assertEqual(result['known_neighbors'], 2)
        self.assertEqual(result['unresolved_entries'], 1)
        self.assertTrue(result['neighbors'][0]['recently_reachable'])
        self.assertFalse(result['neighbors'][1]['recently_reachable'])
        self.assertFalse(result['complete_inventory'])
        self.assertEqual([c.args[0] for c in run.call_args_list], [
            ['/usr/sbin/ip', '-j', 'address', 'show'],
            ['/usr/sbin/ip', '-j', 'route', 'show'],
            ['/usr/sbin/ip', '-j', '-6', 'route', 'show'],
            ['/usr/sbin/ip', '-j', 'neigh', 'show']])
        with self.assertRaises(ValueError):
            catalog.validate('network.local', {'command':'anything'})

    @patch('hexos.agent.network.shutil.which', return_value=None)
    def test_missing_dependency_is_not_empty_network(self, which):
        with self.assertRaises(RuntimeError):
            snapshot()
