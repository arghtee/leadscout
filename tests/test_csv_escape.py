import csv
import io

import pytest

from leadscout.export.csv_export import UTF8_BOM, escape_cell, write_csv


@pytest.mark.parametrize(
    "value",
    [
        "=1+1",
        '=HYPERLINK("http://evil.example","x")',
        "+SUM(A1)",
        "-2+3",
        "@SUM(A1)",
        "\t=1",
        "\r=1",
    ],
)
def test_ac12_formula_prefixes_are_escaped(value: str) -> None:
    """AC-12: a cell value beginning with '=' (or + - @ TAB CR) is neutralised."""
    assert escape_cell(value) == "'" + value


@pytest.mark.parametrize("value", ["Jane Smith", "", "O'Brien", "1 High St", "a=b"])
def test_safe_values_untouched(value: str) -> None:
    assert escape_cell(value) == value


def test_e164_phone_preserved_only_in_phone_column() -> None:
    assert escape_cell("+447700900123", column="phone") == "+447700900123"
    assert escape_cell("+447700900123", column="name") == "'+447700900123"


@pytest.mark.parametrize("value", ["+44 7700 900123", "+1-202-555", "+SUM(A1)", "+0123"])
def test_non_e164_phone_still_escaped(value: str) -> None:
    assert escape_cell(value, column="phone") == "'" + value


def test_write_csv_rfc4180_quoting_and_crlf() -> None:
    rows = [{"a": 'He said "hi", then left', "b": "line1\nline2"}]
    out = write_csv(rows, ["a", "b"])
    assert out.startswith("a,b\r\n")
    assert '"He said ""hi"", then left"' in out
    parsed = list(csv.reader(io.StringIO(out, newline="")))
    assert parsed == [["a", "b"], ['He said "hi", then left', "line1\nline2"]]


def test_write_csv_escapes_injection_in_written_output() -> None:
    out = write_csv([{"name": "=cmd|' /C calc'!A0"}], ["name"])
    parsed = list(csv.reader(io.StringIO(out, newline="")))
    assert parsed[1] == ["'=cmd|' /C calc'!A0"]


def test_bom_optional() -> None:
    assert not write_csv([], ["a"]).startswith(UTF8_BOM)
    assert write_csv([], ["a"], bom=True).startswith(UTF8_BOM + "a")
