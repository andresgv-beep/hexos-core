import copy
import unittest
from pathlib import Path
import json
import tempfile
from unittest.mock import patch
from hexos.agent.nas_session import command, execute, read, present_result


class NasSessionTest(unittest.TestCase):
    def test_read_maps_link_and_raid_without_degrading_single_member(self):
        payload=dict(storage=dict(output='md3 : active raid1 sdc5[0]\n 123 blocks [1/1] [U]\nDEVICE=sda\n/sys/devices/ata1/host0\n'),
                     kernel=dict(output='ata1: hard resetting link'),
                     smart=[dict(disk='sda',exit_code=0,summary='197 Current_Pending_Sector 0x0012 100 100 000 Old_age Always - 0')])
        with patch('hexos.agent.nas_session.hosts.credentials',return_value=dict(user='u',password='p',port=22)), \
             patch('hexos.agent.nas_session.execute',return_value=payload):
            result=read('/unused','diagnosis',device='fixture')
        self.assertTrue(result['facts']['raid'][0]['all_configured_members_present'])
        self.assertEqual(result['facts']['links_in_error_log'],[dict(link='ata1',disk='sda')])
        self.assertEqual(result['facts']['smart_attributes'][0]['attributes']['Current_Pending_Sector'],'0')

    def test_diagnosis_collects_smart_for_discovered_disks(self):
        def fake(workspace,password,section,disk=None):
            output='DEVICE=sda\nDEVICE=sdb\n' if section=='storage' else 'SMART overall-health: PASSED\n197 Current_Pending_Sector 0\n'
            return dict(output=output,exit_code=0,timed_out=False,truncated=False)
        with patch('hexos.agent.nas_session.execute',side_effect=fake) as calls:
            result=execute('/unused','unused','diagnosis')
        self.assertEqual([d['disk'] for d in result['smart']],['sda','sdb'])
        self.assertEqual([c.args[2] for c in calls.call_args_list],['storage','kernel','smart','smart'])

    def test_normal_link_is_not_reported_as_error_and_nvme_unknown(self):
        data=dict(storage=dict(output='md0 : active raid1 sdc1[0]\n 42 blocks [12/1] [U___________]\nDEVICE=sda\n/sys/devices/ata1/host0\n'),
            kernel=dict(output='ata1: SATA link up 6.0 Gbps\nata2: hard resetting link'),
            smart=[dict(disk='nvme0n1',exit_code=2,summary=''),
                   dict(disk='sda',exit_code=0,summary='SMART overall-health self-assessment test result: PASSED')])
        result=present_result(data,'diagnosis')
        self.assertEqual(result['facts']['links_in_error_log'],[dict(link='ata2',disk=None)])
        self.assertEqual(result['smart'][0]['health_assessment'],'unknown')
        self.assertEqual(result['smart'][1]['health_assessment'],'PASSED')
        self.assertTrue(result['facts']['raid'][0]['slot_count_is_DSM_default'])
        # ata2 tiene un reinicio pero no hay correspondencia con un sd: se nombra el enlace.
        suspect=result['primary_suspect']
        self.assertEqual((suspect['link'],suspect['disk'],suspect['confidence']),('ata2',None,'baja'))
        self.assertIn('apunta al enlace ata2',result['headline'])
        self.assertNotIn('disco ata2',result['headline'])

    def test_failing_link_is_named_before_raid_and_identified_by_serial(self):
        kernel=('ata1: SError: { PHYRdyChg 10B8B DevExch }\n'
                'ata1.00: device unplugged\n'
                'ata1: hard resetting link\n'
                'ata1: SATA link up 1.5 Gbps (SStatus 113 SControl 310)\n'
                'ata1.00: configured for UDMA/33\n'
                'ata2: SATA link up 6.0 Gbps (SStatus 133 SControl 300)\n')
        smart=[dict(disk='sda',exit_code=0,summary='Device Model:     ST4000VN008-2DR166\n'
                    'Serial Number:    ZGY95407\n'
                    'SATA Version is:  SATA 3.1, 6.0 Gb/s (current: 1.5 Gb/s)\n'
                    'SMART overall-health self-assessment test result: PASSED\n'
                    '199 UDMA_CRC_Error_Count 0x003e 200 200 000 Old_age Always - 0\n'
                    '197 Current_Pending_Sector 0x0012 100 100 000 Old_age Always - 0\n'),
               dict(disk='sdb',exit_code=0,summary='SMART overall-health self-assessment test result: PASSED\n')]
        data=dict(storage=dict(output='md0 : active raid1 sdc1[0]\n 42 blocks [12/1] [U___________]\n'
                               'md2 : active raid1 sda3[2] sdb3[3]\n 99 blocks [2/2] [UU]\n'
                               'DEVICE=sda\n/sys/devices/pci0000:00/ata1/host0\n'
                               'DEVICE=sdb\n/sys/devices/pci0000:00/ata2/host1\n'),
                  kernel=dict(output=kernel),smart=smart)
        result=present_result(data,'diagnosis')
        self.assertEqual(list(result)[0],'headline')
        suspect=result['primary_suspect']
        self.assertEqual((suspect['disk'],suspect['link'],suspect['confidence']),('sda','ata1','alta'))
        self.assertEqual(suspect['serial'],'ZGY95407')
        self.assertEqual(suspect['kernel_speed_limit'],'1.5 Gbps')
        self.assertEqual(suspect['transfer_mode'],'UDMA/33')
        self.assertEqual((suspect['drive_supports'],suspect['drive_reports_current']),('6.0 Gb/s','1.5 Gb/s'))
        self.assertEqual(suspect['surface_counters']['Current_Pending_Sector'],'0')
        self.assertIn('sda',result['headline'])
        self.assertIn('no a los arrays RAID',result['headline'])
        self.assertIn('6.0 Gbps',result['headline'])
        self.assertEqual(result['other_disks_with_link_events'],[])
        self.assertEqual(suspect['cause'],'undetermined')
        self.assertTrue(any('DevExch' in line for line in suspect['evidence']))
        self.assertLessEqual(len(suspect['evidence']),3)
        self.assertIn('smart_assessment_limit',result['facts'])
        self.assertNotIn('assessment_limit',result['smart'][0])
        self.assertNotIn('ID# ATTRIBUTE_NAME',result['smart'][0]['summary'])
        # ata2 negocia a plena velocidad y sin eventos: no puede aparecer como sospechoso.
        self.assertEqual(result['facts']['link_state']['ata2']['events'],{})

    def test_system_arrays_are_separated_from_data_pools(self):
        data=dict(storage=dict(output='md0 : active raid1 sdc1[0]\n 42 blocks [12/1] [U___________]\n'
                               'md1 : active raid1 sdc2[0]\n 42 blocks [12/1] [U___________]\n'
                               'md2 : active raid1 sda3[2] sdb3[3]\n 99 blocks [2/2] [UU]\n'),
                  kernel=dict(output=''),smart=[])
        result=present_result(data,'diagnosis')
        summary=result['facts']['raid_summary']
        self.assertIn('Pools de datos completos: md2',summary)
        self.assertIn('Incompletos: ninguno',summary)
        system=[entry for entry in result['facts']['raid'] if entry['role']=='DSM_system_partition']
        self.assertEqual([entry['array'] for entry in system],['md0','md1'])
        self.assertTrue(all(entry['slot_count_is_DSM_default'] for entry in system))
        self.assertIn('no 12 discos físicos',summary)
        self.assertEqual(system[0]['members'],['sdc1'])
        # El aviso se da una vez en el resumen, no repetido en cada array.
        self.assertNotIn('observation',system[0])
        self.assertNotIn('primary_suspect',result)
        self.assertIn('Sin eventos de enlace',result['headline'])

    def test_whole_buffer_tally_outranks_a_single_recent_blip(self):
        kernel=('LINK_EVENT_TALLY\n     13 ata1\n      1 ata5\n LINK_EVENT_TALLY_END\n'
                'ata5: hard resetting link\n'
                'ata1: hard resetting link\n')
        storage=('DEVICE=sda\n/sys/devices/pci0000:00/ata1/host0\n'
                 'DEVICE=sde\n/sys/devices/pci0000:00/ata5/host4\n')
        result=present_result(dict(storage=dict(output=storage),kernel=dict(output=kernel),smart=[]),'diagnosis')
        self.assertEqual(result['primary_suspect']['disk'],'sda')
        self.assertEqual(result['primary_suspect']['events_in_whole_buffer'],13)
        self.assertIn('13 eventos de enlace en todo el buffer',result['headline'])
        self.assertEqual([item['disk'] for item in result['other_disks_with_link_events']],['sde'])
        self.assertNotIn('LINK_EVENT_TALLY',result['kernel']['output'])

    def test_presenting_a_saved_result_again_keeps_the_same_finding(self):
        # Los replays reutilizan lo guardado, donde /proc/mdstat y el recuento ya se retiraron.
        kernel=('LINK_EVENT_TALLY\n      9 ata1\n LINK_EVENT_TALLY_END\n'
                'ata1: SError: { PHYRdyChg 10B8B DevExch }\n'
                'ata1: SATA link up 1.5 Gbps (SStatus 113 SControl 310)\n')
        data=dict(storage=dict(output='md0 : active raid1 sdc1[0]\n 42 blocks [12/1] [U___________]\n'
                               'md2 : active raid1 sda3[2] sdb3[3]\n 99 blocks [2/2] [UU]\n'
                               'DEVICE=sda\n/sys/devices/pci0000:00/ata1/host0\n'),
                  kernel=dict(output=kernel),
                  smart=[dict(disk='sda',exit_code=0,summary='Serial Number:    ZGY95407\n'
                              '197 Current_Pending_Sector 0x0012 100 100 000 Old_age Always - 0\n')])
        first=present_result(data,'diagnosis')
        self.assertNotIn('output',first['storage'])
        second=present_result(copy.deepcopy(first),'diagnosis')
        self.assertEqual(first['headline'],second['headline'])
        self.assertEqual(second['primary_suspect']['disk'],'sda')
        self.assertEqual(second['primary_suspect']['serial'],'ZGY95407')
        self.assertEqual(second['primary_suspect']['events_in_whole_buffer'],9)
        self.assertEqual(second['primary_suspect']['surface_counters']['Current_Pending_Sector'],'0')
        self.assertEqual([entry['array'] for entry in second['facts']['raid']],['md0','md2'])
        self.assertEqual(len(second['primary_suspect']['evidence']),1)

    def test_kernel_command_counts_events_before_tailing(self):
        remote=command('kernel')
        self.assertIn('LINK_EVENT_TALLY',remote)
        self.assertIn('tail -n 65',remote)
        self.assertNotIn('rm ',remote)

    def test_link_speed_downshift_survives_the_kernel_excerpt(self):
        noise='\n'.join('ata9: irrelevante %d'%i for i in range(40))
        kernel=('ata1: hard resetting link\n'
                'ata1: SATA link up 1.5 Gbps (SStatus 113 SControl 310)\n')+noise
        result=present_result(dict(storage=dict(output=''),kernel=dict(output=kernel),smart=[]),'diagnosis')
        self.assertIn('SATA link up 1.5 Gbps',result['kernel']['output'])
        self.assertEqual(result['facts']['link_state']['ata1']['kernel_speed_limit'],'1.5 Gbps')

    def test_boot_link_reset_and_full_speed_cap_are_not_a_fault(self):
        # Caso real: un reinicio a los 7,5 s del arranque y SControl 330 (tope = máximo SATA)
        # en un disco de 6.0 Gb/s sin errores CRC ni de superficie. No es una avería.
        kernel=('[    7.586694] ata3.00: hard resetting link\n'
                '[    8.120000] ata3: SATA link up 6.0 Gbps (SStatus 133 SControl 330)\n'
                '[    8.200000] ata3.00: configured for UDMA/133\n')
        smart=[dict(disk='sdc',exit_code=0,summary='Device Model:     ST6000VN006-2ZM186\n'
                    'Serial Number:    ZVX043S3\n'
                    'SATA Version is:  SATA 3.3, 6.0 Gb/s (current: 6.0 Gb/s)\n'
                    '199 UDMA_CRC_Error_Count 0x003e 200 200 000 Old_age Always - 0\n')]
        storage='DEVICE=sdc\n/sys/devices/pci0000:00/ata3/host2\n'
        result=present_result(dict(storage=dict(output=storage),kernel=dict(output=kernel),smart=smart),'diagnosis')
        self.assertNotIn('primary_suspect',result)
        self.assertIn('Sin eventos de enlace',result['headline'])
        state=result['facts']['link_state']['ata3']
        self.assertEqual((state['events'],state['boot_link_events']),({},1))
        self.assertEqual(state['kernel_speed_limit'],'6.0 Gbps')

    def test_link_reset_after_boot_still_counts(self):
        kernel='[ 5231.412000] ata1: hard resetting link\n'
        storage='DEVICE=sda\n/sys/devices/pci0000:00/ata1/host0\n'
        result=present_result(dict(storage=dict(output=storage),kernel=dict(output=kernel),smart=[]),'diagnosis')
        self.assertEqual(result['primary_suspect']['disk'],'sda')
        self.assertEqual(result['primary_suspect']['events'],{'hard_resets':1})

    def test_speed_cap_equal_to_drive_capability_is_not_a_downshift(self):
        kernel=('[ 900.0] ata2: hard resetting link\n'
                '[ 901.0] ata2: SATA link up 6.0 Gbps (SStatus 133 SControl 330)\n')
        smart=[dict(disk='sdb',exit_code=0,summary='SATA Version is:  SATA 3.3, 6.0 Gb/s (current: 6.0 Gb/s)\n')]
        storage='DEVICE=sdb\n/sys/devices/pci0000:00/ata2/host1\n'
        result=present_result(dict(storage=dict(output=storage),kernel=dict(output=kernel),smart=smart),'diagnosis')
        self.assertEqual(result['primary_suspect']['confidence'],'baja')
        self.assertNotIn('limitó',result['headline'])

    def test_kernel_tally_skips_boot_link_resets(self):
        remote=command('kernel')
        self.assertIn('< 60',remote)
        self.assertIn('hard resetting link|slow to respond/) next',remote)

    def test_smart_without_disk_collects_diagnosis(self):
        with patch('hexos.agent.nas_session.hosts.credentials',return_value=dict(user='u',password='p',port=22)), \
             patch('hexos.agent.nas_session.execute',return_value=dict(error='fixture')) as run:
            result=read('/unused','smart',device='fixture')
        self.assertEqual(run.call_args.args[2],'diagnosis')
        self.assertEqual(result['effective_section'],'diagnosis')

    def test_read_without_stored_credentials_explains_how_to_save_them(self):
        with patch('hexos.agent.nas_session.hosts.credentials',return_value=None), \
             patch('hexos.agent.nas_session.execute') as run:
            with self.assertRaises(ValueError) as caught:
                read('/unused','diagnosis',device='synology')
        run.assert_not_called()
        message=str(caught.exception)
        # Ya no manda ejecutar un script: lo pide la interfaz.
        self.assertIn('La interfaz lo pedirá',message)
        self.assertNotIn('python3 -m',message)
        self.assertIn('no pidas la contraseña por el chat',message.lower())
        self.assertIn('no significa que el equipo esté sano',message)

    def test_no_address_or_account_is_hardcoded(self):
        source=Path('hexos/agent/nas_session.py').read_text()
        self.assertNotIn('192.168',source)
        self.assertNotIn('helios@',source)

    def test_storage_reports_missing_diagnostic_coverage(self):
        result=present_result(dict(output='md0 [12/1]',exit_code=0),'storage')
        self.assertEqual(result['scope'],'partial_storage_layout_only')
        self.assertIn('SMART',result['missing_checks'])
        self.assertEqual(result['next_read'],dict(section='diagnosis'))

    def test_only_fixed_read_commands(self):
        for section in ('system','storage','kernel','messages'):
            self.assertTrue(command(section))
        self.assertIn('smartctl -i -H -A -l error -l selftest /dev/sda',command('smart','sda'))
        for section,disk in [('reboot',None),('smart','sda; reboot'),('smart','/dev/sda'),('kernel','sda'),('smart',None)]:
            with self.assertRaises(ValueError): command(section,disk)


class NombreParcialTest(unittest.TestCase):
    """«el servidor srv1» tiene que encontrar a 'servidorsrv1', no pedir su contraseña."""

    def setUp(self):
        from hexos.agent import hosts
        self.hosts = hosts
        self.tmp = tempfile.TemporaryDirectory(prefix='hexos-nombre-')
        self.addCleanup(self.tmp.cleanup)
        hosts.save(self.tmp.name, 'servidorsrv1', 'helios', 'x', port=30, host='uno.ddns.net')
        hosts.save(self.tmp.name, 'synology 2', 'helios', 'x', port=22, host='dos.ddns.net')

    def test_un_fragmento_encuentra_el_equipo(self):
        for dicho in ('srv1', 'servidor srv1', 'SERVIDORSRV1', 'Servidorsrv1 '):
            with self.subTest(dicho):
                self.assertEqual(self.hosts.match(self.tmp.name, dicho), 'servidorsrv1')

    def test_con_varios_candidatos_se_pregunta_en_vez_de_elegir(self):
        self.hosts.save(self.tmp.name, 'servidorsrv1 viejo', 'helios', 'x')
        with self.assertRaises(ValueError) as e:
            self.hosts.match(self.tmp.name, 'srv1')
        self.assertIn('encaja con varios', str(e.exception))

    def test_un_fragmento_demasiado_corto_no_encaja_con_nada(self):
        self.assertIsNone(self.hosts.match(self.tmp.name, 's'))
        self.assertIsNone(self.hosts.match(self.tmp.name, ''))

    def test_un_nombre_que_no_es_de_nadie_sigue_sin_serlo(self):
        self.assertIsNone(self.hosts.match(self.tmp.name, 'nimos'))

    def test_no_se_usa_para_borrar(self):
        # Olvidar por un fragmento borraría el equipo equivocado sin remedio.
        with self.assertRaises(ValueError):
            self.hosts.forget(self.tmp.name, 'srv1')
        self.assertIn('servidorsrv1', self.hosts.load(self.tmp.name))

    def test_la_lectura_dice_por_qué_nombre_acabó_leyendo(self):
        from unittest.mock import patch
        from hexos.agent import nas_session
        salida = dict(output='', exit_code=0, timed_out=False, target='servidorsrv1')
        with patch.object(nas_session, 'execute', return_value=salida):
            r = nas_session.read(self.tmp.name, section='space', device='srv1')
        self.assertEqual(r['understood_as'], 'servidorsrv1')
        self.assertIn("se leyó 'servidorsrv1'", r['note'])
