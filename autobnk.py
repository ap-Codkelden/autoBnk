""" 
AutoBnk4 main 
version 4.0

  The MIT License (MIT)
  Copyright (c) 2008 - 2013 Renat Nasridinov, <mavladi@gmail.com>
  
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

  
  TODO:
  переписать код так, чтобы не имел значения порядок элементов в конфигах
  """

import argparse
import sqlite3
import xml.etree.ElementTree as ET
import os.path
from os import listdir
from os.path import isfile, join

arg_parser = argparse.ArgumentParser(description='Выборка сумм уплаченных налогов из  \
                                    файлов ГКС (приказ ГКУ/ГНСУ №74/194 от 25.04.2002)', \
                                    epilog='По умолчанию вывод осуществляестя в ASCII-таблицу\
                                    в файле bank.txt каталога, указанного в конфигурационном \
                                    файле (см. документацию)')
arg_parser.add_argument('-html', '--htmlfile', help='в файл HTML', \
                        action='store_true', default=False, dest='htmlfile')



"""
Глобальные списки, константы и прочее
"""
# константа госбюджет
DB = 0
# константа местный бюджет
MB = 1

header = ['Податок','Жовтн','Тернів','Північн','Кр. р-н','ВСЬОГО']

tr_ext = []    # кортеж для расширений файлов казны
raj_dict = {}  # словарь сопоставления казначейств районам


class writer:
	def __init__(self, array):
		self.a = []
		for i in array:
			self.a.append([i[0], 0 if i[1] == None else hrn(i[1]), \
				0 if i[2] == None else hrn(i[2]), \
				hrn((0 if i[1] == None else i[1]) + (0 if i[2] == None else i[2])), \
				0 if i[3] == None else hrn(i[3]), \
				hrn((0 if i[1] == None else i[1]) + (0 if i[2] == None else i[2]) + \
					(0 if i[3] == None else hrn(i[3])))])

		# константа для количества столбцов
		self.COLUMN_COUNT = 6

	def max_len(self):
		# ширина столбцов в порядке следования
		out_width=[]
		for i in range(self.COLUMN_COUNT):
			# пустой временный список для длин строк в столбце
			temp = []
			for line in self.a:
				temp.append(len(line[i]) if i==0 else len(str(line[i])))
			out_width.append(max(temp)+2)
		self.cols_width =  out_width

	def print_divider(self):
		# просто выводит строку разделитель
		divider = ''
		for i in self.cols_width:
			# ширина столбца + 2 символа
			divider = divider + '+' + '-' * (i+2)
		divider = divider + '+'
		print(divider)

	def write_txt(self):
		#txt_file = open(out_directory+'\\bank.txt', 'w')
		#txt_file.write('win')
		#txt_file.close()


		h = ''


	def make_header_cell(self, head_cell_text, space_count):
		try:
			#if space_count
			return (' '* int(space_count)) + head_cell_text + (' ' * int(space_count))  + '|'
		except:
			print('space_count',space_count)





# класс формирования основной таблицы в спсике списков
class make_table:
	def __init__(self, bank):
		self.summary = ET.parse('config\\summary.xml')
		lines=[]
		self.s = self.summary.getroot()
		for e in self.s[0]:
			lines.append(int(e.text))
		# Здесь self.bank - кортеж, уже содержащий суммы по строкам, 
		# и с номером впереди, по которому была сортировка
		self.bank=bank

	def make_var(self, varname):
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

	def fill_list(self):
		# сюда запишем результат
		over_list = []
		""" создание полного массива для дальнейшей обрботки """
		# находим раздел конфига inserts 
		f = self.summary.find('inserts')
		z = enumerate(self.bank)
		# z - нумерованный список, УЖЕ СОДЕРЖАЩИЙ ИТОГИ
		for element in z:
			over_list.append([element[1][1], element[1][2], element[1][3], element[1][4]])
			# нумерация с 0, не забываем
			for ins_item in f:
				if element[0] == int(ins_item[0].text):
					over_list.append(self.make_var(ins_item[1].text))
		# over_list - просто готовый список списков
		# print('over_list', over_list)
		return over_list


class db_processing:
	def __init__(self):
		# база данных в памяти
		self.engine = sqlite3.connect(':memory:')
		#print('>> Engine created.')
		self.db_cur = self.engine.cursor()

	def cross_process(self):
		self.db_cur.execute("INSERT INTO itog \
								SELECT code AS code, raj AS raj, SUM(zn) as zn \
								FROM itog_tmp GROUP BY code, raj")
		self.db_cur.execute("CREATE TABLE bank_sum (code text, raj83 integer, raj87 integer, raj18 integer)")
		self.db_cur.execute("INSERT INTO bank_sum \
								SELECT u.code, \
										sum(s83.zn) as raj83, \
										sum(s87.zn) as raj87, \
										sum(s18.zn) as raj18 \
								FROM etalon u \
									left outer join \
										itog s83 on u.code = s83.code \
										and s83.raj = 83 \
									left outer join \
										itog s87 on u.code = s87.code \
										and s87.raj = 87 \
									left outer join \
										itog s18 on u.code = s18.code \
										and s18.raj = 18 \
								GROUP BY u.code")
		self.db_cur.execute("SELECT e.nompp, e.name, \
									s.raj83, s.raj87, s.raj18 \
									from etalon e \
									left outer join \
									bank_sum s \
									on e.code = s.code\
									ORDER BY nompp")
		return(self.db_cur.fetchall())

	def make_etalon(self):
		etalon_row = ET.parse('config\\etalon.xml')
		table = etalon_row.getroot()
		for row in table:
			self.db_cur.execute('insert into etalon (code, name, nompp) values ("%s", "%s", %d)' % (row[0].text, row[1].text, int(row[2].text)))
			self.engine.commit()

	def create_tables(self, raj_list):
		# создание таблиц
		self.db_cur.execute("CREATE TABLE bank (raj integer, rozd text, rd text, pg text, st text, zn integer, bd integer)")
		self.db_cur.execute("CREATE TABLE itog_tmp (code text, raj integer, zn integer)")
		self.db_cur.execute("CREATE TABLE itog (code text, raj integer, zn integer)")
		self.db_cur.execute("CREATE TABLE etalon (code text, name text, nompp integer)")
		self.engine.commit()

	def fill_table(self, tr_values, raj_code):
		# заполнение таблицы
		for e in tr_values:
			self.db_cur.execute('insert into bank values (%s, %s, "%s", "%s", "%s", %s, %s)' % 
				(raj_dict[raj_code],e[0],e[1][0],e[1][1],e[1][2],e[2],str(e[3])))
			self.engine.commit()

	def list_tables(self):
		# перечисление таблиц
		self.db_cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
		print(self.db_cur.fetchall())

	def retrieve_table(self, table_name):
		# вывод таблицы по имени
		print("Таблица: ", table_name)
		self.db_cur.execute("SELECT * FROM "+table_name)
		for element in self.db_cur.fetchall():
			print(element)
		print('-'*80)

	def sql_construct(self,code,params):
		rozd = ('' if params[0]==None else " AND rozd='"+params[0]+"'")
		bd = params[1] # всегда присутствует
		rd = params[2] # всегда присутствует
		pg = ('' if params[3]==None else " AND pg='"+params[3]+"'")
		coef = params[4] # всегда присутствует
		query = "SELECT raj, SUM(zn) * %f as 'zn' FROM bank WHERE bd=%s AND rd='%s' %s %s GROUP BY raj;" % (float(params[4]), params[1], params[2], pg, rozd)
		self.db_cur.execute(query)
		for e in self.db_cur.fetchall():
			# район, код, сумма
			self.db_cur.execute("insert into itog_tmp values (%s, %s, %d)" % (code, e[0], e[1]))


	def processing(self):
		tax_list = ET.parse('config\\tax.xml')
		tax = tax_list.getroot()
		for row in tax:
			for query in row:
				params = []
				# переменная c - от "компонент"
				# <rozd> <bd> <rd> <pg> <coef>
				for c in query:
					params.append(c if c == None else c.text) 
				self.sql_construct(row.attrib['code'],params)

def parse_file(tr_dir, tr_f):
	# получаем имя файла, соединяя папку и имя
	tr_file_name=os.path.join(tr_dir, tr_f)
	# определяем тип бюджета
	if tr_f[2]=='0':
		bd_type=DB
	else:
		bd_type=MB
	tr_val = []
	with open(tr_file_name, encoding='cp866') as tr_file:
		tr_lines = tr_file.readlines()
		tr_file.close()
	for i in range(len(tr_lines)):
		e = tr_lines[i].split()
		if len(e)>4 and e[1].isdigit():
			del(e[1])
			del(e[-1])
			e[1]=[e[1][0:4],e[1][4:6],e[1][6:]]
			e[-1]=float(e[-1].replace("'",""))*100
			e.append(bd_type)
			tr_val.append(e)
	base.fill_table(tr_val, tr_f[-3:])

def config():
	if os.path.exists('config\\config.xml'):
		treasury_conf = ET.parse('config\\config.xml')
		tr = treasury_conf.getroot()
		bank_dir=tr[0][0].text
		if not os.path.exists(tr[0][1].text):
			os.makedirs(tr[0][1].text)
			#print(tr[0][1].text)
		for tr_code in tr.iter('code'):
			tr_ext.append(tr_code.text)
		for item in tr.iter('file'):
			raj_dict[item[1].text]=item[2].text
		return bank_dir

def get_outdir_name():
	treasury_conf = ET.parse('config\\config.xml')
	tr = treasury_conf.getroot()
	return tr[0][1].text

def make(bankpath):
	base.create_tables(tr_ext)
	# Создание списков файлов 
	for i in [ f for f in listdir(bankpath) if isfile(os.path.join(bankpath,f)) ]:
		parse_file(bankpath,i)

def hrn(num):
	return round(num/100)



if __name__=="__main__":
	results = arg_parser.parse_args()
	print(results)
	
	# подготовка, генерация таблицы в 
	# fill_list()
	base = db_processing()
	make(config())
	base.processing()
	base.make_etalon()
	out_directory = get_outdir_name()
	print('out_directory',out_directory)
	
	q = make_table(base.cross_process())
	g=writer(q.fill_list())
	g.max_len()
	g.write_txt()