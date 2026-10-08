from datetime import datetime, timedelta
from pathlib import Path

import pytest

import bank_master_creator
from bank_master_creator import (
    check,
    create,
    escape,
    main,
    make_bank_insert_sql,
    make_branch_insert_sql,
    quote,
    read_rows,
)

NOW = datetime(2026, 1, 2, 3, 4, 5)
BANK_SQL = "(20260102_030405)銀行マスタINSERT.sql"
BRANCH_SQL = "(20260102_030405)支店マスタINSERT.sql"

BANK = ("0001", "000", "ﾃｽﾄ", "テスト銀行", "1")
BRANCH = ("0001", "001", "ﾃｽﾄｼﾃﾝ", "テスト支店", "2")


def write_input(path: Path, lines: list[tuple[str, ...] | str]) -> Path:
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

    def test_utf8_and_lf_only(self, tmp_path):
        src = write_input(tmp_path / "in.txt", [BANK, BRANCH])

        for path in create(src, tmp_path, now=NOW):
            data = path.read_bytes()
            assert b"\r" not in data
            assert data.endswith(b";\n")
            data.decode("utf-8")

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

    def test_rejects_wrong_field_count(self, tmp_path):
        src = write_input(tmp_path / "in.txt", [BANK, BRANCH, BRANCH[:4]])

        with pytest.raises(ValueError, match="3 行目"):
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
    """fixtures/sample.txt からの出力が、保存済みの期待ファイルとバイト単位で一致します。"""
    fixtures = Path(__file__).parent / "fixtures"

    bank, branch = create(fixtures / "sample.txt", tmp_path, now=NOW)

    assert bank.read_bytes() == (fixtures / "bank.sql").read_bytes()
    assert branch.read_bytes() == (fixtures / "branch.sql").read_bytes()


class TestDeleteBeforeInsert:
    def test_default_has_no_transaction(self, tmp_path):
        src = write_input(tmp_path / "in.txt", [BANK, BRANCH])

        bank, _ = create(src, tmp_path, now=NOW)

        assert bank.read_text(encoding="utf-8") == (
            "SET NAMES utf8mb4;\n" + make_bank_insert_sql(list(BANK)) + "\n"
        )

    def test_bank_file_layout(self, tmp_path):
        src = write_input(tmp_path / "in.txt", [BANK, BRANCH])

        bank, _ = create(src, tmp_path, now=NOW, delete_before_insert=True)

        assert bank.read_text(encoding="utf-8").splitlines() == [
            "SET NAMES utf8mb4;",
            "START TRANSACTION;",
            "DELETE FROM m_banks;",
            make_bank_insert_sql(list(BANK)),
            "COMMIT;",
        ]

    def test_branch_file_deletes_branch_table_only(self, tmp_path):
        src = write_input(tmp_path / "in.txt", [BANK, BRANCH])

        _, branch = create(src, tmp_path, now=NOW, delete_before_insert=True)

        text = branch.read_text(encoding="utf-8")
        assert "DELETE FROM m_bank_branches;\n" in text
        assert "m_banks;" not in text

    def test_no_rows_still_clears_table(self, tmp_path):
        src = write_input(tmp_path / "in.txt", [BANK])

        _, branch = create(src, tmp_path, now=NOW, delete_before_insert=True)

        assert branch.read_text(encoding="utf-8").splitlines() == [
            "SET NAMES utf8mb4;",
            "START TRANSACTION;",
            "DELETE FROM m_bank_branches;",
            "COMMIT;",
        ]

    def test_lf_and_utf8(self, tmp_path):
        src = write_input(tmp_path / "in.txt", [BANK, BRANCH])

        for path in create(src, tmp_path, now=NOW, delete_before_insert=True):
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

    def test_check_function(self):
        report = check([bank_row()], [branch_row(), branch_row()])

        assert report.duplicate_branch_codes == ["0001-001"]
        assert report.problems

    def test_rejects_delete_before_insert(self, tmp_path, capsys):
        with pytest.raises(SystemExit) as excinfo:
            main(["--check", "--delete-before-insert"])

        assert excinfo.value.code == 2


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

    def test_help_mentions_options(self, capsys):
        with pytest.raises(SystemExit) as excinfo:
            main(["--help"])

        assert excinfo.value.code == 0
        out = capsys.readouterr().out
        assert "--input" in out
        assert "--output-dir" in out
