# Сторонние компоненты

Языковые модели `app/models/{rus,eng}.traineddata` взяты без изменений из tesseract-ocr/tessdata_fast, commit 87416418657359cb625c412a48b6e1d6d41c29bd. Apache License 2.0 включена в `app/models/LICENSE`; URL и SHA-256 каждого файла — в `manifest.json`. Модели не являются обученными на документах пользователей.

Приложение использует следующие пакеты; лицензии и copyright Python/npm-пакетов сохраняются в устанавливаемых дистрибутивах. Источники лицензий базовых сред перечислены ниже:

| Компонент | Лицензия / источник |
| --- | --- |
| Tesseract.js / tesseract.js-core 7 | Apache-2.0, https://github.com/naptha/tesseract.js и https://github.com/naptha/tesseract.js-core |
| pypdf | BSD-3-Clause, https://github.com/py-pdf/pypdf |
| pypdfium2 / PDFium | Apache-2.0 / BSD-3-Clause и сторонние лицензии PDFium, https://github.com/pypdfium2-team/pypdfium2 |
| Pillow | MIT-CMU (HPND), https://github.com/python-pillow/Pillow |
| NumPy | BSD-3-Clause, https://github.com/numpy/numpy |
| openpyxl | MIT, https://foss.heptapod.net/openpyxl/openpyxl |
| Python | PSF, https://docs.python.org/3/license.html |
| Node.js | MIT и встроенные сторонние компоненты, https://github.com/nodejs/node/blob/main/LICENSE |
| Debian / libstdc++ | Набор лицензий Debian; libstdc++ GPL-3.0 с GCC Runtime Library Exception. Лицензии системных пакетов: `/usr/share/doc/` внутри образа |

npm-транзитивные пакеты перечислены в package-lock.json. Дистрибутивы библиотек, Node и базовые образы скачиваются из официальных источников при сборке, не перепаковываются в исходный архив. Для распространения готового Docker-образа нужно сохранить находящиеся внутри него тексты сторонних лицензий.

Исходные синтетические примеры созданы для этого проекта, не содержат документов заказчика, персональных сведений или фрагментов исходных сканов. Файл шрифта в комплект не включён; PDF содержит растровое изображение.

Лицензия собственного кода команды отдельно не выбрана. Эта заметка не предоставляет дополнительных прав на собственный код и не меняет лицензии сторонних компонентов. Перед выбором open-source лицензии нужно решение владельца кода; публичный репозиторий для просмотра жюри сам по себе не назначает такую лицензию.
