import io
import subprocess
import sys
import tomllib
from collections.abc import Sequence
from datetime import datetime, timedelta
from pathlib import Path
from typing import ClassVar

import pytest

import bank_master_creator
from bank_master_creator import (
    build_parser,
    check,
    create,
    diff_rows,
    escape,
    filter_rows,
    main,
    make_bank_insert_sql,
    make_branch_insert_sql,
    quote,
    read_rows,
    search_banks,
    write_sql,
    write_sql_stream,
)

NOW = datetime(2026, 1, 2, 3, 4, 5)
BANK_SQL = "(20260102_030405)銀行マスタINSERT.sql"
BRANCH_SQL = "(20260102_030405)支店マスタINSERT.sql"

BANK = ("0001", "000", "ﾃｽﾄ", "テスト銀行", "1")
BRANCH = ("0001", "001", "ﾃｽﾄｼﾃﾝ", "テスト支店", "2")


def write_input(path: Path, lines: Sequence[tuple[str, ...] | str]) -> Path:
    """合成データを ginkositen.txt と同じ形式で書き出します。

    cp932, CRLF で、ｶﾅは 15 桁に埋め、ｶﾅと名前は引用符で囲みます。
    """
    text = ""
    for line in lines:
        if isinstance(line, str):
            text += line + "\r\n"
            continue
        fields = list(line)
        if len(fields) == 5:
            fields[2] = f'"{fields[2].ljust(15)}"'
            fields[3] = f'"{fields[3]}"'
        text += ",".join(fields) + "\r\n"
    path.write_bytes(text.encode("cp932"))
    return path


def _readable(path: Path) -> bool:
    try:
        path.read_bytes()
    except PermissionError:
        return False
    return True


def bank_row(name="テスト銀行", kana="ﾃｽﾄ"):
    return ["0001", "000", kana.ljust(15), name, "1"]


def branch_row(name="テスト支店", kana="ﾃｽﾄｼﾃﾝ"):
    return ["0001", "001", kana.ljust(15), name, "2"]


class TestEscape:
    def test_passthrough(self):
        assert escape("テスト銀行 ﾃｽﾄ-1") == "テスト銀行 ﾃｽﾄ-1"

    def test_single_quote(self):
        assert escape("テスト'銀行") == "テスト\\'銀行"

    def test_backslash(self):
        assert escape("a\\b") == "a\\\\b"

    def test_escaped_quote_input(self):
        assert escape("\\'") == "\\\\\\'"

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("\x00", "\\0"),
            ("\n", "\\n"),
            ("\r", "\\r"),
            ("\x1a", "\\Z"),
        ],
    )
    def test_control_chars(self, raw, expected):
        assert escape(f"a{raw}b") == f"a{expected}b"


def test_quote():
    assert quote("テスト'銀行") == "'テスト\\'銀行'"


class TestMakeBankInsertSql:
    def test_exact(self):
        assert make_bank_insert_sql(bank_row()) == (
            "INSERT INTO m_banks (bank_code, bank_name, bank_name_kana) "
            "VALUES ('0001', 'テスト銀行', 'ﾃｽﾄ');"
        )

    def test_quote_in_name(self):
        sql = make_bank_insert_sql(bank_row(name="テスト'銀行"))
        assert "'テスト\\'銀行'" in sql


class TestMakeBranchInsertSql:
    def test_exact(self):
        assert make_branch_insert_sql(branch_row()) == (
            "INSERT INTO m_bank_branches (bank_code, branch_code, branch_name, branch_name_kana) "
            "VALUES ('0001', '001', 'テスト支店', 'ﾃｽﾄｼﾃﾝ');"
        )

    def test_quote_in_name(self):
        sql = make_branch_insert_sql(branch_row(name="テスト'支店"))
        assert "'テスト\\'支店'" in sql


class TestKana:
    def test_strips_trailing_ascii_spaces_only(self):
        sql = make_bank_insert_sql(bank_row(kana=" ﾃｽﾄ\u3000"))
        assert sql.endswith("' ﾃｽﾄ\u3000');")


class TestCreate:
    def test_writes_both_files(self, tmp_path):
        src = write_input(tmp_path / "in.txt", [BANK, BRANCH, BRANCH])
        out = tmp_path / "out"

        bank, branch = create(src, out, now=NOW)

        assert bank == out / BANK_SQL
        assert branch == out / BRANCH_SQL
        assert bank.read_text(encoding="utf-8").splitlines() == [
            "SET NAMES utf8mb4;",
            "INSERT INTO m_banks (bank_code, bank_name, bank_name_kana)"
            " VALUES ('0001', 'テスト銀行', 'ﾃｽﾄ');",
        ]
        assert len(branch.read_text(encoding="utf-8").splitlines()) == 3

    def test_header_only_when_no_rows(self, tmp_path):
        src = write_input(tmp_path / "in.txt", [BANK])

        _, branch = create(src, tmp_path, now=NOW)

        assert branch.read_text(encoding="utf-8") == "SET NAMES utf8mb4;\n"

    def test_comma_in_quoted_name(self, tmp_path):
        src = write_input(tmp_path / "in.txt", [("0001", "000", "ﾃｽﾄ", "テスト,銀行", "1")])

        bank, _ = create(src, tmp_path, now=NOW)

        assert "'テスト,銀行'" in bank.read_text(encoding="utf-8")

    def test_shares_one_timestamp(self, tmp_path, monkeypatch):
        class FakeDatetime:
            current = NOW

            @classmethod
            def now(cls):
                cls.current += timedelta(seconds=1)
                return cls.current

        monkeypatch.setattr(bank_master_creator, "datetime", FakeDatetime)
        src = write_input(tmp_path / "in.txt", [BANK, BRANCH])

        bank, branch = create(src, tmp_path)

        assert bank.name.split(")")[0] == branch.name.split(")")[0]

    def test_overwrites_existing(self, tmp_path):
        src = write_input(tmp_path / "in.txt", [BANK, BRANCH])
        (tmp_path / BANK_SQL).write_text("old\nold\nold\n", encoding="utf-8")

        bank, _ = create(src, tmp_path, now=NOW)

        assert bank.read_text(encoding="utf-8") == (
            "SET NAMES utf8mb4;\n" + make_bank_insert_sql(list(BANK)) + "\n"
        )

    def test_creates_nested_output_dir(self, tmp_path):
        src = write_input(tmp_path / "in.txt", [BANK, BRANCH])

        bank, branch = create(src, tmp_path / "a" / "b", now=NOW)

        assert bank.exists()
        assert branch.exists()

    def test_skips_blank_lines(self, tmp_path):
        src = write_input(tmp_path / "in.txt", [BANK, "", BRANCH, ""])

        bank, branch = create(src, tmp_path, now=NOW)

        assert len(bank.read_text(encoding="utf-8").splitlines()) == 2
        assert len(branch.read_text(encoding="utf-8").splitlines()) == 2

    def test_rejects_unknown_flag(self, tmp_path):
        src = write_input(tmp_path / "in.txt", [BANK, (*BRANCH[:4], "3")])

        with pytest.raises(ValueError, match="2 行目"):
            create(src, tmp_path / "out", now=NOW)

    def test_invalid_input_leaves_no_files(self, tmp_path):
        src = write_input(tmp_path / "in.txt", [BANK, BRANCH, BRANCH[:4]])
        out = tmp_path / "out"

        with pytest.raises(ValueError, match="3 行目"):
            create(src, out, now=NOW)

        assert not out.exists()

    def test_cp932_only_char(self, tmp_path):
        src = write_input(tmp_path / "in.txt", [(*BANK[:3], "㈱テスト", "1")])

        bank, _ = create(src, tmp_path, now=NOW)

        assert "'㈱テスト'" in bank.read_text(encoding="utf-8")


def test_golden_fixture(tmp_path):
    """fixtures/sample.txt からの出力が、保存済みの期待ファイルとバイト単位で一致します。

    sample.txt は架空のデータで、cp932 特有の文字 (㈱)、ｶﾅの記号 (ｵ-ﾌﾟﾝ.ﾃｽﾄ)、
    15 桁のｶﾅの詰め方、複数の銀行と支店の並びを含みます。
    """
    fixtures = Path(__file__).parent / "fixtures"

    bank, branch = create(fixtures / "sample.txt", tmp_path, now=NOW)

    assert bank.read_bytes() == (fixtures / "bank.sql").read_bytes()
    assert branch.read_bytes() == (fixtures / "branch.sql").read_bytes()


class TestDeleteBeforeInsert:
    def test_bank_file_layout(self, tmp_path):
        src = write_input(tmp_path / "in.txt", [BANK, BRANCH])

        bank, _ = write_sql(*read_rows(src), tmp_path, NOW, delete_before_insert=True)

        assert bank.read_text(encoding="utf-8").splitlines() == [
            "SET NAMES utf8mb4;",
            "START TRANSACTION;",
            "DELETE FROM m_banks;",
            make_bank_insert_sql(list(BANK)),
            "COMMIT;",
        ]

    def test_branch_file_deletes_branch_table_only(self, tmp_path):
        src = write_input(tmp_path / "in.txt", [BANK, BRANCH])

        _, branch = write_sql(*read_rows(src), tmp_path, NOW, delete_before_insert=True)

        text = branch.read_text(encoding="utf-8")
        assert "DELETE FROM m_bank_branches;\n" in text
        assert "m_banks;" not in text

    def test_no_rows_still_clears_table(self, tmp_path):
        src = write_input(tmp_path / "in.txt", [BANK])

        _, branch = write_sql(*read_rows(src), tmp_path, NOW, delete_before_insert=True)

        assert branch.read_text(encoding="utf-8").splitlines() == [
            "SET NAMES utf8mb4;",
            "START TRANSACTION;",
            "DELETE FROM m_bank_branches;",
            "COMMIT;",
        ]

    def test_lf_and_utf8(self, tmp_path):
        src = write_input(tmp_path / "in.txt", [BANK, BRANCH])

        for path in write_sql(*read_rows(src), tmp_path, NOW, delete_before_insert=True):
            data = path.read_bytes()
            assert b"\r" not in data
            assert data.endswith(b"COMMIT;\n")
            data.decode("utf-8")

    def test_main_flag(self, tmp_path):
        src = write_input(tmp_path / "in.txt", [BANK, BRANCH])
        out = tmp_path / "out"

        main(["--input", str(src), "--output-dir", str(out), "--delete-before-insert"])

        for path in out.iterdir():
            assert "DELETE FROM " in path.read_text(encoding="utf-8")


class TestCheck:
    def test_clean_input_report(self, tmp_path, capsys):
        src = write_input(tmp_path / "in.txt", [BANK, BRANCH, ("0001", "002", "ﾆ", "二", "2")])

        main(["--input", str(src), "--check", "--output-dir", str(tmp_path / "out")])

        assert capsys.readouterr().out == (
            "銀行: 1 件、支店: 2 件\n"
            "銀行コード重複: 0\n"
            "銀行+支店コード重複: 0\n"
            "銀行行のない支店: 0\n"
            "支店のない銀行: 0\n"
            "ｶﾅが 15 文字 (切り詰めの可能性): 0\n"
        )
        assert not (tmp_path / "out").exists()

    def test_duplicates_and_orphans_fail(self, tmp_path, capsys):
        src = write_input(
            tmp_path / "in.txt",
            [BANK, BANK, BRANCH, BRANCH, ("0009", "001", "ﾅｼ", "無し", "2")],
        )

        with pytest.raises(SystemExit) as excinfo:
            main(["--input", str(src), "--check"])

        assert excinfo.value.code == 1
        captured = capsys.readouterr()
        assert "銀行コード重複: 1 (0001)\n" in captured.out
        assert "銀行+支店コード重複: 1 (0001-001)\n" in captured.out
        assert "銀行行のない支店: 1 (0009-001)\n" in captured.out
        assert captured.err == "エラー: データに問題があります。\n"

    def test_warnings_only_exit_0(self, tmp_path, capsys):
        src = write_input(
            tmp_path / "in.txt",
            [BANK, ("0002", "000", "ｱｲｳｴｵｶｷｸｹｺｻｼｽｾｿ", "長い銀行", "1"), BRANCH],
        )

        main(["--input", str(src), "--check"])

        out = capsys.readouterr().out
        assert "支店のない銀行: 1\n" in out
        assert "ｶﾅが 15 文字 (切り詰めの可能性): 1\n" in out

    def test_invalid_row_exits_1(self, tmp_path, capsys):
        src = write_input(tmp_path / "in.txt", [BANK, BRANCH[:4]])

        with pytest.raises(SystemExit) as excinfo:
            main(["--input", str(src), "--check"])

        assert excinfo.value.code == 1
        assert capsys.readouterr().err == "エラー: 2 行目: 項目数が 4 です。\n"

    def test_codes_are_capped(self):
        banks = [
            [f"{i:04d}", "000", "ｶﾅ".ljust(15), "銀行", "1"] for i in range(12) for _ in (0, 1)
        ]

        line = check(banks, []).lines()[1]

        assert line.startswith("銀行コード重複: 12 (0000, 0001, ")
        assert line.endswith(", 0009 ほか 2 件)")

    def test_check_function(self):
        report = check([bank_row()], [branch_row(), branch_row()])

        assert report.duplicate_branch_codes == ["0001-001"]
        assert report.problems

    def test_rejects_delete_before_insert(self):
        with pytest.raises(SystemExit) as excinfo:
            main(["--check", "--delete-before-insert"])

        assert excinfo.value.code == 2


class TestRowsPerInsert:
    def test_groups_values(self, tmp_path):
        branches = [branch_row(), branch_row(name="二"), branch_row(name="三")]

        _, branch = write_sql([bank_row()], branches, tmp_path, NOW, rows_per_insert=2)

        assert branch.read_text(encoding="utf-8").splitlines() == [
            "SET NAMES utf8mb4;",
            "INSERT INTO m_bank_branches (bank_code, branch_code, branch_name, branch_name_kana)"
            " VALUES",
            "('0001', '001', 'テスト支店', 'ﾃｽﾄｼﾃﾝ'),",
            "('0001', '001', '二', 'ﾃｽﾄｼﾃﾝ');",
            "INSERT INTO m_bank_branches (bank_code, branch_code, branch_name, branch_name_kana)"
            " VALUES ('0001', '001', '三', 'ﾃｽﾄｼﾃﾝ');",
        ]

    def test_empty_table_with_grouping(self, tmp_path):
        _, branch = write_sql([bank_row()], [], tmp_path, NOW, rows_per_insert=100)

        assert branch.read_text(encoding="utf-8") == "SET NAMES utf8mb4;\n"

    def test_main_flag_with_delete_before_insert(self, tmp_path):
        src = write_input(tmp_path / "in.txt", [BANK, BRANCH, BRANCH])
        out = tmp_path / "out"

        main([
            "--input", str(src), "--output-dir", str(out), "--no-timestamp",
            "--rows-per-insert", "10", "--delete-before-insert",
        ])  # fmt: skip

        lines = (out / "支店マスタINSERT.sql").read_text(encoding="utf-8").splitlines()
        assert lines[2] == "DELETE FROM m_bank_branches;"
        assert lines[3].endswith(" VALUES")
        assert lines[-1] == "COMMIT;"
        assert sum(line.startswith("INSERT") for line in lines) == 1

    @pytest.mark.parametrize("value", ["0", "-1", "x"])
    def test_rejects_non_positive(self, value, capsys):
        with pytest.raises(SystemExit) as excinfo:
            main(["--rows-per-insert", value])

        assert excinfo.value.code == 2
        assert f"{value!r} は不正です。1 以上の整数を指定してください。" in capsys.readouterr().err


class TestStdout:
    def test_combined_stream(self):
        out = io.StringIO()

        write_sql_stream([bank_row()], [branch_row()], out)

        assert out.getvalue().splitlines() == [
            "SET NAMES utf8mb4;",
            make_bank_insert_sql(bank_row()),
            make_branch_insert_sql(branch_row()),
        ]

    def test_delete_before_insert_single_transaction(self):
        out = io.StringIO()

        write_sql_stream([bank_row()], [], out, delete_before_insert=True)

        assert out.getvalue().splitlines() == [
            "SET NAMES utf8mb4;",
            "START TRANSACTION;",
            "DELETE FROM m_banks;",
            make_bank_insert_sql(bank_row()),
            "DELETE FROM m_bank_branches;",
            "COMMIT;",
        ]

    def test_main_writes_sql_to_stdout_and_summary_to_stderr(self, tmp_path, capsys):
        src = write_input(tmp_path / "in.txt", [BANK, BRANCH, BRANCH])

        main(["--input", str(src), "--stdout", "--rows-per-insert", "2"])

        captured = capsys.readouterr()
        assert captured.out.startswith("SET NAMES utf8mb4;\nINSERT INTO m_banks ")
        assert captured.out.endswith("');\n")
        assert captured.out.count("INSERT") == 2
        assert captured.err == "銀行 1 件、支店 2 件\n"
        assert not (tmp_path / "output").exists()

    def test_main_with_delete_before_insert(self, tmp_path, capsys):
        src = write_input(tmp_path / "in.txt", [BANK, BRANCH])

        main(["--input", str(src), "--stdout", "--delete-before-insert"])

        lines = capsys.readouterr().out.splitlines()
        assert lines[1] == "START TRANSACTION;"
        assert lines[-1] == "COMMIT;"

    def test_rejects_check(self):
        with pytest.raises(SystemExit) as excinfo:
            main(["--stdout", "--check"])

        assert excinfo.value.code == 2

    @pytest.mark.parametrize("mode", ["--stdout", "--diff-from"])
    def test_broken_pipe_has_no_traceback(self, tmp_path, mode):
        """mysql や head が途中で終了してパイプが閉じても、トレースバックを出しません。"""
        rows = [("0001", f"{i:05d}", "ｼﾃﾝ", f"支店{i}", "2") for i in range(30000)]
        src = write_input(tmp_path / "in.txt", [BANK, *rows])
        old = write_input(tmp_path / "old.txt", [BANK])
        script = Path(__file__).parent.parent / "bank_master_creator.py"
        args = [mode, str(old)] if mode == "--diff-from" else [mode]

        proc = subprocess.Popen(  # noqa: S603 (引数は固定です)
            [sys.executable, str(script), "--input", str(src), *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert proc.stdout is not None
        proc.stdout.read(100)
        proc.stdout.close()
        _, stderr = proc.communicate(timeout=30)

        assert proc.returncode == 1
        assert b"Traceback" not in stderr
        assert "標準出力に書き出せません".encode() in stderr


class TestBankCode:
    ROWS: ClassVar = [
        BANK,
        BRANCH,
        ("0001", "002", "ﾆ", "二", "2"),
        ("0002", "000", "ｲ", "イ銀行", "1"),
        ("0002", "001", "ｲｼﾃﾝ", "イ支店", "2"),
    ]

    def test_filters_banks_and_their_branches(self, tmp_path, capsys):
        src = write_input(tmp_path / "in.txt", self.ROWS)

        main(["--input", str(src), "--bank-code", "0002", "--stdout"])

        captured = capsys.readouterr()
        inserts = [line for line in captured.out.splitlines() if line.startswith("INSERT")]
        assert len(inserts) == 2
        assert "('0002', 'イ銀行', 'ｲ')" in inserts[0]
        assert "('0002', '001', 'イ支店', 'ｲｼﾃﾝ')" in inserts[1]
        assert captured.err == "銀行 1 件、支店 1 件 (--bank-code で絞り込み)\n"

    def test_comma_list_equals_repeated_flag_and_keeps_input_order(self, tmp_path, capsys):
        src = write_input(tmp_path / "in.txt", self.ROWS)

        main(["--input", str(src), "--bank-code", "0002,0001", "--stdout"])
        first = capsys.readouterr().out
        main(["--input", str(src), "--bank-code", "0002", "--bank-code", "0001", "--stdout"])
        second = capsys.readouterr().out

        assert first == second
        assert first.index("'0001', 'テスト銀行'") < first.index("'0002', 'イ銀行'")

    def test_unknown_code_exits_1_and_writes_nothing(self, tmp_path, capsys):
        src = write_input(tmp_path / "in.txt", self.ROWS)
        out = tmp_path / "out"

        with pytest.raises(SystemExit) as excinfo:
            main(["--input", str(src), "--bank-code", "0009", "--output-dir", str(out)])

        assert excinfo.value.code == 1
        assert capsys.readouterr().err == "エラー: 銀行コード 0009 は入力にありません。\n"
        assert not out.exists()

    @pytest.mark.parametrize("value", ["1", "00011", "00a1", "", "0001,"])
    def test_rejects_malformed_code(self, value):
        with pytest.raises(SystemExit) as excinfo:
            main(["--bank-code", value])

        assert excinfo.value.code == 2

    def test_seed_combo(self, tmp_path, capsys):
        src = write_input(tmp_path / "in.txt", self.ROWS)

        main([
            "--input", str(src), "--bank-code", "0001", "--stdout",
            "--delete-before-insert", "--rows-per-insert", "500",
        ])  # fmt: skip

        lines = capsys.readouterr().out.splitlines()
        assert lines[:3] == ["SET NAMES utf8mb4;", "START TRANSACTION;", "DELETE FROM m_banks;"]
        assert lines[3].startswith("INSERT INTO m_banks ")
        assert lines[4] == "DELETE FROM m_bank_branches;"
        assert lines[5].endswith(" VALUES")
        assert lines[6:] == [
            "('0001', '001', 'テスト支店', 'ﾃｽﾄｼﾃﾝ'),",
            "('0001', '002', '二', 'ﾆ');",
            "COMMIT;",
        ]

    def test_filter_applies_to_check(self, tmp_path, capsys):
        src = write_input(tmp_path / "in.txt", [*self.ROWS, ("0002", "001", "ｲｼﾃﾝ", "イ支店", "2")])

        main(["--input", str(src), "--check", "--bank-code", "0001"])

        assert capsys.readouterr().out.startswith("銀行: 1 件、支店: 2 件\n")

    def test_filter_applies_to_diff_from(self, tmp_path, capsys):
        old = write_input(tmp_path / "old.txt", self.ROWS)
        new = write_input(
            tmp_path / "new.txt", [*self.ROWS[:3], ("0003", "000", "ｳ", "ウ銀行", "1")]
        )

        main(["--input", str(new), "--diff-from", str(old), "--bank-code", "0001"])

        out = capsys.readouterr().out
        assert "銀行: 追加 0 件、削除 0 件、名称変更 0 件\n" in out
        assert "支店: 追加 0 件、削除 0 件、名称変更 0 件\n" in out

    def test_file_mode_writes_filtered_files(self, tmp_path):
        src = write_input(tmp_path / "in.txt", self.ROWS)

        main(
            [
                "--input",
                str(src),
                "--output-dir",
                str(tmp_path),
                "--no-timestamp",
                "--bank-code",
                "0001",
            ]
        )

        bank = (tmp_path / "銀行マスタINSERT.sql").read_text(encoding="utf-8")
        branch = (tmp_path / "支店マスタINSERT.sql").read_text(encoding="utf-8")
        assert bank.count("INSERT") == 1
        assert branch.count("INSERT") == 2

    def test_filter_rows_function(self):
        banks = [bank_row(), ["0002", "000", "ｲ".ljust(15), "イ銀行", "1"]]
        branches = [branch_row(), ["0002", "001", "ｲ".ljust(15), "イ支店", "2"]]

        assert filter_rows(banks, branches, ["0002"]) == ([banks[1]], [branches[1]])
        with pytest.raises(ValueError, match="0009"):
            filter_rows(banks, branches, ["0009"])


class TestStdin:
    @staticmethod
    def feed(monkeypatch: pytest.MonkeyPatch, path: Path) -> None:
        monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(path.read_bytes())))

    def test_check_from_stdin(self, tmp_path, monkeypatch, capsys):
        self.feed(monkeypatch, write_input(tmp_path / "in.txt", [BANK, BRANCH]))

        main(["--input", "-", "--check"])

        assert capsys.readouterr().out.startswith("銀行: 1 件、支店: 1 件\n")

    def test_stdout_from_stdin(self, tmp_path, monkeypatch, capsys):
        src = write_input(tmp_path / "in.txt", [BANK, BRANCH, BRANCH])
        self.feed(monkeypatch, src)
        expected = io.StringIO()
        write_sql_stream(*read_rows(src), expected)

        main(["--input", "-", "--stdout"])

        captured = capsys.readouterr()
        assert captured.out == expected.getvalue()
        assert captured.err == "銀行 1 件、支店 2 件\n"

    def test_writes_files_from_stdin(self, tmp_path, monkeypatch, capsys):
        self.feed(monkeypatch, write_input(tmp_path / "in.txt", [BANK, BRANCH]))

        main(["--input", "-", "--output-dir", str(tmp_path / "out")])

        assert len(list((tmp_path / "out").iterdir())) == 2

    def test_invalid_row_reports_line_number(self, tmp_path, monkeypatch, capsys):
        self.feed(monkeypatch, write_input(tmp_path / "in.txt", [BANK, BRANCH, BRANCH[:4]]))

        with pytest.raises(SystemExit) as excinfo:
            main(["--input", "-", "--check"])

        assert excinfo.value.code == 1
        assert capsys.readouterr().err == "エラー: 3 行目: 項目数が 4 です。\n"

    def test_diff_from_stdin_header(self, tmp_path, monkeypatch, capsys):
        new = write_input(tmp_path / "new.txt", [BANK, BRANCH])
        self.feed(monkeypatch, write_input(tmp_path / "old.txt", [BANK]))

        main(["--input", str(new), "--diff-from", "-"])

        assert capsys.readouterr().out.startswith(f"標準入力 → {new}\n")

    def test_both_stdin_rejected(self):
        with pytest.raises(SystemExit) as excinfo:
            main(["--input", "-", "--diff-from", "-"])

        assert excinfo.value.code == 2

    def test_empty_stdin_exits_1(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(b"")))

        with pytest.raises(SystemExit) as excinfo:
            main(["--input", "-"])

        assert excinfo.value.code == 1
        assert capsys.readouterr().err == "エラー: 入力に行がありません。\n"

    def test_subprocess_reads_binary_stdin(self, tmp_path):
        src = write_input(tmp_path / "in.txt", [BANK, BRANCH])
        script = Path(__file__).parent.parent / "bank_master_creator.py"

        proc = subprocess.run(  # noqa: S603 (引数は固定です)
            [sys.executable, str(script), "--input", "-", "--check"],
            input=src.read_bytes(),
            capture_output=True,
            timeout=30,
            check=False,
        )

        assert proc.returncode == 0, proc.stderr
        assert proc.stdout.decode("utf-8").startswith("銀行: 1 件、支店: 1 件\n")


class TestLookup:
    ROWS: ClassVar = [
        ("0001", "000", "ﾐｽﾞﾎ", "みずほ", "1"),
        ("0005", "000", "ﾐﾂﾋﾞｼﾕ-ｴﾌｼﾞｴｲ", "三菱ＵＦＪ", "1"),
        ("0001", "001", "ﾄｳｷﾖｳ", "東京営業部", "2"),
        ("0001", "002", "ｼﾌﾞﾔ", "渋谷", "2"),
        ("0005", "001", "ﾎﾝﾃﾝ", "本店", "2"),
    ]

    def test_search_prints_tsv(self, tmp_path, capsys):
        src = write_input(tmp_path / "in.txt", self.ROWS)

        main(["--input", str(src), "--search", "みずほ", "--output-dir", str(tmp_path / "out")])

        captured = capsys.readouterr()
        assert captured.out == "0001\t000\tみずほ\tﾐｽﾞﾎ\n"
        assert captured.err == "1 件\n"
        assert not (tmp_path / "out").exists()

    @pytest.mark.parametrize(
        ("query", "code"),
        [("ﾐｽﾞﾎ", "0001"), ("ミズホ", "0001"), ("UFJ", "0005"), ("ufj", "0005"), ("ＵＦＪ", "0005")],  # noqa: RUF001
    )
    def test_search_ignores_width_and_case(self, tmp_path, capsys, query, code):
        src = write_input(tmp_path / "in.txt", self.ROWS)

        main(["--input", str(src), "--search", query])

        assert capsys.readouterr().out.startswith(f"{code}\t000\t")

    def test_search_no_hit_exits_1(self, tmp_path, capsys):
        src = write_input(tmp_path / "in.txt", self.ROWS)

        with pytest.raises(SystemExit) as excinfo:
            main(["--input", str(src), "--search", "ない"])

        assert excinfo.value.code == 1
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == "エラー: 該当する銀行がありません。\n"

    def test_list_prints_bank_then_branches(self, tmp_path, capsys):
        src = write_input(tmp_path / "in.txt", self.ROWS)

        main(["--input", str(src), "--list", "0001"])

        captured = capsys.readouterr()
        assert captured.out == (
            "0001\t000\tみずほ\tﾐｽﾞﾎ\n0001\t001\t東京営業部\tﾄｳｷﾖｳ\n0001\t002\t渋谷\tｼﾌﾞﾔ\n"
        )
        assert captured.err == "支店 2 件\n"

    def test_list_unknown_code_exits_1(self, tmp_path, capsys):
        src = write_input(tmp_path / "in.txt", self.ROWS)

        with pytest.raises(SystemExit) as excinfo:
            main(["--input", str(src), "--list", "0009"])

        assert excinfo.value.code == 1
        assert capsys.readouterr().err == "エラー: 銀行コード 0009 は入力にありません。\n"

    @pytest.mark.parametrize(
        "argv",
        [
            ["--list", "0001", "--stdout"],
            ["--search", "x", "--check"],
            ["--search", "x", "--list", "0001"],
            ["--list", "0001", "--delete-before-insert"],
        ],
    )
    def test_exclusive_with_other_modes(self, argv):
        with pytest.raises(SystemExit) as excinfo:
            main(argv)

        assert excinfo.value.code == 2

    def test_search_banks_function(self):
        banks = [bank_row(), ["0005", "000", "ﾐﾂﾋﾞｼﾕ-ｴﾌｼﾞｴｲ".ljust(15), "三菱ＵＦＪ", "1"]]

        assert search_banks(banks, "ufj") == [banks[1]]
        assert search_banks(banks, "テスト") == [banks[0]]
        assert search_banks(banks, "") == banks

    @pytest.mark.parametrize(
        "code", ["", "001", "00001", "0001,0005", "abcd", "\uff10\uff10\uff10\uff11"]
    )
    def test_list_rejects_invalid_code(self, code):
        with pytest.raises(SystemExit) as excinfo:
            main(["--list", code])

        assert excinfo.value.code == 2

    def test_lookup_respects_bank_filter(self, tmp_path, capsys):
        src = write_input(tmp_path / "in.txt", self.ROWS)

        main(["--input", str(src), "--search", "", "--bank-code", "0005"])

        captured = capsys.readouterr()
        assert captured.out == "0005\t000\t三菱ＵＦＪ\tﾐﾂﾋﾞｼﾕ-ｴﾌｼﾞｴｲ\n"  # noqa: RUF001
        assert captured.err == "1 件\n"


class TestNoTimestamp:
    def test_fixed_names(self, tmp_path):
        src = write_input(tmp_path / "in.txt", [BANK, BRANCH])

        bank, branch = write_sql(*read_rows(src), tmp_path, timestamp=False)

        assert bank == tmp_path / "銀行マスタINSERT.sql"
        assert branch == tmp_path / "支店マスタINSERT.sql"
        assert bank.read_text(encoding="utf-8").startswith("SET NAMES utf8mb4;\n")

    def test_main_flag(self, tmp_path, capsys):
        src = write_input(tmp_path / "in.txt", [BANK, BRANCH])
        out = tmp_path / "out"

        main(["--input", str(src), "--output-dir", str(out), "--no-timestamp"])

        assert sorted(p.name for p in out.iterdir()) == [
            "支店マスタINSERT.sql",
            "銀行マスタINSERT.sql",
        ]
        assert str(out / "銀行マスタINSERT.sql") in capsys.readouterr().out


class TestDiff:
    def test_diff_rows(self):
        old = [bank_row(), branch_row(), ["0001", "002", "ｷｴﾙ".ljust(15), "消える", "2"]]
        new = [
            bank_row(name="新テスト銀行"),
            branch_row(kana="ｼﾝﾃｽﾄｼﾃﾝ"),
            ["0001", "003", "ﾌｴﾙ".ljust(15), "増える", "2"],
        ]

        result = diff_rows(old, new)

        assert result.added == [new[2]]
        assert result.removed == [old[2]]
        assert result.changed == [(old[0], new[0]), (old[1], new[1])]

    def test_padding_only_difference_is_not_a_change(self):
        old = [branch_row(kana="ｱ")]
        new = [["0001", "001", "ｱ", "テスト支店", "2"]]

        assert diff_rows(old, new).changed == []

    def test_main_report(self, tmp_path, capsys):
        old = write_input(
            tmp_path / "old.txt",
            [("0001", "000", "ｱ", "ア銀行", "1"), ("0002", "000", "ｲ", "イ銀行", "1"), BRANCH],
        )
        new = write_input(
            tmp_path / "new.txt",
            [
                ("0001", "000", "ｱ", "ア銀行", "1"),
                ("0003", "000", "ｳ", "ウ銀行", "1"),
                ("0001", "001", "ﾃｽﾄｼﾃﾝ", "テスト本店", "2"),
                ("0003", "001", "ｳ", "ウ支店", "2"),
            ],
        )

        main(["--input", str(new), "--diff-from", str(old), "--output-dir", str(tmp_path / "out")])

        assert capsys.readouterr().out == (
            f"{old} → {new}\n"
            "銀行: 追加 1 件、削除 1 件、名称変更 0 件\n"
            "支店: 追加 1 件、削除 0 件、名称変更 1 件\n"
            "+ 銀行 0003 ウ銀行 (ｳ)\n"
            "- 銀行 0002 イ銀行 (ｲ)\n"
            "+ 支店 0003-001 ウ支店 (ｳ)\n"
            "~ 支店 0001-001 テスト支店 (ﾃｽﾄｼﾃﾝ) → テスト本店 (ﾃｽﾄｼﾃﾝ)\n"
        )
        assert not (tmp_path / "out").exists()

    def test_missing_old_file_exits_1(self, tmp_path, capsys):
        new = write_input(tmp_path / "new.txt", [BANK, BRANCH])

        with pytest.raises(SystemExit) as excinfo:
            main(["--input", str(new), "--diff-from", str(tmp_path / "old.txt")])

        assert excinfo.value.code == 1
        assert capsys.readouterr().err == f"エラー: {tmp_path / 'old.txt'} が見つかりません。\n"

    def test_rejects_check(self, tmp_path):
        with pytest.raises(SystemExit) as excinfo:
            main(["--check", "--diff-from", str(tmp_path)])

        assert excinfo.value.code == 2

    def test_duplicate_codes_use_last_row(self):
        old = [bank_row(name="一つ目"), bank_row(name="二つ目")]

        assert diff_rows(old, [bank_row(name="二つ目")]).changed == []

    def test_empty_old_file_lists_everything_as_added(self, tmp_path, capsys):
        new = write_input(tmp_path / "new.txt", [BANK, BRANCH])
        old = write_input(tmp_path / "old.txt", [])

        main(["--input", str(new), "--diff-from", str(old)])

        assert "銀行: 追加 1 件、削除 0 件、名称変更 0 件\n" in capsys.readouterr().out


class TestReadRows:
    def test_splits_banks_and_branches(self, tmp_path):
        src = write_input(tmp_path / "in.txt", [BANK, BRANCH, BRANCH])

        banks, branches = read_rows(src)

        assert banks == [[*BANK[:2], BANK[2].ljust(15), *BANK[3:]]]
        assert len(branches) == 2

    def test_decode_error_reports_line_number(self, tmp_path):
        src = write_input(tmp_path / "in.txt", [BANK, BRANCH])
        src.write_bytes(src.read_bytes() + '0002,000,"ﾃｽﾄ","テスト",1\r\n'.encode())

        with pytest.raises(ValueError, match=r"^3 行目: .*UTF-8"):
            read_rows(src)

    def test_utf8_bom_reports_first_line(self, tmp_path):
        src = write_input(tmp_path / "in.txt", [BANK, BRANCH])
        src.write_bytes(b"\xef\xbb\xbf" + src.read_bytes())

        with pytest.raises(ValueError, match=r"^1 行目"):
            read_rows(src)

    def test_cr_only_line_endings(self, tmp_path):
        src = write_input(tmp_path / "in.txt", [BANK, BRANCH])
        src.write_bytes(src.read_bytes().replace(b"\r\n", b"\r"))

        banks, branches = read_rows(src)

        assert len(banks) == 1
        assert len(branches) == 1

    def test_no_trailing_newline(self, tmp_path):
        src = write_input(tmp_path / "in.txt", [BANK, BRANCH])
        src.write_bytes(src.read_bytes().rstrip(b"\r\n"))

        banks, branches = read_rows(src)

        assert len(banks) == 1
        assert len(branches) == 1

    def test_csv_error_reports_line_number(self, tmp_path):
        src = write_input(tmp_path / "in.txt", [BANK, '0001,001,"ﾃｽﾄ","テスト支店,2', BRANCH])

        with pytest.raises(ValueError, match=r"^3 行目付近: CSV として読めません"):
            read_rows(src)


class TestMain:
    def test_uses_default_paths(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        write_input(tmp_path / "ginkositen.txt", [BANK, BRANCH])

        main([])

        files = sorted(p.name for p in (tmp_path / "output").iterdir())
        assert len(files) == 2
        printed = capsys.readouterr().out
        for name in files:
            assert name in printed

    def test_argv_none_uses_sys_argv(self, tmp_path, monkeypatch, capsys):
        src = write_input(tmp_path / "in.txt", [BANK, BRANCH])
        monkeypatch.setattr(sys, "argv", ["bank_master_creator.py", "--input", str(src), "--check"])

        main()

        assert capsys.readouterr().out.startswith("銀行: 1 件、支店: 1 件\n")

    def test_output_dir_is_a_file_exits_1(self, tmp_path, capsys):
        src = write_input(tmp_path / "in.txt", [BANK, BRANCH])
        out = tmp_path / "out"
        out.write_text("file", encoding="utf-8")

        with pytest.raises(SystemExit) as excinfo:
            main(["--input", str(src), "--output-dir", str(out)])

        assert excinfo.value.code == 1
        assert capsys.readouterr().err == f"エラー: {out} はディレクトリではありません。\n"

    def test_input_and_output_dir_options(self, tmp_path, capsys):
        src = write_input(tmp_path / "data.txt", [BANK, BRANCH])
        out = tmp_path / "sql"

        main(["--input", str(src), "--output-dir", str(out)])

        assert len(list(out.iterdir())) == 2
        assert str(out) in capsys.readouterr().out

    def test_prints_summary_to_stderr(self, tmp_path, capsys):
        src = write_input(tmp_path / "in.txt", [BANK, BRANCH, BRANCH])

        main(["--input", str(src), "--output-dir", str(tmp_path / "out")])

        captured = capsys.readouterr()
        assert captured.err == "銀行 1 件、支店 2 件\n"
        assert "件" not in captured.out

    def test_invalid_row_exits_1_without_traceback(self, tmp_path, capsys):
        src = write_input(tmp_path / "in.txt", [BANK, BRANCH, BRANCH[:4]])
        out = tmp_path / "out"

        with pytest.raises(SystemExit) as excinfo:
            main(["--input", str(src), "--output-dir", str(out)])

        assert excinfo.value.code == 1
        assert capsys.readouterr().err == "エラー: 3 行目: 項目数が 4 です。\n"
        assert not out.exists()

    def test_missing_input_exits_1(self, tmp_path, capsys):
        with pytest.raises(SystemExit) as excinfo:
            main(["--input", str(tmp_path / "nothing.txt")])

        assert excinfo.value.code == 1
        assert capsys.readouterr().err == f"エラー: {tmp_path / 'nothing.txt'} が見つかりません。\n"

    def test_directory_input_exits_1_with_hint(self, tmp_path, capsys):
        with pytest.raises(SystemExit) as excinfo:
            main(["--input", str(tmp_path)])

        assert excinfo.value.code == 1
        err = capsys.readouterr().err
        assert err.startswith(f"エラー: {tmp_path} はディレクトリです")
        assert "Docker" in err

    def test_utf8_input_exits_1_with_hint(self, tmp_path, capsys):
        src = tmp_path / "in.txt"
        src.write_text('0001,000,"ﾃｽﾄ","テスト銀行",1\r\n', encoding="utf-8")

        with pytest.raises(SystemExit) as excinfo:
            main(["--input", str(src)])

        assert excinfo.value.code == 1
        assert capsys.readouterr().err == (
            "エラー: 1 行目: cp932 として読めません (UTF-8 で保存していませんか?)\n"
        )

    def test_empty_input_exits_1(self, tmp_path, capsys):
        src = write_input(tmp_path / "in.txt", ["", ""])

        with pytest.raises(SystemExit) as excinfo:
            main(["--input", str(src), "--output-dir", str(tmp_path / "out")])

        assert excinfo.value.code == 1
        assert capsys.readouterr().err == "エラー: 入力に行がありません。\n"
        assert not (tmp_path / "out").exists()

    def test_empty_input_is_fine_for_check(self, tmp_path, capsys):
        src = write_input(tmp_path / "in.txt", [""])

        main(["--input", str(src), "--check"])

        assert capsys.readouterr().out.startswith("銀行: 0 件、支店: 0 件\n")

    @pytest.mark.parametrize("mode", [[], ["--check"], ["--diff-from"]])
    def test_closed_stdout_is_tolerated(self, tmp_path, monkeypatch, capsys, mode):
        src = write_input(tmp_path / "in.txt", [BANK, BRANCH])
        monkeypatch.setattr(sys, "stdout", None)
        if mode == ["--diff-from"]:
            mode = ["--diff-from", str(src)]

        main(["--input", str(src), "--output-dir", str(tmp_path / "out"), *mode])

        assert "Traceback" not in capsys.readouterr().err

    def test_closed_stdout_fails_for_stdout_mode(self, tmp_path, monkeypatch, capsys):
        src = write_input(tmp_path / "in.txt", [BANK, BRANCH])
        monkeypatch.setattr(sys, "stdout", None)

        with pytest.raises(SystemExit) as excinfo:
            main(["--input", str(src), "--stdout"])

        assert excinfo.value.code == 1
        assert capsys.readouterr().err == "エラー: 標準出力が閉じています。\n"

    def test_unreadable_input_exits_1(self, tmp_path, capsys):
        src = write_input(tmp_path / "in.txt", [BANK, BRANCH])
        src.chmod(0)
        if _readable(src):
            pytest.skip("root など、権限に関係なく読める環境です。")

        with pytest.raises(SystemExit) as excinfo:
            main(["--input", str(src)])

        assert excinfo.value.code == 1
        assert capsys.readouterr().err == f"エラー: {src} を読めません (Permission denied)。\n"

    def test_output_parent_is_a_file_exits_1(self, tmp_path, capsys):
        src = write_input(tmp_path / "in.txt", [BANK, BRANCH])
        (tmp_path / "file").write_text("x", encoding="utf-8")

        with pytest.raises(SystemExit) as excinfo:
            main(["--input", str(src), "--output-dir", str(tmp_path / "file" / "out")])

        assert excinfo.value.code == 1
        assert capsys.readouterr().err == (
            f"エラー: {tmp_path / 'file' / 'out'} に書き出せません (Not a directory)。\n"
        )

    def test_help_mentions_options(self, capsys):
        with pytest.raises(SystemExit) as excinfo:
            main(["--help"])

        assert excinfo.value.code == 0
        out = capsys.readouterr().out
        assert "--input" in out
        assert "--output-dir" in out


def test_readme_options_table_matches_parser():
    """README の Options 表にある引数と argparse の引数が一致します。"""
    readme = (Path(__file__).parent.parent / "README.md").read_text(encoding="utf-8")
    documented = {
        line.split("`")[1].split()[0] for line in readme.splitlines() if line.startswith("| `--")
    }
    parser_options = {
        option for action in build_parser()._actions for option in action.option_strings
    }

    assert documented == parser_options - {"-h", "--help"}


def test_version_matches_pyproject(capsys):
    pyproject = tomllib.loads((Path(__file__).parent.parent / "pyproject.toml").read_text("utf-8"))

    with pytest.raises(SystemExit) as excinfo:
        main(["--version"])

    assert excinfo.value.code == 0
    assert capsys.readouterr().out == f"bank_master_creator.py {pyproject['project']['version']}\n"
    assert bank_master_creator.__version__ == pyproject["project"]["version"]


def test_old_python_is_rejected_with_one_line(tmp_path):
    script = Path(__file__).parent.parent / "bank_master_creator.py"
    source = script.read_text("utf-8").replace(
        "sys.version_info < (3, 11)", "sys.version_info < (99, 0)"
    )
    patched = tmp_path / "patched.py"
    patched.write_text(source, "utf-8")

    proc = subprocess.run(  # noqa: S603 (引数は固定です)
        [sys.executable, str(patched), "--version"], capture_output=True, timeout=30, check=False
    )

    assert proc.returncode == 1
    assert (
        proc.stderr.decode("utf-8")
        == f"エラー: Python 3.11 以上が必要です ({sys.version.split()[0]})。\n"
    )
    assert proc.stdout == b""
