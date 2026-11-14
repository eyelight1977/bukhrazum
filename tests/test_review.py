"""Regressions for concrete issues found during final review; synthetic documents only."""
import unittest,uuid,zipfile
from pathlib import Path
import openpyxl
from unittest.mock import patch
from app.engine import extract_primary,reconcile,ROOT
from app.server import validate_config
from test_rules import fixture,CONFIG,row
class Review(unittest.TestCase):
 def directory(self):
  p=ROOT/'work/review_tests'/uuid.uuid4().hex;p.mkdir(parents=True);return p
 def test_repeated_payroll_codes_are_summed_and_name_has_no_meaning(self):
  p=self.directory();f=p/'!эталон-обычный-документ.xlsx';w=openpyxl.Workbook();s=w.active
  s.append(['Ведомость по оплате труда']);s.append(['0201',30]);s.append(['0201',20]);s.append(['0202',10]);w.save(f);w.close()
  d=extract_primary(f,'test',p);self.assertEqual(d['role'],'primary');self.assertEqual(d['components']['0201'],'50.00');self.assertEqual(d['amount'],'60.00')
 def test_renamed_reference_is_excluded_before_values(self):
  p=self.directory();f=p/'ordinary.xlsx';w=openpyxl.Workbook();w.active.title='Эталон';w.active['A1']='private sentinel';w.save(f);w.close()
  d=extract_primary(f,'test',p);self.assertEqual(d['role'],'reference');self.assertNotIn('private sentinel',str(d))
 def test_same_amount_confirmation_keeps_independent_split(self):
  r=reconcile(fixture(),[{'target':'doc:0:amount','value':'60.00'}],CONFIG);self.assertEqual(row(r,7)['expected'],'50.00')
  r=reconcile(fixture(),[{'target':'doc:0:amount','value':'61.00'}],CONFIG);self.assertIsNone(row(r,7)['expected'])
 def test_docx_same_number_uses_selected_paragraph(self):
  p=self.directory();f=p/'document.docx'
  with zipfile.ZipFile(f,'w') as z:z.writestr('word/document.xml','<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>15,00</w:t></w:r></w:p><w:p><w:r><w:t>Итого 15,00 руб.</w:t></w:r></w:p></w:body></w:document>')
  d=extract_primary(f,'test',p);self.assertEqual(d['locator'],'Абзац 2')
 def test_export_preserves_prior_saved_report(self):
  from app.server import persist_export
  path=self.directory()/'report.html';persist_export(path,'first');second=persist_export(path,'second')
  self.assertEqual(path.read_text(),'first');self.assertEqual(second.read_text(),'second');self.assertEqual(persist_export(path,'second'),second)
 def test_threshold_finite_and_range(self):
  for value in ['NaN','inf','-1','101']:
   with patch.dict('os.environ',{'OCR_CONFIDENCE_THRESHOLD':value}):
    with self.assertRaises(ValueError):validate_config(dict(CONFIG))
if __name__=='__main__':unittest.main()
