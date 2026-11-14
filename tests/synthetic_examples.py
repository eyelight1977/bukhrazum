"""Two public end-to-end examples. Inputs/expected outputs are outside application code."""
from pathlib import Path
import argparse,base64,json,time,urllib.request
ROOT=Path(__file__).resolve().parents[1]
def request(url,body=None):
 req=urllib.request.Request(url,json.dumps(body).encode() if body is not None else None,{'Content-Type':'application/json'})
 return json.load(urllib.request.urlopen(req,timeout=30))
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--url',default='http://127.0.0.1:8765');args=parser.parse_args()
 results=[]
 for folder in sorted((ROOT/'examples').glob('0*')):
  expected=json.loads((folder/'expected.json').read_text());config={k:expected[k] for k in ['contract','target','start','end']};config['incomplete_policy']='qualified'
  def upload(p):return {'name':'document'+p.suffix,'data':base64.b64encode(p.read_bytes()).decode()}
  sources=sorted(p for p in folder.iterdir() if p.suffix in ['.docx','.xlsx'])
  # Include a renamed exact report copy: must be excluded by content hash.
  payload={'config':config,'report':upload(folder/'report.pdf'),'documents':[upload(p) for p in sources]+[upload(folder/'report.pdf')]}
  cid=request(args.url+'/api/cases',payload)['id'];print(folder.name,cid,flush=True);started=time.monotonic()
  for _ in range(240):
   data=request(args.url+'/api/cases/'+cid)
   if data['state'] in ['done','failed']:break
   time.sleep(1)
  assert data['state']=='done',data
  r=data['result'];columns={str(c['number']):c for c in r['columns']}
  for n,value in expected['reported'].items():assert columns[n]['value']==value,(n,columns[n]['value'],value)
  # Explicit test-only confirmation checks the scan's exact expected value first.
  confirmations=[]
  for n,c in columns.items():
   if int(n)>=3 and c['requires_review']:
    assert c['value'] is not None,(n,c['review_reasons'])
    data=request(args.url+f'/api/cases/{cid}/decisions',{'target':'kfz:'+n,'value':c['value'],'note':'Синтетический автотест: подтверждение чтения'});confirmations.append(int(n))
  r=data['result'];rows={str(v['column']):v for v in r['rows'] if v['column']}
  for n,value in expected['expected'].items():assert rows[n]['expected']==value,(n,rows[n])
  assert rows['15']['delta']==expected['delta'] and rows['17']['delta']==expected['delta']
  assert r['summary']['mismatch']==expected['issue_groups']
  assert len(r['arithmetic'])==5 and all(v['status']=='confirmed' for v in r['arithmetic']),r['arithmetic']
  assert r['conclusion']['kind']==expected['conclusion_after_reading_confirmation'],r['conclusion']
  combined={v['key']:v for v in r['rows'] if v['column'] is None}
  assert combined['combined:8,9']['expected']==expected['combined_8_9'] and combined['combined:8,9']['status']=='confirmed'
  assert combined['combined:13,14']['reported']==expected['combined_13_14'] and combined['combined:13,14']['expected'] is None
  assert rows['8']['status']==rows['9']['status']=='unverified'
  assert sum(d['state']=='excluded' and d.get('role')=='primary' for d in r['documents'])==expected['exclusions']
  assert any(d['role']=='report_copy' for d in r['documents'])
  html=urllib.request.urlopen(args.url+f'/api/cases/{cid}/report').read().decode()
  assert 'Первичные и расчетные документы' in html and 'data:image/png;base64,' in html
  results.append({'example':folder.name,'passed':True,'case':cid,'seconds':round(time.monotonic()-started,1),'test_reading_confirmations':confirmations})
 print(json.dumps(results,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
