import test from 'node:test';
import assert from 'node:assert/strict';
import { webcrypto } from 'node:crypto';
import { createClientId } from '../lib/helios/ids';

test('HTTP client without randomUUID generates distinct v4 identifiers', () => {
  const source = { getRandomValues: webcrypto.getRandomValues.bind(webcrypto) } as Pick<Crypto, 'getRandomValues'>;
  const ids = new Set(Array.from({length: 1000}, () => createClientId(source)));
  assert.equal(ids.size, 1000);
  for (const id of ids) assert.match(id, /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
});

test('secure contexts retain native UUID generation', () => {
  const source = { randomUUID: () => '00000000-0000-4000-8000-000000000000',
    getRandomValues: () => { throw new Error('unexpected fallback'); } } as unknown as Crypto;
  assert.equal(createClientId(source), '00000000-0000-4000-8000-000000000000');
});

test('missing secure randomness fails explicitly', () => {
  assert.throws(() => createClientId({} as Crypto), /identificador seguro/);
});
