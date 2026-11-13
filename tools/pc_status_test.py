"""Estado de este PC: una lectura que contesta «qué consume», «por qué va lento»."""
import types
import unittest

from hexos.agent import catalog, pc_status

GB = 1 << 30


class Proceso:
    def __init__(self, nombre, cpu, rss, falla=False):
        self.info = dict(name=nombre)
        self.cpu, self.rss, self.falla = cpu, rss, falla

    def cpu_percent(self, _):
        if self.falla:
            raise Ps.NoSuchProcess()
        return self.cpu

    def memory_info(self):
        return types.SimpleNamespace(rss=self.rss)


class Ps:
    """Un psutil de mentira con lo justo."""
    class NoSuchProcess(Exception): pass
    class AccessDenied(Exception): pass

    def __init__(self, procesos, *, ram=(32 * GB, 20 * GB), disco=70.0, grados=60, pila=None):
        self.procesos, self.ram, self.disco, self.grados, self.pila = procesos, ram, disco, grados, pila

    def process_iter(self, _): return list(self.procesos)
    def cpu_count(self): return 8
    def cpu_percent(self, _): return 37.0
    def boot_time(self): return 1000.0
    def virtual_memory(self):
        total, libre = self.ram
        return types.SimpleNamespace(total=total, available=libre, percent=100 * (total - libre) / total)
    def disk_partitions(self, all=False):
        P = lambda d, m, f: types.SimpleNamespace(device=d, mountpoint=m, fstype=f)
        return [P('/dev/a', '/', 'ext4'), P('/dev/loop1', '/snap/x/1', 'squashfs'), P('/dev/a', '/home', 'ext4')]
    def disk_usage(self, _):
        return types.SimpleNamespace(total=500 * GB, used=int(5 * GB * self.disco), free=int(5 * GB * (100 - self.disco)),
                                     percent=self.disco)
    def sensors_temperatures(self):
        return {'coretemp': [types.SimpleNamespace(current=self.grados - 5), types.SimpleNamespace(current=self.grados)]}
    def sensors_battery(self): return self.pila


def grafica(usada=6222, procesos=(('GPU-a', '/opt/helios_runtime', '6168'),)):
    def consultar(campos, consulta='--query-gpu'):
        if consulta == '--query-gpu':
            return [['RTX 5070', '13', str(usada), '8151', '48', '8.40', 'GPU-a']]
        return [list(p) for p in procesos]
    return consultar


def dos_graficas(campos, consulta='--query-gpu'):
    """El sobremesa con el 26B repartido en las dos tarjetas y un juego en una."""
    if consulta == '--query-gpu':
        return [['RTX 2080 Ti', '40', '10900', '11264', '60', '120.0', 'GPU-a'],
                ['RTX 4070 Ti', '35', '11700', '12282', '55', '110.0', 'GPU-b']]
    return [['GPU-a', '/opt/helios_runtime', '10800'], ['GPU-b', '/opt/helios_runtime', '9000'],
            ['GPU-b', r'C:\Juegos\WoW.exe', '2400']]


def medir(ps, consultar=lambda *a, **k: []):
    return pc_status.estado(ps=ps, consultar=consultar, muestra=0, ahora=lambda: 1000.0 + 3 * 86400 + 7200)


class EstadoTest(unittest.TestCase):
    def test_suma_los_procesos_de_un_mismo_programa(self):
        r = medir(Ps([Proceso('chrome', 80, GB), Proceso('chrome', 160, 2 * GB), Proceso('vim', 8, GB // 2),
                      Proceso('quieto', 0, 3 * GB), Proceso('muerto', 0, 0, falla=True)]))
        self.assertEqual(r['mas_cpu'], [dict(programa='chrome', cpu='30 %', memoria='3,0 GB', procesos=2),
                                         dict(programa='vim', cpu='1 %', memoria='512 MB')])
        self.assertEqual([f['programa'] for f in r['mas_memoria']], ['chrome', 'quieto', 'vim'])

    def test_equipo_parado_lo_dice_en_vez_de_listar_ceros(self):
        r = medir(Ps([Proceso('quieto', 0, GB)]))
        self.assertIn('Ningún programa', r['mas_cpu'])

    def test_lo_normal_dice_que_no_hay_nada(self):
        r = medir(Ps([Proceso('vim', 8, GB)]), grafica())
        self.assertEqual(len(r['avisos']), 1)
        self.assertIn('Nada fuera de lo normal', r['avisos'][0])
        self.assertEqual(r['equipo']['encendido_hace'], '3 d 2 h')
        self.assertEqual(r['cpu'], dict(uso='37 %', nucleos=8, temperatura='60 °C'))
        self.assertEqual(r['memoria'], dict(usada='12,0 GB de 32,0 GB (38 %)', libre='20,0 GB'))
        self.assertEqual([d['montado_en'] for d in r['discos']], ['/'])       # ni snaps ni el mismo disco dos veces
        self.assertNotIn('bateria', r)

    def test_grafica_llena_dice_quien_la_ocupa(self):
        # El caso real: el modelo no cargaba porque el juego tenía 2,2 GB de la gráfica.
        r = medir(Ps([]), grafica(7900, (('GPU-a', r'C:\Program Files\WoW\WoWClassic.exe', '2185'),
                                         ('GPU-a', '/opt/helios_runtime', '5400'))))
        g = r['grafica'][0]
        self.assertEqual(g['memoria_libre'], '251 MiB')
        self.assertEqual(g['la_ocupan'], [dict(programa='helios_runtime', memoria='5400 MiB'),
                                          dict(programa='WoWClassic.exe', memoria='2185 MiB')])
        self.assertIn('helios_runtime', r['avisos'][0])
        self.assertNotIn('memoria_usada_mib', g)

    def test_con_dos_graficas_cada_una_dice_quien_la_ocupa(self):
        r = medir(Ps([]), dos_graficas)
        primera, segunda = r['grafica']
        self.assertEqual(primera['la_ocupan'], [dict(programa='helios_runtime', memoria='10800 MiB')])
        self.assertEqual(segunda['la_ocupan'], [dict(programa='helios_runtime', memoria='9000 MiB'),
                                                dict(programa='WoW.exe', memoria='2400 MiB')])
        # Los dos avisos nombran a quien ocupa SU tarjeta, no la otra.
        self.assertEqual(len(r['avisos']), 2)
        self.assertIn('10800 MiB', r['avisos'][0])
        self.assertIn('9000 MiB', r['avisos'][1])

    def test_avisa_de_ram_disco_calor_y_bateria(self):
        pila = types.SimpleNamespace(percent=9.0, power_plugged=False, secsleft=1500)
        r = medir(Ps([Proceso('blender', 10, 29 * GB)], ram=(32 * GB, GB), disco=95.0, grados=96, pila=pila))
        texto = ' '.join(r['avisos'])
        for esperado in ('RAM está al 97 %', 'blender', 'El disco / está al 95 %', '96 °C', 'Queda 9 % de batería'):
            self.assertIn(esperado, texto)
        self.assertEqual(r['bateria'], dict(carga='9 %', enchufado=False, le_queda='0 h 25 min'))

    def test_sin_grafica_nvidia_no_hay_seccion(self):
        self.assertNotIn('grafica', medir(Ps([])))

    def test_sin_psutil_lo_dice(self):
        original, pc_status.psutil = pc_status.psutil, None
        try:
            with self.assertRaisesRegex(RuntimeError, 'psutil'):
                pc_status.estado()
        finally:
            pc_status.psutil = original


class CatalogoTest(unittest.TestCase):
    def test_esta_en_el_grupo_sistema_y_no_lleva_argumentos(self):
        self.assertEqual(catalog.group_of('system.status'), 'sistema')
        self.assertNotIn('system.status', catalog.tools_for([]))
        for palabra in ('consumo', 'lentitud', 'gráfica', 'batería'):
            self.assertIn(palabra, catalog.GROUP_GUIDANCE['sistema'])


if __name__ == '__main__':
    unittest.main()
