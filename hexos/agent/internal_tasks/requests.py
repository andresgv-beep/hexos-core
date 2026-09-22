"""Fichas acotadas y decisiones sin autoridad directa sobre efectos."""
import json
from uuid import uuid4
from ..media_jobs.policy import TERMINAL


def build(job, evidence):
    if job['state'] in TERMINAL:
        raise ValueError('La tarea ya terminó')
    if not isinstance(evidence, list) or len(evidence) > 6:
        raise ValueError('Como máximo seis observaciones recientes')
    if any(not isinstance(e, dict) or not isinstance(e.get('id'), str) for e in evidence):
        raise ValueError('Cada evidencia necesita identificador')
    if len({e['id'] for e in evidence}) != len(evidence):
        raise ValueError('Identificadores de evidencia duplicados')
    allowed = ['wait', 'report_incident']
    if job['state'] == 'running':
        allowed.append('request_stop')
    if job['state'] == 'awaiting_review':
        if job.get('review_kind') == 'publication' and job.get('validation',{}).get('valid') is True:
            allowed.append('publish')
        elif job.get('review_kind') == 'recovery':
            allowed.append('request_stop')
    result = dict(schema_version=1, request_id=uuid4().hex, job_id=job['id'],
                  expected_revision=job['revision'], state=job['state'],
                  profile_id=job['profile']['id'], source=job['source'],
                  recovery_attempts=job['attempt'], evidence=evidence,
                  review_kind=job.get('review_kind'),
                  allowed_actions=allowed)
    raw = json.dumps(result, ensure_ascii=False, allow_nan=False)
    if len(raw) > 12000:
        raise ValueError('Ficha demasiado grande; resumir evidencia antes de inferir')
    return json.loads(raw)


def validate(request, decision, current_job):
    fields = {'request_id','job_id','expected_revision','action','reason','evidence_ids'}
    if not isinstance(decision, dict) or set(decision) != fields:
        raise ValueError('Esquema de decisión inválido')
    for key in ('request_id','job_id','expected_revision'):
        if type(decision[key]) is not type(request[key]) or decision[key] != request[key]:
            raise ValueError('Decisión ajena a la ficha')
    if (current_job['id'] != request['job_id'] or current_job['revision'] != request['expected_revision']
            or current_job['state'] != request['state'] or current_job['state'] in TERMINAL):
        raise ValueError('Ficha obsoleta: volver a observar')
    if decision['action'] not in request['allowed_actions']:
        raise ValueError('Acción no permitida')
    if not isinstance(decision['reason'], str) or not 1 <= len(decision['reason']) <= 600:
        raise ValueError('Motivo breve requerido')
    ids = decision['evidence_ids']
    valid = {e['id'] for e in request['evidence']}
    if not isinstance(ids, list) or any(not isinstance(i,str) or i not in valid for i in ids):
        raise ValueError('Evidencia inexistente')
    if decision['action'] != 'wait' and not ids:
        raise ValueError('Una intervención necesita evidencia')
    return decision
