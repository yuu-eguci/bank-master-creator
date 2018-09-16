#!/usr/bin/env python
# coding: utf-8

'''銀行マスタSQL作成ちゃん
http://ykaku.com/ginkokensaku/index.php
ここでDLできる銀行支店データを使って銀行マスタのSQLを作成するちゃんです。
'''

'''銀行マスタ テーブル定義はこれ使ってね。
CREATE TABLE `m_banks` (
  `bank_id` INT NOT NULL AUTO_INCREMENT COMMENT '銀行マスタ、banksのpk。ただし支店マスタとつなげるときはコレじゃなくてbank_codeを使うこと。',
  `bank_code` VARCHAR(45) NULL COMMENT '銀行コード。支店マスタとつなげるときはこれを使う。',
  `bank_name` VARCHAR(100) NULL COMMENT '銀行名。',
  `bank_name_kana` VARCHAR(100) NULL COMMENT '銀行名ｶﾅ',
  `create_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'INSERT日',
  `create_by` INT(11) NULL DEFAULT NULL COMMENT 'INSERT者',
  `update_at` DATETIME NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'UPDATE日',
  `update_by` INT(11) NULL DEFAULT NULL COMMENT 'UPDATE者',
  PRIMARY KEY (`bank_id`));
'''

'''支店マスタ テーブル定義はこれ使ってね。
CREATE TABLE `m_bank_branches` (
  `bank_branch_id` int(11) NOT NULL AUTO_INCREMENT COMMENT '支店マスタ、bank_branchesのpk。ただし銀行マスタとつなげるときはbank_codeを使う。',
  `bank_code` varchar(45) DEFAULT NULL COMMENT '銀行コード。銀行マスタとつなげるときはこれを使う。',
  `branch_code` varchar(45) DEFAULT NULL COMMENT '支店コード。',
  `branch_name` varchar(100) DEFAULT NULL COMMENT '銀行名。',
  `branch_name_kana` varchar(100) DEFAULT NULL COMMENT '銀行名ｶﾅ',
  `create_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'INSERT日',
  `create_by` int(11) DEFAULT NULL COMMENT 'INSERT者',
  `update_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'UPDATE日',
  `update_by` int(11) DEFAULT NULL COMMENT 'UPDATE者',
  PRIMARY KEY (`bank_branch_id`));
'''

import csv
from datetime import datetime

# 元データ。
ORIGINAL_DATA = 'ginkositen.txt'

# カラムのインデックス。
# [0]銀行コード [1]支店コード(親は0) [2]名前ｶﾅ [3]銀行名or支店名 [4]1なら銀行行2なら支店行
BANK_CODE   = 0
BRANCH_CODE = 1
NAME_KANA   = 2
NAME        = 3
ROW_FLAG    = 4
ROW_BANK   = '1'
ROW_BRANCH = '2'


def create():
    '''メインメソッド。'''

    # ファイルを先に作っておきます。
    bank   = datetime.now().strftime("(%Y%m%d_%H%M%S)") + '銀行マスタINSERT.sql'
    branch = datetime.now().strftime("(%Y%m%d_%H%M%S)") + '支店マスタINSERT.sql'
    with open(bank, 'a', encoding='UTF8') as bank_file,\
         open(branch, 'a', encoding='UTF8') as branch_file:

        # 元データを一行ずつ見ていきます。
        with open(ORIGINAL_DATA, 'r', encoding='SJIS') as original_file:
            for row in csv.reader(original_file):

                # 銀行なら銀行ファイルに追加します。
                if row[ROW_FLAG] == ROW_BANK:
                    bank_file.write(make_bank_insert_sql(row) + '\n')

                # 支店なら支店ファイルに追加します。
                if row[ROW_FLAG] == ROW_BRANCH:
                    branch_file.write(make_branch_insert_sql(row) + '\n')


def make_bank_insert_sql(row):
    '''銀行マスタ用INSERT SQLを作成します。'''

    return ' '.join([
        'INSERT INTO m_banks',
            '(bank_code, bank_name, bank_name_kana)',
        'VALUES',
            '(',
                ','.join(
                    map(lambda _: f"'{_}'",
                        [row[BANK_CODE], row[NAME], row[NAME_KANA].rstrip()])),
            ');',
    ])


def make_branch_insert_sql(row):
    '''支店マスタ用INSERT SQLを作成します。'''

    return ' '.join([
        'INSERT INTO m_bank_branches',
            '(bank_code, branch_code, branch_name, branch_name_kana)',
        'VALUES',
            '(',
                ','.join(
                    map(lambda _: f"'{_}'",
                        [row[BANK_CODE], row[BRANCH_CODE], row[NAME], row[NAME_KANA].rstrip()])),
            ');',
    ])


if __name__ == '__main__':
    create()
