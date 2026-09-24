import assert from 'node:assert/strict';
import test from 'node:test';
import { createHexosTransport } from '../lib/helios/hexos';
import { listFileCopies, readFilePage } from '../lib/helios/files';
import { renderToStaticMarkup } from 'react-dom/server';
import { createElement } from 'react';
import { NasFileViewer } from '../components/NasFileViewer';

test('only successful file opens can open the NAS viewer', async () => {
  const id='a'.repeat(32);
  const fetcher=(async () => Response.json({reply:'Archivo abierto',tools:[
    {tool:'nas.file_open',result:{file_id:id}},
    {tool:'nas.file_open',failed:true,result:{file_id:'b'.repeat(32)}},
    {tool:'nas.file_open',result:{file_id:'../../outside'}},
  ]})) as typeof fetch;
  const result=await createHexosTransport('/api',fetcher).send('Abre el documento');
  assert.deepEqual(result.fileIds,[id]);
});

test('file text API validates chunks and encodes no arbitrary source path',async () => {
  const original=globalThis.fetch;
  try {
    const id='a'.repeat(32); const urls:string[]=[];
    globalThis.fetch=(async url => { urls.push(String(url)); return Response.json({text:'hola',next_offset:4}); }) as typeof fetch;
    assert.deepEqual(await readFilePage(id),{text:'hola',next_offset:4});
    assert.equal(urls[0],`/api/helios/files/${id}/text?offset=0`);
    await assert.rejects(readFilePage('../etc/passwd'),/Identificador/);
    globalThis.fetch=(async () => Response.json({text:'x',next_offset:0})) as typeof fetch;
    await assert.rejects(readFilePage(id),/inválido/);
    globalThis.fetch=(async () => Response.json([{file_id:'../etc/passwd'}])) as typeof fetch;
    assert.deepEqual(await listFileCopies(),[]);
  } finally { globalThis.fetch=original; }
});

test('viewer has a persistent files entry and renders no remote executable frame',() => {
  const html=renderToStaticMarkup(createElement(NasFileViewer,{onClose(){}}));
  assert.match(html,/Archivos del NAS/);
  assert.match(html,/Selecciona un archivo/);
  assert.doesNotMatch(html,/<iframe|<script/);
});

test('embedded NAS viewer exposes expansion without nesting a modal', () => {
  const html = renderToStaticMarkup(createElement(NasFileViewer, { embedded: true, onClose() {}, onExpand() {} }));
  assert.doesNotMatch(html, /<dialog/);
  assert.match(html, /Ampliar visor NAS/);
  assert.match(html, /Archivos del NAS/);
  const modal = renderToStaticMarkup(createElement(NasFileViewer, { onClose() {} }));
  assert.match(modal, /<dialog/);
});
