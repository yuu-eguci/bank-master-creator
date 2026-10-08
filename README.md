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

文字コードは UTF-8 です。先頭行は `SET NAMES utf8mb4;` で、以降は 1 行に 1 つの INSERT 文です (`--rows-per-insert` を使った場合を除きます)。同名ファイルがあれば上書きします。Docker 実行時、ファイル名の日時は日本時間です (環境変数 `TZ` で変更できます)。

## Usage

- データの差し替え: `ginkositen.txt` (Shift_JIS/CP932) を上書きして再実行します。再ビルドは不要です。
- Linux でユーザ ID が 1000 以外の場合: `docker compose run --rm --build --user "$(id -u):$(id -g)" app`
- テストと lint と型チェック (mypy): `docker compose run --rm --build test`
- Docker なし (Python 3.11 以上。CI では 3.11 と 3.14 で確認しています): `python bank_master_creator.py`
- 終了時に `銀行 1338 件、支店 31048 件` のような件数を標準エラー出力に表示します。
- 文字列は MySQL 向けにエスケープします (`\`, `'`, NUL, 改行, CR, Ctrl-Z)。sql_mode の `NO_BACKSLASH_ESCAPES` には対応していません。
- 不正な行 (項目数が 5 でない、種別フラグが 1/2 以外、引用符が閉じていない) があると、行番号を示してエラーで止まります (引用符のエラーは検出した行なので目安です)。入力ファイルがない、cp932 として読めない、出力先に書き出せない場合も `エラー:` で始まる 1 行を表示して終了コード 1 で止まります。

## Options

`docker compose run --rm app --check` のように引数をそのまま渡せます。ただしコンテナから見えるのは `ginkositen.txt` と `output/` だけなので、他のパスを使う場合は Docker なしで実行してください。

| オプション | 説明 |
| --- | --- |
| `--input PATH` | 入力ファイルです (既定: `ginkositen.txt`)。 |
| `--output-dir PATH` | 出力先ディレクトリです (既定: `output/`)。 |
| `--no-timestamp` | ファイル名を `銀行マスタINSERT.sql`・`支店マスタINSERT.sql` に固定します。スクリプトから扱いやすく、前回の出力と diff しやすくなります。 |
| `--stdout` | ファイルを作らず、銀行マスタ・支店マスタの SQL を 1 つにまとめて標準出力に書きます (`SET NAMES` は先頭に 1 回、`--delete-before-insert` では両テーブルを 1 つのトランザクションで入れ直します)。例: `docker compose run --rm app --stdout --delete-before-insert \| mysql -u user -p db` (`--build` を付けるとビルドのログが混ざるので、先にビルドしておきます)。 |
| `--rows-per-insert N` | 1 つの INSERT 文に N 行をまとめます (既定: 1)。`VALUES` の各行は改行で区切ります。手元の MySQL 8.4 では支店 31048 件の読み込みが、既定で約 24 秒、`--delete-before-insert` (トランザクション) で約 1.6 秒、`--rows-per-insert 500` で約 0.3 秒でした。 |
| `--delete-before-insert` | 入れ直し (洗い替え) 用です。各ファイルの INSERT の前に `START TRANSACTION;` と `DELETE FROM テーブル名;` が入り、末尾に `COMMIT;` が付きます。途中でエラーになると COMMIT されないので既存データは残ります。`AUTO_INCREMENT` の ID は振り直されません (結合には `bank_code` を使う前提です)。 |
| `--check` | ファイルを作らず、件数と検査結果を表示します。銀行コードの重複、銀行+支店コードの重複、銀行行のない支店は該当コード (10 件まで) も表示し、あれば終了コード 1 です。支店のない銀行、ｶﾅが 15 文字の行 (元データの上限で切れている可能性) は件数のみです。 |
| `--diff-from OLD` | ファイルを作らず、OLD (古い `ginkositen.txt`) から `--input` のファイルへの銀行・支店の追加 (`+`)・削除 (`-`)・名称変更 (`~`) を表示します。再ダウンロードしたデータを入れ直す前の確認に使います。コードが重複しているデータでは後の行を使うので、先に `--check` で確認してください。 |

`--delete-before-insert`、`--check`、`--diff-from` は同時に指定できません。`--stdout` も `--check`、`--diff-from` とは同時に指定できません。オプションの指定が不正な場合は使い方を表示して終了コード 2 で止まります。

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
