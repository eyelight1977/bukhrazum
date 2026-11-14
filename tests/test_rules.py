import unittest,copy
from app.engine import reconcile,select_amount

CONFIG={'target':'Этап теста','start':'2026-01-01','end':'2026-01-31','contract':'1/2/3-4','incomplete_policy':'qualified'}
def fixture():
    values={3:'1',4:'0',5:'60',6:'56',7:'50',8:'6',9:'4',10:'18',11:'16',12:'15',13:'1',14:'2',15:'10',16:'20',17:'108'}
    cols=[{'number':n,'name':f'Поле {n}','value':v,'raw_text':v,'requires_review':False,'evidence':'test.png'} for n,v in values.items()]
    cols=[{'number':1,'name':'Этап','value':'Тест'},{'number':2,'name':'Месяц','value':None}]+cols
    docs=[]
    for i,(article,amount,components) in enumerate([('0200','60',{'0201':'50','0202':'10'}),('0300','18',{}),('0800','10',{}),('0900','20',{})]):
        docs.append({'id':str(i),'name':f'Документ {i}','role':'primary','hash':str(i),'document_number':str(i),'contract':'1/2/3-4','date':'2026-01-10','article':article,'candidates':[article],'amount':amount,'components':components,'amount_requires_review':False,'article_requires_review':False})
    return {'report':{'columns':cols,'contract':'1/2/3-4'},'documents':docs}
def row(result,n):return next(x for x in result['rows'] if x['column']==n)

class Rules(unittest.TestCase):
    def test_amount_dates_signs_units_and_currency(self):
        value,_,review=select_amount('Дата: 28.01.2026. Итого: -1 250,50 руб.')
        self.assertEqual(value,'-1250.50');self.assertFalse(review)
        self.assertEqual(select_amount('Стоимость услуг: 1,25 тыс. руб.')[0],'1250.00')
        self.assertTrue(select_amount('Стоимость: 125,00 USD')[2])
        self.assertIsNone(select_amount('Дата: 28.01.2026')[0])
    def test_valid_aggregates_without_false_errors(self):
        r=reconcile(fixture(),[],CONFIG)
        self.assertEqual(r['summary']['mismatch'],0)
        self.assertTrue(all(row(r,n)['status']=='confirmed' for n in [5,7,10,15,16]))
        self.assertEqual(row(r,8)['status'],'unverified')
        self.assertEqual(r['conclusion']['kind'],'qualified')
    def test_missing_ocr_blocks_transitive_totals_and_cannot_be_confirmed_away(self):
        raw=fixture();raw['report']['columns'][6]['value']=None
        r=reconcile(raw,[],CONFIG)
        self.assertTrue(all(row(r,n)['status']=='unverified' for n in [7,6,5,17]))
        r=reconcile(raw,[{'target':'kfz:5','value':'60'}],CONFIG)
        self.assertEqual(row(r,5)['status'],'unverified')
    def test_zero_is_real_value_and_none_is_not_zero(self):
        raw=fixture();raw['documents'][2]['amount']='0';raw['report']['columns'][14]['value']='0'
        r=reconcile(raw,[],CONFIG);self.assertEqual(row(r,15)['status'],'confirmed')
        raw['documents'][2]['amount']=None;r=reconcile(raw,[],CONFIG)
        self.assertIsNone(row(r,15)['expected']);self.assertEqual(row(r,15)['status'],'unverified')
    def test_month_gap_is_incomplete_not_error(self):
        config={**CONFIG,'end':'2026-02-28'};r=reconcile(fixture(),[],config)
        self.assertIsNone(row(r,5)['expected']);self.assertIsNone(row(r,7)['expected']);self.assertEqual(row(r,7)['status'],'unverified')
    def test_error_file_does_not_disappear_into_clean_result(self):
        raw=fixture();raw['documents'].append({'id':'bad','name':'Повреждённый.pdf','role':'primary','error':'Не прочитан'})
        r=reconcile(raw,[],CONFIG)
        self.assertEqual(r['conclusion']['kind'],'review');self.assertIsNone(row(r,15)['expected'])
    def test_duplicate_foreign_period_and_contract(self):
        raw=fixture();duplicate=copy.deepcopy(raw['documents'][2]);duplicate['id']='dup'
        foreign=copy.deepcopy(raw['documents'][2]);foreign.update(id='foreign',hash='foreign',contract='9/9/9-9')
        late=copy.deepcopy(raw['documents'][2]);late.update(id='late',hash='late',date='2026-02-01')
        raw['documents']+=[duplicate,foreign,late];r=reconcile(raw,[],CONFIG)
        self.assertEqual(sum(d['state']=='excluded' for d in r['documents']),3);self.assertEqual(row(r,15)['expected'],'10.00')
    def test_ambiguous_article_blocks_candidates_until_user_choice(self):
        raw=fixture();d=raw['documents'][2];d.update(article=None,candidates=['0800','0900'],article_requires_review=True)
        r=reconcile(raw,[],CONFIG);self.assertIsNone(row(r,15)['expected']);self.assertIsNone(row(r,16)['expected'])
        r=reconcile(raw,[{'target':'doc:2:article','value':'0800'}],CONFIG);self.assertEqual(row(r,15)['status'],'confirmed')
    def test_user_override_preserves_raw_and_changes_result(self):
        raw=fixture();before=copy.deepcopy(raw)
        r=reconcile(raw,[{'target':'kfz:15','value':'12'}],CONFIG)
        self.assertEqual(raw,before);self.assertEqual(row(r,15)['ocr_value'],'10');self.assertEqual(row(r,15)['delta'],'2.00');self.assertEqual(r['conclusion']['kind'],'rework')
    def test_policy_changes_recommendation_not_calculations(self):
        raw=fixture();a=reconcile(raw,[],CONFIG);b=reconcile(raw,[],{**CONFIG,'incomplete_policy':'strict'})
        self.assertEqual(a['rows'],b['rows']);self.assertEqual(b['conclusion']['kind'],'review')

if __name__=='__main__':unittest.main()
