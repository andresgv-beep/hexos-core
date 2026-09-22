"""Vinculación entre catálogo observado, bibliotecas permitidas y fichas."""
from pathlib import Path
import tempfile
import unittest
from hexos.agent.file_catalog.sqlite_repository import database
from hexos.agent.media_jobs.selection import resolve
from hexos.agent.media_jobs.store import JobStore, Conflict
from tools.media_jobs_test import source,profile


class SelectionTest(unittest.TestCase):
    def test_only_observed_movies_in_operator_libraries(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=database(tmp)
            db.execute('INSERT INTO scans VALUES (?,?,?,?,?)',('scan','nas','now','[]','{}'))
            db.execute('INSERT INTO files VALUES (?,?,?,?,?,?,?,?,?)',
                       ('scan','/peliculas/A.mkv','/peliculas','A.mkv',123,456,'789',10,'video'))
            db.commit();db.close()
            libs=[dict(device='nas',root='/peliculas',kind='movie')]
            selected=resolve(tmp,'scan',['/peliculas/A.mkv'],libs)
            self.assertEqual(selected[0]['identity']['filesystem_id'],'789')
            store=JobStore(tmp)
            try:
                batch=store.create(selected,profile(),'nas/HandBrake','request',0)
                self.assertEqual(batch['jobs'][0]['source']['destination'],'/peliculas/A.optimizada.mkv')
            finally: store.close()
            for paths,bindings in [(['/peliculas/missing.mkv'],libs),(['/peliculas/A.mkv'],[]),
                                   (['/peliculas/A.mkv'],[dict(device='nas',root='/peliculas',kind='series')])]:
                with self.assertRaises(ValueError): resolve(tmp,'scan',paths,bindings)

    def test_different_extensions_cannot_collide_at_destination(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=JobStore(tmp)
            try:
                s=source()
                other=dict(s,path=s['path'].replace('.mkv','.mp4'))
                with self.assertRaises(Conflict): store.create([s,other],profile(),'encoder','request',0)
            finally: store.close()


if __name__=='__main__': unittest.main()
