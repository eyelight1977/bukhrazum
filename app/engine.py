"""Local extraction and reconciliation. No reference answers or network clients."""
from __future__ import annotations
from pathlib import Path
from io import BytesIO
from decimal import Decimal, InvalidOperation
from datetime import datetime, date
import calendar, hashlib, html, json, math, os, re, shutil, subprocess, zipfile
import xml.etree.ElementTree as ET
from PIL import Image
from pypdf import PdfReader
import pypdfium2 as pdfium
import openpyxl
from . import kfz_layout, kfz_confirmation, kfz_assemble
from .checks import arithmetic, reading_reasons

ROOT = Path(__file__).resolve().parents[1]
ARTICLES = {'0200':'Оплата труда','0300':'Страховые взносы','0800':'Общепроизводственные','0900':'Общехозяйственные'}
MONEY = re.compile(r'(?<![\d/])[-−]?\d(?:[\d \u00a0\u202f]*\d)?[,.]\d{2}(?!\d)')
CONTRACT = re.compile(r'\b\d{1,4}/\d{1,4}/\d{1,4}-\d{1,6}\b')
MONTHS = ['январ','феврал','март','апрел','ма','июн','июл','август','сентябр','октябр','ноябр','декабр']

def dump(path, value):
    Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')

def number(value):
    if value is None or isinstance(value,bool): return None
    try:
        v=Decimal(re.sub(r'\s+','',str(value)).replace(',','.').replace('−','-'))
        return v if v.is_finite() else None
    except InvalidOperation:return None

def money(value):
    d=number(value)
    try:return str(d.quantize(Decimal('.01'))) if d is not None else None
    except InvalidOperation:return None

def guard_zip(path):
    with zipfile.ZipFile(path) as z:
        if len(z.infolist())>2500 or sum(x.file_size for x in z.infolist())>100_000_000:
            raise ValueError('Слишком большой распакованный документ')

def ocr(jobs, directory):
    """One worker for all jobs. Local language/core files, network blocked in workers."""
    directory=Path(directory); directory.mkdir(parents=True,exist_ok=True)
    jobs=[{**j,'image':str(Path(j['image']).resolve())} for j in jobs]
    dump(directory/'jobs.json',jobs)
    node=os.environ.get('OCR_NODE_BIN') or shutil.which('node')
    if not node:raise RuntimeError('Node.js не найден: нужен для локального Tesseract.js')
    env=os.environ.copy();env['OCR_MODELS_DIR']=str(ROOT/'app/models')
    completed=subprocess.run([node,'--require',str(ROOT/'app/offline.cjs'),str(ROOT/'app/ocr.cjs'),str(directory/'jobs.json'),str(directory/'output.json')],
                             env=env,cwd=ROOT,capture_output=True,text=True,timeout=180)
    if completed.returncode:
        # Keep diagnostic technical details local; avoid echoing document text to logs/UI.
        (directory/'engine_error.log').write_text(completed.stderr)
        raise RuntimeError('Не удалось запустить локальный OCR; проверь зависимости и модели, см. engine_error.log')
    return json.loads((directory/'output.json').read_text())['results']

def scan_pdf(path, directory, page_index=0):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    doc=pdfium.PdfDocument(Path(path).read_bytes())
    if len(doc)>20:raise ValueError('Лимит прототипа: 20 страниц на PDF')
    page=doc[page_index]
    if page.get_width()*page.get_height()*4>8_000_000:
        page.close();doc.close();raise ValueError('Страница PDF слишком велика для безопасной обработки')
    im=page.render(scale=2).to_pil().convert('RGB')
    im.save(directory/'page.png');page.close();doc.close()
    return im

def report_extract(path, directory, target, threshold):
    directory=Path(directory)
    for name in ['input','runs','evidence']:(directory/name).mkdir(parents=True,exist_ok=True)
    r=PdfReader(BytesIO(Path(path).read_bytes()))
    if len(r.pages)!=1:raise ValueError('Для КФЗ поддержана проверенная одностраничная форма с 17 столбцами')
    images=list(r.pages[0].images)
    if len(images)==1:
        im=Image.open(BytesIO(images[0].data))
        if im.width*im.height>8_000_000:raise ValueError('Скан КФЗ слишком велик: лимит 8 млн пикселей')
        im=im.convert('RGB')
    else:
        im=scan_pdf(path,directory/'render')
    im.save(directory/'input/scan.png')
    im.resize((im.width*3,im.height*3),Image.Resampling.LANCZOS).save(directory/'input/scan_3x.png')
    base=ocr([{'id':'page_psm3','image':directory/'input/scan_3x.png','psm':3}],directory/'runs/base_ocr')
    dump(directory/'runs/baseline.json',{'results':base})
    kfz_layout.extract(directory,target)
    jobs=json.loads((directory/'runs/cell_jobs.json').read_text())
    for j in jobs:j['image']=directory/j['image']
    dump(directory/'runs/cells.json',{'results':ocr(jobs,directory/'runs/header_ocr')})
    kfz_confirmation.prepare(directory)
    jobs=json.loads((directory/'runs/confirmation_jobs.json').read_text())
    for j in jobs:j['image']=directory/j['image']
    dump(directory/'runs/confirmation.json',{'results':ocr(jobs,directory/'runs/confirmation_ocr')})
    result=kfz_assemble.assemble(directory,threshold)
    match=CONTRACT.search(base[0]['text']);result['contract']=match.group() if match else None
    for c in result['columns']:
        c['evidence']='report/'+c['evidence']
        for h in c['header_path']:h['evidence']='report/'+h['evidence']
        if c.get('text_only_confirmation'):
            confirm=c['text_only_confirmation'];confirm['evidence']='report/'+str(Path(confirm['evidence']).relative_to(directory)) if Path(confirm['evidence']).is_absolute() else 'report/'+confirm['evidence']
    result['source_copy']=str(Path(path).relative_to(directory.parent))
    result['source_manifest']='report/source_manifest.json'
    dump(directory/'source_manifest.json',{'source_copy':result['source_copy'],'source_sha256':hashlib.sha256(Path(path).read_bytes()).hexdigest(),
        'image_size':list(im.size),'page':1,'target':target,'engine':'Tesseract.js 7.0.0','confidence_threshold':threshold})
    result['source_image']='report/input/scan.png';result['raw_ocr_path']='report/runs/baseline.json'
    return result

def text_metadata(text):
    norm=text.replace('\u00a0',' ').replace('\u202f',' ')
    contract=CONTRACT.search(norm)
    dates=[]
    for m in re.finditer(r'\b(\d{2})[.](\d{2})[.](20\d{2})\b',norm):
        try:dates.append(date(int(m[3]),int(m[2]),int(m[1])).isoformat())
        except ValueError:pass
    docnum=re.search(r'(?:№\s*|Документ:\s*|(?:Акт|УПД|записка|Справка[^\n]{0,18})\s+)([A-ZА-ЯЁа-яa-z0-9][A-ZА-ЯЁа-яa-z0-9/\-]{1,30})',norm,re.I)
    result={'contract':contract.group() if contract else None,'date':dates[0] if dates else None,
            'document_number':docnum.group(1) if docnum and re.search(r'\d',docnum.group(1)) else None}
    period=re.search(r'Период:\s*([^\n|]+)',norm,re.I)
    if period and not result['date']:
        value=period[1].strip().lower();year=re.search(r'20\d{2}',value)
        if year:
            for i,month in enumerate(MONTHS,1):
                if value.startswith(month):result['date']=date(int(year[0]),i,1).isoformat();break
    return result

def classify(text):
    t=text.lower().replace('ё','е')
    if 'начислено взносов' in t:return '0300',['0300'],'Заголовок расчёта страховых взносов',False
    if 'ведомость по оплате труда' in t or ('0201' in t and '0202' in t):return '0200',['0200'],'Коды начислений и заголовок зарплатной ведомости',False
    if 'общехозяйствен' in t:return '0900',['0900'],'В документе прямо указано общехозяйственное назначение',False
    if 'общепроизводствен' in t:return '0800',['0800'],'В документе прямо указано общепроизводственное назначение',False
    production=any(w in t for w in ['производствен','калибров','испытательного стенда','измерительного оборудования'])
    administration=any(w in t for w in ['административ','управленческ','управления договором','организационно-управленческ','общехозяйствен'])
    if production and not administration:return '0800',['0800'],'Назначение операции: обеспечение производственных работ/оборудования',False
    if administration and not production:return '0900',['0900'],'Назначение операции: управление и административное обеспечение',False
    candidates=['0800','0900'] if production and administration else list(ARTICLES)
    return None,candidates,'Назначение неоднозначно: требуется выбор пользователя',True

def select_amount(text):
    matches=list(MONEY.finditer(text));scored=[]
    dates=[m.span() for m in re.finditer(r'\b\d{2}\.\d{2}\.\d{4}\b',text)]
    for m in matches:
        if any(m.start()<end and m.end()>start for start,end in dates):continue
        context=text[max(0,m.start()-100):min(len(text),m.end()+30)]
        score=0
        if re.search(r'итого|к оплате|сумма|стоимость|стоимост|всего',context,re.I):score+=3
        if re.search(r'руб|₽',context,re.I):score+=2
        if re.search(r'\d{2}\.\d{2}\.20\d{2}',m.group()):score-=10
        scored.append((score,m))
    if not scored:return None,None,True
    best=max(s for s,_ in scored)
    top=[m for s,m in scored if s==best]
    distinct={money(m.group()) for m in top}
    chosen=top[-1]
    context=text[max(0,chosen.start()-40):chosen.end()+35]
    value=number(chosen.group())
    if re.search(r'тыс\.?\s*руб',context,re.I):value*=1000
    currency_unknown=bool(re.search(r'USD|EUR|доллар|евро|\$|€',context,re.I))
    return money(value),chosen,len(distinct)>1 or best<2 or currency_unknown

def pdf_value_evidence(path, page_index, needle, image, directory, occurrence=0):
    doc=pdfium.PdfDocument(Path(path).read_bytes());page=doc[page_index];text=page.get_textpage()
    search=text.search(needle);match=None
    for _ in range(occurrence+1):match=search.get_next()
    if not match:
        text.close();page.close();doc.close();return None
    start,count=match;boxes=[text.get_charbox(i) for i in range(start,start+count)]
    left=min(b[0] for b in boxes);right=max(b[2] for b in boxes);bottom=min(b[1] for b in boxes);top=max(b[3] for b in boxes)
    sx=image.width/page.get_width();sy=image.height/page.get_height()
    bbox=[max(0,int(left*sx)-30),max(0,int((page.get_height()-top)*sy)-22),min(image.width,math.ceil(right*sx)+30),min(image.height,math.ceil((page.get_height()-bottom)*sy)+22)]
    image.crop(bbox).save(Path(directory)/'amount.png')
    text.close();page.close();doc.close();return bbox

def extract_primary(path, file_id, case_directory):
    path=Path(path);directory=Path(case_directory)/'sources'/file_id;directory.mkdir(parents=True,exist_ok=True)
    ext=path.suffix.lower();text='';amount=None;amount_match=None;amount_ambiguous=False;components={};locator='';image=None;bbox=None;scan=False
    if ext in ['.xlsx','.docx']:guard_zip(path)
    if ext=='.xlsx':
        wb=openpyxl.load_workbook(BytesIO(path.read_bytes()),data_only=False,read_only=True,keep_links=False)
        if any('эталон' in name.lower() for name in wb.sheetnames):
            wb.close()
            return {'id':file_id,'name':path.name,'role':'reference','text':'','excluded_reason':'Контрольная книга исключена до извлечения значений'}
        texts=[];evidence=[];found=[]
        for sheet in wb:
            for row in sheet.iter_rows(max_row=min(sheet.max_row or 10000,10000),max_col=min(sheet.max_column or 100,100)):
                cells=[c for c in row if c.value is not None]
                if not cells:continue
                texts.append(' | '.join(str(c.value) for c in cells))
                vals=[str(c.value) for c in cells]
                if any(v in ('0201','0202') for v in vals):
                    nums=[c for c in cells if isinstance(c.value,(int,float))]
                    if nums:
                        code=next(v for v in vals if v in ('0201','0202'));cell=nums[-1]
                        components[code]=money((number(components.get(code)) or Decimal(0))+number(cell.value));found.append((sheet.title,cell.coordinate))
                        evidence.append((sheet.title,[f'{c.coordinate}: {c.value}' for c in cells]))
            # Insurance is identified by labels, never by the workbook filename.
            for row in sheet.iter_rows(max_row=min(sheet.max_row or 10000,10000),max_col=min(sheet.max_column or 100,100)):
                header=next((c for c in row if c.value and 'начислено взносов' in str(c.value).lower()),None)
                if header:
                    for next_row in sheet.iter_rows(min_row=header.row+1,max_row=min(header.row+15,sheet.max_row or header.row+15)):
                        cell=next_row[header.column-1]
                        if isinstance(cell.value,(int,float)):
                            amount=money(cell.value);found.append((sheet.title,cell.coordinate));evidence.append((sheet.title,[f'{c.coordinate}: {c.value}' for c in next_row if c.value is not None]));break
        text='\n'.join(texts)
        if components:amount=money(sum(number(v) for v in components.values()))
        locator='; '.join(f'{sheet}!{cell}' for sheet,cell in found)
        snippet='\n'.join(f'{s}: '+ ' | '.join(v) for s,v in evidence)
        (directory/'fragment.html').write_text('<!doctype html><meta charset="utf-8"><title>Фрагмент таблицы</title><pre style="white-space:pre-wrap;font:16px system-ui">'+html.escape(snippet or text[:4000])+'</pre>')
        wb.close()
    elif ext=='.docx':
        with zipfile.ZipFile(path) as z:
            xml=ET.fromstring(z.read('word/document.xml'));ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
            paragraphs=[''.join(el.itertext()) for el in []]
            paragraphs=[''.join(n.text or '' for n in para.findall('.//w:t',ns)) for para in xml.findall('.//w:p',ns)]
            text='\n'.join(paragraphs)
        amount,amount_match,amount_ambiguous=select_amount(text)
        offset=0;paragraph_index=None
        for i,v in enumerate(paragraphs):
            if amount_match and offset<=amount_match.start()<offset+len(v):paragraph_index=i+1;break
            offset+=len(v)+1
        locator=f'Абзац {paragraph_index}' if paragraph_index else 'Текст документа'
        snippet=text[max(0,(amount_match.start() if amount_match else 0)-250):min(len(text),(amount_match.end() if amount_match else 0)+100)]
        (directory/'fragment.html').write_text('<!doctype html><meta charset="utf-8"><title>Фрагмент документа</title><pre style="white-space:pre-wrap;font:16px system-ui">'+html.escape(snippet)+'</pre>')
    elif ext in ['.pdf','.png','.jpg','.jpeg']:
        ocr_words=[];page_texts=[];ocr_runs=None;page_index=0
        if ext=='.pdf':
            reader=PdfReader(BytesIO(path.read_bytes()))
            if len(reader.pages)>20:raise ValueError('Лимит: 20 страниц на PDF')
            pages=[page.extract_text() or '' for page in reader.pages]
            image=scan_pdf(path,directory)
            if all(t.strip() for t in pages):page_texts=pages;text='\n'.join(pages)
            else:
                jobs=[]
                for i in range(len(pages)):
                    page_dir=directory/f'page_{i+1}';im=scan_pdf(path,page_dir,i)
                    im.resize((im.width*2,im.height*2),Image.Resampling.LANCZOS).save(page_dir/'ocr.png')
                    jobs.append({'id':str(i+1),'image':page_dir/'ocr.png','psm':3})
                runs=ocr(jobs,directory/'ocr');ocr_runs=runs;page_texts=[r['text'] for r in runs];text='\n'.join(page_texts);scan=True
                # Use full-page evidence for later pages; first page gets a precise OCR crop.
                from .kfz_layout import read_words
                first=runs[0]
                for line in read_words(first):
                    for w in line:
                        w['bbox']=[x*3/2 for x in w['bbox']];ocr_words.append(w)
        else:
            image=Image.open(path)
            if image.width*image.height>8_000_000:raise ValueError('Изображение слишком большое')
            image=image.convert('RGB')
            image.save(directory/'page.png');image.resize((image.width*2,image.height*2),Image.Resampling.LANCZOS).save(directory/'ocr.png')
            runs=ocr([{'id':'1','image':directory/'ocr.png','psm':3}],directory/'ocr');text=runs[0]['text'];scan=True
            from .kfz_layout import read_words
            for line in read_words(runs[0]):
                for w in line:w['bbox']=[x*3/2 for x in w['bbox']];ocr_words.append(w)
        amount,amount_match,amount_ambiguous=select_amount(text)
        if amount_match and ext=='.pdf':
            offset=0
            for i,page_text in enumerate(page_texts):
                if offset<=amount_match.start()<offset+len(page_text):page_index=i;break
                offset+=len(page_text)+1
            if page_index:
                image=scan_pdf(path,directory,page_index)
                if ocr_runs:
                    from .kfz_layout import read_words
                    ocr_words=[]
                    for line in read_words(ocr_runs[page_index]):
                        for w in line:w['bbox']=[x*3/2 for x in w['bbox']];ocr_words.append(w)
        locator=f'Страница {page_index+1}';snippet=text[max(0,(amount_match.start() if amount_match else 0)-160):min(len(text),(amount_match.end() if amount_match else 0)+80)]
        if amount_match and not scan and ext=='.pdf':bbox=pdf_value_evidence(path,page_index,amount_match.group(),image,directory, page_texts[page_index][:amount_match.start()-sum(len(t)+1 for t in page_texts[:page_index])].count(amount_match.group()))
        elif amount_match and scan:
            # Locate the actual decimal-token suffix, then keep all nearby number words.
            suffix=amount_match.group().split()[-1]
            matches=[w for w in ocr_words if suffix in w['text']]
            if matches:
                match=matches[-1];cy=(match['bbox'][1]+match['bbox'][3])/2
                nearby=[w for w in ocr_words if abs((w['bbox'][1]+w['bbox'][3])/2-cy)<18 and re.fullmatch(r'[\d ,.\-]+',w['text'])]
                if nearby:
                    bbox=[max(0,math.floor(min(w['bbox'][0] for w in nearby))-12),max(0,math.floor(min(w['bbox'][1] for w in nearby))-12),min(image.width,math.ceil(max(w['bbox'][2] for w in nearby))+12),min(image.height,math.ceil(max(w['bbox'][3] for w in nearby))+12)]
                    image.crop(bbox).save(directory/'amount.png')
                    amount_ambiguous=amount_ambiguous or min(w['confidence'] for w in nearby)<85
    else:raise ValueError('Поддерживаются PDF, DOCX, XLSX, PNG и JPEG')
    if re.search(r'НАБОР ДАННЫХ ДЛЯ КЕЙСА',text,re.I):
        return {'id':file_id,'name':path.name,'role':'instructions','text':'','excluded_reason':'Инструкция к набору, не первичный документ'}
    if ext=='.xlsx' and ('ПРАВИЛЬНЫЕ ОТВЕТЫ' in text or 'ЭТАЛОН ПРОВЕРКИ' in text):
        return {'id':file_id,'name':path.name,'role':'reference','text':'','excluded_reason':'Контрольный файл не участвует в извлечении и расчётах'}
    metadata=text_metadata(text)
    if ext=='.xlsx':
        period=re.search(r'Период:\s*([^\n|]+)',text,re.I)
        if period:
            value=period[1].lower();year=re.search(r'20\d{2}',value)
            if year:
                for i,month in enumerate(MONTHS,1):
                    if value.strip().startswith(month):metadata['date']=date(int(year[0]),i,1).isoformat();break
    article,candidates,reason,review=classify(text)
    evidence=f'sources/{file_id}/'+('amount.png' if (directory/'amount.png').exists() else 'page.png' if image else 'fragment.html')
    dump(directory/'extracted.json',{'text':text,'metadata':metadata,'amount':amount,'components':components})
    return {'id':file_id,'name':path.name,'role':'primary','hash':hashlib.sha256(path.read_bytes()).hexdigest(),
            'text':text,**metadata,'amount':amount,'components':components,'article':article,'candidates':candidates,
            'source_amount_text':amount_match.group() if amount_match else None,'amount_unit':'рубли',
            'classification_reason':reason,'article_requires_review':review,'amount_requires_review':amount_ambiguous or amount is None,
            'evidence':evidence,'bbox':bbox,'snippet':snippet,'locator':locator,'source':str(path.relative_to(case_directory))}

def month_keys(start,end):
    y,m=start.year,start.month;keys=[]
    while (y,m)<=(end.year,end.month):
        keys.append(f'{y:04d}-{m:02d}');m+=1
        if m==13:y,m=y+1,1
    return keys

def reconcile(raw, decisions, config):
    """Apply append-only user decisions over immutable extraction, then recalculate."""
    docs=json.loads(json.dumps(raw['documents']));report=json.loads(json.dumps(raw['report']))
    effective={}
    for decision in decisions:effective[decision['target']]=decision
    cols={c['number']:c for c in report['columns']}
    for n,c in cols.items():
        override=effective.get(f'kfz:{n}')
        c['effective_value']=override['value'] if override else c['value']
        c['user_decision']=override
        c['ready']=n<3 or (number(c['effective_value']) is not None and (not c.get('requires_review') or override is not None))
        c['intrinsic_ready']=c['ready']
    dependencies={6:[7,8],5:[6,9],11:[12,13],10:[11,14],17:[5,10,15,16]}
    def resolved(n):
        return cols[n]['intrinsic_ready'] and all(resolved(k) for k in dependencies.get(n,[]))
    for n,c in cols.items():
        c['ready']=resolved(n)
        c['unresolved_dependencies']=[k for k in dependencies.get(n,[]) if not resolved(k)]
        c['reading_reasons']=reading_reasons(c)
    contract=config.get('contract') or report.get('contract')
    start=date.fromisoformat(config['start']);end=date.fromisoformat(config['end']);months=month_keys(start,end)
    seen={};warnings=[];active=[];blocked=set();reasons={k:[] for k in ARTICLES}
    for doc in docs:
        if doc.get('role')!='primary':doc['state']='excluded';continue
        for field in ['amount','article','date','contract']:
            decision=effective.get(f'doc:{doc["id"]}:{field}')
            doc[f'{field}_decision']=decision
            doc[f'effective_{field}']=decision['value'] if decision else doc.get(field)
        if doc.get('error'):
            doc['state']='error';blocked.update(ARTICLES);warnings.append(doc['error']);continue
        c=doc['effective_contract'];dt=doc['effective_date'];art=doc['effective_article'];amt=number(doc['effective_amount'])
        if c and contract and c!=contract:doc['state']='excluded';doc['excluded_reason']='Другой договор';continue
        if dt and not start<=date.fromisoformat(dt)<=end:doc['state']='excluded';doc['excluded_reason']='Вне периода проверки';continue
        key=doc.get('hash') or doc['id']
        semantic=(c,dt,doc.get('document_number'),str(amt))
        if key in seen or (doc.get('document_number') and semantic in seen):
            doc['state']='excluded';doc['excluded_reason']='Дубликат';doc['duplicate_of']=seen.get(key,seen.get(semantic));continue
        seen[key]=doc['id'];seen[semantic]=doc['id']
        unresolved=[]
        if not c or not contract:unresolved.append('Не определён договор')
        if not dt:unresolved.append('Не определён период/дата')
        if not art or (doc.get('article_requires_review') and not doc['article_decision']):unresolved.append('Подтверди статью расходов')
        if amt is None or (doc.get('amount_requires_review') and not doc['amount_decision']):unresolved.append('Уточни или подтверди сумму')
        if unresolved:
            doc['state']='review';doc['review_reasons']=unresolved
            for a in ([art] if art else doc.get('candidates',list(ARTICLES))):blocked.add(a);reasons[a].extend(unresolved)
        else:doc['state']='included';active.append(doc)
    expected={};sources={k:[] for k in ARTICLES};base=bonus=None
    for article in ARTICLES:
        group=[d for d in active if d['effective_article']==article];sources[article]=[d['id'] for d in group]
        complete=bool(group) and article not in blocked
        if article in ['0200','0300']:
            present={d['effective_date'][:7] for d in group}
            missing=sorted(set(months)-present)
            if missing:complete=False;reasons[article].append('Нет документов за месяцы: '+', '.join(missing))
            repeated=[m for m in present if sum(d['effective_date'].startswith(m) for d in group)>1]
            if repeated:complete=False;reasons[article].append('Несколько месячных расчётов: '+', '.join(repeated))
        expected[article]=sum((number(d['effective_amount']) for d in group),Decimal(0)) if complete else None
        if not group:reasons[article].append('Нет достаточных подтверждающих документов')
        if article=='0200' and complete:
            base=bonus=Decimal(0)
            for doc in group:
                if '0201' not in doc['components'] or '0202' not in doc['components']:
                    base=bonus=None;break
                base+=number(doc['components']['0201']);bonus+=number(doc['components']['0202'])
            # User change to total alone does not establish the split.
            if any(d['amount_decision'] and number(d['effective_amount'])!=number(d['amount']) for d in group):base=bonus=None
    mapping={5:'0200',7:'0200',10:'0300',15:'0800',16:'0900'}
    rows=[]
    for n in range(3,18):
        c=cols[n];article=mapping.get(n);exp=base if n==7 else expected.get(article) if article else None
        if n==17:exp=sum(expected.values(),Decimal(0)) if all(v is not None for v in expected.values()) else None
        actual=number(c['effective_value']);ready=c['ready'];why=[]
        if not c['intrinsic_ready']:why.extend(c['reading_reasons'])
        if c['unresolved_dependencies']:why.append('Для завершения сверки подтверди значения КФЗ: '+', '.join((cols[k].get('name') or 'Показатель')+' (столбец '+str(k)+')' for k in c['unresolved_dependencies']))
        if exp is None:
            detail_reason={3:'Нет документов, подтверждающих трудоёмкость',4:'Нет отдельного подтверждения материальных затрат; отсутствие документов не доказывает ноль',
                17:'Недостаточно подтверждающих документов для одной или нескольких статей итога (0200, 0300, 0800, 0900)'}
            why.extend(reasons.get(article,[]) or [detail_reason.get(n,'Недостаточно первичных и расчетных документов для отдельной детализации')])
        delta=actual-exp if actual is not None and exp is not None else None
        status='unverified' if not ready or exp is None else 'confirmed' if delta.quantize(Decimal('.01'))==0 else 'mismatch'
        rows.append({'key':f'kfz:{n}','column':n,'name':c['name'] or f'Столбец {n}','reported':money(actual),'expected':money(exp),'delta':money(delta),
                     'status':status,'reasons':why,'sources':[x for ids in sources.values() for x in ids] if n==17 else sources.get(article,[]),'evidence':c['evidence'],
                     'ocr_value':c['value'],'ocr_text':c['raw_text'],'requires_review':not ready,'decision':c['user_decision'],
                     'category':'сумма' if status=='mismatch' else 'недостаточно данных' if status=='unverified' else None})
    # Combined evidence never establishes its individual components.
    insurance_group=[d for d in active if d['effective_article']=='0300']
    insurance_extra=None
    if expected['0300'] is not None and all(number(d.get('insurance_components',{}).get('extra_and_reserve')) is not None for d in insurance_group):
        insurance_extra=sum((number(d['insurance_components']['extra_and_reserve']) for d in insurance_group),Decimal(0))
    combined_specs=[
        ('Дополнительная зарплата и резерв отпусков — столбцы 8+9',[8,9],bonus,'0200'),
        ('Взносы с дополнительной зарплаты и резерва отпусков — столбцы 13+14',[13,14],insurance_extra,'0300'),
        ('Сумма четырёх основных статей',[5,10,15,16],None,None)]
    for label,numbers,exp,article in combined_specs:
        if article is None:
            exp=sum(expected.values(),Decimal(0)) if all(v is not None for v in expected.values()) else None
        vals=[number(cols[n]['effective_value']) for n in numbers]
        actual=sum(vals,Decimal(0)) if all(v is not None for v in vals) else None
        ready=all(cols[n]['ready'] for n in numbers)
        delta=actual-exp if actual is not None and exp is not None else None
        status='unverified' if not ready or exp is None else 'confirmed' if money(delta)=='0.00' else 'mismatch'
        why=[]
        for n in numbers:
            if not cols[n]['intrinsic_ready']:why.extend(f'Столбец {n}: {x}' for x in cols[n]['reading_reasons'])
            if cols[n]['unresolved_dependencies']:why.append(f'Для завершения сверки подтверди значения составляющих показателя в столбце {n}')
        if exp is None:
            why.append('Недостаточно подтверждающих документов: нет независимой детализации взносов по дополнительной зарплате и резерву отпусков' if numbers==[13,14] else 'Недостаточно подтверждающих документов для объединённого показателя')
        if numbers==[13,14]:why.append('Общая сумма взносов и предполагаемый процент не подтверждают эту разбивку')
        why.append('Проверяется только объединённая сумма; отдельные составляющие сохраняют свой статус')
        rows.append({'key':'combined:'+','.join(map(str,numbers)),'column':None,'columns':numbers,'name':label,
                     'reported':money(actual),'expected':money(exp),'delta':money(delta),'status':status,
                     'sources':sources.get(article,[]) if article and exp is not None else [x for ids in sources.values() for x in ids] if article is None else [],
                     'reasons':why,'category':'сумма' if status=='mismatch' else 'недостаточно данных' if status=='unverified' else None})
    # Attach indicator-specific amounts and locators. A document total is never a wage component.
    by_id={d['id']:d for d in docs}
    for row in rows:
        row.setdefault('columns',[row['column']] if row['column'] else [])
        row['source_label']='Документы'
        row['terms']=[]
        for source_id in row['sources']:
            d=by_id[source_id]
            component='0201' if row['column']==7 else '0202' if row['columns']==[8,9] else 'insurance_extra' if row['columns']==[13,14] else 'total'
            value=d.get('components',{}).get(component) if component in ['0201','0202'] else d.get('insurance_components',{}).get('extra_and_reserve') if component=='insurance_extra' else d.get('effective_amount')
            row['terms'].append({'document_id':source_id,'component':component,'value':money(value),'label':d['name']})
        if row['status']=='confirmed':row['reasons'].insert(0,'Значение совпадает с независимой суммой по документам до копейки')
        elif row['status']=='mismatch':row['reasons'].insert(0,'Значение отчёта отличается от суммы по документам')
        elif row['delta']=='0.00':row['reasons'].insert(0,'Сумма по документам совпадает со значением КФЗ')
        row['status_label']=('Недостаточно подтверждающих документов' if row['key']=='combined:13,14' and row['expected'] is None else
                             'Подтверждено документами' if row['status']=='confirmed' else 'Расхождение' if row['status']=='mismatch' else 'Не проверено')
        if row['key']=='combined:5,10,15,16' or row['column']==17:
            row['derived_from']=[r['key'] for r in rows if r['column'] in [5,10,15,16] and r['status']=='mismatch']
            row['reasons'].append('Итог по статьям 5, 10, 15, 16. Расхождения статей не учитываются повторно и не суммируются с этим итогом')
            if row['column']==17:row['reasons'].append('Проверка общей суммы не подтверждает каждую статью и её внутреннюю разбивку')
    arithmetic_rows=arithmetic(cols,number,money)
    if next(r for r in arithmetic_rows if r['column']==17)['status']=='mismatch':
        next(r for r in rows if r['column']==17)['derived_from'].append('arithmetic:17')
    # Recommendations use statuses, never just an empty mismatch counter.
    # Combined diagnostics explain a root mismatch; do not count it as a second error.
    mismatches=[r for r in rows if r['status']=='mismatch' and r['key']!='combined:5,10,15,16' and r['column']!=17];unknown=[r for r in rows if r['status']=='unverified']
    issue_groups={}
    for r in mismatches:
        group='article:'+str(mapping.get(r['column']) or ('0200' if r['columns']==[8,9] else '0300' if r['columns']==[13,14] else r['key']))
        issue_groups.setdefault(group,[]).append(r['key'])
    arithmetic_errors=[r for r in arithmetic_rows if r['status']=='mismatch']
    reviews=[d for d in docs if d.get('state') in ['review','error']]
    if mismatches or arithmetic_errors:conclusion={'kind':'rework','title':'Вернуть на доработку','text':'Обнаружены расхождения. Сверь строки и подтверждающие документы.'}
    elif reviews or any(not c['ready'] for n,c in cols.items() if n>=3):
        conclusion={'kind':'review','title':'Сначала уточнить входные данные','text':'Есть неуточнённые значения или документы. Рекомендация о подписании пока не сформирована.'}
    elif unknown and config.get('incomplete_policy','qualified')=='qualified':
        conclusion={'kind':'qualified','title':'Рекомендуется подписание с оговорками','text':'По проверенным показателям расхождений не выявлено. Ниже перечислены непроверенные показатели и причины. Временное правило до уточнения у заказчика.'}
    elif unknown:conclusion={'kind':'review','title':'Нужна дополнительная проверка','text':'Часть показателей не подтверждена; рекомендация о подписании не сформирована.'}
    else:conclusion={'kind':'confirmed','title':'Проверенные показатели подтверждены','text':'Проверка в пределах загруженного комплекта не выявила расхождений.'}
    return {'rows':rows,'arithmetic':arithmetic_rows,'report_source':{'image':report.get('source_image'),'source':report.get('source_copy'),'target':config['target']},'issue_groups':issue_groups,'documents':docs,'columns':list(cols.values()),'conclusion':conclusion,'unverified':[{'name':r['name'],'reasons':r['reasons']} for r in unknown],
            'summary':{'confirmed':sum(r['status']=='confirmed' for r in rows),'mismatch':len(issue_groups),'unverified':len(unknown),'review_documents':len(reviews),'arithmetic_confirmed':sum(r['status']=='confirmed' for r in arithmetic_rows),'arithmetic_mismatch':len(arithmetic_errors),'arithmetic_unverified':sum(r['status']=='unverified' for r in arithmetic_rows)},
            'config':{**config,'contract':contract},'decisions':decisions,'policy_provisional':True}

def process_case(directory, report_path, primary_paths, config, progress=lambda *_:None):
    directory=Path(directory);progress('report','Распознаю КФЗ и шапку таблицы')
    report=report_extract(report_path,directory/'report',config['target'],config.get('confidence_threshold',85))
    documents=[]
    for i,(file_id,path) in enumerate(primary_paths):
        progress('primaries',f'Читаю первичные и расчетные документы: {i+1} из {len(primary_paths)}')
        if hashlib.sha256(Path(path).read_bytes()).hexdigest()==hashlib.sha256(Path(report_path).read_bytes()).hexdigest():
            documents.append({'id':file_id,'name':Path(path).name,'role':'report_copy','excluded_reason':'Копия проверяемой КФЗ, не независимый подтверждающий документ'});continue
        try:documents.append(extract_primary(path,file_id,directory))
        except Exception as exc:
            documents.append({'id':file_id,'name':Path(path).name,'role':'primary','error':f'Не удалось прочитать файл ({type(exc).__name__})','candidates':list(ARTICLES)})
    raw={'report':report,'documents':documents,'extraction_version':1}
    dump(directory/'raw_extraction.json',raw);return raw
