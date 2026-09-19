"""Run against an isolated HTTP workspace; uses the real model and local notes only."""
import concurrent.futures
import json
import sys
import time
import urllib.request

base = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8080/api'


def api(path, body=None):
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode()
    request = urllib.request.Request(base + '/' + path, data=data,
                                    headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(request, timeout=180) as response:
        return json.load(response)


with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
    start = time.monotonic()
    future = pool.submit(api, 'chat', dict(request_id='live-cancel', thinking=False,
        text='Escribe un cuento de ficción largo sobre un faro azul en una isla. Desarróllalo con muchos detalles, sin consultar herramientas.'))
    observed = []
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        state = api('status')
        generation = state.get('generation')
        if generation and generation['request_id'] == 'live-cancel':
            assert '<|' not in generation['text'] and '<channel|' not in generation['text']
            if generation['text'] and (not observed or observed[-1] != generation['text']):
                observed.append(generation['text'])
            if len(observed) >= 2 and len(observed[-1]) >= 40:
                assert not future.done(), 'preview only arrived after completion'
                break
        if future.done():
            raise AssertionError('generation finished before live text was observed: ' + str(future.result()))
        time.sleep(.1)
    assert observed, 'no live preview'
    print('LIVE_PREVIEW', dict(updates=len(observed), chars=len(observed[-1]), seconds=time.monotonic()-start), flush=True)
    assert api('cancel', {'request_id':'wrong'})['ok'] is False
    cancel_at = time.monotonic()
    assert api('cancel', {'request_id':'live-cancel'})['ok'] is True
    result = future.result(timeout=30)
    assert result.get('cancelled') and 'interrumpida' in result['reply']
    print('CANCEL', dict(ms=(time.monotonic()-cancel_at)*1000, reply=result['reply']), flush=True)
    assert api('status')['state'] == 'idle'
    assert api('status')['generation'] is None
    history = api('history')
    assert history[-1]['text'] == result['reply']
    next_reply = api('chat', dict(request_id='live-next', text='Responde únicamente: seguimos.'))
    assert 'seguimos' in next_reply['reply'].lower(), next_reply
    print('NEXT', next_reply['reply'], flush=True)
    notes = api('chat', dict(request_id='live-tools',
        text='Consulta las notas guardadas usando la herramienta de notas y dime cuántas hay.'))
    assert any(t['tool'] == 'note.list' and not t.get('failed') for t in notes['tools']), notes
    print('TOOLS', [t['tool'] for t in notes['tools']], notes['reply'], flush=True)
    print('PASS live: progressive HTTP preview, targeted cancellation, archived partial, next turn and validated tool')
