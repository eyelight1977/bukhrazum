from pathlib import Path
import unittest
import uuid
import zipfile
import openpyxl

from app.evidence import workbook_views, document_view

ROOT=Path(__file__).resolve().parents[1]


class Evidence(unittest.TestCase):
    def directory(self):
        directory=ROOT/'work'/'evidence_tests'/uuid.uuid4().hex
        directory.mkdir(parents=True)
        return directory

    def test_workbook_component_highlights_actual_component_not_total(self):
        path=self.directory()/'synthetic.xlsx'
        wb=openpyxl.Workbook();ws=wb.active;ws.title='Начисления'
        ws.append(['Код','Описание','Сумма'])
        ws.append(['0201','Основная',50]);ws.append(['0202','Дополнительная и резерв',10]);ws.append(['Итого',None,'=SUM(C2:C3)'])
        wb.save(path);wb.close()
        views=workbook_views(path,{'locator':'Начисления!C2; Начисления!C3'})
        self.assertEqual(views['0201']['highlights'],[{'sheet':'Начисления','address':'C2'}])
        self.assertEqual(views['0202']['highlights'],[{'sheet':'Начисления','address':'C3'}])
        self.assertEqual(len(views['total']['highlights']),2)
        self.assertIn('Начисления!C2',views['0201']['locator'])

    def test_docx_preserves_paragraph_and_table_location(self):
        path=self.directory()/'synthetic.docx'
        with zipfile.ZipFile(path,'w') as z:
            z.writestr('word/document.xml','''<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Основание</w:t></w:r></w:p><w:tbl><w:tr><w:tc><w:p><w:r><w:t>Стоимость</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>15,00 руб.</w:t></w:r></w:p></w:tc></w:tr></w:tbl></w:body></w:document>''')
        view=document_view(path,{'locator':'Абзац 3','source_amount_text':'15,00'})
        self.assertEqual(view['paragraph'],3)
        self.assertEqual(view['blocks'][1]['kind'],'table')
        self.assertEqual(view['blocks'][1]['rows'][0][1][0],{'number':3,'text':'15,00 руб.'})

    def test_structured_preview_escapes_in_renderer(self):
        from app.reporting import render_report
        from app.engine import reconcile
        from test_rules import fixture,CONFIG
        raw=fixture();raw['documents'][0]['name']='<script>alert(1)</script>'
        result=reconcile(raw,[],CONFIG)
        page=render_report({'id':'test','result':result},self.directory())
        self.assertNotIn('<script>alert(1)</script>',page)
        self.assertIn(r'\u003cscript\u003ealert(1)\u003c/script\u003e',page)
        self.assertIn('check-arithmetic-${v.column}',page)
        self.assertIn('BukhReport.render',page)
        self.assertIn('Первичные и расчетные документы',page)
        self.assertIn('Расчёт',page)


if __name__=='__main__':unittest.main()
