AutoBnk (Auto Bank)
===================

**WARNING!**

This project is no longer supported and remains here only for explorational and historical purposes.

Feel free to fork and use according to license conditions.

Скрипт для выборки сумм налогов, сборов, прочих обязательных платежей, 
контролируемых ГФС Украины, из файлов ГКС (приказ ГКУ/ГНСУ [№74/194 від 25.04.2002](http://zakon4.rada.gov.ua/laws/show/z0436-02))

#### Рекомендации

Для запуска в Windows рекомендуется использовать `*.bat`/`*.cmd` файл, в 
котором предусмотрена смена кодировки терминала, например так:

    @echo OFF
    chcp 1251 > nul && python autobnk.py -m '`
