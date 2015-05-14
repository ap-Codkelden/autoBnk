#!/usr/bin/env python 
# -*- coding: utf-8 -*-

""" 
The MIT License (MIT)
Copyright (c) 2008 - 2015 Renat Nasridinov, <mavladi@gmail.com>

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE. 
"""

import argparse
from jinja2 import Template, Environment, PackageLoader
import decimal
import sqlite3
import sys
import webbrowser
import yaml
from datetime import date
import os.path
from os import listdir
from os.path import isfile, join
from xml.dom import minidom
from utils import dbfToList, ESVZIP, ExtractESV, CalculateESV


version = '4.2.1'

ArgParser = argparse.ArgumentParser(description='Выборка сумм уплаченных ' 
    'налогов из файлов ГКС (приказ ГКУ/ГНСУ №74/194 от 25.04.2002)', 
    epilog='По умолчанию вывод осуществляестя в HTML-файл bankMMDD.html в ' 
    'каталог, указанный в конфигурационном файле (см. документацию)')

ArgParser.add_argument('--version', action='version', 
    version='%(prog)s {}'.format(version))

ArgParser.add_argument('-xml', '--xmlfile', help='генерировать XML-файл '
    'обмена данными bankMMDD.xml', action='store_true', default=False, 
    dest='xmlfile')

ArgParser.add_argument('-d', '--disk', help='создавать файл базы данных на '
    'диске', action='store_true', default=False, dest='disk')

ArgParser.add_argument('-nosep', '--noseparator', help='не использовать '
    'разделитель разрядов', action='store_true')

ArgParser.add_argument('-m', '--mark', help='символ, используемый в качестве '
    'разделителя разрядов', action='store', default=" ", type=str, 
    dest='decimal_mark')

#------------------------Классы обработки ошибок------------------------------

class AutobnkErrors(Exception):
    """ Базовый класс исключений в этом модуле """
    pass

class DirectoryNotFound(AutobnkErrors):
    """ Исключение, возникающее при отсутствии каталога для входных 
    банковвских файлов.

    Атрибуты:
    dir_path- путь, которго нет
    message - сообщение """
    def __init__(self, dir_path):
        self.message = "Каталог {} не найден и будет создан.".format(dir_path)

class UnknownError(AutobnkErrors):
    """ Исключение, возникающее при всяких прочих ошибках."""
    def __init__(self):
        self.message = "Неизвестная ошибка."

class CSSFileNotFoundError(AutobnkErrors):
    """Возникает в случае отсутствия файла стилей `config\bank.css`.
    Агрументы:
        csspath - путь к конфигурационному файлу, которго нет.
    """
    def __init__(self, csspath):
        self.message = ("ПРЕДУПРЕЖДЕНИЕ: Отсутствует файл каскадных таблиц "
            "стилей `{}`. Файл HTML отформатирован не будет.".format(csspath))


class ConfigFileNotFoundError(FileNotFoundError):
    """Возникает в случае отсутствия конфигурационных файлов в директории 
    `config`.
    Агрументы:
        configpath - путь к конфигурационному файлу, которго нет
    """
    def __init__(self, filename):
        super().__init__(self, filename)
        self.filename = filename
        self.message = ('Конфигурационный файл `{}` не найден.\nПродолжение '
            'работы невозможно.'.format(self.filename))


class WrongSeparatorError(AutobnkErrors):
    """Исключение, возникающее если длина разделителя превышает 1 символ или 
    разделитель является цифрой или буквой.

    Атрибуты:
    sep - неверный разделитель
    """
    def __init__(self, sep):
        print("Разделитель `{}` неверный. Будет установлен разделитель по "
            "умолчанию.".format(sep))


class TreasuryFilesNotFound(FileNotFoundError):
    """ Исключение, возникающее при отсутствии казначейских файлов.
    Атрибуты:
        message - сообщение """
    def __init__(self):
        FileNotFoundError.__init__(self)
        self.message = ('Отсутствуют казначейские выписки.\nПродолжение '
            'работы невозможно.')


class DateHandle:
    """ Класс обработки даты и перевода даты в 36-ричной системе
    счисления в обычную дату  
    При создании экземпляра получает текущую дату в том числе в 
    виде кортежа timetuple """
    def __init__(self):
        self.f = date.today().timetuple()
        # self.year = self.f.tm_year


    def BankDate(self, datestring):
        """ Получает строку, описывающую месяц и день (MD) в параметре 
        datestring и возвращает дату в немецком формате, т. е. DD.MM.YYYY
        """
        month = str(int(datestring[0],36)).zfill(2)
        day = str(int(datestring[1], 36)).zfill(2)
        return '.'.join([day, month, str(self.f.tm_year)])


    def CurrentDate(self):
        """Возвращает текущую дату как строковую переменную 'DD.MM.YYYY'"""
        day, month = str(self.f.tm_mday), str(self.f.tm_mon)
        return '.'.join([day.zfill(2), month.zfill(2), str(self.f.tm_year)])


class Writer:
    """При вызове этого класса создается его переменная `a`
    (Writer.a), которая содержит готовый список строк выходной таблицы 
    Он выгодно отличается уже тем, что суммы уже в гривнах.
    """
    def __init__(self, array):
        self.a = array

    def GetList(self):
        return self.a

# класс формирования основной таблицы в спсике списков
class MakeTables:
    """ Класс создания таблиц
    При создании переменной класса bank присваивается содержимое кортежа, 
    содержащего суммы по строкам и номер сортировки
    """
    def __init__(self, bank):
        self.summary = summary_conf
        # Здесь self.bank - кортеж, уже содержащий отобранные запросами 
        # суммы по строкам, 
        self.bank=bank


    def MakeSum(self, varname):
        """Формирует ИТОГОВЫЕ СТРОКИ, которые будут добавлены в 
        таблицу на печать. Номер строки из файла конфигурации сравнивается с 
        номером строки в итоговой таблице, и в случае совпадения значения 
        этой строки добавляются в общему итогу.
        Параметры:
            varname - имя переменной из раздела `sums` файла конфигурации 
            summary.yaml
        """
        try:
            s18 = s83 = s87 = 0 # начальные нулевые значения
            total = [s18,s83,s87,]
            for d in self.summary['sums']:
                if d['varname'] == varname:
                    total_row = [d['desc']] # начало строки итогов
                    numb3rs = d['lines']
                    for i in self.bank:
                        if i[0] in numb3rs:
                            # замена None => 0
                            l = [0 if x is None else x for x in i[2:]]
                            total = [x+y for x,y in zip(total,l)]
                    total_row.extend(total)
            return total_row
        except:
            raise


    def FillList(self):
        """Создание полного массива для дальнейшей обрботки. 
        Этот массив рекомендуется использовать для работы с другими 
        форматами, если чем-то не устроит XML-файл
        Значения сумм налогов в этом списке умножены на 100, то есть 
        123,45 грн. выглядит как 12345 
        ВАЖНО: номера строк для печати разделителей считать БЕЗ УЧЕТА 
        разделителей!
        """
        # сюда запишем результат
        over_list = []
        # z - нумеруем список, УЖЕ СОДЕРЖАЩИЙ ИТОГИ
        # для проверки номеров строк
        z = enumerate(self.bank)
        for element in z:
            # добавляем строки из таблицы 
            # нумерация с 0, не забываем
            over_list.append([element[1][1],element[1][2],element[1][3], 
                element[1][4]])
            for ins_item in self.summary['insert']:
                # а если номер строки совпдает -- вставляем строку итогов
                if element[0] == ins_item['line']:
                    over_list.append(self.MakeSum(ins_item['varname']))
        # over_list - просто готовый список списков, но без итоговых столбцов
        return over_list

class DBProcessing:
    """ При создании экземпляра класса в памяти создается база SQLite3 БД 
    engine и курсор этой БД db_cur

    Класс предоставляет методы:

    CrossProcess -- возвращает результат запроса сводной таблицу (pivot table)
        из имеющихся таблиц etalon и значений по районам из таблицы itog
    GetEtalon -- заполняет таблицы etalon и footer, в которых хранятся 
        перечни налогов и столбцы районов (описаны в файле etalon.yaml)
    CreateTables -- создает таблицы: bank, itog_tmp, itog, etalon, принимая в 
        качаестве параметра raj_list коды территорий казначейств из 
        config.yaml
    FooterCrossProcess -- функция полностью аналогична CrossProcess, но 
        возвращает данные для таблицы внизу страницы. Также определяет функцию 
        GetCodes, которая возвращает строку, содержщую коды для вставки 
        в запрос кодов. 
    Processing -- парсит конфиг условий выборки tax.yaml и затем для каждого 
    условия вызывает SQL-запрос с соответствущими параметрам, и записывает 
    результат запроса в БД.  
    ListTables() -- служебный метод, возвращает список таблиц в БД
    RetrieveTable(table_name) -- служебный метод возвращает из БД таблицу с 
            именем table_name в БД
    FillTable(tr_values, raj_code) -- заполняет таблицу bank значениями из 
            казначейских файлов
    """ 

    def __init__(self, disk=False, name=None):
        """
        Инициализация класса.
        Принимает параметры:
            disk - может принимать значения true|false или 0|1. Укзаывает, 
                создавать файл базы данных на диске или в памяти. По 
                умолчанию равен False.
            name - имя базы даных
        """
        if not disk:
            # база данных в памяти
            self.engine = sqlite3.connect(':memory:')
        else:
            # база данных на диске
            self.engine = sqlite3.connect(name)
        self.db_cur = self.engine.cursor()

    def CrossProcess(self):
        self.db_cur.execute("""INSERT INTO itog 
                        SELECT code AS code, raj AS raj, SUM(zn) as zn 
                        FROM itog_tmp GROUP BY code, raj""")
        self.db_cur.execute("""CREATE TABLE bank_sum AS 
                        SELECT u.code as code, 
                                sum(s83.zn) as raj83, 
                                sum(s87.zn) as raj87, 
                                sum(s18.zn) as raj18 
                        FROM etalon u 
                            left outer join 
                                itog s83 on u.code = s83.code 
                                and s83.raj = 83 
                            left outer join 
                                itog s87 on u.code = s87.code 
                                and s87.raj = 87 
                            left outer join 
                                itog s18 on u.code = s18.code 
                                and s18.raj = 18 
                            GROUP BY u.code""")
        self.db_cur.execute("""SELECT 
                                    e.nompp, 
                                    e.name,
                                    IFNULL(s.raj83,0), 
                                    IFNULL(s.raj87,0), 
                                    IFNULL(s.raj18,0) 
                                FROM 
                                    etalon e 
                                LEFT OUTER JOIN 
                                    bank_sum s 
                                ON 
                                    e.code = s.code
                                ORDER BY 
                                    nompp""")
        return self.db_cur.fetchall()

    def FooterCrossProcess(self):
        def GetCodes(footer=etalon['footer']):
            list_codes = []
            for f in footer:
                list_codes.append(f['code'])
            return ','.join([str(x) for x in list_codes])

        query = ("CREATE TABLE footer_itog AS "
                "SELECT code AS code, raj AS raj, SUM(zn) as zn "
                "FROM itog_tmp WHERE code IN({})"
                "GROUP BY code, raj".format(GetCodes()))
        self.db_cur.execute(query)
        self.db_cur.execute("""CREATE TABLE footer_sum AS 
                        SELECT u.code as code, 
                                sum(s83.zn) as raj83, 
                                sum(s87.zn) as raj87, 
                                sum(s18.zn) as raj18 
                        FROM footer u 
                            left outer join 
                                footer_itog s83 on u.code = s83.code 
                                and s83.raj = 83 
                            left outer join 
                                footer_itog s87 on u.code = s87.code 
                                and s87.raj = 87 
                            left outer join 
                                footer_itog s18 on u.code = s18.code 
                                and s18.raj = 18 
                            GROUP BY u.code""")
        self.db_cur.execute("""SELECT 
                                    e.nompp, 
                                    e.name,
                                    IFNULL(s.raj83,0), 
                                    IFNULL(s.raj87,0), 
                                    IFNULL(s.raj18,0) 
                                FROM 
                                    footer e 
                                LEFT OUTER JOIN 
                                    footer_sum s 
                                ON 
                                    e.code = s.code
                                ORDER BY 
                                    nompp""")
        return self.db_cur.fetchall()


    def GetEtalon(self):
        for row in etalon['etalons']:
            self.db_cur.execute("""INSERT INTO etalon (code, name, nompp) """
                        """VALUES ("{}", "{}", {})""".format(
                            row['code'], 
                            row['name'], 
                            row['row']))
        for row in etalon['footer']:
            self.db_cur.execute("""INSERT INTO footer (code, name, nompp) """
                        """VALUES ("{}", "{}", {})""".format(
                            row['code'], 
                            row['name'], 
                            row['row']))
        self.engine.commit()
            

    def CreateTables(self): #, raj_list):
        try:
            # создание таблиц
            self.db_cur.execute("""CREATE TABLE bank (raj integer, rozd text,
                rd text, pg text, st text, zn integer, bd integer)""")
            self.db_cur.execute("""CREATE TABLE itog_tmp (code text, 
                raj integer, zn integer)""")
            self.db_cur.execute("""CREATE TABLE itog (code text, raj integer, 
                zn integer)""")
            self.db_cur.execute("""CREATE TABLE etalon (code text, name text, 
                nompp integer)""")
            self.db_cur.execute("""CREATE TABLE footer (code text, name text, 
                nompp integer)""")
            self.engine.commit()
        except sqlite3.OperationalError:
            print('Таблица уже существует в базе данных.')
            sys.exit()


    def FillTable(self, tr_values, raj_code):
        try:
            # заполнение таблицы
            for e in tr_values:
                self.db_cur.execute("insert into bank values "
                    "({},{},'{}','{}','{}',{},{})".format(raj_dict[raj_code], 
                        e[0], e[1][0], e[1][1], e[1][2], e[2], e[3]))
            self.engine.commit()
        except KeyError as e:
            print('Банковские файлы имеют расширение `{}` вместо расширений '
                'в виде кодов казначейств.\nПереименуйте файлы и '
                'перезапустите программу'.format(e.args[0]))
            sys.exit()
            raise


    def ListTables(self):
        # перечисление таблиц
        self.db_cur.execute("SELECT name FROM sqlite_master WHERE "
            "type='table' ORDER BY name;")
        print(self.db_cur.fetchall())


    def RetrieveTable(self, table_name):
        # вывод таблицы по имени
        print("Таблица: ", table_name)
        self.db_cur.execute("SELECT * FROM "+table_name)
        for element in self.db_cur.fetchall():
            print(element)
        print('-'*78)


    def Processing(self):
        try:
            tax = ReadYAMLConf('tax.yaml')
        except ConfigFileNotFoundError as e:
            raise
            sys.exit()
        else:
            for row in tax['tax']:
                code = row['_code']
                for query in row['row']:
                    raj = '' if not 'raj' in query['query'] \
                        else " AND raj='{}'".format(query['query']['raj'])
                    rozd = '' if not 'rozd' in query['query'] \
                        else " AND rozd='{}'".format(query['query']['rozd'])
                    bd = query['query']['bd']
                    rd = query['query']['rd']
                    pg = '' if not 'pg' in query['query'] \
                        else " AND pg='{}'".format(query['query']['pg'])
                    st = '' if not 'st' in query['query'] \
                        else " AND st='{}'".format(query['query']['st'])
                    coef = 1.00 if not 'coef' in query['query'] \
                        else query['query']['coef']
                    try:
                        query = """SELECT raj, 
                                      SUM(zn) * {0} as 'zn' 
                                   FROM 
                                      bank 
                                   WHERE 
                                      bd={1} AND rd='{2}' {3} {4} {5} {6} 
                                   GROUP BY raj;""".format(
                                      float(coef), #0
                                      bd, #1
                                      rd, #2
                                      pg, #3
                                      rozd, #4
                                      st, #5
                                      raj)  #6
                        self.db_cur.execute(query)
                        for e in self.db_cur.fetchall():
                            # район, код, сумма
                            self.db_cur.execute("INSERT INTO itog_tmp VALUES "
                                "('{}', '{}', {})".format(code, e[0], e[1]))
                    except:
                        raise 

class WriteFile():
    """ Получает дату банковских файлов в виде параметра tr_files_date. Дата 
    файлов была получена ранее из процедуры Make
    """
    def __init__(self):
        self.dt=DateHandle()
        self.tr_date = fn

    def GetCSS(self, cssname='bank.css'):
        """Открывает минифицированный файл CSS и возвращает его содержимое 
        для вставки в HTML-файл
        """
        try:
            csspath = os.path.join('config',cssname)
            if os.path.isfile(csspath): 
                return open(csspath,'r').read() 
            else:
                raise CSSFileNotFoundError(csspath)
        except CSSFileNotFoundError as e:
            print(e.message)


    def ComposeFileName(self, extension, temp=False):
        """ Формирование имени выходного файла
        принимает расширение extension БЕЗ ТОЧКИ и возвращает 'bankMMDD.ext' 
        с учётом пути сохранения, определенного в config.yaml
        Параметр temp определяет, вызвана ли функция для возврата временного 
        имени файла в случае, если файл занят (см. процедуру WriteFile).
        """
        if not temp:
            filename = ''.join([
                    'bank',self.dt.BankDate(fn)[3:5], self.dt.BankDate(fn)[:2]
                ])
        else:
            filename = 'temp'
        return ''.join((out_directory,os.sep,filename,'.', extension))


    def GetDelimitersPosition(self):
        """ Возвращает словарь из списков (single_ln, double_ln, emph_ln, 
        italic_ln), содержащих номера строк, после которых применяются 
        эффекты:

        Список      Эффект                  ключ словаря/класс CSS
        single_ln   одинарная линия         single
        double_ln   полужирный с  рамкой    double
        emph_ln     полужирный              emphasis
        italic_ln   курсив                  italic

        Эти данные хранятся в переменных раздела <divs> singleline, 
        doubleline, italic и emphline соответственно файла summary.yaml
        """

        position_values = summary_conf['divs']
        keys, values = position_values.keys(), position_values.values()
        return dict(zip(keys,values))


    def MakeHTML(self, rows, esv=None):
        """Компонует страницу html.
        Получает словарь, содержащий номера строк, после которых будут 
        вставлены разделители либо применено форматирование (функция 
        GetDelimitersPosition) в переменную insert_rows.
        Определяет внутреннюю функцию GetCSSSelector, которая получает номер 
        строки и ищет его в словаре, который возвращает функция 
        GetDelimitersPosition и возвращает имя селектора CSS (или имена 
        нескольких селекторов через пробел), если строке не сопоставлен 
        стиль, возвращает пустую строку.
        Также содержит функцию Separator - добавляет разделитель разрядов, 
        определенный в переменной decimal_mark в зависимости от значения 
        переменной noseparator. 
        По умолчанию добавляет в качестве разделителя пробел.
        """

        insert_rows = self.GetDelimitersPosition()

        # устанавливаем правила округления
        decimal.getcontext().rounding=decimal.ROUND_HALF_EVEN


        def DoSeparate(sep_num, noseparator=noseparator):
            sep_num = decimal.Decimal(sep_num/100).quantize(decimal.Decimal('0'))
            if noseparator:
                return str(sep_num)
            else:
                return format(int(sep_num), ",d").replace(",", decimal_mark)


        def GetCSSSelector(row_num, delims=insert_rows):
            # пустой список для стилей
            class_items = []
            for k,v in delims.items():
                # row_num - 1: нумерация с 0
                # чтобы было согласовано с итогами
                if row_num - 2 in v:
                    class_items.append(k)
            if class_items:
                return ' '.join(class_items)
            else:
                return ''

        # считываем содержимое шаблона 
        try:
            environment = Environment(loader=PackageLoader('autobnk', 'config'))
            environment.filters['separator'] = DoSeparate
            page_template = environment.get_template('bank.tmpl')
        except FileNotFoundError:
            print("ФАТАЛЬНО: Отсутствуeт шаблон веб-страницы.\nПродолжение "
                "работы невозможно.")
            sys.exit()

        # словарь page_data будет передан в шаблон
        page_data = {
            'cur_date': self.dt.CurrentDate(),
            'bank_date': self.dt.BankDate(self.tr_date),
            'css': self.GetCSS(),
        }

        # пустой список строк
        table_rows = []
        # Генерируется новый список с нумерацией строк, начинающейся с 1
        # 
        for row in [(x[0]+1, x[1]) for x in enumerate(rows)]:
            r = [GetCSSSelector(row[0])] # получим CSS 
            name = [row[1][0]]          # название налога
            # к готовой строке добавляются суммы налогов
            r.extend(name)
            r.extend(row[1][1:])
            # Формируется строка таблицы в разметке HTML
            table_rows.append(r)
        page_data['rows'] = table_rows
        page_data['footer'] = base.FooterCrossProcess()
        if esv:
            page_data['esv'] = esv
        return page_template.render(page_data=page_data)


    def WriteFile(self, content):
        try:
            fn = self.ComposeFileName('html')
            with open(fn, 'w', encoding='utf-8') as f:
                f.write(content)
            return fn
        except PermissionError:
            sys.stdout.write("\nФайл занят и будет сохранен под именем" 
                "'tmp.html'")
            fn = self.ComposeFileName('html',temp=True)
            with open(fn, 'w') as f:
                f.write(content)
        finally:
            return fn


    def WriteXML(self, rows):
        """ Просто сохранение строк в XML-файл """
        import xml.etree.ElementTree as ET
        root = ET.Element('bank')
        d = DateHandle()
        tr_file_date = ET.SubElement(root, 'bank_date')
        # дата в виде YYYYMMDD
        tr_file_date.text = (self.dt.BankDate(fn)[-4:] + 
                            self.dt.BankDate(fn)[3:5] + 
                            self.dt.BankDate(fn)[:2])
        data = ET.SubElement(root, 'data')
        # вывод таблицы
        for row in rows:
            line = ET.SubElement(data, 'line')
            name = ET.SubElement(line, 'name')
            name.text=row[0]
            raj83 = ET.SubElement(line, 'raj83')
            raj83.text = str(row[1])
            raj87 = ET.SubElement(line, 'raj87')
            raj87.text = str(row[2])
            raj18 = ET.SubElement(line, 'raj18')
            raj18.text = str(row[3])
        with open(self.ComposeFileName('xml'),mode='bw') as xml_file:
            xml_file.write(
                minidom.parseString(
                    ET.tostring(root)
                    ).toprettyxml(indent="\t", encoding='windows-1251'))


def ParseFile(tr_dir, tr_f):
    # получаем имя файла, соединяя папку и имя
    tr_file_name=os.path.join(tr_dir, tr_f)
    # определяем тип бюджета
    if tr_f[2]=='0':
        bd_type=DB
    else:
        bd_type=MB
    # нужно открыть файл и скормить его 
    li = dbfToList(tr_file_name)
    tr_val = li.read_table()
    # вызываем процедуру заполнения таблицы, передавая ей
    # список строк tr_val и код территории казначейства 
    # (расширение файла)
    base.FillTable(tr_val, tr_f[-3:])


def ReadConfig():
    """Парсит файл конфигурации `config.yaml` и проводит следующие операции:
        - Наполняет кортеж для расширений файлов казны tr_ext кодами 
        территорий казначейств
        - Создает нужные папки, если их нет.
    """
    config = ReadYAMLConf('config.yaml')
    try:
        out_dir = config['config']['path']['path-out']
        if not os.path.exists(out_dir):
            os.makedirs(out_dir)
        for f in config['config']['treasury_files']:
            if 'inverse' in f:
                tr_inv.append(f['file']['code'])
            tr_ext.append(f['file']['code'])
            raj_dict[f['file']['code']] = f['file']['raj']
        return config['config']['path']['path-bank'], \
               config['config']['path']['path-out']
    except:
        raise


def Make(bankpath):
    """Создание таблиц """
    base.CreateTables()
    """Создание списка казначейских файлов по списку 
    из директории, указанной в конфигурационном файле """
    files = GetFileNames(bankpath=bankpath)
    try:
        if len(files) == 0:
            raise TreasuryFilesNotFound
    except TreasuryFilesNotFound as e:
        print(e.message)
        sys.exit()
    for i in files:
        ParseFile(bankpath, i)
    # вернем 1е имя файла для получения даты
    return files[0]

def PrintApprove(question, default = 'yes'):
    """Спрашивает пользователя 'y/n' в терминале и ждет его ответа.
    question -- вопрос, который видит пользователь.
    default -- ответ, который будет принят при нажати Enter. Должен
        быть yes, no или None (в последнем случае ждет ответа до победы).
    answer принимает одно из значений "yes" или "no".
    """
    valid = {"yes": True, "y": True, "n": False, "no": False}
    if default == None:
        prompt = " [y/n] "
    elif default == "yes":
        prompt = " [Y/n] "
    elif default == "no":
        prompt = " [y/N] "
    else:
        raise ValueError("Неправильное значение ответа, по умолчанию {}"
            .format(default))
    while True:
        sys.stdout.write(question + prompt)
        choice = input().lower()
        if default is not None and choice == '':
            return valid[default]
        elif choice in valid:
            return valid[choice]
        else:
            sys.stdout.write("Правильные ответы 'y/yes' или 'n/no'\n")


def GetFileNames(bankpath):
    """Возвращает массив, содержащий имена казначейских файлов."""
    return [f for f in listdir(bankpath) if isfile(os.path.join(bankpath,f)) 
        and f[4]=='0' and ((f[3]=='1' and not f[9:] in tr_inv)  
        or ((f[2]=='0' or (f[2]=='1' and f[3]=='0')) and f[9:] in tr_inv))]


def ReadYAMLConf(configname):
    """Читет файл конфигурации, имя которого передано в параметре `configname` 
    и возвращает его в сериализованном виде.
    """
    configpath = lambda p: os.path.join('config', p)
    try: 
        if not os.path.isfile(configpath(configname)):
            raise ConfigFileNotFoundError(configname)
    except ConfigFileNotFoundError as e:
        print(e.message)
        sys.exit()
    except:
        raise
    else:
        with open(configpath(configname), encoding="utf-8") as cf_yaml:
            return yaml.load(cf_yaml)


if __name__=="__main__":
    # получаем агрументы командной строки
    results = ArgParser.parse_args()
    # наличие разделителя и сам разделитель 
    try:
        noseparator = results.noseparator
        decimal_mark = results.decimal_mark
        if (not decimal_mark and not noseparator) or len(decimal_mark)>1 or \
            decimal_mark.isdigit() or decimal_mark.isalpha():
            raise WrongSeparatorError(decimal_mark)
    except WrongSeparatorError:
        decimal_mark = "'"

    """ Глобальные списки, константы и прочее """
    # константа госбюджет
    DB = 0
    # константа местный бюджет
    MB = 1

    # списки для расширений файлов казны
    # и для кодов казначейств, для которых необходимо условие выборки, 
    # согласно которго бюджет имеет признак "сводный" - 0
    tr_ext = []
    tr_inv = []
    raj_dict = {} # словарь сопоставления казначейств районам

    # Чтение из файлов конфигурации config/*.yaml  
    # в соответствующие переменные для глоабльного использования
    summary_conf = ReadYAMLConf('summary.yaml')
    etalon = ReadYAMLConf('etalon.yaml')
    # получаем из конфигурационных файлов пути: 
    #   out_directory -- путь для записи файлов
    #   bank_directory -- путь к казначейским файлам
    bank_directory, out_directory = ReadConfig()
    for dir_ in bank_directory, out_directory:
        try:
            if not os.path.isdir(dir_):
                raise DirectoryNotFound(dir_)
        except DirectoryNotFound as e:
            os.mkdir(dir_)
            print(e.message)
            sys.exit()

    # подготовка, генерация таблицы в  FillList()
    #if not results.disk:
    dh = DateHandle()   # экз. класса обработки даты
    # создание имени файла базы данных - берется дата банка из имени файла
    # разделяется на ДД, ММ, ГГГГ, переворачивается и создаем имя
    db_date = dh.BankDate(GetFileNames(bank_directory)[0][5:7])
    h = db_date.split('.')
    h.reverse()
    db_name = os.path.join(out_directory, ''.join([ 
        'bank', 
        ''.join(h), 
        '.db' 
        ]))
    if os.path.isfile(db_name):
        os.remove(db_name)
    base = DBProcessing(disk=results.disk, name=db_name)
    # попытка посчиать ЕСВ
    esv = ExtractESV(os.path.join(bank_directory,ESVZIP), tr_ext)
    #if esv:
    #    esv = decimal.Decimal(esv/100).quantize(decimal.Decimal('0'))
    #    print(esv)
    # fn - имя файла для получения даты
    fn = Make(bank_directory)[5:7]
    base.Processing()
    base.GetEtalon()
    # основная таблица + таблица внизу
    q = MakeTables(base.CrossProcess())
    #base.FooterCrossProcess()
    g=Writer(q.FillList())
    # экземпляр WriteFile
    html_wr = WriteFile()
    # делаем html
    # html_page -- имя файла с расширением ".html"
    html_page = html_wr.WriteFile(html_wr.MakeHTML(g.GetList(),esv=esv))

    if PrintApprove("Открыть?"):
        webbrowser.open(html_page, new=2, autoraise=True)
        sys.stdout.write("\nФайл сохранен в {}\n".format(html_page))
    if results.xmlfile:
        html_wr.WriteXML(g.a)
        sys.stdout.write(
            "\nФайл XML сохранен в директорию сохранения как "
            "{0}.".format(''.join((html_page.split('.')[0],'xml')))
            )
    input("\n\nНажмите Enter для выхода.")
