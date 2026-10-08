"""銀行支店データ (ginkositen.txt) から銀行マスタ・支店マスタの INSERT SQL を作成します。

テーブル定義は README.md を参照してください。
"""

import argparse
import csv
import io
import sys
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import NoReturn, TextIO

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


BANK_TABLE = ("m_banks", "bank_code, bank_name, bank_name_kana")
BRANCH_TABLE = ("m_bank_branches", "bank_code, branch_code, branch_name, branch_name_kana")


def _bank_values(row: list[str]) -> str:
    return ", ".join(quote(v) for v in (row[BANK_CODE], row[NAME], row[NAME_KANA].rstrip(" ")))


def _branch_values(row: list[str]) -> str:
    values = (row[BANK_CODE], row[BRANCH_CODE], row[NAME], row[NAME_KANA].rstrip(" "))
    return ", ".join(quote(v) for v in values)


def _insert_sql(table: str, columns: str, values_list: list[str]) -> str:
    # 値はすべて quote() でエスケープ済みです。
    if len(values_list) == 1:
        return f"INSERT INTO {table} ({columns}) VALUES ({values_list[0]});"  # noqa: S608
    body = ",\n".join(f"({values})" for values in values_list)
    return f"INSERT INTO {table} ({columns}) VALUES\n{body};"


def make_insert_sqls(
    table: str, columns: str, values_list: list[str], rows_per_insert: int
) -> list[str]:
    """rows_per_insert 行ずつまとめた INSERT 文のリストを作ります。"""
    return [
        _insert_sql(table, columns, values_list[i : i + rows_per_insert])
        for i in range(0, len(values_list), rows_per_insert)
    ]


def make_bank_insert_sql(row: list[str]) -> str:
    """銀行マスタ用 INSERT SQL を作成します。"""
    return _insert_sql(*BANK_TABLE, [_bank_values(row)])


def make_branch_insert_sql(row: list[str]) -> str:
    """支店マスタ用 INSERT SQL を作成します。"""
    return _insert_sql(*BRANCH_TABLE, [_branch_values(row)])


def _decoded_lines(input_path: Path) -> Iterator[str]:
    # 1 行ずつ cp932 でデコードし、失敗した行の番号を示します。
    # 改行は CRLF/LF/CR のどれでも構いません。
    for line_num, raw in enumerate(input_path.read_bytes().splitlines(keepends=True), 1):
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
    reader = csv.reader(_decoded_lines(input_path), strict=True)
    try:
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
    except csv.Error as e:
        raise ValueError(f"{reader.line_num} 行目: CSV として読めません ({e})") from None
    return banks, branches


def write_sql(
    banks: list[list[str]],
    branches: list[list[str]],
    output_dir: Path,
    now: datetime | None = None,
    *,
    delete_before_insert: bool = False,
    timestamp: bool = True,
    rows_per_insert: int = 1,
) -> tuple[Path, Path]:
    """output_dir に銀行マスタ・支店マスタの INSERT SQL を書き出し、2 つのパスを返します。

    delete_before_insert が真なら、トランザクション内でテーブルを空にしてから INSERT します。
    timestamp が偽なら、ファイル名の先頭に日時を付けません。
    rows_per_insert は 1 つの INSERT 文にまとめる行数です。
    """
    prefix = (now or datetime.now().astimezone()).strftime("(%Y%m%d_%H%M%S)") if timestamp else ""
    output_dir.mkdir(parents=True, exist_ok=True)
    bank_path = output_dir / f"{prefix}銀行マスタINSERT.sql"
    branch_path = output_dir / f"{prefix}支店マスタINSERT.sql"
    targets = (
        (bank_path, BANK_TABLE, [_bank_values(row) for row in banks]),
        (branch_path, BRANCH_TABLE, [_branch_values(row) for row in branches]),
    )
    for path, table, values_list in targets:
        with path.open("w", encoding="utf-8", newline="\n") as f:
            f.write(HEADER)
            if delete_before_insert:
                f.write("START TRANSACTION;\n")
            _write_table(f, table, values_list, delete_before_insert, rows_per_insert)
            if delete_before_insert:
                f.write("COMMIT;\n")
    return bank_path, branch_path


def write_sql_stream(
    banks: list[list[str]],
    branches: list[list[str]],
    out: TextIO,
    *,
    delete_before_insert: bool = False,
    rows_per_insert: int = 1,
) -> None:
    """銀行マスタ・支店マスタの SQL を 1 つのストリームにまとめて書きます。

    delete_before_insert が真なら、両テーブルを 1 つのトランザクションで入れ直します。
    """
    out.write(HEADER)
    if delete_before_insert:
        out.write("START TRANSACTION;\n")
    _write_table(
        out, BANK_TABLE, [_bank_values(row) for row in banks], delete_before_insert, rows_per_insert
    )
    _write_table(
        out,
        BRANCH_TABLE,
        [_branch_values(row) for row in branches],
        delete_before_insert,
        rows_per_insert,
    )
    if delete_before_insert:
        out.write("COMMIT;\n")


def _write_table(
    out: TextIO,
    table: tuple[str, str],
    values_list: list[str],
    delete_before_insert: bool,
    rows_per_insert: int,
) -> None:
    name, columns = table
    if delete_before_insert:
        out.write(f"DELETE FROM {name};\n")  # noqa: S608 (name は定数です)
    for sql in make_insert_sqls(name, columns, values_list, rows_per_insert):
        out.write(sql + "\n")


def create(
    input_path: Path,
    output_dir: Path,
    now: datetime | None = None,
    *,
    delete_before_insert: bool = False,
    timestamp: bool = True,
) -> tuple[Path, Path]:
    """input_path を読み、output_dir に銀行マスタ・支店マスタの INSERT SQL を書き出します。

    不正な行があれば ValueError を送出します。その場合ファイルは作りません。
    """
    banks, branches = read_rows(input_path)
    return write_sql(
        banks,
        branches,
        output_dir,
        now,
        delete_before_insert=delete_before_insert,
        timestamp=timestamp,
    )


# 元データのｶﾅは 15 文字で切られているため、15 文字ちょうどなら切り詰めの可能性があります。
KANA_WIDTH = 15
# --check で表示するコードの最大数です。
MAX_CODES_SHOWN = 10


@dataclass
class Report:
    """--check の検査結果です。duplicate_*/orphan_branches があれば問題ありとみなします。"""

    banks: int
    branches: int
    duplicate_bank_codes: list[str]
    duplicate_branch_codes: list[str]
    orphan_branches: list[str]
    banks_without_branches: int
    truncated_kana: int

    @property
    def problems(self) -> bool:
        return bool(
            self.duplicate_bank_codes or self.duplicate_branch_codes or self.orphan_branches
        )

    def lines(self) -> list[str]:
        def with_codes(label: str, codes: list[str]) -> str:
            shown = ", ".join(codes[:MAX_CODES_SHOWN])
            rest = len(codes) - MAX_CODES_SHOWN
            if rest > 0:
                shown += f" ほか {rest} 件"
            return f"{label}: {len(codes)}" + (f" ({shown})" if codes else "")

        return [
            f"銀行: {self.banks} 件、支店: {self.branches} 件",
            with_codes("銀行コード重複", self.duplicate_bank_codes),
            with_codes("銀行+支店コード重複", self.duplicate_branch_codes),
            with_codes("銀行行のない支店", self.orphan_branches),
            f"支店のない銀行: {self.banks_without_branches}",
            f"ｶﾅが {KANA_WIDTH} 文字 (切り詰めの可能性): {self.truncated_kana}",
        ]


def _duplicates(keys: list[str]) -> list[str]:
    return [key for key, count in Counter(keys).items() if count > 1]


def check(banks: list[list[str]], branches: list[list[str]]) -> Report:
    """銀行行・支店行の整合性を検査します。"""
    bank_codes = [row[BANK_CODE] for row in banks]
    branch_keys = [f"{row[BANK_CODE]}-{row[BRANCH_CODE]}" for row in branches]
    bank_code_set = set(bank_codes)
    branch_bank_codes = {row[BANK_CODE] for row in branches}
    return Report(
        banks=len(banks),
        branches=len(branches),
        duplicate_bank_codes=_duplicates(bank_codes),
        duplicate_branch_codes=_duplicates(branch_keys),
        orphan_branches=[
            key
            for row, key in zip(branches, branch_keys, strict=True)
            if row[BANK_CODE] not in bank_code_set
        ],
        banks_without_branches=sum(code not in branch_bank_codes for code in bank_codes),
        truncated_kana=sum(
            len(row[NAME_KANA].rstrip(" ")) >= KANA_WIDTH for row in banks + branches
        ),
    )


@dataclass
class Diff:
    """--diff-from の比較結果です。"""

    added: list[list[str]]
    removed: list[list[str]]
    changed: list[tuple[list[str], list[str]]]


def _row_key(row: list[str]) -> tuple[str, str]:
    return row[BANK_CODE], row[BRANCH_CODE]


def _row_value(row: list[str]) -> tuple[str, str]:
    return row[NAME], row[NAME_KANA].rstrip(" ")


def diff_rows(old: list[list[str]], new: list[list[str]]) -> Diff:
    """銀行コード・支店コードをキーに、old から new への追加・削除・名称変更を求めます。"""
    old_by_key = {_row_key(row): row for row in old}
    new_by_key = {_row_key(row): row for row in new}
    return Diff(
        added=[row for key, row in new_by_key.items() if key not in old_by_key],
        removed=[row for key, row in old_by_key.items() if key not in new_by_key],
        changed=[
            (row, new_by_key[key])
            for key, row in old_by_key.items()
            if key in new_by_key and _row_value(row) != _row_value(new_by_key[key])
        ],
    )


def _code(row: list[str]) -> str:
    return row[BANK_CODE] if row[ROW_FLAG] == ROW_BANK else f"{row[BANK_CODE]}-{row[BRANCH_CODE]}"


def _name(row: list[str]) -> str:
    name, kana = _row_value(row)
    return f"{name} ({kana})"


def diff_lines(banks: Diff, branches: Diff) -> list[str]:
    """--diff-from の表示行を作ります。"""
    lines = [
        f"{label}: 追加 {len(d.added)} 件、削除 {len(d.removed)} 件、名称変更 {len(d.changed)} 件"
        for label, d in (("銀行", banks), ("支店", branches))
    ]
    for label, d in (("銀行", banks), ("支店", branches)):
        lines += [f"+ {label} {_code(row)} {_name(row)}" for row in d.added]
        lines += [f"- {label} {_code(row)} {_name(row)}" for row in d.removed]
        lines += [f"~ {label} {_code(old)} {_name(old)} → {_name(new)}" for old, new in d.changed]
    return lines


def _positive_int(text: str) -> int:
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError("1 以上を指定してください。")
    return value


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--input", type=Path, default=Path(ORIGINAL_DATA), help="入力ファイル (cp932)"
    )
    parser.add_argument(
        "--output-dir", type=Path, default=Path("output"), help="出力先ディレクトリ"
    )
    parser.add_argument(
        "--no-timestamp",
        action="store_true",
        help="ファイル名の先頭に日時を付けない (銀行マスタINSERT.sql, 支店マスタINSERT.sql)",
    )
    parser.add_argument(
        "--rows-per-insert",
        type=_positive_int,
        default=1,
        metavar="N",
        help="1 つの INSERT 文にまとめる行数 (既定: 1)",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="ファイルを作らず、銀行・支店の SQL をまとめて標準出力に書く (mysql へのパイプ用)",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--delete-before-insert",
        action="store_true",
        help="トランザクション内でテーブルを空にしてから INSERT する (入れ直し用)",
    )
    mode.add_argument(
        "--check", action="store_true", help="ファイルを作らず、件数と検査結果だけを表示する"
    )
    mode.add_argument(
        "--diff-from",
        type=Path,
        metavar="OLD",
        help="ファイルを作らず、OLD から --input への追加・削除・名称変更を表示する",
    )
    args = parser.parse_args(argv)
    if args.stdout and (args.check or args.diff_from):
        parser.error("--stdout は --check, --diff-from と同時に指定できません。")
    return args


def _fail(message: str) -> NoReturn:
    print(f"エラー: {message}", file=sys.stderr)
    sys.exit(1)


def _read_or_fail(path: Path) -> tuple[list[list[str]], list[list[str]]]:
    try:
        return read_rows(path)
    except FileNotFoundError:
        _fail(f"{path} が見つかりません。")
    except IsADirectoryError:
        _fail(
            f"{path} はディレクトリです。"
            "(Docker で入力ファイルがないまま実行すると空のディレクトリができます。"
            "削除してから入力ファイルを置いてください。)"
        )
    except ValueError as e:
        _fail(str(e))


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    banks, branches = _read_or_fail(args.input)
    if args.diff_from:
        old_banks, old_branches = _read_or_fail(args.diff_from)
        print("\n".join(diff_lines(diff_rows(old_banks, banks), diff_rows(old_branches, branches))))
        return
    if args.check:
        report = check(banks, branches)
        print("\n".join(report.lines()))
        if report.problems:
            _fail("データに問題があります。")
        return
    if args.stdout:
        if isinstance(sys.stdout, io.TextIOWrapper):
            # Windows など、標準出力が UTF-8 でない環境のためです。
            sys.stdout.reconfigure(encoding="utf-8", newline="\n")
        write_sql_stream(
            banks,
            branches,
            sys.stdout,
            delete_before_insert=args.delete_before_insert,
            rows_per_insert=args.rows_per_insert,
        )
        print(f"銀行 {len(banks)} 件、支店 {len(branches)} 件", file=sys.stderr)
        return
    try:
        paths = write_sql(
            banks,
            branches,
            args.output_dir,
            delete_before_insert=args.delete_before_insert,
            timestamp=not args.no_timestamp,
            rows_per_insert=args.rows_per_insert,
        )
    except OSError as e:
        _fail(f"{args.output_dir} に書き出せません ({e.strerror})。")
    for path in paths:
        print(path)
    print(f"銀行 {len(banks)} 件、支店 {len(branches)} 件", file=sys.stderr)


if __name__ == "__main__":
    main()
