"""Grid/row extraction from OCR and scan pixels. Does not read visual reference."""
from pathlib import Path
from collections import defaultdict
from decimal import Decimal
import csv, io, json, re, hashlib
import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
SCALE = 3

def read_words(run):
    fields = 'level page block paragraph line word left top width height conf text'.split()
    groups = defaultdict(list)
    for r in csv.DictReader(io.StringIO(run['tsv']), delimiter='\t', fieldnames=fields):
        if r['level'] != '5' or not r['text'].strip():
            continue
        w = {'text': r['text'], 'confidence': float(r['conf']),
             'bbox': [int(r['left'])/SCALE, int(r['top'])/SCALE,
                      (int(r['left'])+int(r['width']))/SCALE,
                      (int(r['top'])+int(r['height']))/SCALE]}
        groups[tuple(r[k] for k in ['page','block','paragraph','line'])].append(w)
    return list(groups.values())

def groups_of_indices(indices, gap=2):
    result = []
    for x in indices:
        if not result or x > result[-1][-1] + gap:
            result.append([int(x)])
        else:
            result[-1].append(int(x))
    return result

def longest_runs(row, minimum=60):
    edges = np.diff(np.r_[False, row, False].astype(np.int8))
    return [(int(a),int(b)) for a,b in zip(np.flatnonzero(edges==1), np.flatnonzero(edges==-1)) if b-a>=minimum]

def label_tokens(text):
    """Ignore punctuation/year suffixes, never change or approximate digits."""
    tokens=re.findall(r'\d+|[a-zа-яё]+',text.casefold().replace('ё','е'))
    return tuple(token for i,token in enumerate(tokens)
                 if not (token in {'г','год','года','году'} and i and re.fullmatch(r'\d{4}',tokens[i-1])))

def select_target_line(lines,number_words,target_label):
    header_y=float(np.median([(w['bbox'][1]+w['bbox'][3])/2 for w in number_words]))
    centers=[(w['bbox'][0]+w['bbox'][2])/2 for w in number_words]
    # Row labels occupy the first two columns; amounts must not participate.
    label_right=(centers[1]+centers[2])/2
    wanted=label_tokens(target_label);matches=[];available=[]
    for words in lines:
        label=[w for w in words if (w['bbox'][0]+w['bbox'][2])/2<label_right
               and (w['bbox'][1]+w['bbox'][3])/2>header_y+3 and w['text']!='|']
        text=' '.join(w['text'] for w in sorted(label,key=lambda w:w['bbox'][0]))
        if not text:continue
        available.append(text)
        if label_tokens(text)==wanted:matches.append(words)
    if len(matches)==1:return matches[0]
    if len(matches)>1:
        raise ValueError('Найдено несколько строк с таким этапом и годом. Уточни название строки; автоматический выбор не выполнен.')
    choices='; '.join(dict.fromkeys(available))
    raise ValueError(f'Строка «{target_label}» не найдена. '+(f'Распознаны строки: {choices}. Укажи нужную.' if choices else 'Не удалось прочитать подписи строк. Проверь файл КФЗ.'))

def extract(workspace, target_label):
    HERE = Path(workspace)
    baseline = json.loads((HERE/'runs/baseline.json').read_text())['results'][0]
    lines = read_words(baseline)
    candidates = []
    for words in lines:
        numeric = [int(w['text']) for w in words if re.fullmatch(r'\d+', w['text'])]
        if len(numeric) >= 8 and numeric == list(range(1,len(numeric)+1)):
            candidates.append(words)
    if len(candidates)!=1:
        raise ValueError(f'Column number row ambiguous/missing: {len(candidates)} candidates')
    number_words = sorted(candidates[0], key=lambda w:w['bbox'][0])
    assert len(number_words)==17, 'This experiment validates the 17-column form only'
    target=select_target_line(lines,number_words,target_label)
    im = Image.open(HERE/'input/scan.png').convert('RGB')
    binary = np.asarray(im.convert('L')) < 150
    runs = [longest_runs(row) for row in binary]
    horizontal_mask=np.zeros(binary.shape,dtype=bool)
    for y,segments in enumerate(runs):
        for a,b in segments: horizontal_mask[y,a:b]=True
    hscore = np.array([sum(b-a for a,b in row) for row in runs])
    hg = groups_of_indices(np.flatnonzero(hscore>im.width*.16))
    ys = [max(g,key=lambda y:hscore[y]) for g in hg]
    if len(ys)<6: raise ValueError('Insufficient table grid')
    table_y0,table_y1 = min(ys),max(ys)
    # Slight skew puts opposite ends of a rule on adjacent image rows.
    line_pixels=[y for group in hg for y in group]
    left=min(a for y in line_pixels for a,b in runs[y]);right=max(b for y in line_pixels for a,b in runs[y])
    centers = [(w['bbox'][0]+w['bbox'][2])/2 for w in number_words]
    vs = binary[table_y0:table_y1+1].sum(0)
    xs = [left]
    for c0,c1 in zip(centers,centers[1:]):
        lo,hi=int(c0+3),int(c1-3)
        xs.append(int(lo+np.argmax(vs[lo:hi])))
    xs.append(right)
    if any(a>=b for a,b in zip(xs,xs[1:])):
        raise ValueError('Non-increasing column boundaries')
    number_y = float(np.median([(w['bbox'][1]+w['bbox'][3])/2 for w in number_words]))
    header_bottom = max(y for y in ys if y<number_y)
    target_y = float(np.median([(w['bbox'][1]+w['bbox'][3])/2 for w in target]))
    row_top=max(y for y in ys if y<target_y); row_bottom=min(y for y in ys if y>target_y)
    jobs=[]; columns=[]
    def crop(box,filename):
        x0,y0,x1,y1=map(int,box)
        # Evidence retains borders; recognition uses one source-pixel inset and padding.
        im.crop((x0,y0,x1,y1)).resize(((x1-x0)*3,(y1-y0)*3),Image.Resampling.LANCZOS).save(HERE/'evidence'/filename)
        content=im.crop((x0+1,y0+1,x1-1,y1-1))
        padded=Image.new('RGB',(content.width*3+24,content.height*3+24),'white')
        padded.paste(content.resize((content.width*3,content.height*3),Image.Resampling.LANCZOS),(12,12))
        recname='recognize_'+filename;padded.save(HERE/'evidence'/recname)
        return 'evidence/'+recname
    dropped=[]
    for i in range(17):
        words=[w for w in target if xs[i] <= (w['bbox'][0]+w['bbox'][2])/2 < xs[i+1]]
        tokens=[w for w in words if w['text']!='|']
        dropped.extend(w for w in words if w['text']=='|')
        raw=' '.join(w['text'] for w in tokens)
        normalized=re.sub(r'\s+','',raw).replace(',','.')
        valid=bool(re.fullmatch(r'-?\d+\.\d{2}',normalized)) if i>=2 else None
        box=[xs[i],row_top,xs[i+1],row_bottom]
        evidence=f'column_{i+1:02d}.png'
        recpath=crop(box,evidence)
        col={'number':i+1,'number_ocr':number_words[i]['text'],'number_bbox':number_words[i]['bbox'],
             'raw_text':raw,'value':normalized if valid else None,'parse_status':('ok' if valid else 'not_a_numeric_value'),
             'source_bbox':box,'source_page':1,'image_size':list(im.size),'evidence':'evidence/'+evidence,
             'words':tokens,'minimum_word_confidence':min([w['confidence'] for w in tokens],default=None)}
        columns.append(col)
        if i>=2: jobs.append({'id':f'value_{i+1:02d}','image':recpath,'psm':7,'whitelist':'0123456789.,- '})
    # Detect the merged row label from the missing border between columns 1 and 2.
    border=binary[row_top+2:row_bottom-1,max(0,xs[1]-2):xs[1]+3].any(1).mean()
    merged = border < .5
    label_words=[w for w in target if (w['bbox'][0]+w['bbox'][2])/2<xs[2]]
    label=' '.join(w['text'] for w in label_words)
    label_crop=crop([xs[0],row_top,xs[2],row_bottom],'row_label.png')
    jobs.append({'id':'row_label','image':label_crop,'psm':7})
    # Reconstruct merged header cells using the actual drawn grid, not text values.
    hy=[y for y in ys if y<=header_bottom]; nr=len(hy)-1
    parent=list(range(nr*17))
    def find(a):
        while parent[a]!=a: parent[a]=parent[parent[a]];a=parent[a]
        return a
    def union(a,b):parent[find(a)]=find(b)
    for r in range(nr):
        for c in range(17):
            if c<16:
                x=xs[c+1]; band=binary[hy[r]+3:hy[r+1]-2,x-2:x+3]
                score=float(band.any(1).mean()) if band.size else 1
                if score<.55:union(r*17+c,r*17+c+1)
            if r<nr-1:
                y=hy[r+1];band=horizontal_mask[y-2:y+3,xs[c]+3:xs[c+1]-2]
                score=float(band.any(0).mean()) if band.size else 1
                if score<.55:union(r*17+c,(r+1)*17+c)
    comps=defaultdict(list)
    for r in range(nr):
        for c in range(17):comps[find(r*17+c)].append((r,c))
    headers=[]
    for i,component in enumerate(comps.values()):
        rr=[x[0] for x in component];cc=[x[1] for x in component]
        if len(component)!=(max(rr)-min(rr)+1)*(max(cc)-min(cc)+1):
            raise ValueError('Nonrectangular merged header component; confirmation required')
        box=[xs[min(cc)],hy[min(rr)],xs[max(cc)+1],hy[max(rr)+1]]
        image=crop(box,f'header_{i:02d}.png')
        headers.append({'id':f'header_{i:02d}','columns':list(range(min(cc)+1,max(cc)+2)), 'source_bbox':box,
                        'evidence':f'evidence/header_{i:02d}.png'})
        jobs.append({'id':f'header_{i:02d}','image':image,'psm':6})
    overlay=im.copy();draw=ImageDraw.Draw(overlay)
    for col in columns:
        draw.rectangle(col['source_bbox'],outline='red',width=1)
        draw.text((col['source_bbox'][0]+3,row_top-14),str(col['number']),fill='red')
    overlay.crop((left,table_y0-20,right+1,row_bottom+24)).resize(((right-left+1)*2,(row_bottom+44-table_y0)*2)).save(HERE/'evidence/overlay.png')
    result={'method':'Tesseract.js PSM 3 on scan upscaled 3x; numbers and target row found in OCR; pixel grid supplies boundaries',
       'baseline_run':'page_psm3','target_label_ocr':label,'merged_columns':[1,2] if merged else [],
       'grid':{'x':xs,'y':ys,'header_bottom':header_bottom,'row_top':row_top,'row_bottom':row_bottom},
       'columns':columns,'headers':headers,'discarded_grid_glyphs':dropped,
       'normalization':'Remove whitespace, decimal comma to point. No digit correction, arithmetic filling, or reference values.'}
    (HERE/'runs/extracted_initial.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    (HERE/'runs/cell_jobs.json').write_text(json.dumps(jobs,ensure_ascii=False,indent=2))


    return result
