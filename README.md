BankMasterCreator
===

[http://ykaku.com/ginkokensaku/index.php](http://ykaku.com/ginkokensaku/index.php) でダウンロードできる銀行支店データ (`ginkositen.txt`) から、銀行マスタ・支店マスタの INSERT SQL を作成します。

- Docker: 対応!
- Python: 3.14!
- Linter: ruff!
- Test: pytest!

## パッと実行してみたい

```bash
docker compose run --rm --build app
```

`output/` に次の 2 ファイルができます。

- `(YYYYmmdd_HHMMSS)銀行マスタINSERT.sql`: `m_banks` への INSERT 文です。
- `(YYYYmmdd_HHMMSS)支店マスタINSERT.sql`: `m_bank_branches` への INSERT 文です。

文字コードは UTF-8 で、1 行に 1 つの INSERT 文を出力します。同名ファイルがあれば上書きします。Docker 実行時、ファイル名の日時は日本時間です (環境変数 `TZ` で変更できます)。

## Usage

- データの差し替え: `ginkositen.txt` (Shift_JIS/CP932) を上書きして再実行します。再ビルドは不要です。
- Linux でユーザ ID が 1000 以外の場合: `docker compose run --rm --build --user "$(id -u):$(id -g)" app`
- テストと lint: `docker compose run --rm --build test`
- Docker なし (Python 3.14): `python bank_master_creator.py`
- 文字列は MySQL 向けにエスケープします (`\`, `'`, NUL, 改行, CR, Ctrl-Z)。sql_mode の `NO_BACKSLASH_ESCAPES` には対応していません。
- 不正な行 (項目数が 5 でない、種別フラグが 1/2 以外) があると、行番号を示してエラーで止まります。

## DB definition

銀行マスタ

```sql
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
```

支店マスタ

```sql
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
```
