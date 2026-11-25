import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from sample_data.make_sample import build
from p6_assistant import read_xer_bytes, run_checks
from p6_assistant.report import to_excel


def _result():
    _, tables = read_xer_bytes(build().encode("utf-8"))
    return run_checks(tables, "1")


def counts(res):
    return dict(zip(res["summary"]["key"], res["summary"]["Count"]))


def test_parser_reads_tables():
    _, tables = read_xer_bytes(build().encode("utf-8"))
    assert len(tables["TASK"]) == 17 and len(tables["TASKPRED"]) == 17


def test_seeded_defects_are_found():
    c = counts(_result())
    assert c["leads"] == 1
    assert c["lags"] == 1
    assert c["hard"] == 1
    assert c["neg_float"] == 1
    assert c["dups"] == 2          # both rows of the duplicated pair
    assert c["bad_links"] == 1
    assert c["loops"] == 1
    assert c["status"] == 1        # B110 active without an actual start
    assert c["bad_dates"] == 2     # future actual (E140) + forecast before data date (D110)
    assert c["high_dur"] == 1 and c["high_float"] >= 2


def test_open_ends():
    d = _result()["detail"]
    assert "E110" in set(d["no_pred"].task_code) and "E110" in set(d["no_succ"].task_code)
    assert "D100" in set(d["no_succ"].task_code)


def test_excel_export_has_summary():
    import io, openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(to_excel(_result())))
    assert "Summary" in wb.sheetnames
