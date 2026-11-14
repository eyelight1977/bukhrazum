"""Assemble OCR values and semantic header paths; never reads the visual reference."""
from pathlib import Path
import json,re
from .kfz_layout import read_words

def assemble(workspace, confidence_threshold=85):
    p=Path(workspace)
    d=json.loads((p/'runs/extracted_initial.json').read_text())
    cells={r['id']:r for r in json.loads((p/'runs/cells.json').read_text())['results']}
    confirm={r['id']:r for r in json.loads((p/'runs/confirmation.json').read_text())['results']}
    words=[w for line in read_words(json.loads((p/'runs/baseline.json').read_text())['results'][0]) for w in line]
    def normalize(s):
        t=re.sub(r'\s+','',s).replace(',','.')
        return t if re.fullmatch(r'-?\d+\.\d{2}',t) else None
    for h in d['headers']:
        text=cells[h['id']]['text'].strip();h['crop_ocr_text']=text
        h['text_source']='cell OCR'
        if not text:
            x0,y0,x1,y1=h['source_bbox']
            chosen=[w for w in words if x0<(w['bbox'][0]+w['bbox'][2])/2<x1 and y0<(w['bbox'][1]+w['bbox'][3])/2<y1 and w['text']!='|']
            text=' '.join(w['text'] for w in sorted(chosen,key=lambda w:(w['bbox'][1],w['bbox'][0])))
            h['text_source']='full-page OCR fallback; crop OCR empty'
        h['ocr_text']=text
    for col in d['columns']:
        n=col['number'];chain=[h for h in d['headers'] if n in h['columns']]
        chain.sort(key=lambda h:(h['source_bbox'][1],h['source_bbox'][3]))
        texts=[h['ocr_text'].replace('ё','е').lower() for h in chain]
        path=' '.join(texts);leaf=texts[-1];name=None
        if 'трудоемкость' in path:name='Трудоемкость, человеко-месяцы'
        elif 'материальн' in path:name='Материальные затраты'
        elif '0800' in path:name='0800 Общепроизводственные затраты'
        elif '0900' in path:name='0900 Общехозяйственные затраты'
        elif '0200' in path:
            if '211' not in path:name='0200 Оплата труда всего'
            elif 'резерв' in path:name='Резерв отпусков, счет 211'
            elif 'основная' in leaf:name='Основная зарплата'
            elif 'дополн' in leaf:name='Дополнительная зарплата без резерва'
            elif 'всего' in leaf:name='Зарплата, счет 211, всего без резерва'
        elif '0300' in path:
            if '213' not in path:name='0300 Страховые взносы всего'
            elif 'резерв' in path:name='Взносы с резерва отпусков, счет 213'
            elif 'основная' in leaf:name='Взносы с основной зарплаты'
            elif 'дополн' in leaf:name='Взносы с дополнительной зарплаты без резерва'
            elif 'всего' in leaf:name='Взносы, счет 213, всего без резерва'
        elif 'итого' in path:name='Итого'
        elif 'этап' in path:name='Этап'
        elif 'месяц' in path:name='Месяц'
        col['name']=name;col['header_mapping_status']='ok' if name else 'unresolved'
        col['header_path']=[{'id':h['id'],'ocr_text':h['ocr_text'],'source':h['text_source'],'bbox':h['source_bbox'],'evidence':h['evidence']} for h in chain]
        if n>=3:
            first=cells[f'value_{n:02d}'];second=confirm.get(f'text_only_{n:02d}',{'text':'','confidence':0,'source_bbox':col['source_bbox'],'image':col['evidence']})
            col['bordered_cell_diagnostic']={'text':first['text'].strip(),'value':normalize(first['text'])}
            col['text_only_confirmation']={'text':second['text'].strip(),'value':normalize(second['text']),'confidence':second['confidence'],'source_bbox':second['source_bbox'],'evidence':second['image']}
            col['two_pass_agreement']=col['value'] is not None and col['value']==normalize(second['text'])
            low=col['minimum_word_confidence'] is None or col['minimum_word_confidence']<confidence_threshold
            col['requires_review']=not col['two_pass_agreement'] or not name or low
            col['review_reasons']=[]
            if not col['two_pass_agreement']:col['review_reasons'].append('Page OCR and text-only crop OCR disagree or are missing')
            if not name:col['review_reasons'].append('Header meaning unresolved')
            if low:col['review_reasons'].append('Low or absent OCR confidence; threshold is experimental, not a probability')
        elif n==1:col['value']=d['target_label_ocr'];col['parse_status']='merged_label'
        else:col['value']=None;col['parse_status']='merged_with_column_1_no_separate_value'
    d['header_mapping_method']='Canonical labels inferred from recognized hierarchy using article codes, accounts, and keywords; no fixed number-to-label mapping or reference values.'
    d['source_copy']='input/КФЗ_копия.pdf'
    d['source_image']='input/scan.png'
    d['source_manifest']='source_manifest.json'
    (p/'runs/extracted_final.json').write_text(json.dumps(d,ensure_ascii=False,indent=2))
    return d
