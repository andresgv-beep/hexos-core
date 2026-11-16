import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { CLAVE_TEMA, GUION_TEMA, MANDOS, TEMA_ATAJOS, TEMA_BASE, TEMA_MANDOS, aplicarTema, guardarTema, leerTema,
         mismoTema, type Tema } from '../lib/helios/tema';

const oscuro: Tema = { fondo: 'negro', lienzo: 'liso', contorno: 'discreto', forma: 'recto', color: 'hueso' };

function raizFalsa() {
  const puestos: Record<string, string> = { 'data-fondo': 'azul', lang: 'es' };
  return { puestos, setAttribute: (n: string, v: string) => { puestos[n] = v; }, removeAttribute: (n: string) => { delete puestos[n]; } };
}

test('a saved theme is read back, and anything missing or unknown falls back to the usual look', () => {
  assert.deepEqual(leerTema(JSON.stringify(oscuro)), oscuro);
  assert.deepEqual(leerTema(JSON.stringify({ fondo: 'negro', color: 'fucsia', forma: 7, otra: 'cosa' })), { ...TEMA_BASE, fondo: 'negro' });
  for (const roto of [null, undefined, '', 'no es json', '[]', '"negro"', 'null'])
    assert.deepEqual(leerTema(roto), TEMA_BASE);
  assert.ok(mismoTema(leerTema('{}'), TEMA_BASE));
  // Un tema guardado antes de que existiera un mando sigue valiendo: lo que no trae va como siempre.
  assert.deepEqual(leerTema(JSON.stringify({ fondo: 'negro', color: 'cian' })), { ...TEMA_BASE, fondo: 'negro', color: 'cian' });
  assert.ok(!mismoTema(oscuro, TEMA_BASE));
});

test('applying a theme sets one attribute per control and the usual value removes it', () => {
  const raiz = raizFalsa();
  aplicarTema(raiz, { ...TEMA_BASE, color: 'cian', forma: 'suave' });
  assert.deepEqual(raiz.puestos, { lang: 'es', 'data-color': 'cian', 'data-forma': 'suave' });
  aplicarTema(raiz, TEMA_BASE);
  assert.deepEqual(raiz.puestos, { lang: 'es' }, 'the usual look is the absence of attributes');
});

test('the theme is kept in this browser, and the usual look keeps nothing', () => {
  const guardado: Record<string, string> = {};
  const almacen = { setItem: (k: string, v: string) => { guardado[k] = v; }, removeItem: (k: string) => { delete guardado[k]; } };
  guardarTema(oscuro, almacen);
  assert.deepEqual(leerTema(guardado[CLAVE_TEMA]), oscuro);
  guardarTema(TEMA_BASE, almacen);
  assert.deepEqual(guardado, {});
  guardarTema(oscuro, null);
  guardarTema(oscuro, { setItem: () => { throw new Error('QuotaExceededError'); }, removeItem: () => {} });
});

test('the script in the head applies the same theme before the first paint', () => {
  const correr = (valor: string | null, falla = false) => {
    const raiz = raizFalsa();
    delete raiz.puestos['data-fondo'];
    new Function('localStorage', 'document', GUION_TEMA)(
      { getItem: (k: string) => { if (falla) throw new Error('SecurityError'); return k === CLAVE_TEMA ? valor : null; } },
      { documentElement: raiz });
    return raiz.puestos;
  };
  for (const tema of [oscuro, TEMA_BASE, { ...TEMA_BASE, fondo: 'azul' } as Tema, ...TEMA_ATAJOS.map(a => a.tema)]) {
    const esperado = raizFalsa();
    delete esperado.puestos['data-fondo'];
    aplicarTema(esperado, tema);
    assert.deepEqual(correr(JSON.stringify(tema)), esperado.puestos);
  }
  assert.deepEqual(correr(null), { lang: 'es' });
  assert.deepEqual(correr('null'), { lang: 'es' });
  assert.deepEqual(correr('no es json'), { lang: 'es' });
  assert.deepEqual(correr(JSON.stringify({ color: 'fucsia', fondo: 'negro' })), { lang: 'es', 'data-fondo': 'negro' });
  assert.deepEqual(correr(JSON.stringify(oscuro), true), { lang: 'es' }, 'blocked storage leaves the usual look');
});

test('every option has its block in the theme stylesheet, and the stylesheet has no orphan blocks', () => {
  const hoja = readFileSync(new URL('../app/temas.css', import.meta.url), 'utf8');
  const bloques = [...hoja.matchAll(/^:root\[data-(\w+)="(\w+)"\] \{/gm)].map(m => `${m[1]}=${m[2]}`).sort();
  const opciones = MANDOS.flatMap(mando => TEMA_MANDOS[mando].opciones.map(o => o.id)
    .filter(id => id !== TEMA_BASE[mando]).map(id => `${mando}=${id}`)).sort();
  assert.deepEqual(bloques, opciones);
  for (const atajo of TEMA_ATAJOS) assert.deepEqual(leerTema(JSON.stringify(atajo.tema)), atajo.tema);
  // Los contornos discretos apagan tonos que el color acaba de dar: tienen que ir después.
  assert.ok(hoja.indexOf('data-contorno="discreto"') > hoja.lastIndexOf('data-color='));
});
