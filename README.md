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

文字コードは UTF-8 です。先頭行は `SET NAMES utf8mb4;` で、以降は 1 行に 1 つの INSERT 文です。同名ファイルがあれば上書きします。Docker 実行時、ファイル名の日時は日本時間です (環境変数 `TZ` で変更できます)。

## Usage

- データの差し替え: `ginkositen.txt` (Shift_JIS/CP932) を上書きして再実行します。再ビルドは不要です。
- Linux でユーザ ID が 1000 以外の場合: `docker compose run --rm --build --user "$(id -u):$(id -g)" app`
- テストと lint と型チェック (mypy): `docker compose run --rm --build test`
- Docker なし (Python 3.14): `python bank_master_creator.py`
- 入力・出力先の変更: `--input PATH` と `--output-dir PATH` で指定します (既定は `ginkositen.txt` と `output/`)。Docker では `docker compose run --rm app --help` のように引数をそのまま渡せます。
- 終了時に `銀行 1338 件、支店 31048 件` のような件数を標準エラー出力に表示します。
- 書き出さずに確認: `--check` を付けると、ファイルを作らずに件数と検査結果を表示します。検査項目は銀行コードの重複、銀行+支店コードの重複、銀行行のない支店 (以上は該当コードも表示し、あれば終了コード 1)、支店のない銀行、ｶﾅが 15 文字の行 (元データの上限で切れている可能性。件数のみ) です。
- 入れ直し (洗い替え): `--delete-before-insert` を付けると、各ファイルの INSERT の前に `START TRANSACTION;` と `DELETE FROM テーブル名;` が入り、末尾に `COMMIT;` が付きます。データを再ダウンロードして入れ直すときに使います。途中でエラーになると COMMIT されないので既存データは残ります。`AUTO_INCREMENT` の ID は振り直されません (結合には `bank_code` を使う前提です)。
- 文字列は MySQL 向けにエスケープします (`\`, `'`, NUL, 改行, CR, Ctrl-Z)。sql_mode の `NO_BACKSLASH_ESCAPES` には対応していません。
- 不正な行 (項目数が 5 でない、種別フラグが 1/2 以外) があると、行番号を示してエラーで止まります。入力ファイルがない、または cp932 として読めない場合も `エラー:` で始まる 1 行を表示して終了コード 1 で止まります。

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
  `branch_name` varchar(100) DEFAULT NULL COMMENT '支店名。',
  `branch_name_kana` varchar(100) DEFAULT NULL COMMENT '支店名ｶﾅ',
  `create_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'INSERT日',
  `create_by` int(11) DEFAULT NULL COMMENT 'INSERT者',
  `update_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'UPDATE日',
  `update_by` int(11) DEFAULT NULL COMMENT 'UPDATE者',
  PRIMARY KEY (`bank_branch_id`));
```
