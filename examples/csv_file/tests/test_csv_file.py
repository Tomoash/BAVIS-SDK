"""Tests of the CSV file example: a log file in pytest's tmp_path that the test keeps appending to."""
import os
import time

import pytest

from bavis import sdk
from bavis.sdk import testing
from bavis_drv_csv_file.drivers import csv_file

SPEC = csv_file.SPECS[0]
HEADER = "time;temp_in;temp_out;state;alarm\n"


@pytest.fixture
def log(tmp_path):
    path = tmp_path / "logger" / "mereni.csv"
    path.parent.mkdir()
    path.write_text(HEADER + "2026-11-06 10:00:00;21,5;8,2;RUN;0\n", encoding="utf-8")
    return path


def append(path, line):
    with open(path, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    st = os.stat(path)
    os.utime(path, (st.st_atime, st.st_mtime + 1))         # coarse file systems: make sure the change time moves


def _conn(**params):
    return testing.connection("csv_file", host="", params={"path": "logger/mereni.csv", **params})


def test_spec_is_valid():
    assert sdk.check_spec(SPEC) is None


@pytest.mark.parametrize("address,ok", [("temp_in", True), ("Teplota venku", True), ("", False), ("a;b", False)])
def test_check_address(address, ok):
    assert (csv_file.check_address(address, "float32") is None) is ok


def test_reads_the_last_row_relative_to_data_dir(log):
    conn = _conn()
    tags = testing.tags(conn, [("TIN", "temp_in"), ("TOUT", "temp_out"), ("STATE", "state", "string"),
                               ("ALARM", "alarm", "bool"), ("NOPE", "humidity")])
    vals = testing.poll_once(conn, tags, spec=SPEC, data_dir=str(log.parent.parent))
    assert vals == {"TIN": 21.5, "TOUT": 8.2, "STATE": "RUN", "ALARM": False, "NOPE": None}


def test_follows_new_rows_and_caches(log):
    conn = _conn()
    tags = testing.tags(conn, [("TIN", "temp_in")])
    with testing.run_driver(conn, tags, spec=SPEC, data_dir=str(log.parent.parent)) as run:
        assert testing.wait_for(lambda: run.sink.values.get("TIN") == 21.5)
        append(log, "2026-11-06 10:01:00;22,0;8,1;RUN;1")
        assert testing.wait_for(lambda: run.sink.values.get("TIN") == 22.0)
        assert run.driver.mtime == os.stat(log).st_mtime


def test_large_file_reads_only_the_tail(tmp_path):
    path = tmp_path / "big.csv"
    rows = "".join(f"2026-11-06 10:{i % 60:02d}:00;{i},0;0;RUN;0\n" for i in range(20000))
    path.write_text(HEADER + rows, encoding="utf-8")
    assert os.path.getsize(path) > csv_file.TAIL_BYTES
    conn = _conn(path=str(path))
    assert testing.poll_once(conn, testing.tags(conn, [("TIN", "temp_in")]), spec=SPEC) == {"TIN": 19999.0}


def test_dot_decimal_and_comma_separator(tmp_path):
    path = tmp_path / "en.csv"
    path.write_text("t,temp\n1,21.25\n", encoding="utf-8")
    conn = _conn(path=str(path), separator="comma", decimal="dot")
    assert testing.poll_once(conn, testing.tags(conn, [("T", "temp")]), spec=SPEC) == {"T": 21.25}


def test_errors_disconnect(log, tmp_path):
    conn = _conn(path=str(tmp_path / "missing.csv"))
    with pytest.raises(sdk.DriverError, match="neexistuje"):
        testing.poll_once(conn, testing.tags(conn, [("T", "temp_in")]), spec=SPEC)
    with pytest.raises(sdk.DriverError, match=".csv"):
        csv_file.read_file(str(tmp_path / "secret.ini"), ";")
    old = time.time() - 3600
    os.utime(log, (old, old))
    conn = _conn(max_age_s=60)
    with pytest.raises(sdk.DriverError, match="nezměnil"):
        testing.poll_once(conn, testing.tags(conn, [("T", "temp_in")]), spec=SPEC, data_dir=str(log.parent.parent))
    conn = _conn()
    with pytest.raises(sdk.DriverError, match="nemá sloupce"):
        testing.poll_once(conn, testing.tags(conn, [("T", "humidity")]), spec=SPEC, data_dir=str(log.parent.parent))


def test_browse_and_import_tags(log):
    ctx = sdk.TestCtx(data_dir=str(log.parent.parent))
    res = csv_file.browse(_conn(), ctx)
    assert res["flat"] and [i["address"] for i in res["items"]] == ["time", "temp_in", "temp_out", "state", "alarm"]
    assert {i["address"]: i["type"] for i in res["items"]}["temp_in"] == "float32"
    out = csv_file.items_to_tags(res["items"][1:3] + [{"name": "Teplota venku", "address": "Teplota venku"}], "c1", "csv_", "Log")
    names = [t["name"] for t in out["tags"]]
    assert names == ["csv_temp_in", "csv_temp_out", "csv_Teplota_venku"]
    project = {"name": "x", "connections": [{"id": "c1", "driver": "csv_file", "params": {"path": "logger/mereni.csv"}}],
               "tags": out["tags"]}
    _p, errs = sdk.validate_project(project)
    assert errs == []


def test_connection_test_button(log):
    r = csv_file.test_once(_conn(), sdk.TestCtx(data_dir=str(log.parent.parent)))
    assert r["msg"].startswith("mereni.csv: 5 sloupců")
