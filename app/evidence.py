"""Structured local previews, using only saved upload copies. No office renderer required."""
from pathlib import Path
from io import BytesIO
import re
import zipfile
import xml.etree.ElementTree as ET
import openpyxl
from PIL import Image

NS = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}


def workbook_views(path, doc):
    wb = openpyxl.load_workbook(BytesIO(path.read_bytes()), data_only=False, read_only=True, keep_links=False)
    sheets, components, total, insurance = [], {}, [], []
    for sheet in wb:
        rows = []
        for row in sheet.iter_rows(max_row=min(sheet.max_row or 10000, 10000), max_col=min(sheet.max_column or 100, 100)):
            cells = [c for c in row if c.value is not None]
            if not cells:
                continue
            rows.append({'row': cells[0].row, 'cells': [{'address': c.coordinate, 'column': c.column,
                          'text': str(c.value)} for c in cells]})
            code = next((str(c.value) for c in cells if str(c.value) in ('0201', '0202')), None)
            nums = [c for c in cells if isinstance(c.value, (int, float)) and not isinstance(c.value, bool)]
            if code and nums:
                components.setdefault(code, []).append({'sheet': sheet.title, 'address': nums[-1].coordinate})
        sheets.append({'name': sheet.title, 'rows': rows})
    # The extraction already stored the total's cells. Keep the same coordinates, not a guessed total cell.
    for locator in doc.get('locator', '').split('; '):
        if '!' in locator:
            sheet, address = locator.rsplit('!', 1)
            if re.fullmatch(r'[A-Z]+[1-9][0-9]*', address):
                total.append({'sheet': sheet, 'address': address})
    wb.close()
    def view(cells):
        return {'kind': 'workbook', 'sheets': sheets, 'highlights': cells,
                'locator': '; '.join(f'{c["sheet"]}!{c["address"]}' for c in cells)}
    result = {'total': view(total)}
    result.update({key: view(cells) for key, cells in components.items()})
    return result


def document_view(path, doc):
    with zipfile.ZipFile(path) as z:
        xml = ET.fromstring(z.read('word/document.xml'))
    paragraph_number = 0
    def paragraph(el):
        nonlocal paragraph_number
        paragraph_number += 1
        return {'number': paragraph_number, 'text': ''.join(n.text or '' for n in el.findall('.//w:t', NS))}
    blocks = []
    table_number = 0
    body = xml.find('w:body', NS)
    for el in body:
        if el.tag.endswith('}p'):
            blocks.append({'kind': 'paragraph', **paragraph(el)})
        elif el.tag.endswith('}tbl'):
            table_number += 1
            rows = []
            for tr in el.findall('w:tr', NS):
                rows.append([[paragraph(p) for p in cell.findall('.//w:p', NS)] for cell in tr.findall('w:tc', NS)])
            blocks.append({'kind': 'table', 'number': table_number, 'rows': rows})
    m = re.search(r'Абзац (\d+)', doc.get('locator', ''))
    return {'kind': 'document', 'blocks': blocks, 'paragraph': int(m[1]) if m else None,
            'highlight_text': doc.get('source_amount_text'), 'locator': doc.get('locator', 'Текст документа')}


def report_field_view(result, number):
    """Frame a field together with its full recognized header hierarchy, never a bare number."""
    column=next(c for c in result['columns'] if c['number']==number)
    value=column.get('source_bbox')
    headers=[h['bbox'] for h in column.get('header_path',[]) if h.get('bbox')]
    view={'kind':'image','image':result['report_source'].get('image'),
          'highlights':[value] if value else [],'header_highlights':headers,
          'caption':f'Строка «{result["config"]["target"]}», столбец {number}: '+(column.get('name') or 'Показатель КФЗ')}
    if value and headers:
        boxes=[value,*headers]
        width,height=column.get('image_size') or [max(b[2] for b in boxes)+12,max(b[3] for b in boxes)+12]
        view['focus_bbox']=[max(0,min(b[0] for b in boxes)-12),max(0,min(b[1] for b in boxes)-12),
                            min(width,max(b[2] for b in boxes)+12),min(height,max(b[3] for b in boxes)+12)]
    return view


def attach_views(result, directory):
    """Also works for checks saved before structured previews were introduced."""
    directory = Path(directory).resolve()
    result['report_views']={str(c['number']):report_field_view(result,c['number']) for c in result['columns'] if c['number']>=3}
    for doc in result['documents']:
        if doc.get('role') != 'primary' or not doc.get('source'):
            continue
        source = (directory / doc['source']).resolve()
        if not source.is_relative_to(directory) or not source.is_file():
            continue
        try:
            if source.suffix.lower() == '.xlsx':
                doc['views'] = workbook_views(source, doc)
            elif source.suffix.lower() == '.docx':
                doc['views'] = {'total': document_view(source, doc)}
            else:
                image = f'sources/{doc["id"]}/page.png'
                image_path = directory / image
                if not image_path.is_file():
                    image = doc.get('evidence')
                    image_path = directory / image if image else None
                if image_path and image_path.is_file():
                    with Image.open(image_path) as im:
                        size = list(im.size)
                    doc['views'] = {'total': {'kind': 'image', 'image': image, 'image_size': size,
                                             'highlights': [doc['bbox']] if doc.get('bbox') and image.endswith('/page.png') else [],
                                             'locator': doc.get('locator', '')}}
        except (OSError, ValueError, KeyError, zipfile.BadZipFile, ET.ParseError):
            doc['preview_error'] = 'Не удалось построить контекст источника; доступен сохранённый фрагмент'
    by_id = {d['id']: d for d in result['documents']}
    for row in result['rows']:
        for term in row['terms']:
            doc = by_id[term['document_id']]
            view = doc.get('views', {}).get(term['component'])
            term['locator'] = view.get('locator') if view else None
            term['preview_available'] = view is not None
    return result
