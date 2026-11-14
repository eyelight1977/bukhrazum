"""Exercise the real HTTP boundary with isolated empty storage, no OCR or user data."""
import unittest,subprocess,sys,os,socket,time,json,urllib.request,urllib.error,uuid,base64
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class HTTP(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.storage=ROOT/'work/http_tests'/uuid.uuid4().hex;cls.storage.mkdir(parents=True)
  with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
  cls.base=f'http://127.0.0.1:{port}'
  env={**os.environ,'APP_PORT':str(port),'APP_HOST':'127.0.0.1','APP_DATA_DIR':str(cls.storage),'APP_RESULTS_DIR':str(cls.storage/'exports')}
  cls.process=subprocess.Popen([sys.executable,'-m','app.server'],cwd=ROOT,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  for _ in range(100):
   try:urllib.request.urlopen(cls.base+'/api/health',timeout=1).close();return
   except OSError:time.sleep(.05)
  raise RuntimeError('HTTP test server not available')
 @classmethod
 def tearDownClass(cls):cls.process.terminate();cls.process.wait(timeout=10)
 def test_invalid_report_creates_no_upload_directory(self):
  body={'config':{'target':'Тест','start':'2026-01-01','end':'2026-01-31'},'report':{'name':'wrong.txt','data':base64.b64encode(b'not PDF').decode()},'documents':[]}
  before=set(self.storage.iterdir())
  with self.assertRaises(urllib.error.HTTPError) as c:urllib.request.urlopen(urllib.request.Request(self.base+'/api/cases',json.dumps(body).encode(),{'Content-Type':'application/json'}))
  self.assertEqual(c.exception.code,400);self.assertEqual(before,set(self.storage.iterdir()))
 def test_foreign_origin_rejected(self):
  req=urllib.request.Request(self.base+'/api/cases',b'{}',{'Content-Type':'application/json','Origin':'https://another.example'})
  with self.assertRaises(urllib.error.HTTPError) as c:urllib.request.urlopen(req)
  self.assertEqual(c.exception.code,400)
 def test_traversal_cannot_read_source(self):
  for suffix in ['/../server.py','/%2e%2e/server.py','/files/'+'a'*32+'/%2e%2e/checks.sqlite3']:
   with self.assertRaises(urllib.error.HTTPError) as c:urllib.request.urlopen(self.base+suffix)
   self.assertEqual(c.exception.code,404)
 def test_health_has_no_external_services(self):
  data=json.load(urllib.request.urlopen(self.base+'/api/health'));self.assertEqual(data['external_services'],[])
if __name__=='__main__':unittest.main()
