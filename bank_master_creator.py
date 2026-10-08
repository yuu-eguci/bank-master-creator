"""銀行支店データ (ginkositen.txt) から銀行マスタ・支店マスタの INSERT SQL を作成します。

テーブル定義は README.md を参照してください。
"""

import csv
from datetime import datetime
from pathlib import Path

# 元データ。
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


def create(input_path: Path, output_dir: Path, now: datetime | None = None) -> tuple[Path, Path]:
    """input_path を読み、output_dir に銀行マスタ・支店マスタの INSERT SQL を書き出します。

    不正な行があれば ValueError を送出します。その場合ファイルは作りません。
    """
    bank_lines: list[str] = []
    branch_lines: list[str] = []
    with input_path.open(encoding="cp932", newline="") as f:
        reader = csv.reader(f)
        for row in reader:
            if not row:
                continue
            if len(row) != COLUMNS:
                raise ValueError(f"{reader.line_num} 行目: 項目数が {len(row)} です。")
            flag = row[ROW_FLAG]
            if flag == ROW_BANK:
                bank_lines.append(make_bank_insert_sql(row) + "\n")
            elif flag == ROW_BRANCH:
                branch_lines.append(make_branch_insert_sql(row) + "\n")
            else:
                raise ValueError(f"{reader.line_num} 行目: 種別フラグ {flag!r} は不明です。")

    prefix = (now or datetime.now()).strftime("(%Y%m%d_%H%M%S)")
    output_dir.mkdir(parents=True, exist_ok=True)
    bank_path = output_dir / f"{prefix}銀行マスタINSERT.sql"
    branch_path = output_dir / f"{prefix}支店マスタINSERT.sql"
    for path, lines in ((bank_path, bank_lines), (branch_path, branch_lines)):
        with path.open("w", encoding="utf-8", newline="\n") as f:
            f.writelines(lines)
    return bank_path, branch_path


def main() -> None:
    for path in create(Path(ORIGINAL_DATA), Path("output")):
        print(path)


if __name__ == "__main__":
    main()
