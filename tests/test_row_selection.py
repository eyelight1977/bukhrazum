import unittest
from app.kfz_layout import select_target_line

def words(text,y):
    return [{'text':token,'bbox':[i*20,y,i*20+16,y+10]} for i,token in enumerate(text.split())]
NUMBERS=[{'text':str(i),'bbox':[i*100,100,i*100+10,110]} for i in range(1,18)]

class RowSelection(unittest.TestCase):
    def setUp(self):
        self.old=words('3 этап, 2025 г.:',130)
        self.current=words('3 этап, 2026 г.:',150)
        self.lines=[NUMBERS,self.old,self.current]
    def test_user_input_without_comma_or_year_suffix(self):
        self.assertIs(select_target_line(self.lines,NUMBERS,'3 этап 2026'),self.current)
    def test_spacing_punctuation_and_case(self):
        for label in ['3 этап, 2026 г.','3 ЭТАП,\u00a02026г.:','3  этап  2026 года']:
            self.assertIs(select_target_line(self.lines,NUMBERS,label),self.current)
    def test_wrong_year_is_not_silently_substituted(self):
        with self.assertRaisesRegex(ValueError,'не найдена'):
            select_target_line(self.lines,NUMBERS,'3 этап 2027')
    def test_duplicate_rows_are_not_chosen_arbitrarily(self):
        with self.assertRaisesRegex(ValueError,'несколько строк'):
            select_target_line(self.lines+[words('3 этап 2026 г.',170)],NUMBERS,'3 этап 2026')
    def test_amounts_and_page_headers_cannot_match_a_row(self):
        above=words('3 этап 2026',30)
        number_in_amount=[{'text':'3 этап 2026','bbox':[500,150,600,160]}]
        with self.assertRaisesRegex(ValueError,'не найдена'):
            select_target_line([above,number_in_amount],NUMBERS,'3 этап 2026')
if __name__=='__main__':unittest.main()
