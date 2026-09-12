import tempfile
import unittest
from unittest.mock import patch
from hexos.agent.chat import Agent
from hexos.agent.devices import dispatch
from hexos.agent.devices import annotate


def observation(mac='aa:bb:cc:dd:ee:ff', ip='192.168.1.10'):
    return dict(observed_at='2026-09-12T12:00:00Z', truncated=False, note='passive', neighbors=[
        dict(mac=mac, ip=ip, interface='eth0', state=['STALE'])])


class DevicesTest(unittest.TestCase):
    def test_suffix_ambiguity_never_labels_a_device(self):
        with tempfile.TemporaryDirectory() as tmp:
            agent=Agent(tmp,None)
            with agent.store() as s:
                data=observation()
                data['neighbors'] += [dict(ip='10.0.0.10',mac='11:22:33:44:55:66',interface='eth1',state=['STALE'])]
                with patch('hexos.agent.devices.snapshot',return_value=data):
                    agent.tool(s,'device.refresh',{})
                quote='el 10 es mi NAS'
                s.db.execute('INSERT INTO conversation VALUES (?,?,?,?,?)',('u','now','user',quote,quote))
                s.db.commit()
                with self.assertRaises(ValueError):
                    agent.tool(s,'device.identify',dict(target='10',name='NAS'),turn_id='u')
                self.assertTrue(all(d['identity'] is None for d in agent.tool(s,'device.list',{})['devices']))

    def test_two_suffixes_use_current_message_and_reject_wrong_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            agent = Agent(tmp, None)
            with agent.store() as s:
                data = observation()
                data['neighbors'] = [dict(ip='192.168.1.'+str(n), mac=f'aa:bb:cc:dd:ee:{n:02x}', interface='eth0',state=['STALE']) for n in (243,131,249)]
                with patch('hexos.agent.devices.snapshot', return_value=data):
                    agent.tool(s,'device.refresh',{})
                quote='guara el que termina en 243 como synology, el 131 como nimos nas'
                s.db.execute('INSERT INTO conversation VALUES (?,?,?,?,?)', ('u','now','user',quote,quote))
                s.db.commit()
                with self.assertRaises(ValueError):
                    agent.tool(s,'device.identify',dict(target='192.168.1.249',name='synology'),turn_id='u')
                for target, name in [('243','synology'),('131','nimos nas')]:
                    result=agent.tool(s,'device.identify',dict(target=target,name=name),turn_id='u')
                    self.assertEqual(result['device']['identity']['source_id'],'u')
                    self.assertEqual(result['device']['identity']['name'],name)
                before=s.db.total_changes
                self.assertEqual(agent.tool(s,'device.list',{'query':'synology OR nimos nas'})['total'],2)
                enriched=annotate(s,data)
                self.assertEqual({n['name'] for n in enriched['identified_neighbors']},{'synology','nimos nas'})
                impostor=observation(mac='00:11:22:33:44:55',ip='192.168.1.243')
                self.assertEqual(annotate(s,impostor)['identified_neighbors'],[])
                self.assertEqual(s.db.total_changes,before)
                with self.assertRaises(ValueError):
                    agent.tool(s,'device.identify',dict(target='131',name='synology'),turn_id='u')

    def test_identity_persists_without_following_reassigned_ip(self):
        with tempfile.TemporaryDirectory() as tmp:
            agent = Agent(tmp, None)
            with agent.store() as s:
                with patch('hexos.agent.devices.snapshot', return_value=observation()):
                    dispatch(s, 'device.refresh', {})
                quote = '192.168.1.10 es mi NAS Faro'
                s.db.execute('INSERT INTO conversation VALUES (?,?,?,?,?)', ('u','now','user',quote,quote))
                s.db.commit()
                args = dict(target='192.168.1.10', name='NAS Faro', kind='NAS', source_id='u', evidence=quote)
                dispatch(s, 'device.identify', args)
                with patch('hexos.agent.devices.snapshot', return_value=observation(ip='192.168.1.11')):
                    dispatch(s, 'device.refresh', {})
                self.assertEqual(dispatch(s,'device.list',{})['devices'][0]['identity']['name'], 'NAS Faro')
                with patch('hexos.agent.devices.snapshot', return_value=observation(mac='11:22:33:44:55:66')):
                    dispatch(s, 'device.refresh', {})
                devices = dispatch(s, 'device.list', {})['devices']
                self.assertEqual(len(devices), 2)
                self.assertIsNone(next(d for d in devices if d['in_latest_snapshot'])['identity'])
            with Agent(tmp, None).store() as s:
                self.assertEqual(dispatch(s, 'device.list', {'query':'NAS Faro'})['total'], 1)

    def test_rejects_invented_or_assistant_evidence_and_old_correction(self):
        with tempfile.TemporaryDirectory() as tmp:
            with Agent(tmp, None).store() as s:
                with patch('hexos.agent.devices.snapshot', return_value=observation()):
                    dispatch(s, 'device.refresh', {})
                for uid, role, quote in [('a','assistant','192.168.1.10 es router'),
                                         ('u','user','192.168.1.10 es NAS'),
                                         ('v','user','192.168.1.10 es Raspberry')]:
                    s.db.execute('INSERT INTO conversation VALUES (?,?,?,?,?)', (uid,'now',role,quote,quote))
                args=dict(target='192.168.1.10', name='router', evidence='192.168.1.10 es router')
                with self.assertRaises(ValueError): dispatch(s,'device.identify',args)
                args['evidence']='192.168.1.10 es NAS'; args['name']='router'
                with self.assertRaises(ValueError): dispatch(s,'device.identify',args)
                dispatch(s,'device.identify',dict(target='192.168.1.10',name='Raspberry',source_id='v',evidence='192.168.1.10 es Raspberry'))
                args['name']='NAS'
                with self.assertRaises(ValueError): dispatch(s,'device.identify',args)
