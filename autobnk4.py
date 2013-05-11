""" 
AutoBnk4 main 
version 4.0

  The MIT License (MIT)
  Copyright (c) 2013 Renat Nasridinov, <mavladi@gmail.com>
  
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
  THE SOFTWARE. """

import sqlite3
import xml.etree.ElementTree as ET
import os.path
from os import listdir
from os.path import isfile, join


"""
Глобальные списки, константы и прочее
"""
# константа госбюджет
DB = 0
# константа местный бюджет
MB = 1

tr_ext = []    # кортеж для расширений файлов казны
raj_dict = {}  # словарь сопоставления казначейств районам

class db_processing:
	def __init__(self):
		# база данных в памяти
		self.engine = sqlite3.connect(':memory:')
		print('>> Engine created.')
		self.db_cur = self.engine.cursor()

	def cross_process(self):
		self.db_cur.execute("ALTER TABLE etalon RENAME TO temp_names")
		self.db_cur.execute("CREATE TABLE bank_sum (name text, raj83 integer, raj87 integer, raj18 integer)")
		self.db_cur.execute("INSERT INTO bank_sum SELECT u.name, s83.zn as raj83, s87.zn as raj87, s18.zn as raj18 from temp_names u left outer join itog s83 on u.code = s83.code and s83.raj = 83 left outer join itog s87 on u.code = s87.code and s87.raj = 87 left outer join itog s18 on u.code = s18.code and s18.raj = 18")

	def make_etalon(self):
		etalon_row = ET.parse('config\\etalon.xml')
		table = etalon_row.getroot()
		for row in table:
			#print('insert into etalon (code, name) values ("%s", "%s")' % (row[0].text, row[1].text))
			self.db_cur.execute('insert into etalon (code, name) values ("%s", "%s")' % (row[0].text, row[1].text))
			self.engine.commit()

	def create_tables(self, raj_list):
		# создание таблиц
		self.db_cur.execute("CREATE TABLE bank (raj integer, rozd text, rd text, pg text, st text, zn integer, bd integer)")
		self.engine.commit()
		self.db_cur.execute("CREATE TABLE itog (code text, raj integer, zn integer)")
		self.engine.commit()
		self.db_cur.execute("CREATE TABLE etalon (code text, name text)")
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
		query = "SELECT raj, SUM(zn) * %s as 'zn' FROM bank WHERE bd=%s AND rd='%s' %s %s GROUP BY raj;" % (params[4], params[1], params[2], pg, rozd)
		# print(query)
		self.db_cur.execute(query)
		# self.db_cur.fetchall())
		for e in self.db_cur.fetchall():
			# район, код, сумма
			self.db_cur.execute("insert into itog values (%s, %s, %d)" % (code, e[0], e[1]))


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
		for tr_code in tr.iter('code'):
			tr_ext.append(tr_code.text)
		for item in tr.iter('file'):
			raj_dict[item[1].text]=item[2].text
		return bank_dir

def make(bankpath):
	base.create_tables(tr_ext)
	# Создание списков файлов 
	for i in [ f for f in listdir(bank_dir) if isfile(os.path.join(bank_dir,f)) ]:
		parse_file(bank_dir,i)

if __name__=="__main__":
	base = db_processing()
	bank_dir=config()
	make(bank_dir)
	base.processing()
	base.make_etalon()
	base.cross_process()
	base.retrieve_table('bank')
	base.retrieve_table('itog')
	base.retrieve_table('bank_sum')
	base.retrieve_table('temp_names')