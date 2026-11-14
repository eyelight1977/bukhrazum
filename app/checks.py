"""Arithmetic of the report, independent of documentary evidence."""
from decimal import Decimal

FORMULAS = {5: [6, 9], 6: [7, 8], 10: [11, 14], 11: [12, 13], 17: [5, 10, 15, 16]}


def arithmetic(columns, number, money):
    rows = []
    for target, operands in FORMULAS.items():
        refs = [target, *operands]
        missing = [n for n in refs if number(columns[n]['effective_value']) is None]
        uncertain = [n for n in refs if n not in missing and not columns[n]['intrinsic_ready']]
        values = [number(columns[n]['effective_value']) for n in operands]
        expected = sum(values, Decimal(0)) if all(v is not None for v in values) else None
        actual = number(columns[target]['effective_value'])
        delta = actual - expected if actual is not None and expected is not None else None
        status = 'unverified' if missing or uncertain else 'confirmed' if money(delta) == '0.00' else 'mismatch'
        reasons = []
        if missing:
            reasons.append('Не распознаны значения КФЗ: столбцы ' + ', '.join(map(str, missing)))
        if uncertain:
            reasons.append('Подтверди значения в полях КФЗ: столбцы ' + ', '.join(map(str, uncertain)))
        if status == 'confirmed':
            reasons.append('Значение равно сумме слагаемых КФЗ. Эта проверка не подтверждает соответствие отчёта первичным и расчетным документам.')
        elif status == 'mismatch':
            reasons.append('Значение не равно сумме слагаемых самой КФЗ.')
        rows.append({
            'key': f'arithmetic:{target}', 'column': target, 'columns': [target],
            'name': columns[target].get('name') or f'Столбец {target}', 'source_label': 'Расчёт',
            'formula': f'{target} = ' + ' + '.join(map(str, operands)),
            'formula_values': money(actual) if not operands else (money(actual) or 'не распознано') + ' = ' + ' + '.join(money(v) or 'не распознано' for v in values),
            'reported': money(actual), 'expected': money(expected), 'delta': money(delta), 'status': status,
            'status_label': {'confirmed': 'Арифметика верна', 'mismatch': 'Ошибка арифметики', 'unverified': 'Нужно уточнить значения КФЗ'}[status],
            'reasons': reasons, 'sources': [], 'terms': [
                {'column': n, 'label': f'Столбец {n}', 'value': money(columns[n]['effective_value']),
                 'evidence': columns[n].get('evidence'), 'bbox': columns[n].get('source_bbox'),
                 'ready': columns[n]['intrinsic_ready']} for n in operands],
            'missing_columns': missing, 'uncertain_columns': uncertain,
        })
    return rows


def reading_reasons(column):
    """Explain the actual OCR gate, without describing an engine score as a probability."""
    if column.get('user_decision'):
        return []
    if column.get('effective_value') is None:
        return ['Значение КФЗ не распознано']
    if not column.get('requires_review'):
        return []
    if column.get('header_mapping_status') == 'unresolved':
        return ['Уточни, к какому показателю относится выделенное значение КФЗ']
    return ['Подтверди значение в выделенном поле КФЗ, чтобы завершить сверку']
