"""El banco contra llama-server: mismo prompt y mismas herramientas, otro motor.

Sustituye a NativeTransport solo en el banco. HexOS sigue renderizando la plantilla
y parseando las llamadas, así que un cambio de resultado es del modelo o del motor,
no de cómo se le habla. Sirve para probar modelos que Héctor aún no carga.
"""
import json
import os
import subprocess
import threading
import time
import urllib.request

PUERTO = 18091
CUDA = os.path.expanduser('~/opt/cuda13/usr/local/cuda-13.1/lib64')
MOTIVOS = dict(eos='eos', word='stop', limit='max_tokens')


def resultado(datos):
    """La respuesta de /completion en la forma de un evento completed de Héctor."""
    tiempos, parada = datos.get('timings') or {}, datos.get('stop_type', 'eos')
    if datos.get('stopping_word') == '<turn|>':
        parada = 'eos'
    return dict(visible_text=datos.get('content', ''), finish_reason=MOTIVOS.get(parada, parada),
                usage=dict(generated_tokens=tiempos.get('predicted_n', 0), prefill_tokens=tiempos.get('prompt_n', 0),
                           prefill_reused=datos.get('tokens_cached', 0) - tiempos.get('prompt_n', 0) - tiempos.get('predicted_n', 0)),
                timings=dict(prefill_ms=tiempos.get('prompt_ms', 0), decode_ms=tiempos.get('predicted_ms', 0)),
                model_state=dict(cache_position=datos.get('tokens_cached', 0)))


class LlamaTransport:
    ngl = 99

    def __init__(self, binary, model, ctx, log, multimodal=None):
        # Dos ranuras: la auxiliar redacta avisos sin pisar la caché de la conversación.
        entorno = dict(os.environ, LD_LIBRARY_PATH=os.path.dirname(binary) + ':' + CUDA)
        self.proc = subprocess.Popen([binary, '-m', model, '-c', str(ctx * 2), '-np', '2', '-ngl', str(self.ngl),
                                      '--port', str(PUERTO), '--host', '127.0.0.1', '--special', '--no-webui'],
                                     stdout=log, stderr=log, env=entorno)
        self.model_info = dict(multimodal=False)
        self.cancelled = threading.Event()
        self.stop_tokens = ['<|tool_response>']
        self.pendiente = None
        self.esperar()

    def esperar(self, segundos=900):
        limite = time.time() + segundos
        while time.time() < limite:
            if self.proc.poll() is not None:
                raise RuntimeError('llama-server terminó al cargar: ' + str(self.proc.returncode))
            try:
                urllib.request.urlopen('http://127.0.0.1:%d/health' % PUERTO, timeout=2)
                return
            except OSError:
                time.sleep(1)
        raise RuntimeError('llama-server no respondió')

    def start(self, prompt, image, auxiliar=False):
        if image:
            raise RuntimeError('unsupported_attachment: el banco con llama es solo texto')
        # HexOS escribe <bos> y llama-server añade el suyo.
        self.pendiente = (prompt.removeprefix('<bos>'), 1 if auxiliar else 0)

    def pedir(self, cuerpo):
        peticion = urllib.request.Request('http://127.0.0.1:%d/completion' % PUERTO, json.dumps(cuerpo).encode(),
                                          {'Content-Type': 'application/json'})
        with urllib.request.urlopen(peticion, timeout=3600) as respuesta:
            return json.load(respuesta)

    def finish(self, update=None):
        prompt, ranura = self.pendiente
        self.pendiente = None
        # Con --special el fin de turno llega como texto; Héctor lo corta como parada.
        datos = self.pedir(dict(prompt=prompt, n_predict=3072, temperature=0, cache_prompt=True, id_slot=ranura,
                                stop=[*self.stop_tokens, '<turn|>']))
        if update:
            update(dict(type='text_delta', text=datos.get('content', '')))
        return resultado(datos)

    def control(self, peticion, cuerpo=None):
        return dict(ok=True)

    def cancel(self):
        self.cancelled.set()

    def close(self):
        self.proc.terminate()
        try:
            self.proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            self.proc.kill()
