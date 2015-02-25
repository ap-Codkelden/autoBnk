##### v. 4.0.0 03.05.13

* релиз :)

##### v. 4.0.1 04.06.13

* исправлены ошибки округления
* исправлен алгоритм форимрования ширины столбцов
* добавлен вопрос при выходе

##### v. 4.1.0 06.10.13

+ убран вывод в `TXT`
+ добавлен вывод в HTML (для оформления таблицы в этом файле используется [`bank.css`][bankcss]) и открытие в браузере по умолчанию
+ выборка данных теперь осуществляется из файлов DBF, для чего добавлен 
отдельный [модуль импорта][dbftr]
+ добавлена возможность указания органов казначейства, для которых необходимо учитывать сводный бюджет вместо территориального (`Z` - `'0'`) в `FTGZTMDN.XXX` (константа `TREASURY_INVERSE`)
+ использован другой алгоритм округления
+ добавлен параметр `emphline` в конфигурационном файле `summary.xml`, отвечающий за номера строк, которым необходимо дополнительное полужирное выделение
+ обновлена конфигурация
+ мелкие улучшения

##### v. 4.1.1 05.12.14

* добавлена возможность использовать курсив - параметр `/summary/divs/italic` в `summary.xml`

##### v. 4.1.2 17.02.15

* добавлена возможность создания БД на диске, для чего добавлен ключ 
  запуска `-m` или `--memory` с параметром  `[0|1]`
* операции записи в БД теперь проводятся после всех транзакций, что 
  увеличивает быстродействие. 
* оптимизация алгоритма в части формирования дат при выводе.

##### v. 4.1.3 21.02.15
* добавлена возможность записи выходного файла во временный файл `temp[html|xml]`  в случае если файл существует и занят.

##### v. 4.1.4 25.02.15
* добавлена опциональная возможность указания разделителя разрядов в выходном 
файле. По умолчанию включена, разделителем является пробел.
* В связи с этим добавлены ключи командной строки:
    `-nosep, --noseparator` - не использовать разделитель разрядов
    `-m DECIMAL_MARK, --mark DECIMAL_MARK` - символ, используемый в качестве разделителя разрядов
    Ключ создания БД на диске переименован с `-m`, `--memory` в  `-d`, `--disk` соответственно.
* Добавлен вывод информации о версии.

[dbftr]: https://github.com/ap-Codkelden/autoBnk/blob/master/utils.py
[bankcss]: https://github.com/ap-Codkelden/autoBnk/blob/master/config/bank.css