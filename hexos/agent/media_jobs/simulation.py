"""Doble durable sin SSH ni películas: reconciliación de efectos tras caída local."""
import json
from pathlib import Path
import sqlite3


class Simulation:
    mode = 'simulation'

    def __init__(self, workspace, clock, duration=3360):
        self.clock, self.duration = clock, duration
        Path(workspace).mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(Path(workspace)/'media_simulation.sqlite')
        self.db.execute('CREATE TABLE IF NOT EXISTS effects (key TEXT PRIMARY KEY, body TEXT NOT NULL)')
        self.db.execute('CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, started REAL, stopped INTEGER)')
        self.db.commit()

    def close(self):
        self.db.close()

    def _once(self, key, receipt):
        self.db.execute('INSERT OR IGNORE INTO effects VALUES (?,?)', (key, json.dumps(receipt)))
        self.db.commit()
        return json.loads(self.db.execute('SELECT body FROM effects WHERE key=?', (key,)).fetchone()[0])

    def stage(self, job, key):
        return self._once(key, dict(copied=True, path='/storage/'+job['id']+'/input', simulated=True))

    def start(self, job, key):
        self.db.execute('INSERT OR IGNORE INTO runs VALUES (?,?,0)', (key, self.clock()))
        self.db.commit()
        return self._once(key, dict(run_id=key, simulated=True))

    def observe(self, job):
        row = self.db.execute('SELECT started,stopped FROM runs WHERE id=?', (job['run_id'],)).fetchone()
        if row is None:
            return dict(run_id=job['run_id'], status='unknown')
        elapsed = self.clock()-row[0]
        done = elapsed >= self.duration or row[1]
        return dict(run_id=job['run_id'], status='finished' if done else 'running',
                    exit_code=1 if row[1] else 0, phase='encoding',
                    percent=min(100, elapsed/self.duration*100), eta_seconds=max(0,self.duration-elapsed),
                    output_bytes=int(max(0,elapsed)*1000), activity_counter=int(elapsed), simulated=True)

    def stop(self, job, key):
        # La clave de inicio es derivable incluso si nunca se guardó run_id.
        run_id = job.get('run_id') or f"{job['id']}:{job['attempt']}:ready"
        self.db.execute('UPDATE runs SET stopped=1 WHERE id=?', (run_id,))
        self.db.commit()
        return self._once(key, dict(stopped=True, exclusive=True, simulated=True))

    def restart(self, job, key):
        return self._once(key, dict(stopped=True, healthy=True, simulated=True))

    def verify(self, job, key):
        return self._once(key, dict(valid=True, simulated=True, visual_quality='not_assessed'))

    def publish(self, job, key):
        return self._once(key, dict(published=True, path=job['source']['destination'], simulated=True))

    def index(self, job, key):
        return self._once(key, dict(indexed=True, simulated=True))
