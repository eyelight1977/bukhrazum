"""Single-user local HTTP application, standard library only."""
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, date, timezone
from urllib.parse import urlparse, unquote
import argparse, base64, math, hashlib, html, json, mimetypes, os, re, sqlite3, threading, uuid
from .engine import ROOT, process_case, reconcile, money, ARTICLES
from .evidence import attach_views
from . import __version__

DATA=Path(os.environ.get('APP_DATA_DIR',str(ROOT/'work'))).resolve()
RESULTS=Path(os.environ.get('APP_RESULTS_DIR',str(ROOT/'results'))).resolve()
POOL=ThreadPoolExecutor(max_workers=1)

def now():return datetime.now(timezone.utc).isoformat()
def connect():
    DATA.mkdir(parents=True,exist_ok=True)
    c=sqlite3.connect(DATA/'checks.sqlite3',timeout=20);c.row_factory=sqlite3.Row
    return c
def init():
    with connect() as db:
        db.executescript('''CREATE TABLE IF NOT EXISTS checks(id TEXT PRIMARY KEY, created TEXT, state TEXT, message TEXT, config TEXT, raw TEXT);
        CREATE TABLE IF NOT EXISTS decisions(id INTEGER PRIMARY KEY AUTOINCREMENT, check_id TEXT, target TEXT, value TEXT, created TEXT, note TEXT);''')
        db.execute("UPDATE checks SET state='failed',message='Обработка была прервана. Создай новую проверку; сохранённые файлы не изменены.' WHERE raw IS NULL AND state NOT IN ('done','failed')")
    RESULTS.mkdir(parents=True,exist_ok=True)
def progress(check_id,state,message):
    with connect() as db:db.execute('UPDATE checks SET state=?, message=? WHERE id=?',(state,message,check_id))
def run_check(check_id,report,files,config):
    try:
        raw=process_case(DATA/check_id,report,files,config,lambda s,m:progress(check_id,s,m))
        with connect() as db:db.execute('UPDATE checks SET raw=?,state=?,message=? WHERE id=?',(json.dumps(raw,ensure_ascii=False),'done','Сверка готова',check_id))
    except Exception as e:
        # User-facing error, no raw source text, secrets or stack trace.
        progress(check_id,'failed',str(e) if isinstance(e,(ValueError,RuntimeError)) else f'Не удалось обработать КФЗ ({type(e).__name__})')
def view(check_id):
    with connect() as db:
        c=db.execute('SELECT * FROM checks WHERE id=?',(check_id,)).fetchone()
        if not c:raise KeyError('Проверка не найдена')
        decisions=[dict(d) for d in db.execute('SELECT id,target,value,created,note FROM decisions WHERE check_id=? ORDER BY id',(check_id,))]
    base={k:c[k] for k in ['id','created','state','message']};config=json.loads(c['config']);base['config']=config
    if c['raw']:base['result']=attach_views(reconcile(json.loads(c['raw']),decisions,config),DATA/check_id)
    return base
def persist_export(path, content):
    """Keep earlier saved reports; changed results receive a content-addressed name."""
    encoded=content.encode('utf-8')
    if path.exists():
        if path.read_bytes()==encoded:return path
        path=path.with_name(path.stem+'-'+hashlib.sha256(encoded).hexdigest()+path.suffix)
    try:
        with path.open('xb') as f:f.write(encoded)
    except FileExistsError:
        if path.read_bytes()!=encoded:raise RuntimeError('Имя экспорта уже занято другим содержимым; старый файл сохранён')
    return path

def safe_name(name):
    name=Path(str(name).replace('\\','/')).name
    if not name or name in ('.','..'):raise ValueError('Некорректное имя файла')
    return re.sub(r'[\x00-\x1f]','_',name)[:180]
def validate_config(config):
    if not str(config.get('target','')).strip():raise ValueError('Укажи строку КФЗ для проверки')
    try:start=date.fromisoformat(config['start']);end=date.fromisoformat(config['end'])
    except (KeyError,ValueError):raise ValueError('Укажи начало и конец периода')
    if start>end or (end-start).days>740:raise ValueError('Период должен быть корректным и не превышать два года')
    if config.get('incomplete_policy','qualified') not in ['qualified','strict']:raise ValueError('Неизвестное правило заключения')
    config['confidence_threshold']=float(os.environ.get('OCR_CONFIDENCE_THRESHOLD','85'))
    if not math.isfinite(config['confidence_threshold']) or not 0<=config['confidence_threshold']<=100:raise ValueError('Порог OCR должен быть от 0 до 100')
    return config

class Handler(BaseHTTPRequestHandler):
    server_version='KFZ/1'
    def log_message(self,*args):pass
    def send(self,value,status=200,ctype='application/json; charset=utf-8',headers=None):
        b=value if isinstance(value,(bytes,bytearray)) else json.dumps(value,ensure_ascii=False).encode() if ctype.startswith('application/json') else value.encode() if isinstance(value,str) else value
        self.send_response(status);self.send_header('Content-Type',ctype);self.send_header('Content-Length',str(len(b)))
        self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Cache-Control','no-store')
        for k,v in (headers or {}).items():self.send_header(k,v)
        self.end_headers();self.wfile.write(b)
    def json_body(self):
        length=int(self.headers.get('Content-Length','0'))
        if length<1 or length>60_000_000:raise ValueError('Лимит запроса: 60 МБ')
        origin=self.headers.get('Origin')
        if origin and urlparse(origin).netloc!=self.headers.get('Host'):raise ValueError('Запрос с другого сайта запрещён')
        return json.loads(self.rfile.read(length))
    def file(self,path,root):
        path=path.resolve();root=root.resolve()
        if not path.is_relative_to(root) or not path.is_file():return self.send({'error':'Файл не найден'},404)
        mime=mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
        return self.send(path.read_bytes(),ctype=mime+('; charset=utf-8' if mime.startswith('text/') else ''))
    def do_GET(self):
        try:
            path=unquote(urlparse(self.path).path)
            if path=='/api/health':return self.send({'status':'ok','version':__version__,'processing':'local','external_services':[]})
            if path=='/api/cases':
                with connect() as db:rows=[dict(r) for r in db.execute('SELECT id,created,state,message FROM checks ORDER BY created DESC LIMIT 100')]
                return self.send(rows)
            m=re.fullmatch(r'/api/cases/([a-f0-9]{32})(?:/(json|report))?',path)
            if m:
                data=view(m[1])
                if m[2]=='json':
                    encoded=json.dumps(data,ensure_ascii=False,indent=2);persist_export(RESULTS/(m[1]+'.json'),encoded)
                    return self.send(encoded.encode(),ctype='application/json; charset=utf-8',headers={'Content-Disposition':'attachment; filename="reconciliation.json"'})
                if m[2]=='report':return self.send(export_report(data),ctype='text/html; charset=utf-8')
                return self.send(data)
            m=re.fullmatch(r'/files/([a-f0-9]{32})/(.+)',path)
            if m:return self.file(DATA/m[1]/m[2],DATA/m[1])
            if path=='/':path='/index.html'
            return self.file(ROOT/'app/static'/path.lstrip('/'),ROOT/'app/static')
        except KeyError as e:self.send({'error':str(e)},404)
        except Exception:self.send({'error':'Не удалось получить результат'},500)
    def do_POST(self):
        try:
            path=urlparse(self.path).path;body=self.json_body()
            if path=='/api/cases':
                config=validate_config(body.get('config',{}))
                if not body.get('report'):raise ValueError('Нужен файл КФЗ')
                if Path(safe_name(body['report']['name'])).suffix.lower()!='.pdf':raise ValueError('Итоговая КФЗ должна быть PDF')
                if len(body.get('documents',[]))>100:raise ValueError('Лимит: 100 первичных и расчетных документов')
                uploads=[body['report'],*body.get('documents',[])]
                for upload in uploads:
                    safe_name(upload['name'])
                    if len(base64.b64decode(upload['data'],validate=True))>20_000_000:raise ValueError('Лимит одного файла: 20 МБ')
                check_id=uuid.uuid4().hex;directory=DATA/check_id;directory.mkdir()
                def save(upload,file_id):
                    name=safe_name(upload['name']);content=base64.b64decode(upload['data'],validate=True)
                    if len(content)>20_000_000:raise ValueError('Лимит одного файла: 20 МБ')
                    folder=directory/'uploads'/file_id;folder.mkdir(parents=True);f=folder/name;f.write_bytes(content);return f
                if not body.get('report'):raise ValueError('Нужен файл КФЗ')
                if len(body.get('documents',[]))>100:raise ValueError('Лимит: 100 первичных и расчетных документов')
                report=save(body['report'],'report')
                if report.suffix.lower()!='.pdf':raise ValueError('Итоговая КФЗ должна быть PDF')
                files=[(uuid.uuid4().hex,up) for up in body.get('documents',[])]
                files=[(fid,save(up,fid)) for fid,up in files]
                with connect() as db:db.execute('INSERT INTO checks VALUES(?,?,?,?,?,?)',(check_id,now(),'queued','В очереди',json.dumps(config,ensure_ascii=False),None))
                POOL.submit(run_check,check_id,report,files,config);return self.send({'id':check_id},202)
            m=re.fullmatch(r'/api/cases/([a-f0-9]{32})/decisions',path)
            if m:
                current=view(m[1]);result=current.get('result')
                if not result:raise ValueError('Извлечение ещё не завершено')
                target=body.get('target','');value=str(body.get('value','')).strip();valid=False
                if re.fullmatch(r'kfz:(?:[3-9]|1[0-7])',target):valid=True;value=money(value)
                dm=re.fullmatch(r'doc:([a-f0-9]{32}):(amount|article|date|contract)',target)
                if dm and any(d['id']==dm[1] and not d.get('error') and d.get('role')=='primary' for d in result['documents']):
                    field=dm[2];valid=True
                    if field=='amount':value=money(value)
                    if field=='article' and value not in ARTICLES:raise ValueError('Выбери статью из списка')
                    if field=='date':date.fromisoformat(value)
                    if field=='contract' and not value:raise ValueError('Укажи договор')
                if not valid or value is None:raise ValueError('Некорректное подтверждение или значение')
                with connect() as db:db.execute('INSERT INTO decisions(check_id,target,value,created,note) VALUES(?,?,?,?,?)',(m[1],target,value,now(),str(body.get('note',''))[:1000]))
                return self.send(view(m[1]))
            self.send({'error':'Неизвестный запрос'},404)
        except (ValueError,KeyError,TypeError,json.JSONDecodeError) as e:self.send({'error':str(e)},400)
        except Exception:self.send({'error':'Не удалось сохранить запрос'},500)

def export_report(data):
    from .reporting import render_report
    page=render_report(data,DATA/data['id'])
    persist_export(RESULTS/(data['id']+'.html'),page)
    return page

if __name__=='__main__':
    init();host=os.environ.get('APP_HOST','127.0.0.1');port=int(os.environ.get('APP_PORT','8765'))
    print(f'БухРазум: http://{host}:{port}',flush=True)
    server=ThreadingHTTPServer((host,port),Handler)
    try:server.serve_forever()
    except KeyboardInterrupt:print('\nОстановка помощника; сохранённые проверки остаются на диске.',flush=True)
    finally:
        server.server_close();POOL.shutdown(wait=True)
