"""Regressions from rejected 12B calls, without network or media execution."""
import unittest
from hexos.agent import catalog
from hexos.agent.native import NativeRuntime, NativeSyntax
from tools import native_channels_test


class SearchContractTest(unittest.TestCase):
    def test_empty_filename_filter_is_optional_not_invalid(self):
        for name, args in (
            ('nas.find', {'device':'synology 1', 'roots':['/volume1/multimedia 1']}),
            ('nas.search', {'scan_id':'observed'}),
            ('media.prepare', {'scan_id':'observed','profile_id':'configured','count':3}),
        ):
            with self.subTest(tool=name):
                catalog.validate(name, dict(args, query=''))
                catalog.validate(name, args)
                with self.assertRaises(ValueError):
                    catalog.validate(name, dict(args, query=123))

    def test_identifiers_stay_nonempty_and_schema_matches(self):
        for field in ('scan_id','profile_id'):
            args=dict(scan_id='observed',profile_id='configured')
            args[field]=''
            with self.assertRaisesRegex(ValueError, 'cadena no vacía'):
                catalog.validate('media.prepare',args)
        self.assertNotIn('minLength', NativeRuntime.JSON_TYPE('str','nas.find','query'))
        self.assertEqual(NativeRuntime.JSON_TYPE('str','media.prepare','profile_id')['minLength'],1)

    def test_invalid_call_repair_contains_exact_error_and_arguments(self):
        runtime=native_channels_test.NativeChannelsTest().runtime(
            '<|tool_call>call:nas_find{device:<|"|>synology 1<|"|>,query:12,'
            'roots:[<|"|>/volume1/multimedia 1<|"|>]}<tool_call|>')
        runtime.names={'nas_find':'nas.find'}
        with self.assertRaises(NativeSyntax) as raised:
            runtime.generate([])
        repair=raised.exception.repair
        self.assertIn('nas.find.query',repair)
        self.assertIn('"query": 12',repair)
        self.assertIn('/volume1/multimedia 1',repair)
        self.assertIn('ANTES de ejecutarse',repair)
        self.assertFalse(runtime.pending)


if __name__=='__main__':
    unittest.main()
