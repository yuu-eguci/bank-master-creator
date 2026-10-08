"""銀行支店データ (ginkositen.txt) から銀行マスタ・支店マスタの INSERT SQL を作成します。

テーブル定義は README.md を参照してください。
"""

import argparse
import csv
import sys
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import NoReturn

# 元データ (既定値)。
ORIGINAL_DATA = "ginkositen.txt"

# カラムのインデックス。
# [0]銀行コード [1]支店コード [2]名前ｶﾅ [3]銀行名or支店名 [4]1なら銀行行、2なら支店行
BANK_CODE = 0
BRANCH_CODE = 1
NAME_KANA = 2
NAME = 3
ROW_FLAG = 4
COLUMNS = 5
ROW_BANK = "1"
ROW_BRANCH = "2"

# 出力ファイルの先頭行です。
HEADER = "SET NAMES utf8mb4;\n"

# mysql_real_escape_string に倣ってエスケープします (`"` は対象外です)。
_ESCAPE_TABLE = str.maketrans(
    {
        "\\": "\\\\",
        "'": "\\'",
        "\x00": "\\0",
        "\n": "\\n",
        "\r": "\\r",
        "\x1a": "\\Z",
    }
)


def escape(value: str) -> str:
    """MySQL の文字列リテラル用にエスケープします。"""
    return value.translate(_ESCAPE_TABLE)


def quote(value: str) -> str:
    """エスケープしてシングルクォートで囲みます。"""
    return f"'{escape(value)}'"


def _insert_sql(table: str, columns: str, *values: str) -> str:
    # 値はすべて quote() でエスケープ済みです。
    quoted = ", ".join(quote(v) for v in values)
    return f"INSERT INTO {table} ({columns}) VALUES ({quoted});"  # noqa: S608


def make_bank_insert_sql(row: list[str]) -> str:
    """銀行マスタ用 INSERT SQL を作成します。"""
    return _insert_sql(
        "m_banks",
        "bank_code, bank_name, bank_name_kana",
        row[BANK_CODE],
        row[NAME],
        row[NAME_KANA].rstrip(" "),
    )


def make_branch_insert_sql(row: list[str]) -> str:
    """支店マスタ用 INSERT SQL を作成します。"""
    return _insert_sql(
        "m_bank_branches",
        "bank_code, branch_code, branch_name, branch_name_kana",
        row[BANK_CODE],
        row[BRANCH_CODE],
        row[NAME],
        row[NAME_KANA].rstrip(" "),
    )


def _decoded_lines(input_path: Path) -> Iterator[str]:
    # 1 行ずつ cp932 でデコードし、失敗した行の番号を示します。
    with input_path.open("rb") as f:
        for line_num, raw in enumerate(f, 1):
            try:
                yield raw.decode("cp932")
            except UnicodeDecodeError:
                msg = f"{line_num} 行目: cp932 として読めません (UTF-8 で保存していませんか?)"
                raise ValueError(msg) from None


def read_rows(input_path: Path) -> tuple[list[list[str]], list[list[str]]]:
    """input_path を読み、(銀行行, 支店行) を返します。

    不正な行があれば ValueError を送出します。
    """
    banks: list[list[str]] = []
    branches: list[list[str]] = []
    reader = csv.reader(_decoded_lines(input_path))
    for row in reader:
        if not row:
            continue
        if len(row) != COLUMNS:
            raise ValueError(f"{reader.line_num} 行目: 項目数が {len(row)} です。")
        flag = row[ROW_FLAG]
        if flag == ROW_BANK:
            banks.append(row)
        elif flag == ROW_BRANCH:
            branches.append(row)
        else:
            raise ValueError(f"{reader.line_num} 行目: 種別フラグ {flag!r} は不明です。")
    return banks, branches


def write_sql(
    banks: list[list[str]],
    branches: list[list[str]],
    output_dir: Path,
    now: datetime | None = None,
) -> tuple[Path, Path]:
    """output_dir に銀行マスタ・支店マスタの INSERT SQL を書き出し、2 つのパスを返します。"""
    prefix = (now or datetime.now()).strftime("(%Y%m%d_%H%M%S)")
    output_dir.mkdir(parents=True, exist_ok=True)
    bank_path = output_dir / f"{prefix}銀行マスタINSERT.sql"
    branch_path = output_dir / f"{prefix}支店マスタINSERT.sql"
    bank_lines = [make_bank_insert_sql(row) + "\n" for row in banks]
    branch_lines = [make_branch_insert_sql(row) + "\n" for row in branches]
    for path, lines in ((bank_path, bank_lines), (branch_path, branch_lines)):
        with path.open("w", encoding="utf-8", newline="\n") as f:
            f.write(HEADER)
            f.writelines(lines)
    return bank_path, branch_path


def create(input_path: Path, output_dir: Path, now: datetime | None = None) -> tuple[Path, Path]:
    """input_path を読み、output_dir に銀行マスタ・支店マスタの INSERT SQL を書き出します。

    不正な行があれば ValueError を送出します。その場合ファイルは作りません。
    """
    banks, branches = read_rows(input_path)
    return write_sql(banks, branches, output_dir, now)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--input", type=Path, default=Path(ORIGINAL_DATA), help="入力ファイル (cp932)"
    )
    parser.add_argument(
        "--output-dir", type=Path, default=Path("output"), help="出力先ディレクトリ"
    )
    return parser.parse_args(argv)


def _fail(message: str) -> NoReturn:
    print(f"エラー: {message}", file=sys.stderr)
    sys.exit(1)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    try:
        banks, branches = read_rows(args.input)
    except FileNotFoundError:
        _fail(f"{args.input} が見つかりません。")
    except IsADirectoryError:
        _fail(
            f"{args.input} はディレクトリです。"
            "(Docker で入力ファイルがないまま実行すると空のディレクトリができます。"
            "削除してから入力ファイルを置いてください。)"
        )
    except ValueError as e:
        _fail(str(e))
    for path in write_sql(banks, branches, args.output_dir):
        print(path)
    print(f"銀行 {len(banks)} 件、支店 {len(branches)} 件", file=sys.stderr)


if __name__ == "__main__":
    main()
