"""Business wording and correct document context for a questioned field."""
import unittest,copy
from app.engine import reconcile
from app.checks import reading_reasons
from app.evidence import report_field_view
from test_rules import fixture,CONFIG,row
class BusinessView(unittest.TestCase):
 def test_internal_scores_are_not_business_explanations_and_gate_is_preserved(self):
  raw=fixture();c=next(c for c in raw['report']['columns'] if c['number']==10)
  c.update(requires_review=True,two_pass_agreement=True,minimum_word_confidence=82.5,review_reasons=['Low OCR confidence'])
  reasons=reading_reasons({**c,'effective_value':c['value']})
  self.assertEqual(reasons,['Подтверди значение в выделенном поле КФЗ, чтобы завершить сверку'])
  r=reconcile(raw,[],CONFIG);self.assertEqual(row(r,10)['status'],'unverified');self.assertEqual(row(r,10)['delta'],'0.00')
  r=reconcile(raw,[{'target':'kfz:10','value':'18.00'}],CONFIG);self.assertEqual(row(r,10)['status'],'confirmed')
 def test_fragment_contains_entire_header_hierarchy_number_gap_and_selected_row(self):
  result={'columns':[{'number':10,'name':'Взносы','image_size':[1000,700],'source_bbox':[600,560,700,580],'header_path':[{'bbox':[600,300,900,350]},{'bbox':[600,350,700,500]}]}], 'report_source':{'image':'scan.png'},'config':{'target':'3 этап 2026'}}
  view=report_field_view(result,10);box=view['focus_bbox']
  for b in [*view['header_highlights'],*view['highlights']]:self.assertTrue(box[0]<=b[0]<b[2]<=box[2] and box[1]<=b[1]<b[3]<=box[3])
  self.assertLess(box[1],300);self.assertGreater(box[3],580);self.assertIn('3 этап 2026',view['caption']);self.assertIn('столбец 10',view['caption'])
if __name__=='__main__':unittest.main()
