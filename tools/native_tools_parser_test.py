import unittest
from pathlib import Path
import sys

# `native_tools_audit` es un hermano de este fichero, no parte del paquete
# `hexos`, así que el import pelado solo resolvía ejecutando DESDE tools/. En un
# barrido desde la raíz salía rojo estando sana, y una prueba que miente en rojo
# es peor que ninguna: enseña a no mirar los fallos.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from native_tools_audit import parse_native


class Test(unittest.TestCase):
    def test_prefilled_thought(self):
        calls,final,thought=parse_native('razonamiento<channel|>Respuesta',True)
        self.assertEqual(final,'Respuesta')
        self.assertEqual(thought,'razonamiento')
        self.assertEqual(calls,[])

    def test_native_call(self):
        calls,_,_=parse_native('<|tool_call>call:read_disk{server:<|"|>Faro<|"|>}<tool_call|><|tool_response>')
        self.assertEqual(calls,[{'name':'read_disk','arguments':{'server':'Faro'}}])

    def test_reject_unparsed_argument(self):
        with self.assertRaises(ValueError):
            parse_native('<|tool_call>call:read_disk{server:Faro}<tool_call|>')


if __name__=='__main__':unittest.main()
