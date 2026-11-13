"""Con qué se puede programar en este equipo: una lectura antes de crear o instalar nada."""
import unittest

from hexos.agent import catalog, entorno

SALIDAS = {
    'gcc': 'gcc (Ubuntu 15.2.0-4ubuntu4) 15.2.0\nCopyright (C) 2025',
    'g++': 'g++ (Ubuntu 15.2.0-4ubuntu4) 15.2.0',
    'nvcc': 'nvcc: NVIDIA (R) Cuda compiler driver\nCuda compilation tools, release 13.1, V13.1.80',
    'python3': 'Python 3.14.4',
    'java': 'openjdk version "25.0.1" 2026-01-20',
    'go': 'go version go1.26.8 linux/amd64',
    'git': 'git version 2.53.0',
    'raro': 'sin numeros',
}


def equipo(instalados, *, aparte=(), pip=True, venv=True, rotos=()):
    """Un equipo de mentira: qué programas hay, cuáles fuera del PATH y cuáles no contestan."""
    def localizar(nombre):
        if nombre in aparte:
            return '/opt/aparte/' + nombre, True
        return ('/usr/bin/' + nombre, False) if nombre in instalados else (None, False)

    def runner(partes):
        nombre = partes[0].rsplit('/', 1)[-1]
        if nombre in rotos:
            return 1, ''
        if partes[1:3] == ['-m', 'pip']:
            return (0, 'pip 25.1 from /usr/lib/python3') if pip else (1, 'No module named pip')
        if partes[1:2] == ['-c']:
            return (0, '') if venv else (1, 'ModuleNotFoundError')
        return 0, SALIDAS.get(nombre, nombre + ' 1.2.3')

    return entorno.reconocer(localizar=localizar, runner=runner)


class ReconocerTest(unittest.TestCase):
    def test_lee_la_version_venga_en_la_linea_que_venga(self):
        r = equipo({'gcc', 'g++', 'python3', 'go', 'git'}, aparte={'nvcc'})
        self.assertEqual(r['listo_para']['C']['tiene'], dict(gcc='15.2.0'))
        self.assertEqual(r['listo_para']['CUDA']['tiene']['nvcc'], '13.1')
        self.assertEqual(r['listo_para']['Go']['tiene'], dict(go='1.26.8'))
        self.assertEqual(r['control_de_versiones'], dict(git='2.53.0'))

    def test_listo_es_tener_todo_lo_imprescindible(self):
        r = equipo({'gcc', 'g++', 'python3', 'java'})
        self.assertEqual(list(r['listo_para']), ['C', 'C++', 'Python'])
        # El caso real del portátil: hay java para ejecutar, pero no javac para compilar.
        self.assertEqual(r['no_se_puede_todavia']['Java'], dict(falta='javac', tiene=dict(java='25.0.1')))
        self.assertEqual(r['no_se_puede_todavia']['CUDA']['falta'], 'nvcc')
        self.assertEqual(r['no_se_puede_todavia']['Rust'], dict(falta='todo: no hay nada instalado'))
        # Cada lenguaje en un solo sitio: listado en dos, el modelo dio Java por utilizable.
        self.assertEqual(set(r['listo_para']) & set(r['no_se_puede_todavia']), set())

    def test_un_grupo_se_cumple_con_cualquiera_de_sus_programas(self):
        r = equipo({'clang', 'clang++'})
        self.assertEqual(list(r['listo_para']), ['C', 'C++'])

    def test_lo_que_acompana_no_impide_trabajar(self):
        r = equipo({'gcc'})
        self.assertIn('C', r['listo_para'])
        self.assertIn('cmake', r['listo_para']['C']['sin'])

    def test_dice_lo_que_esta_fuera_del_path(self):
        # nvcc en /usr/local/cuda/bin: `which nvcc` decía que no existía.
        r = equipo({'g++'}, aparte={'nvcc'})
        self.assertIn('CUDA', r['listo_para'])
        self.assertEqual(r['fuera_del_path'], dict(nvcc='/opt/aparte/nvcc'))
        self.assertNotIn('fuera_del_path', equipo({'gcc'}))

    def test_pip_y_venv_son_piezas_de_python_que_pueden_faltar(self):
        r = equipo({'python3'}, pip=False, venv=False)
        self.assertEqual(r['listo_para']['Python'], dict(tiene=dict(python3='3.14.4'), sin=['pip', 'venv']))
        r = equipo({'python3'})
        self.assertEqual(r['listo_para']['Python']['tiene'], dict(python3='3.14.4', pip='25.1', venv='sí'))

    def test_sin_python_no_se_pregunta_por_sus_piezas(self):
        r = equipo({'gcc'})
        self.assertEqual(r['no_se_puede_todavia']['Python'], dict(falta='todo: no hay nada instalado'))

    def test_un_programa_que_no_contesta_sigue_estando_instalado(self):
        r = equipo({'gcc', 'raro', 'go'}, rotos={'go'})
        self.assertEqual(r['listo_para']['Go']['tiene'], dict(go='instalado, no dice su versión'))

    def test_equipo_vacio_lo_dice_en_vez_de_listas_vacias(self):
        r = equipo(set())
        self.assertIn('ningún lenguaje', r['listo_para'])
        self.assertEqual(len(r['no_se_puede_todavia']), len(entorno.LENGUAJES))
        self.assertEqual(r['gestores_de_paquetes'], 'ninguno conocido')
        self.assertNotIn('control_de_versiones', r)

    def test_nombra_los_gestores_con_los_que_se_instalaria(self):
        self.assertEqual(equipo({'apt', 'flatpak', 'gcc'})['gestores_de_paquetes'], ['apt', 'flatpak'])
        self.assertEqual(equipo({'winget'})['gestores_de_paquetes'], ['winget'])

    def test_contra_este_equipo_no_revienta(self):
        r = entorno.reconocer()
        self.assertTrue(r['equipo']['nombre'] and r['equipo']['sistema'])
        self.assertIn('Python', r['listo_para'])           # estas pruebas corren con él


class BuscarTest(unittest.TestCase):
    def test_mira_las_carpetas_de_las_variables_de_entorno(self):
        self.assertIn('/opt/cuda-13/bin', entorno.carpetas_aparte(dict(CUDA_HOME='/opt/cuda-13')))

    def test_lo_que_no_existe_no_tiene_ruta(self):
        self.assertEqual(entorno.buscar('programa-que-no-existe-xyz'), (None, False))


class CatalogoTest(unittest.TestCase):
    def test_esta_en_el_grupo_sistema_y_no_lleva_argumentos(self):
        self.assertEqual(catalog.group_of('system.toolchain'), 'sistema')
        self.assertNotIn('system.toolchain', catalog.tools_for([]))
        definicion = catalog.TOOLS['system.toolchain']
        self.assertEqual(definicion['effect'], 'read')
        self.assertIn('Compiladores', catalog.GROUP_GUIDANCE['sistema'])


if __name__ == '__main__':
    unittest.main()
