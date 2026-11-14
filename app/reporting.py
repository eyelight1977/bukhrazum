"""Standalone, offline HTML uses exactly the application's result renderer."""
import base64
import html
import json
from pathlib import Path


def script_json(value):
    # JSON lives inside a script element: prevent closing tags and HTML entities.
    return json.dumps(value, ensure_ascii=False).replace('&', '\\u0026').replace('<', '\\u003c').replace('>', '\\u003e')


def render_report(data, directory):
    result = data.get('result')
    if not result:
        return '<meta charset="utf-8"><p>Обработка ещё не завершена</p>'
    directory = Path(directory).resolve()
    assets = {}
    def visit(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key in ('image', 'evidence') and isinstance(item, str) and item.endswith('.png'):
                    path = (directory / item).resolve()
                    if path.is_relative_to(directory) and path.is_file() and item not in assets:
                        assets[item] = 'data:image/png;base64,' + base64.b64encode(path.read_bytes()).decode()
                else:
                    visit(item)
        elif isinstance(value, list):
            for item in value: visit(item)
    visit(result)
    static = Path(__file__).parent / 'static'
    css = (static/'report.css').read_text()
    renderer = (static/'report_view.js').read_text()
    fallback = '<noscript><p>Для раскрытия источников включи JavaScript. Краткий результат:</p><table>'
    for row in result['rows']:
        if row['column'] in (5,10,15,16,17):
            fallback += '<tr>'+''.join('<td>'+html.escape(str(value if value is not None else 'Нет данных'))+'</td>' for value in (row['name'],row['reported'],row['expected'],row['delta'],row['status_label'],'; '.join(row['reasons'])))+'</tr>'
    fallback += '</table></noscript>'
    return f'''<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>БухРазум — результат проверки</title><style>{css}</style></head><body><header><strong>БухРазум</strong><span>Команда «УмЗаРазум»</span></header><main><div id="reportHost"></div>{fallback}</main><script id="report-data" type="application/json">{script_json(data)}</script><script id="report-assets" type="application/json">{script_json(assets)}</script><script>{renderer}</script><script>const reportAssets=JSON.parse(document.querySelector('#report-assets').textContent);BukhReport.render(document.querySelector('#reportHost'),JSON.parse(document.querySelector('#report-data').textContent),{{readonly:true,asset:p=>reportAssets[p]||''}});</script></body></html>'''
