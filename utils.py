#!/usr/bin/env python 
# -*- coding: utf-8 -*-

"""
autobnk_utils
Copyright (c) 2008 - 2015 Renat Nasridinov, <mavladi@gmail.com>

Модуль вспомогательных утилит для autobnk.py
Распространяется на тех же условиях, что и autobnk.py
"""

class dbfToList:
    """Класс считывания таблицы из файла DBF в список. 
    Возвращает список, в который вложены списки, являющиеся строками исходной 
    таблицы.
    Примечание. В файлах из ГКСУ дескриптор полей начинается с 32-го байта, и 
    описание поля в дескрипторе полей занимает тоже 32 байта (позиции байтов 
    для считывания соответственно количество записей, количество байт в 
    заголовке, и количество байт в записи. 
    """
    def __init__(self, dbfname):
        """Параметры:
            dbfname - имя файла DBF
        """
        self.dbf = dbfname
        self.bytelist = (4,2,2)
        self._list = []
        self.dfile = open(self.dbf,'rb')
        self._readbytes()

        
    def _readbytes(self):
        """переменная _list будет содержать:
        [<количество записей>,<число байт в заголовке файла>,<число байт поля>]
        В случае с казначейской таблицей это [69, 257, 56]
        """
        # с 4й позиции начинается число записей
        self.dfile.seek(4)
        for i in self.bytelist:
            self._list.append(self.dfile.read(i))
        for i in range(len(self._list)):
            self._list[i]=int.from_bytes(self._list[i],byteorder='little')
        
    def _get_fields(self):
        self.dfile.seek(32)
        _fielddesc = []
        for i in range(int(self._list[1]-2-32)):
            if i % 32 == 0:
                _p = self.dfile.read(32)
                field_desc = _p
                _fielddesc.append(tuple([field_desc[:4].decode().split('\x00')[0],\
                    field_desc[11:12].decode(),int.from_bytes(field_desc[16:17],\
                    byteorder='little')]))
        return (_fielddesc)


    def read_table(self):
        """Непосредственно парсит таблицу и возвращает переменную _rowlist, 
        которая является списком списков вида
        ['2', ['1905', '03', '00'], 0, 0]
        """
        # получаем имена и длины и типы полей:
        # _th = self._get_fields()
        rowlist = []
        self.dfile.seek(self._list[1])
        for i in range (self._list[0]):
            g = self.dfile.read(56).decode()[1:]
            # сильное колдунство -- y нас изначально известны нужные поля:
            rowlist.append([g[11:12],[g[15:23][:4],g[15:23][4:6], \
                g[15:23][6:8]], int(g[23:40]), self.dbf.split('\\')[-1][2]])
        return rowlist


