import copy
import json
from pathlib import Path
import unittest
import uuid

from app.engine import reconcile
from test_rules import fixture, CONFIG, row


def formula(result, target):
    return next(r for r in result['arithmetic'] if r['column']==target)


class Arithmetic(unittest.TestCase):
    def test_all_five_formulas_need_no_primaries(self):
        raw=fixture();raw['documents']=[]
        r=reconcile(raw,[],CONFIG)
        self.assertEqual([v['formula'] for v in r['arithmetic']],['5 = 6 + 9','6 = 7 + 8','10 = 11 + 14','11 = 12 + 13','17 = 5 + 10 + 15 + 16'])
        self.assertTrue(all(v['status']=='confirmed' and v['source_label']=='Расчёт' for v in r['arithmetic']))
        self.assertEqual(row(r,5)['status'],'unverified')

    def test_correct_arithmetic_does_not_hide_document_mismatch_or_duplicate_it(self):
        raw=fixture();raw['documents'][2]['amount']='9'
        r=reconcile(raw,[],CONFIG)
        self.assertEqual(row(r,15)['delta'],'1.00')
        self.assertEqual(formula(r,17)['status'],'confirmed')
        combined=next(v for v in r['rows'] if v['key']=='combined:5,10,15,16')
        self.assertEqual(combined['delta'],'1.00')
        self.assertEqual(combined['derived_from'],['kfz:15'])
        self.assertEqual(row(r,17)['delta'],'1.00')
        self.assertEqual(row(r,17)['derived_from'],['kfz:15'])
        self.assertEqual(r['summary']['mismatch'],1)

    def test_modified_extraction_copy_has_wrong_arithmetic(self):
        original=fixture();changed=copy.deepcopy(original)
        next(c for c in changed['report']['columns'] if c['number']==17)['value']='109'
        directory=Path(__file__).resolve().parents[1]/'work'/'arithmetic_tests'/uuid.uuid4().hex
        directory.mkdir(parents=True)
        (directory/'original_extraction.json').write_text(json.dumps(original))
        (directory/'modified_extraction.json').write_text(json.dumps(changed))
        r=reconcile(json.loads((directory/'modified_extraction.json').read_text()),[],CONFIG)
        self.assertEqual(formula(r,17)['delta'],'1.00')
        self.assertEqual(formula(r,17)['status'],'mismatch')
        self.assertEqual(next(c for c in original['report']['columns'] if c['number']==17)['value'],'108')

    def test_missing_and_real_zero_are_distinct(self):
        raw=fixture();cols={c['number']:c for c in raw['report']['columns']}
        cols[8]['value']=None
        r=reconcile(raw,[],CONFIG)
        self.assertIsNone(formula(r,6)['expected'])
        self.assertEqual(formula(r,6)['missing_columns'],[8])
        cols[8]['value']='0';cols[7]['value']='56'
        r=reconcile(raw,[],CONFIG)
        self.assertEqual(formula(r,6)['expected'],'56.00')
        self.assertEqual(formula(r,6)['status'],'confirmed')

    def test_same_numbers_still_wait_for_ocr_then_recalculate(self):
        raw=fixture();cols={c['number']:c for c in raw['report']['columns']}
        cols[10].update(requires_review=True,minimum_word_confidence=80,two_pass_agreement=True,
                        review_reasons=['Low or absent OCR confidence'])
        before=copy.deepcopy(raw)
        r=reconcile(raw,[],CONFIG)
        self.assertEqual(formula(r,10)['delta'],'0.00')
        self.assertEqual(formula(r,10)['status'],'unverified')
        self.assertEqual(formula(r,10)['uncertain_columns'],[10])
        r=reconcile(raw,[{'target':'kfz:10','value':'18'}],CONFIG)
        self.assertEqual(formula(r,10)['status'],'confirmed')
        self.assertEqual(row(r,10)['status'],'confirmed')
        r=reconcile(raw,[{'target':'kfz:10','value':'19'}],CONFIG)
        self.assertEqual(formula(r,10)['delta'],'1.00')
        self.assertEqual(formula(r,17)['delta'],'-1.00')
        self.assertEqual(raw,before)

    def test_arithmetic_requires_direct_cells_not_unrelated_nested_cells(self):
        raw=fixture();next(c for c in raw['report']['columns'] if c['number']==7)['value']=None
        r=reconcile(raw,[],CONFIG)
        self.assertEqual(formula(r,6)['status'],'unverified')
        self.assertEqual(formula(r,5)['status'],'confirmed')
        self.assertEqual(formula(r,17)['status'],'confirmed')
        self.assertEqual(row(r,5)['status'],'unverified')

    def test_combined_salary_is_independent_but_components_stay_unverified(self):
        r=reconcile(fixture(),[],CONFIG)
        combined=next(v for v in r['rows'] if v['key']=='combined:8,9')
        self.assertEqual((combined['reported'],combined['expected'],combined['status']),('10.00','10.00','confirmed'))
        self.assertEqual(combined['terms'][0]['value'],'10.00')
        self.assertEqual(combined['terms'][0]['component'],'0202')
        self.assertEqual(row(r,7)['terms'][0]['value'],'50.00')
        self.assertEqual(row(r,7)['terms'][0]['component'],'0201')
        self.assertEqual(row(r,5)['terms'][0]['value'],'60.00')
        self.assertEqual(row(r,8)['status'],row(r,9)['status'])
        self.assertEqual(row(r,8)['status'],'unverified')

    def test_combined_insurance_cannot_be_inferred_from_total_or_report(self):
        raw=fixture();r=reconcile(raw,[],CONFIG)
        combined=next(v for v in r['rows'] if v['key']=='combined:13,14')
        self.assertEqual(combined['reported'],'3.00')
        self.assertIsNone(combined['expected'])
        self.assertEqual(combined['status_label'],'Недостаточно подтверждающих документов')
        self.assertEqual(combined['terms'],[])
        next(c for c in raw['report']['columns'] if c['number']==13)['value']='8'
        r=reconcile(raw,[],CONFIG);combined=next(v for v in r['rows'] if v['key']=='combined:13,14')
        self.assertEqual(combined['reported'],'10.00')
        self.assertIsNone(combined['expected'])

    def test_all_formula_terms_have_correct_cell_references(self):
        r=reconcile(fixture(),[],CONFIG)
        expected={5:[6,9],6:[7,8],10:[11,14],11:[12,13],17:[5,10,15,16]}
        for v in r['arithmetic']:
            self.assertEqual([t['column'] for t in v['terms']],expected[v['column']])
            self.assertEqual(v['columns'],[v['column']])


if __name__=='__main__':unittest.main()
