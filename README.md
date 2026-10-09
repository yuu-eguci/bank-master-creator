BankMasterCreator
===

[銀行支店データ](http://ykaku.com/ginkokensaku/index.php) から、銀行マスタ・支店マスタの INSERT SQL を作るやつ。

- Docker: 対応!
- Python: 3.14!
- Linter: ruff!
- Test: pytest!

## パッと実行してみたい

```bash
docker compose run --rm --build app
```

`output/` に銀行用・支店用の SQL ができる。文字コードは UTF-8。

- `(YYYYmmdd_HHMMSS)銀行マスタINSERT.sql` --> `m_banks` 用
- `(YYYYmmdd_HHMMSS)支店マスタINSERT.sql` --> `m_bank_branches` 用

同名ファイルは上書き。ファイル名の日時は日本時間。

同梱データは 2018 年ごろのもの。実際に使うなら `ginkositen.txt` を最新版に差し替えてね。
入力は Shift_JIS / CP932。データの差し替えだけなら再ビルド不要。

## SQL を作る前に

```bash
docker compose run --rm app --check
```

件数・コードの重複・銀行が見つからない支店をチェックする。SQL はまだ作らない。

## 銀行や支店を探す

```bash
docker compose run --rm app --search みずほ
docker compose run --rm app --search トウキョウ --loose-kana
docker compose run --rm app --list 0001
```

検索結果はタブ区切りで表示。ここでも SQL は作らない。
元データのカナは「東京」が `ﾄｳｷﾖｳ` だったりするので、ふつうの読み方で探すなら `--loose-kana` が便利。

## Options

`docker compose run --rm app --help` でも見られるよ。

| オプション | なにする? |
| --- | --- |
| `--input PATH` | 入力ファイル。既定は `ginkositen.txt`。`-` なら標準入力。 |
| `--output-dir PATH` | 出力先。既定は `output/`。 |
| `--bank-code CODES` | 指定した銀行とその支店だけ。例: `0001,0005`。 |
| `--no-timestamp` | ファイル名から日時を外す。 |
| `--rows-per-insert N` | INSERT を N 行ずつまとめる。既定は 1。 |
| `--stdout` | SQL をファイルじゃなく標準出力へ。 |
| `--delete-before-insert` | 既存データを DELETE してから入れ直す SQL を作る。 |
| `--check` | 件数とデータの整合性チェック。 |
| `--diff-from OLD` | 古いデータとの差分を見る。 |
| `--search TEXT` | 銀行名・カナで部分一致検索。 |
| `--loose-kana` | 検索時にひらがな・小さいカナ・長音の違いも無視。 |
| `--list CODE` | その銀行と支店を一覧表示。 |
| `--version` | バージョンを見る。 |

`--check`・`--diff-from`・`--search`・`--list`・`--delete-before-insert` はどれか 1 つ。
`--stdout` と組み合わせられるのは、この中では `--delete-before-insert` だけ。
`--loose-kana` は `--search` とセット。

## DB に流し込むなら

先に [テーブル定義](docs/database.md) を用意してね。文字コードは utf8mb4。

```bash
docker compose build app
docker compose run --rm app --stdout --rows-per-insert 500 | mysql --default-character-set=utf8mb4 -u user -p db
```

銀行・支店の SQL をまとめて DB に流す。ビルドは先に済ませるとログが混ざらない。

入れ直すなら `--delete-before-insert` を追加。
これは「既存データを消して入れ直す」オプションなので、対象 DB はよく確認してね。
MySQL の `NO_BACKSLASH_ESCAPES` は非対応。

## 開発するとき

```bash
docker compose run --rm --build test
```

テスト・lint・型チェックをまとめて実行。

Docker なしなら Python 3.11 以上で `python bank_master_creator.py`。
Linux で出力の権限に困ったら `--user "$(id -u):$(id -g)"` を `app` の前に追加してね。

入力・出力の細かい仕様は [データ形式](docs/format.md)、DB 定義と確認クエリは [DB の資料](docs/database.md) に置いてあるよ。
