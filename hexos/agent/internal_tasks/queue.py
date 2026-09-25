"""Despertares persistentes y aplicación transaccional de decisiones de una ficha."""
import json
from uuid import uuid4


def ensure(db):
    db.execute('''CREATE TABLE IF NOT EXISTS media_reviews (
        id TEXT PRIMARY KEY, job_id TEXT NOT NULL, revision INTEGER NOT NULL,
        due REAL NOT NULL, status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
        lease TEXT, expires REAL, request TEXT NOT NULL, result TEXT,
        UNIQUE(job_id,revision))''')


def enqueue(store, job, now):
    from .requests import build
    if not job.get('require_review') or job['state'] not in ('awaiting_review','blocked'):
        return
    publication = job.get('review_kind') == 'publication'
    completion = job.get('completion') or {}
    # En publicación la última observación es de cuando convertía (p. ej. 73 %);
    # con ella el revisor respondía wait para siempre.
    evidence = [dict(id='job-'+str(job['revision']), kind=job.get('review_kind','incident'),
                     error=job.get('error'), observation=None if publication else job.get('observation'),
                     completion={k: completion.get(k) for k in ('status','percent','exit_code','output_bytes')}
                                if completion else None,
                     verified=job.get('validation',{}).get('valid') is True,
                     decoded=job.get('validation',{}).get('decoded') is True,
                     output_hash=job.get('validation',{}).get('sha256'))]
    request = build(job,evidence)
    store.db.execute('INSERT OR IGNORE INTO media_reviews(id,job_id,revision,due,status,request) VALUES (?,?,?,?,?,?)',
                     (request['request_id'],job['id'],job['revision'],now,'pending',json.dumps(request,ensure_ascii=False)))


class ReviewQueue:
    def __init__(self, store):
        self.store=store
        ensure(store.db)

    def claim(self, now):
        with self.store.transaction():
            rows=self.store.db.execute("SELECT * FROM media_reviews WHERE status='pending' AND due<=? AND (expires IS NULL OR expires<=?) ORDER BY rowid",(now,now)).fetchall()
            for row in rows:
                job=self.store.get(row['job_id'])
                if job['revision']!=row['revision'] or job['state'] not in ('awaiting_review','blocked'):
                    self.store.db.execute("UPDATE media_reviews SET status='obsolete' WHERE id=?",(row['id'],));continue
                if row['attempts']>=3:
                    self.store.db.execute("UPDATE media_reviews SET status='attention' WHERE id=?",(row['id'],));continue
                token=uuid4().hex
                self.store.db.execute('UPDATE media_reviews SET lease=?,expires=?,attempts=attempts+1 WHERE id=?',(token,now+60,row['id']))
                return json.loads(row['request']),token
        return None

    def finish(self, request, token, now, *, decision=None, error=None, deferred=False):
        from .requests import validate
        with self.store.transaction():
            row=self.store.db.execute('SELECT * FROM media_reviews WHERE id=?',(request['request_id'],)).fetchone()
            if not row or row['status']!='pending' or row['lease']!=token or row['expires']<=now:
                raise ValueError('Despertar expirado o ya aplicado')
            saved=json.loads(row['request'])
            if saved!=request:
                raise ValueError('Petición alterada')
            job=self.store.get(row['job_id'])
            if job['revision']!=row['revision']:
                self.store.db.execute("UPDATE media_reviews SET status='obsolete' WHERE id=?",(row['id'],));return
            if decision is not None:
                validate(request,decision,job)
            if deferred or error or (decision and decision['action']=='wait'):
                self.store.db.execute('UPDATE media_reviews SET due=?,lease=NULL,expires=NULL,result=?,attempts=attempts-? WHERE id=?',
                                     (now+(2 if deferred else 120),json.dumps(dict(error=error,decision=decision)),int(deferred),row['id']))
                return
            if decision is None:
                raise ValueError('Falta decisión')
            action=decision['action']
            if action=='publish':
                # La ficha verificada, no el texto del modelo, determina archivo y destino.
                if job.get('review_kind')!='publication' or job.get('validation',{}).get('valid') is not True:
                    raise ValueError('Falta validación de publicación')
                job.update(state='publishing',due=now,error=None)
                self.store._save(job)
            elif action=='request_stop':
                job.update(state='recovering',due=now)
                self.store._save(job)
            elif action=='report_incident':
                if job['state']!='blocked':
                    job.update(resume_state=job['state'],state='blocked',due=now)
                    self.store._save(job)
                self.store.db.execute('UPDATE media_batches SET paused=1 WHERE id=?',(job['batch_id'],))
            self.store.event(job['id'],now,'internal_decision',decision)
            self.store.db.execute("UPDATE media_reviews SET status='done',result=?,lease=NULL,expires=NULL WHERE id=?",
                                  (json.dumps(decision,ensure_ascii=False),row['id']))

    def pending(self):
        return [dict(row) for row in self.store.db.execute("SELECT id,job_id,status,attempts,due,result FROM media_reviews WHERE status IN ('pending','attention') ORDER BY rowid LIMIT 20")]
