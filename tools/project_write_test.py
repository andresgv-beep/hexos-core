"""Escribir en el proyecto: el modelo propone, la persona aprueba y solo entonces se escribe."""
import os
import unittest

from hexos.agent import catalog, project_files
from tools.project_files_test import Base


class Escribir(Base):
    def proponer(self, **argumentos):
        with self.agente.store() as store:
            return project_files.proponer(store, **argumentos)

    def aplicar(self, plan):
        with self.agente.store() as store:
            return project_files.aplicar(store, plan)

    def leer(self, ruta):
        return (self.repo / ruta).read_text()


class ProponerTest(Escribir):
    def test_proponer_no_escribe_nada(self):
        plan = self.proponer(path='src/nuevo.cu', content='int f() { return 1; }')
        self.assertFalse((self.repo / 'src/nuevo.cu').exists())
        self.assertEqual((plan['kind'], plan['summary']), ('create', 'crear src/nuevo.cu (1 líneas)'))
        self.assertEqual(plan['diff'], ['@@ -0,0 +1 @@', '+int f() { return 1; }'])

    def test_un_trozo_que_aparece_una_vez(self):
        plan = self.proponer(path='src/main.cu', old='  return 0;', new='  return 1;')
        self.assertEqual((plan['kind'], plan['added'], plan['removed']), ('edit', 1, 1))
        self.assertEqual(self.leer('src/main.cu').count('return 0'), 1)
        self.assertIn('-  return 0;', plan['diff'])
        self.assertIn('+  return 1;', plan['diff'])

    def test_un_trozo_que_no_esta_o_esta_repetido_se_dice(self):
        self.escribir('src/doble.cu', 'a();\na();\n')
        for argumentos, dice in ((dict(path='src/main.cu', old='return 7;', new='x'), 'no aparece tal cual'),
                                 (dict(path='src/doble.cu', old='a();', new='b();'), 'aparece 2 veces'),
                                 (dict(path='src/main.cu', old='x', new='x'), 'iguales'),
                                 (dict(path='src/main.cu', old='x'), 'hacen falta los dos'),
                                 (dict(path='src/main.cu'), 'content con el fichero entero'),
                                 (dict(path='src/main.cu', content='a', old='b', new='c'), 'no las dos cosas')):
            with self.subTest(dice=dice), self.assertRaisesRegex(ValueError, dice):
                self.proponer(**argumentos)

    def test_la_ruta_se_localiza_al_cambiar_un_trozo(self):
        self.assertEqual(self.proponer(path='atencion.cu', old='rápida', new='veloz')['path'], 'kernels/atencion.cu')

    def test_reemplazar_entero_y_lo_que_ya_es_igual(self):
        plan = self.proponer(path='README.md', content='# Motor\nOtra cosa.\n')
        self.assertEqual((plan['kind'], plan['added'], plan['removed']), ('replace', 1, 1))
        with self.assertRaisesRegex(ValueError, 'ya tiene exactamente'):
            self.proponer(path='README.md', content='# Motor\nKernel de atención.')

    def test_los_mismos_limites_que_al_leer_y_alguno_mas(self):
        (self.repo / 'enlace').symlink_to(self.casa)
        for ruta, dice in (('../fuera.txt', 'fuera de la carpeta'), (str(self.casa / 'fuera.txt'), 'fuera de la carpeta'),
                           ('enlace/fuera.txt', 'fuera de la carpeta'), ('.env', 'credenciales'),
                           ('.ssh/authorized_keys', 'credenciales'), ('claves/servidor.pem', 'credenciales'),
                           ('.git/hooks/pre-commit', 'No se escribe dentro de .git'),
                           ('node_modules/lib/index.js', 'No se escribe dentro de node_modules'),
                           ('build/salida.o', 'No se escribe dentro de build'), ('src', 'es una carpeta'), ('.', 'no la carpeta')):
            with self.subTest(ruta=ruta), self.assertRaisesRegex(ValueError, dice):
                self.proponer(path=ruta, content='x')
        self.assertEqual((self.casa / 'fuera.txt').read_text(), 'esto está fuera del proyecto\n')

    def test_tiene_tope_y_no_toca_binarios(self):
        with self.assertRaisesRegex(ValueError, 'más de'):
            self.proponer(path='grande.txt', content='x' * (project_files.MAX_ESCRITO + 1))
        (self.repo / 'foto.bin').write_bytes(b'\x00\x01\x02')
        with self.assertRaisesRegex(ValueError, 'no es un fichero de texto'):
            self.proponer(path='foto.bin', content='x')

    def test_lo_publico_no_lleva_el_contenido_entero(self):
        visto = project_files.publico(self.proponer(path='a.txt', content='secreto no, pero largo'))
        self.assertNotIn('content', visto)
        self.assertIn('diff', visto)


class AplicarTest(Escribir):
    def test_crea_el_fichero_y_sus_carpetas_y_lo_comprueba(self):
        r = self.aplicar(self.proponer(path='src/util/suma.cu', content='int suma(int a, int b) { return a + b; }'))
        self.assertEqual((r['executed'], r['verified']), (True, True))
        self.assertEqual(self.leer('src/util/suma.cu'), 'int suma(int a, int b) { return a + b; }\n')
        self.assertEqual([p.name for p in (self.repo / 'src/util').iterdir()], ['suma.cu'])

    def test_cambia_solo_el_trozo_y_conserva_los_permisos(self):
        os.chmod(self.repo / 'src/main.cu', 0o750)
        r = self.aplicar(self.proponer(path='src/main.cu', old='return 0;', new='return 1;'))
        self.assertTrue(r['verified'])
        self.assertEqual(self.leer('src/main.cu'), 'int main() {\n  lanzar_atencion();\n  return 1;\n}\n')
        self.assertEqual((self.repo / 'src/main.cu').stat().st_mode & 0o777, 0o750)

    def test_si_el_fichero_cambio_entretanto_no_se_pisa(self):
        plan = self.proponer(path='src/main.cu', old='return 0;', new='return 1;')
        self.escribir('src/main.cu', 'int main() { return 5; }\n')
        r = self.aplicar(plan)
        self.assertEqual((r['executed'], 'ha cambiado desde que se propuso' in r['refused']), (False, True))
        self.assertEqual(self.leer('src/main.cu'), 'int main() { return 5; }\n')
        nuevo = self.proponer(path='nuevo.txt', content='a')
        self.escribir('nuevo.txt', 'lo creó la persona\n')
        self.assertFalse(self.aplicar(nuevo)['executed'])
        self.assertEqual(self.leer('nuevo.txt'), 'lo creó la persona\n')

    def test_en_otro_proyecto_no_se_aplica(self):
        plan = self.proponer(path='a.txt', content='a')
        self.agente.create_project('Otro')
        r = self.aplicar(plan)
        self.assertEqual((r['executed'], 'ya no es «Motor»' in r['refused']), (False, True))
        self.assertFalse((self.repo / 'a.txt').exists())


class TarjetaTest(Escribir):
    def setUp(self):
        super().setUp()
        self.plan = self.proponer(path='src/main.cu', old='return 0;', new='return 1;')
        self.agente.session.project_request = self.plan

    def notas(self):
        with self.agente.store() as store:
            return [r[0] for r in store.db.execute("SELECT text FROM conversation WHERE role='user' ORDER BY ts")]

    def test_el_estado_ensena_el_cambio_sin_el_contenido(self):
        self.assertEqual(self.agente.project_request['summary'], 'cambiar src/main.cu (+1 −1)')
        self.assertNotIn('content', self.agente.project_request)

    def test_aprobar_escribe_y_lo_anota(self):
        r = self.agente.decide_project_change(dict(plan_id=self.plan['plan_id'], approve=True))
        self.assertTrue(r['verified'])
        self.assertIn('return 1;', self.leer('src/main.cu'))
        self.assertIsNone(self.agente.project_request)
        self.assertIn('[La persona aprobó en la interfaz: cambiar src/main.cu', self.notas()[-1])
        self.assertIn('escrito y comprobado', self.notas()[-1])
        # Con el contexto vivo el modelo no relee el archivo: la nota va con el turno siguiente.
        self.assertEqual(self.agente.session.notas_interfaz, [self.notas()[-1]])

    def test_rechazar_no_toca_el_fichero(self):
        r = self.agente.decide_project_change(dict(plan_id=self.plan['plan_id'], approve=False))
        self.assertTrue(r['cancelled'])
        self.assertIn('return 0;', self.leer('src/main.cu'))
        self.assertIn('rechazó', self.notas()[-1])

    def test_solo_el_pendiente_y_una_vez(self):
        with self.assertRaises(ValueError):
            self.agente.decide_project_change(dict(plan_id='otro', approve=True))
        self.agente.decide_project_change(dict(plan_id=self.plan['plan_id'], approve=True))
        with self.assertRaises(ValueError):
            self.agente.decide_project_change(dict(plan_id=self.plan['plan_id'], approve=True))

    def test_cambiar_de_proyecto_retira_el_cambio(self):
        self.agente.create_project('Otro')
        self.assertIsNone(self.agente.project_request)

    def test_el_modelo_sabe_que_sigue_pendiente(self):
        self.assertIn('cambiar src/main.cu', project_files.bloque_pendiente(self.agente.project_request))
        self.assertEqual(project_files.bloque_pendiente(None), '')


class DespachoTest(Escribir):
    def pedir(self, **argumentos):
        with self.agente.store() as store:
            return self.agente.dispatcher.dispatch(store, 'project.write', argumentos)

    def test_deja_la_tarjeta_y_no_le_da_al_modelo_con_que_ejecutarla(self):
        r = self.pedir(path='src/main.cu', old='return 0;', new='return 1;')
        self.assertEqual(r['status'], 'pending_approval')
        self.assertFalse({'plan_id', 'content', 'diff'} & set(r))
        self.assertIn('return 0;', self.leer('src/main.cu'))
        self.assertEqual(self.agente.project_request['path'], 'src/main.cu')

    def test_van_de_uno_en_uno_y_repetir_no_cambia_la_tarjeta(self):
        self.pedir(path='a.txt', content='a')
        tarjeta = self.agente.project_request['plan_id']
        self.assertEqual(self.pedir(path='a.txt', content='a')['status'], 'pending_approval')
        self.assertEqual(self.pedir(path='b.txt', content='b')['status'], 'waiting_previous_change')
        self.assertEqual(self.agente.project_request['plan_id'], tarjeta)


class CatalogoTest(unittest.TestCase):
    def test_va_en_el_grupo_del_proyecto_y_no_en_el_chat(self):
        self.assertIn('project.write', catalog.tools_for(['proyecto'], 'agente'))
        self.assertNotIn('project.write', catalog.tools_for(list(catalog.groups_in('chat')), 'chat'))
        catalog.validate('project.write', dict(path='a.txt', content='a'))
        catalog.validate('project.write', dict(path='a.txt', old='a', new='b'))


if __name__ == '__main__':
    unittest.main()
