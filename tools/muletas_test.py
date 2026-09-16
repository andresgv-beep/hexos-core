"""La medida de las muletas: que cuente lo que es y no lo que no."""
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.muletas import medir


class MuletasTest(unittest.TestCase):
    def montar(self, turnos):
        tmp = tempfile.TemporaryDirectory(prefix='hexos-muletas-')
        self.addCleanup(tmp.cleanup)
        ruta = str(Path(tmp.name) / 'work.sqlite')
        db = sqlite3.connect(ruta)
        db.executescript('''CREATE TABLE conversation (id TEXT, ts TEXT, role TEXT, text TEXT, model_text TEXT);
            CREATE TABLE tool_events (seq INTEGER PRIMARY KEY, turn_id TEXT, ts TEXT, body TEXT);
            CREATE TABLE generation_events (seq INTEGER PRIMARY KEY, turn_id TEXT, ts TEXT, body TEXT);''')
        for i, (ts, pasos, prompts) in enumerate(turnos):
            db.execute('INSERT INTO conversation VALUES (?,?,?,?,?)', ('t%d' % i, ts, 'user', 'x', 'x'))
            for paso in pasos:
                db.execute('INSERT INTO tool_events(turn_id,ts,body) VALUES (?,?,?)',
                           ('t%d' % i, ts, json.dumps(paso)))
            for prompt in prompts:
                db.execute('INSERT INTO generation_events(turn_id,ts,body) VALUES (?,?,?)',
                           ('t%d' % i, ts, json.dumps(dict(prompt=prompt))))
        db.commit(); db.close()
        return ruta

    HEXOS = dict(tool='note.show', result=dict(requested_by='hexos'))
    MODELO = dict(tool='note.show', result=dict(id='x'))
    DISENO = dict(tool='history.recall', result=dict(requested_by='hexos'))

    def test_separa_lo_que_hizo_cada_uno(self):
        m = medir(self.montar([('2026-09-16', [self.MODELO], []),
                               ('2026-09-16', [self.HEXOS], [])]))
        self.assertEqual((m['turnos'], m['acciones_modelo'], m['suplencias']), (2, 1, 1))

    def test_lo_que_hexos_hace_siempre_no_cuenta_como_muleta(self):
        # Buscar en el archivo no suple una incapacidad: lo hace siempre.
        m = medir(self.montar([('2026-09-16', [self.DISENO], [])]))
        self.assertEqual(m['suplencias'], 0)
        self.assertEqual(m['por_diseno'], 1)

    def test_un_turno_con_dos_suplencias_cuenta_como_un_turno(self):
        m = medir(self.montar([('2026-09-16', [self.HEXOS, self.HEXOS], [])]))
        self.assertEqual((m['suplencias'], sum(m['detalle'].values())), (1, 2))

    def test_los_avisos_se_cuentan_y_se_clasifican(self):
        m = medir(self.montar([('2026-09-16', [], ['AVISO DE HEXOS: ... no se ha ejecutado note_show ...']),
                               ('2026-09-16', [], ['AVISO DE HEXOS: ... falta por leer synology 2 ...'])]))
        self.assertEqual(m['avisos'], 2)
        self.assertEqual(m['avisos_detalle']['no abrió/cerró lo que dijo'], 1)
        self.assertEqual(m['avisos_detalle']['se dejó equipos o secciones'], 1)

    def test_se_puede_acotar_por_fecha_para_comparar_modelos(self):
        ruta = self.montar([('2026-09-15', [self.HEXOS], []), ('2026-09-16', [self.MODELO], [])])
        self.assertEqual(medir(ruta, desde='2026-09-16')['suplencias'], 0)
        self.assertEqual(medir(ruta, desde='2026-09-16')['turnos'], 1)

    def test_sin_turnos_no_inventa_porcentajes(self):
        self.assertEqual(medir(self.montar([]), desde='2030-01-01')['turnos'], 0)


if __name__ == '__main__':
    unittest.main()
