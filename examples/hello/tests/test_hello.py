"""Tests of the Hello example: no fake device is needed – the driver generates its values itself."""
import pytest

from bavis import sdk
from bavis.sdk import testing
from bavis_drv_hello.drivers import hello

SPEC = hello.SPECS[0]


def test_spec_is_valid():
    assert sdk.check_spec(SPEC) is None


@pytest.mark.parametrize("address,typ,ok", [("counter", "int32", True), ("SINE", "float32", True), ("setpoint", "float32", True),
                                            ("greeting", "string", True), ("greeting", "float32", False), ("", "float32", False),
                                            ("cosine", "float32", False)])
def test_check_address(address, typ, ok):
    assert (hello.check_address(address, typ) is None) is ok


def test_one_cycle_returns_every_tag():
    conn = testing.connection("hello", params={"period_s": 10})
    tags = testing.tags(conn, [("N", "counter", "int32"), ("S", "sine"), ("SP", "setpoint", "float32", "rw"),
                               ("HI", "greeting", "string")])
    vals = testing.poll_once(conn, tags, spec=SPEC)
    assert vals["N"] == 1 and -1.0 <= vals["S"] <= 1.0 and vals["SP"] == 0.0 and vals["HI"] == "Hello from BAVIS"


def test_counter_runs_and_setpoint_is_written_back():
    conn = testing.connection("hello")
    tags = testing.tags(conn, [("N", "counter", "int32"), ("SP", "setpoint", "float32", "rw"), ("S", "sine", "float32", "rw")])
    with testing.run_driver(conn, tags, spec=SPEC) as run:
        assert testing.wait_for(lambda: run.sink.connected and (run.sink.values.get("N") or 0) >= 3)
        run.driver.write(tags[1], 42)
        assert testing.wait_for(lambda: run.sink.values.get("SP") == 42.0)
        with pytest.raises(sdk.DriverError, match="jen číst"):        # only the setpoint can be written
            run.driver.write(tags[2], 1.0)
