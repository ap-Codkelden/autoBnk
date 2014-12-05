""" 
AutoBnk4  
version 4.5.2

  The MIT License (MIT)
  Copyright (c) 2008 - 2014 Renat Nasridinov, <mavladi@gmail.com>
  
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
import math
import sqlite3
import sys
import xml.etree.ElementTree as ET # полёт навигатора!!!
import webbrowser
from datetime import date
import os.path
from os import listdir
from os.path import isfile, join
from xml.dom import minidom
from dbftr import dbfToList

ArgParser = argparse.ArgumentParser(description='Выборка сумм уплаченных \
	налогов из файлов ГКС (приказ ГКУ/ГНСУ №74/194 от 25.04.2002)', \
    epilog='По умолчанию вывод осуществляестя в HTML-файл\
    bankMMDD.html в каталог, указанный в конфигурационном \
    файле (см. документацию)')

ArgParser.add_argument('-xml', '--xmlfile', help='генерировать XML-файл \
	обмена данными bankMMDD.xml', action='store_true', default=False, \
	dest='xmlfile')

""" Глобальные списки, константы и прочее """
# константа TREASURY_INVERSE определяет код(ы) казначейств(а), для которых 
# необходимо условие выборки, согласно которго бюджет имеет признак "сводный"- 0
TREASURY_INVERSE = ('097',)

""" Константы страницы html  
В HTML_BLOCK_START уже внесены переменные для форматирования, в процедуре 
MakeHTML() класса WriteFile происходит непосредственно форматирование."""

HTML_BLOCK_START = """<html><head><meta http-equiv="Content-Type" content="text/html"; charset="windows-1251"><style type="text/css">{0}</style><title></title></head><body><p>Поточна дата: <span id='dt'>{1}</span><br>Дата банку: <span id='dt'>{2}</span></p><table><tr><th>Податок</th><th>Жовтн</th><th>Терн</th><th>Півн</th><th>Кр. р/н</th><th>ВСЬОГО</th></tr>"""
HTML_BLOCK_END = """</table></body></html>"""


# константа госбюджет
DB = 0
# константа местный бюджет
MB = 1

tr_ext = []    # кортеж для расширений файлов казны
raj_dict = {}  # словарь сопоставления казначейств районам

#------------------------Классы обработки ошибок-------------------------------

class AutobnkErrors(Exception):
	""" Базовый класс исключений в этом модуле """
	pass

class DirectoryNotFound(AutobnkErrors):
	""" Исключение, возникающее при отсутствии каталога для входных банковвских 
	файлов.

	Атрибуты:
	dir_path- путь, которго нет
	message - сообщение	"""
	def __init__(self, dir_path):
		self.message = "Каталог %s не найден и будет создан." % (dir_path)

class TreasuryFilesNotFound(FileNotFoundError):
	""" Исключение, возникающее при отсутствии казначейских файлов.
	Атрибуты:
	message - сообщение	"""
	def __init__(self):
		FileNotFoundError.__init__(self)
		self.message = "Отсутствуют казначейские выписки, продолжение работы невозможно.\nДо свидания."

class DateHandle:
	""" Класс обработки даты и перевода даты в 36-ричной системе
	счисления в дату обычную 
	При создании экземпляра получает текущую дату в том числе в 
	виде кортежа timetuple """
	def __init__(self):
		self.f= date.today().timetuple()

	def BankDate(self, datestring):
		""" Получает строку, описывающую месяц и день (MD) в параметре 
		datestring и возвращает дату в немецком формате, т. е. DD.MM.YYYY """
		month=str(int(datestring[0],36)) if len(str(int(datestring[0],36)))>1 \
			else str(int(datestring[0], 36)).rjust(2,'0')
		day=str(int(datestring[1], 36)) if len(str(int(datestring[1], 36)))>1 \
			else str(int(datestring[1], 36)).rjust(2,'0')
		return ''.join((day, '.', month, '.', str(self.f[0])))

	def CurrentDate(self):
		""" Возвращает текущую дату как строковую переменную 'DD.MM.YYYY' """
		curdate = []
		for i in range(0,3):
			if len(str(self.f[i]))<2:
				curdate.append(str(self.f[i]).rjust(2,'0'))
			else:
				curdate.append(str(self.f[i]))
		return ''.join((curdate[2], '.', curdate[1], '.', curdate[0]))

class Writer:
	""" При вызове этого класса создается его переменная a
	(Writer.a), которая содержит готовый список строк выходной таблицы 
	Он выгодно отличается уже тем, что суммы уже в гривнах """
	def __init__(self, array):
		self.a = []
		for i in array:
			# ai -- append_item
			ai1 = 0 if i[1] == None else i[1]
			ai2 = 0 if i[2] == None else i[2]
			ai3 = 0 if i[3] == None else i[3]
			self.a.append([i[0],ai1,ai2,ai1+ai2,ai3,ai1+ai2+ai3])

	def GetList(self):
		return self.a

# класс формирования основной таблицы в спсике списков
class MakeTables:
	""" Класс создания таблиц
	При создании переменной класса bank присваивается содержимое кортежа, содержащего
	суммы по строкам и номер сортировки"""
	def __init__(self, bank):
		self.summary = GetSummaryData() 
		self.s = self.summary.getroot()
		# Здесь self.bank - кортеж, уже содержащий отобранные запросами 
		# суммы по строкам, 
		self.bank=bank

	def MakeSum(self, varname):
		""" Формирует ИТОГОВЫЕ СТРОКИ, которые будут добавлены в 
		таблицу на печать """
		s18 = s83 = s87 = 0
		for d in self.s.iter('sum'):
			if d[0].text==varname:
				desc = d[2].text
				numb3rs = [int(f) for f in d[1].text.split(',')]
				for i in self.bank:
					if i[0] in numb3rs:
						s83 = ((s83 + 0) if i[2]==None else (s83+i[2]))
						s87 = ((s87 + 0) if i[3]==None else (s87+i[3]))
						s18 = ((s18 + 0) if i[4]==None else (s18+i[4]))
		return [desc, s83, s87, s18]

	def FillList(self):
		""" создание полного массива для дальнейшей обрботки. 
		Этот массив рекомендуется использовать для работы с другими 
		форматами, если чем-то не устроит XML-файл
		Значения сумм налогов в этом списке умножены на 100, то есть 
		123,45 грн. выглядит как 12345 
		ВАЖНО: номера строк для печати разделителей считать БЕЗ УЧЕТА 
		разделителей!!! """
		# сюда запишем результат
		over_list = []
		# находим раздел конфига inserts 
		f = self.summary.find('inserts')
		# z - нумеруем список, УЖЕ СОДЕРЖАЩИЙ ИТОГИ
		# для проверки номеров строк
		z = enumerate(self.bank)
		for element in z:
			# добавляем строки из таблицы 
			# нумерация с 0, не забываем
			over_list.append([element[1][1],element[1][2],element[1][3], \
				element[1][4]])
			for ins_item in f:
				# а если номер строки совпдает -- вставляем строку итогов
				if element[0] == int(ins_item[0].text):
					over_list.append(self.MakeSum(ins_item[1].text))
		# over_list - просто готовый список списков, но без итоговых столбцов
		return over_list

class DBProcessing:
	""" При создании экземпляра класса в памяти создается база SQLite3 БД engine
	и курсор этой БД db_cur

	Класс предоставляет методы:

	CrossProcess -- возвращает результат запроса сводной таблицу (pivot table)
		из имеющихся таблиц etalon и значений по районам из таблицы itog
	MakeEtalon -- заполняет таблицу etalon, в которой хранится перечень налогов
		и столбцы районов (описаны в файле etalon.xml)
	CreateTables -- создает таблицы: bank, itog_tmp, itog, etalon, принимая в 
		качаестве параметра raj_list коды территорий казначейств из config.xml
	Processing -- парсит конфиг условий выборки tax.xml и затем для каждого 
	условия вызывает SQLConstruct(code,params) с соответствущими атрибутами
	SQLConstruct(code,params) -- создает строку, содержащую запрос SQL. 
		Принимает параметры:
		code -- код платежа, напимер "110200" из tax.xml
		params -- список параметров из tax.xml (значения rozd, bd, rd, pg, coef)
	ListTables() -- служебный метод, возвращает список таблиц в БД
	RetrieveTable(table_name) -- служебный метод возвращает из БД таблицу с 
			именем table_name в БД
	FillTable(tr_values, raj_code) -- заполняет таблицу bank значениями из 
			казначейских файлов """ 

	def __init__(self):
		# база данных в памяти
		self.engine = sqlite3.connect(':memory:')
		#print('>> Engine created.')
		self.db_cur = self.engine.cursor()

	def CrossProcess(self):
		self.db_cur.execute("INSERT INTO itog \
						SELECT code AS code, raj AS raj, SUM(zn) as zn \
						FROM itog_tmp GROUP BY code, raj")
		self.db_cur.execute("CREATE TABLE bank_sum (code text, raj83 integer, \
			raj87 integer, raj18 integer)")
		self.db_cur.execute("""INSERT INTO bank_sum 
						SELECT u.code, 
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
		self.db_cur.execute("SELECT e.nompp, e.name, \
							s.raj83, s.raj87, s.raj18 \
							from etalon e \
							left outer join \
							bank_sum s \
							on e.code = s.code\
							ORDER BY nompp")
		return (self.db_cur.fetchall())

	def MakeEtalon(self):
		try:
			etalon_row = ET.parse('config\\etalon.xml')
			table = etalon_row.getroot()
			for row in table:
				self.db_cur.execute('insert into etalon (code, name, nompp) values \
					("%s","%s", %d)' % (row[0].text, row[1].text, int(row[2].text)))
				self.engine.commit()
		except FileNotFoundError as e:
			print("Отсутствует конфигурационный файл %s.\nДо свидания." % (e.filename))
			sys.exit()
			

	def CreateTables(self): #, raj_list):
		# создание таблиц
		self.db_cur.execute("CREATE TABLE bank (raj integer, rozd text,rd text, \
			pg text, st text, zn integer, bd integer)")
		self.db_cur.execute("CREATE TABLE itog_tmp (code text, raj integer,\
			zn integer)")
		self.db_cur.execute("CREATE TABLE itog (code text, raj integer, \
			zn integer)")
		self.db_cur.execute("CREATE TABLE etalon (code text, name text, nompp \
			integer)")
		self.engine.commit()

	def FillTable(self, tr_values, raj_code):
		# заполнение таблицы
		for e in tr_values:
			self.db_cur.execute('insert into bank values \
				(%s,%s,"%s","%s","%s",%s,%s)' % \
				(raj_dict[raj_code],e[0],e[1][0],e[1][1],e[1][2],e[2],e[3]))
			self.engine.commit()

	def ListTables(self):
		# перечисление таблиц
		self.db_cur.execute("SELECT name FROM sqlite_master WHERE type='table' \
			ORDER BY name;")
		print(self.db_cur.fetchall())

	def RetrieveTable(self, table_name):
		# вывод таблицы по имени
		print("Таблица: ", table_name)
		self.db_cur.execute("SELECT * FROM "+table_name)
		for element in self.db_cur.fetchall():
			print(element)
		print('-'*80)

	def SQLConstruct(self,code,params):
		rozd = ('' if params[0]==None else " AND rozd='"+params[0]+"'")
		bd = params[1] # всегда присутствует
		rd = params[2] # всегда присутствует
		pg = ('' if params[3]==None else " AND pg='"+params[3]+"'")
		coef = params[4] # всегда присутствует
		query = "SELECT raj, SUM(zn) * %f as 'zn' FROM bank WHERE bd=%s AND \
			rd='%s' %s %s GROUP BY raj;" % (float(params[4]), params[1], \
			params[2], pg, rozd)
		self.db_cur.execute(query)
		for e in self.db_cur.fetchall():
			# район, код, сумма
			self.db_cur.execute("insert into itog_tmp values (%s, %s, %d)" % \
				(code, e[0], e[1]))

	def Processing(self):
		try:
			tax_list = ET.parse('config\\tax.xml')
			tax = tax_list.getroot()
			for row in tax:
				for query in row:
					params = []
					# <rozd> <bd> <rd> <pg> <coef>
					for c in query:
						params.append(c if c == None else c.text) 
					self.SQLConstruct(row.attrib['code'],params)
		except FileNotFoundError as e:
			print("Отсутствует конфигурационный файл %s.\nДо свидания." % (e.filename))
			sys.exit()

class WriteFile():
	""" Получает дату банковских файлов в виде параметра tr_files_date. Дата 
	файлов была получена ранее из процедуры Make
	"""
	def __init__(self):
		self.dt=DateHandle()
		self.tr_date = fn

	def GetCSS(self):
		"""Открывает файл CSS и возвращает его содержимое для вставки в HTML-файл"""
		try:
			return open('config\\bank.css','r').read().replace('\n', '')
		except FileNotFoundError:
			print("ПРЕДУПРЕЖДЕНИЕ: Файл `bank.css` не найден. Таблица будет неотформатирована.")

	def ComposeFileName(self, extension):
		"""	Формирование имени выходного файла
		принимает расширение extension БЕЗ ТОЧКИ и возвращает 'bankMMDD.ext' с 
		учётом пути сохранения, определенного в config.xml
		"""
		return ''.join((out_directory,os.sep,'bank',self.dt.BankDate(fn)[3:5],\
			self.dt.BankDate(fn)[:2],'.', extension))

	def GetDelimitersPosition(self):
		""" Возвращает кортеж из списков (single_ln, double_ln, emph_ln)
		В первом списке single_ln -- номера строк, после которых вставляется 
		просто линия (начиная с версии 4.5 -- оставлена как резерв), во втором 
		double_ln -- номера строк, после которых следует строка, которую нужно
		выделить, в emph_ln -- строки, в которых тоже будет выделение (земля, 
		единый).
		Эти данные хранятся в переменных раздела <divs> singleline, doubleline и
		emphline соответственно (файл summary.xml)
		"""
		summary = GetSummaryData()
		single_ln=list(map(int,summary.find('divs/singleline').text.split(',')))
		double_ln=list(map(int,summary.find('divs/doubleline').text.split(',')))
		emph_ln=list(map(int,summary.find('divs/emphline').text.split(',')))
		italic_ln=list(map(int,summary.find('divs/italic').text.split(',')))
		#return (single_ln, double_ln, emph_ln)
		return (single_ln, double_ln, emph_ln, italic_ln)

	def MakeHTML(self, rows):
		""" Компонует страницу html.
		Переменные: __delims - хранит кортеж разделителей, __counter - счётчик 
		строк, __page_body - пустая строковая переменная для записи тела 
		страницы. 
		Страница формируется как:
			HTML_BLOCK_START + __page_body + HTML_BLOCK_END
		и записывается в дальнейшем в файл процедурой write_html.
		"""
		hrn = lambda x: math.ceil(x/100) if ((x/100) % 1) > 0.51 else math.floor(x/100)
		__delims = self.GetDelimitersPosition()
		__counter = 0
		__page_body = ''
		for r in rows:
			"""
			Вставляет классы CSS
			"""
			__line = __counter+1
			if __line in __delims[1]:
				css = ' class="total"'
			elif __line in __delims[0]:
				css = ' class="single"'
			elif __line in __delims[2]:
				css = ' class="emphasis"'
			elif __line in __delims[3]:
				css = ' class="italic"'
			else:
				css = ''
			__page_body=__page_body + "<tr{0}><td class='names'>{1}</td><td>{2}</td><td>{3}</td><td>{4}</td><td>{5}</td><td>{6}</td></tr>".format(css,r[0],hrn(r[1]),hrn(r[2]),hrn(r[3]),hrn(r[4]),hrn(r[5]))
			__counter+=1
		# __header просто синтаксический сахар 
		__header = HTML_BLOCK_START.format(self.GetCSS(),self.dt.CurrentDate(), \
			self.dt.BankDate(self.tr_date))
		return ''.join([__header,__page_body,HTML_BLOCK_END])

	def WriteFile(self, content):
		fn = self.ComposeFileName('html')
		with open(fn, 'w') as f:
			f.write(content)
		return fn

	def WriteXML(self, rows):
		""" Просто сохранение строк в XML-файл """
		root = ET.Element('bank')
		d = DateHandle()
		tr_file_date = ET.SubElement(root, 'bank_date')
		# дата в виде YYYYMMDD
		tr_file_date.text = self.dt.BankDate(fn)[-4:]+self.dt.BankDate(fn)[3:5]+ \
			self.dt.BankDate(fn)[:2]
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
			raj18.text = str(row[4])
			sum83 = ET.SubElement(line, 'sum83')
			sum83.text = str(row[3])
			sumnord = ET.SubElement(line, 'sumnord')
			sumnord.text = str(row[5])
		with open(self.ComposeFileName('xml'),mode='bw') as xml_file:
			xml_file.write(minidom.parseString(ET.tostring(root)).toprettyxml(indent="\t", \
				encoding='windows-1251'))
		#xml_file.close

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
	"""наполняет кортеж для расширений файлов казны tr_ext кодами территорий 
	казначейств из config.xml"""
	try:
		if os.path.exists('config\\config.xml'):
			treasury_conf = ET.parse('config\\config.xml')
			tr = treasury_conf.getroot()
			if not os.path.exists(tr[0][1].text):
				os.makedirs(tr[0][1].text)
			for tr_code in tr.iter('code'):
				tr_ext.append(tr_code.text)
			for item in tr.iter('file'):
				raj_dict[item[1].text]=item[2].text
			return (tr[0][0].text, tr[0][1].text)
		else:
			raise ConfigFileNotFoundError
	except ConfigFileNotFoundError as e:
		print(e.message)
		sys.exit()

def GetSummaryData():
	"""Поскольку содержимое файла summary.xml используется в GetDelimitersPosition() и 
	как переменная класса MakeTables, процедура его чтения определена здесь. """
	try:
		return ET.parse('config\\summary.xml')
	except FileNotFoundError as e:
		print("Отсутствует конфигурационный файл %s.\nДо свидания." % (e.filename))
		sys.exit()

def Make(bankpath):
	""" создание таблиц """
	base.CreateTables()
	""" Создание списка казначейских файлов """
	files = [f for f in listdir(bankpath) if isfile(os.path.join(bankpath,f)) \
		and f[4]=='0' and ((f[3]=='1' and not f[9:] in TREASURY_INVERSE)  \
		or ((f[2]=='0' or (f[2]=='1' and f[3]=='0')) and f[9:] in \
		TREASURY_INVERSE))]
	try:
		if len(files) == 0:
			raise TreasuryFilesNotFound
	except TreasuryFilesNotFound as e:
		print(e.message)
		sys.exit()
	#print(files)
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
	valid = {"yes":True, "y":True, "n":False, "no":False}
	if default == None:
		prompt = " [y/n] "
	elif default == "yes":
		prompt = " [Y/n] "
	elif default == "no":
		prompt = " [y/N] "
	else:
		raise ValueError("Неправильное значение ответа, по умолчанию '%s'" % \
			default)
	while True:
		sys.stdout.write(question + prompt)
		choice = input().lower()
		if default is not None and choice == '':
			return valid[default]
		elif choice in valid:
			return valid[choice]
		else:
			sys.stdout.write("Правльные ответы 'y/yes' или 'n/no'\n")

if __name__=="__main__":
	# получаем агрументы командной строки
	results = ArgParser.parse_args()
	
	# получаем из конфигурационных файлов 
	# пути 
	# out_directory -- путь для записи файлов
	# bank_directory -- путь к казначейским файлам
	paths = ReadConfig()
	for dir_ in paths:
		try:
			if not os.path.isdir(dir_):
				raise DirectoryNotFound(dir_)
		except DirectoryNotFound as e:
			os.mkdir(dir_)
			print(e.message)
			sys.exit()
	out_directory = paths[1]
	bank_directory = paths[0]

	# подготовка, генерация таблицы в  FillList()
	base = DBProcessing()
	# fn - имя файла для получения даты
	fn = Make(bank_directory)[5:7]
	base.Processing()
	base.MakeEtalon()

	q = MakeTables(base.CrossProcess())
	g=Writer(q.FillList())
	# экземпляр WriteFile
	html_wr = WriteFile()
	# делаем html
	# p -- имя файла с расширением ".html"
	p = html_wr.WriteFile(html_wr.MakeHTML(g.GetList()))
	
	if PrintApprove("Открыть?"):
		webbrowser.open(p, new=2, autoraise=True)
	sys.stdout.write("\nФайл сохранен в '%s'\n" % p)
	if results.xmlfile:
		html_wr.WriteXML(g.a)
		sys.stdout.write("\nФайл XML сохранен в директорию сохранения как {0}.".format(''.join((p.split('.')[0],'xml'))))
	input("\n\nНажмите Enter для выхода.")	
