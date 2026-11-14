"""Escribir en el proyecto: el modelo propone, la persona aprueba y solo entonces se escribe."""
import os
import unittest

from hexos.agent import catalog, project_files
from tools.project_files_test import Base


class Escribir(Base):
    def proponer(self, **argumentos):
        with self.agente.store() as store:
            return project_files.proponer(store, **argumentos)

    def tarjeta(self, *cambios):
        pendiente = None
        for cambio in cambios:
            pendiente = project_files.tarjeta_con(pendiente, cambio)
        return pendiente

    def aplicar(self, *cambios):
        with self.agente.store() as store:
            return project_files.aplicar(store, self.tarjeta(*cambios))

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
        self.assertEqual(self.proponer(path='src/main.cu', content='int main() {}', old='lo de antes', new='int main() {}')['kind'], 'replace')
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
        visto = project_files.publico(self.tarjeta(self.proponer(path='a.txt', content='secreto no, pero largo')))
        self.assertNotIn('content', visto['changes'][0])
        self.assertIn('diff', visto['changes'][0])


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
        self.plan = self.tarjeta(self.proponer(path='src/main.cu', old='return 0;', new='return 1;'))
        self.agente.session.project_request = self.plan

    def notas(self):
        with self.agente.store() as store:
            return [r[0] for r in store.db.execute("SELECT text FROM conversation WHERE role='user' ORDER BY ts")]

    def test_el_estado_ensena_el_cambio_sin_el_contenido(self):
        self.assertEqual(self.agente.project_request['summary'], 'cambiar src/main.cu (+1 −1)')
        self.assertNotIn('content', self.agente.project_request['changes'][0])

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
        self.assertEqual([c['path'] for c in self.agente.project_request['changes']], ['src/main.cu'])

    def test_varios_ficheros_se_juntan_en_una_tarjeta_y_se_aprueban_a_la_vez(self):
        self.pedir(path='app/main.py', content='print("hola")')
        primera = self.agente.project_request['plan_id']
        self.assertEqual(self.pedir(path='app/main.py', content='print("hola")')['status'], 'pending_approval')
        self.assertEqual(self.agente.project_request['plan_id'], primera)       # repetir no cambia la tarjeta
        r = self.pedir(path='README.md', content='# App\n')
        self.assertEqual(r['pending_files'], ['app/main.py', 'README.md'])
        self.pedir(path='app/main.py', content='print("adiós")')                # proponerlo otra vez lo sustituye
        tarjeta = self.agente.project_request
        self.assertNotEqual(tarjeta['plan_id'], primera)                         # se aprueba lo que se ha visto
        self.assertEqual([c['path'] for c in tarjeta['changes']], ['README.md', 'app/main.py'])
        self.assertIn('2 ficheros', tarjeta['summary'])
        with self.assertRaises(ValueError):
            self.agente.decide_project_change(dict(plan_id=primera, approve=True))
        hecho = self.agente.decide_project_change(dict(plan_id=tarjeta['plan_id'], approve=True))
        self.assertEqual((hecho['verified'], hecho['written']), (True, ['README.md', 'app/main.py']))
        self.assertEqual(self.leer('app/main.py'), 'print("adiós")\n')
        self.assertEqual(self.leer('README.md'), '# App\n')

    def test_varios_trozos_del_mismo_fichero_se_suman(self):
        self.pedir(path='src/main.cu', old='return 0;', new='return 1;')
        r = self.pedir(path='src/main.cu', old='lanzar_atencion();', new='lanzar_atencion();\n  comprobar();')
        self.assertEqual(r['pending_files'], ['src/main.cu'])
        cambio = self.agente.project_request['changes'][0]
        self.assertEqual((cambio['added'], cambio['removed']), (2, 1))
        # Tocar otra vez lo ya cambiado se dice, en vez de «no aparece».
        with self.assertRaisesRegex(ValueError, 'ya lo cambia otra propuesta'):
            self.pedir(path='src/main.cu', old='return 0;', new='return 2;')
        self.pedir(path='src/main.cu', old='return 1;', new='return 2;')
        self.agente.decide_project_change(dict(plan_id=self.agente.project_request['plan_id'], approve=True))
        self.assertEqual(self.leer('src/main.cu'), 'int main() {\n  lanzar_atencion();\n  comprobar();\n  return 2;\n}\n')

    def test_el_trozo_casa_aunque_venga_con_el_espacio_de_la_lectura_numerada(self):
        self.escribir('conf.py', "REGISTROS = {\n    'broma': ('bromea',\n              0.9, 'Síguele'),\n    'charla': ('conversa',\n               0.7, 'Charla'),\n}\n")
        # Tal como lo copia el modelo de «2|     'broma'…»: un espacio de más en cada línea.
        self.pedir(path='conf.py', old="     'broma': ('bromea',\n               0.9, 'Síguele'),",
                   new="     'broma': ('bromea',\n               0.8, 'Síguele'),")
        self.agente.decide_project_change(dict(plan_id=self.agente.project_request['plan_id'], approve=True))
        self.assertEqual(self.leer('conf.py'), "REGISTROS = {\n    'broma': ('bromea',\n              0.8, 'Síguele'),\n    'charla': ('conversa',\n               0.7, 'Charla'),\n}\n")
        # Si el trozo podría ser dos sitios, no se adivina.
        self.escribir('doble.py', 'if a:\n    x = 1\nif b:\n        x = 1\n')
        with self.assertRaisesRegex(ValueError, 'no aparece tal cual'):
            self.pedir(path='doble.py', old='x  =  1', new='x = 2')
        with self.assertRaisesRegex(ValueError, 'no aparece tal cual'):
            self.pedir(path='doble.py', old='y = 1', new='y = 2')

    def test_un_fichero_nuevo_que_espera_tambien_se_retoca_por_trozos(self):
        self.pedir(path='app.py', content='def suma(a, b):\n    return a - b\n')
        self.pedir(path='app.py', old='a - b', new='a + b')
        self.agente.decide_project_change(dict(plan_id=self.agente.project_request['plan_id'], approve=True))
        self.assertEqual(self.leer('app.py'), 'def suma(a, b):\n    return a + b\n')

    def test_un_cambio_parcial_mandado_entero_se_acepta_y_se_le_dice(self):
        # Rechazarlo dejó al 26B reenviando el fichero entero seis veces sin cambiar de forma.
        lineas = ['linea %d' % i for i in range(1, 121)]
        self.escribir('largo.py', '\n'.join(lineas) + '\n')
        tocado = list(lineas); tocado[10] = 'cambiada'; tocado[50] = 'otra'
        r = self.pedir(path='largo.py', content='\n'.join(tocado))
        self.assertEqual((r['status'], r['added'], r['removed']), ('pending_approval', 2, 2))
        self.assertIn('con old y new', r['note'])
        self.assertNotIn('whole_file_for_partial', self.agente.project_request['changes'][0])
        self.assertNotIn('con old y new', self.pedir(path='nuevo.py', content='x = 1\n')['note'])

    def test_si_un_fichero_no_cuadra_no_se_escribe_ninguno(self):
        self.pedir(path='uno.txt', content='1')
        self.pedir(path='README.md', content='# Otro\n')
        self.escribir('README.md', 'lo tocó la persona\n')
        hecho = self.agente.decide_project_change(dict(plan_id=self.agente.project_request['plan_id'], approve=True))
        self.assertEqual((hecho['executed'], hecho['written']), (False, []))
        self.assertFalse((self.repo / 'uno.txt').exists())


class MemoriaTest(Escribir):
    def plan(self, **argumentos):
        with self.agente.store() as store:
            return project_files.dispatch(store, 'project.plan', argumentos)

    def memoria(self):
        import json
        return json.loads((self.repo / '.helios' / 'proyecto.json').read_text())

    def test_objetivo_plan_pasos_hechos_y_notas(self):
        r = self.plan(goal='Una calculadora en Python', steps=['Esqueleto', 'Funciones', 'Pruebas'])
        self.assertEqual((r['total'], r['done'], r['next']), (3, 0, '1. Esqueleto'))
        r = self.plan(done=1, note='Se usa unittest, sin dependencias')
        self.assertEqual((r['done'], r['next'], r['notes']), (1, '2. Funciones', 1))
        self.assertNotIn('Siguen pendientes', r['note'])
        # done marca un paso, no «hasta ese», y lo dice.
        r = self.plan(done=3)
        self.assertEqual(([p['done'] for p in r['steps']], 'los anteriores: 2' in r['note']), ([True, False, True], True))
        r = self.plan(steps=['Esqueleto', 'Funciones', 'Pruebas'])
        # Rehacer el plan conserva lo ya hecho.
        r = self.plan(steps=['Esqueleto', 'Funciones', 'Pruebas', 'README'])
        self.assertEqual([p['done'] for p in r['steps']], [True, False, True, False])
        self.assertEqual(self.memoria()['objetivo'], 'Una calculadora en Python')

    def test_los_pasos_valen_tambien_como_objetos(self):
        # Tal como los mandó el 26B: el turno murió en «project.plan.steps: se requiere list».
        argumentos = dict(goal='Calculadora con PyQt6', steps=[dict(done=False, goal='Verificar entorno'),
                                                               dict(step='Estructura'), 'Interfaz'])
        catalog.validate('project.plan', argumentos)
        self.assertEqual(argumentos['steps'], ['Verificar entorno', 'Estructura', 'Interfaz'])
        self.assertEqual([p['step'] for p in self.plan(**argumentos)['steps']], ['Verificar entorno', 'Estructura', 'Interfaz'])
        with self.assertRaisesRegex(ValueError, 'se requiere list'):
            catalog.validate('project.plan', dict(steps=[dict(sin='texto')]))

    def test_dice_que_falta_o_que_el_paso_no_existe(self):
        for argumentos, dice in ((dict(), 'al menos uno'), (dict(done=1), 'El plan tiene 0 pasos'),
                                 (dict(steps=[]), 'lista de pasos'), (dict(goal='  '), 'goal es un texto')):
            with self.subTest(dice=dice), self.assertRaisesRegex(ValueError, dice):
                self.plan(**argumentos)

    def test_lo_escrito_con_aprobacion_lo_apunta_hexos(self):
        self.agente.session.project_request = self.tarjeta(self.proponer(path='a.txt', content='a'))
        self.agente.decide_project_change(dict(plan_id=self.agente.project_request['plan_id'], approve=True))
        self.assertEqual([h['texto'] for h in self.memoria()['hechos']], ['a.txt'])

    def test_va_en_la_ficha_y_no_se_lee_ni_se_pisa_como_un_fichero_mas(self):
        from hexos.agent import projects
        self.plan(goal='Una calculadora', steps=['Esqueleto', 'Pruebas'], done=None)
        self.plan(done=1)
        with self.agente.store() as store:
            ficha = projects.ficha(store, projects.activo(store))
            listado = project_files.dispatch(store, 'project.files', {})
        self.assertIn('Objetivo: Una calculadora', ficha)
        self.assertIn('1. [hecho] Esqueleto 2. [pendiente] Pruebas', ficha)
        self.assertIn('Siguiente paso: 2. Pruebas', ficha)
        self.assertNotIn('.helios/proyecto.json', [f['path'] for f in listado['files']])
        with self.assertRaisesRegex(ValueError, 'No se escribe dentro de .helios'):
            self.proponer(path='.helios/proyecto.json', content='{}')

    def test_una_memoria_rota_no_tumba_nada(self):
        (self.repo / '.helios').mkdir()
        (self.repo / '.helios' / 'proyecto.json').write_text('{esto no es json')
        self.assertEqual(self.plan(note='sigo')['notes'], 1)


class CatalogoTest(unittest.TestCase):
    def test_va_en_el_grupo_del_proyecto_y_no_en_el_chat(self):
        self.assertIn('project.write', catalog.tools_for(['proyecto'], 'agente'))
        self.assertNotIn('project.write', catalog.tools_for(list(catalog.groups_in('chat')), 'chat'))
        catalog.validate('project.write', dict(path='a.txt', content='a'))
        catalog.validate('project.write', dict(path='a.txt', old='a', new='b'))


if __name__ == '__main__':
    unittest.main()
