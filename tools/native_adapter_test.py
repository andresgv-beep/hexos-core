import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from hexos.agent.native import calls_from_text, NativeSyntax
from hexos.agent.catalog import validate


class Tests(unittest.TestCase):
    def test_strings_numbers_and_braces(self):
        out=calls_from_text('<|tool_call>call:document_read{id:<|"|>a{b}<|"|>,start:1,count:40}<tool_call|>')
        self.assertEqual(out[0]['arguments'],{'id':'a{b}','start':1,'count':40})
        validate('document.read',out[0]['arguments'])

    def test_multiple(self):
        out=calls_from_text('<|tool_call>call:report_list{}<tool_call|><|tool_call>call:task_current{}<tool_call|>')
        self.assertEqual(len(out),2)

    def test_invalid_does_not_parse_partial(self):
        for text in ['<|tool_call>call:x{id:<|"|>x<|"|>,id:1}<tool_call|>',
                     '<|tool_call>call:x{id:<|"|>x}',
                     '<|tool_call>call:x{}<tool_call|> basura',
                     '<|tool_call>call:x{id:__import__(1)}<tool_call|>']:
            with self.assertRaises(NativeSyntax):calls_from_text(text)

    def test_limits_and_types(self):
        with self.assertRaises(NativeSyntax):
            calls_from_text('<|tool_call>call:x{}<tool_call|>'*7)
        parsed=calls_from_text('<|tool_call>call:document_read{id:<|"|>x<|"|>,count:true}<tool_call|>')
        with self.assertRaises(ValueError):validate('document.read',parsed[0]['arguments'])


if __name__=='__main__':unittest.main()
