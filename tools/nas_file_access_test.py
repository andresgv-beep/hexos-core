"""Apertura verificada, lectura parcial y entrega de copias sin ejecutar contenido."""
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from hexos.agent import nas_files, nas_files_remote, nas_document_remote
from hexos.agent.file_catalog import file_copies
from hexos.agent.chat_backend.file_http import serve
from hexos.agent.chat import Agent
from hexos.agent.chat_backend.state import AgentDependencies


class FileAccessTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.workspace=self.root/'workspace'
        self.source=self.root/'docs'
        self.source.mkdir()
        self.path=self.source/'document.md'
        self.content=('á🚀'*8000+'\nfin').encode()
        self.path.write_bytes(self.content)
        with patch.object(nas_files,'observe',side_effect=self.observe):
            self.scan=nas_files.find(self.workspace,device='nas',roots=[str(self.source)])['scan_id']

    def observe(self, workspace, device, request):
        module=nas_document_remote if request['operation']=='file_open' else nas_files_remote
        return dict(module.collect(request),device=device,observed_at='2026-09-21')

    def opened(self):
        with patch.object(nas_files,'observe',side_effect=self.observe):
            return nas_files.file_open(self.workspace,scan_id=self.scan,path=str(self.path))

    def test_unicode_long_line_pages_reconstruct_exact_text_without_ssh(self):
        result=self.opened()
        self.assertTrue(result['text_available'])
        self.assertNotIn('content_base64',result)
        pieces=[];offset=0
        with patch.object(nas_files,'observe',side_effect=AssertionError('No remote read')):
            while True:
                page=nas_files.file_read(self.workspace,file_id=result['file_id'],offset=offset,count=333)
                pieces.append(page['text'])
                if page['next_offset'] is None: break
                self.assertGreater(page['next_offset'],offset)
                offset=page['next_offset']
        self.assertEqual(''.join(pieces),self.content.decode())
        self.assertEqual(file_copies.get(self.workspace,result['file_id'])[1],self.content)

    def test_changed_or_replaced_file_does_not_publish(self):
        self.path.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'changed'):
            self.opened()
        self.path.unlink()
        self.path.symlink_to('/etc/hostname')
        with self.assertRaises(ValueError): self.opened()
        self.assertEqual(file_copies.listing(self.workspace),[])

    def test_unobserved_path_never_reaches_reader(self):
        with patch.object(nas_files,'observe') as reader:
            with self.assertRaises(ValueError):
                nas_files.file_open(self.workspace,scan_id=self.scan,path='/etc/passwd')
            reader.assert_not_called()

    def test_binary_copy_is_downloadable_not_falsely_read_as_text(self):
        self.path.write_bytes(b'\0\xff\x10')
        with patch.object(nas_files,'observe',side_effect=self.observe):
            self.scan=nas_files.find(self.workspace,device='nas',roots=[str(self.source)])['scan_id']
        result=self.opened()
        self.assertFalse(result['text_available'])
        with self.assertRaisesRegex(ValueError,'binario'):
            nas_files.file_read(self.workspace,file_id=result['file_id'])

    def test_size_limit_prevents_transport_and_empty_text_is_valid(self):
        with self.path.open('wb') as stream: stream.truncate(8*1024*1024+1)
        with patch.object(nas_files,'observe',side_effect=self.observe):
            self.scan=nas_files.find(self.workspace,device='nas',roots=[str(self.source)])['scan_id']
        with patch.object(nas_files,'observe') as reader:
            with self.assertRaisesRegex(ValueError,'8 MiB'): self.opened_without_patch()
            reader.assert_not_called()
        self.path.write_bytes(b'')
        with patch.object(nas_files,'observe',side_effect=self.observe):
            self.scan=nas_files.find(self.workspace,device='nas',roots=[str(self.source)])['scan_id']
        result=self.opened()
        self.assertIsNone(nas_files.file_read(self.workspace,file_id=result['file_id'])['next_offset'])

    def opened_without_patch(self):
        return nas_files.file_open(self.workspace,scan_id=self.scan,path=str(self.path))

    def test_http_download_matches_hash_and_does_not_serve_arbitrary_paths(self):
        result=self.opened()
        class Handler:
            def __init__(self,path): self.path=path;self.wfile=io.BytesIO();self.headers={}
            def send_response(self,status):self.status=status
            def send_header(self,key,value):self.headers[key]=value
            def end_headers(self):pass
            def respond(self,status,body):self.status=status;self.body=body
        handler=Handler('/api/files/'+result['file_id']+'/download')
        serve(handler,self.workspace)
        self.assertEqual(handler.status,200)
        self.assertEqual(hashlib.sha256(handler.wfile.getvalue()).hexdigest(),result['sha256'])
        self.assertTrue(handler.headers['Content-Disposition'].startswith('attachment;'))
        self.assertEqual(handler.headers['X-Content-Type-Options'],'nosniff')
        handler=Handler('/api/files/../../etc/passwd')
        serve(handler,self.workspace)
        self.assertEqual(handler.status,404)

    def test_dispatch_uses_catalog_device_without_asking_for_device(self):
        def files(workspace,operation,**args):
            self.assertEqual(operation,'file_open')
            self.assertNotIn('device',args)
            return {'file_id':'a'*32,'opened':True}
        agent=Agent(self.workspace,None,dependencies=AgentDependencies(nas_files=files))
        with agent.store() as store:
            result=agent.dispatcher.dispatch(store,'nas.file_open',{'scan_id':self.scan,'path':str(self.path)})
        self.assertTrue(result['opened'])


if __name__=='__main__':unittest.main()
