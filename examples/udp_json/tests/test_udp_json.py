"""Tests of the UDP JSON example: datagrams sent from the test to a port chosen by the OS."""
import json
import socket
import threading
import time

import pytest

from bavis import sdk
from bavis.sdk import testing
from bavis_drv_udp_json.drivers import udp_json

SPEC = udp_json.SPECS[0]


def send(port: int, doc) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.sendto(doc if isinstance(doc, bytes) else json.dumps(doc).encode(), ("127.0.0.1", port))


def _conn(port, **params):
    return testing.connection("udp_json", port=port, poll_ms=50, params=params)


def test_spec_is_valid():
    assert sdk.check_spec(SPEC) is None


@pytest.mark.parametrize("address,ok", [("temp", True), ("cellar/temp", True), ("dev-1.a/hum_2", True),
                                        ("", False), ("a/b/c", False), ("te mp", False), ("/temp", False)])
def test_check_address(address, ok):
    assert (udp_json.check_address(address, "float32") is None) is ok


def test_validate_sender():
    assert udp_json.validate(_conn(1, sender="192.168.0.5")) == []
    assert udp_json.validate(_conn(1, sender="esp32.local"))[0][0] == "params.sender"


def test_values_are_pushed_and_routed_by_device():
    port = testing.free_port(socket.SOCK_DGRAM)
    conn = _conn(port)
    tags = testing.tags(conn, [("T_ANY", "temp"), ("T_CELLAR", "cellar/temp"), ("DOOR", "door", "bool"),
                               ("NAME", "name", "string")])
    with testing.run_driver(conn, tags, spec=SPEC) as run:
        assert testing.wait_for(lambda: run.sink.connected)
        send(port, {"device": "garden", "temp": 18.5, "door": True, "name": "garden"})
        assert testing.wait_for(lambda: run.sink.values.get("T_ANY") == 18.5)
        assert run.sink.values["DOOR"] is True and run.sink.values["NAME"] == "garden"
        assert "T_CELLAR" not in run.sink.values                   # another device – the tag was not touched
        send(port, {"device": "cellar", "temp": 9.0})
        assert testing.wait_for(lambda: run.sink.values.get("T_CELLAR") == 9.0 and run.sink.values.get("T_ANY") == 9.0)
        send(port, b"not json")                                    # ignored, nothing breaks
        send(port, [1, 2, 3])
        time.sleep(0.2)
        assert run.sink.connected


def test_sender_filter():
    port = testing.free_port(socket.SOCK_DGRAM)
    conn = _conn(port, sender="10.255.255.1")                     # nobody in the test sends from this address
    tags = testing.tags(conn, [("T", "temp")])
    with testing.run_driver(conn, tags, spec=SPEC) as run:
        assert testing.wait_for(lambda: run.sink.connected)
        send(port, {"temp": 1.0})
        time.sleep(0.3)
        assert "T" not in run.sink.values


def test_stale_values_and_silence_disconnect():
    port = testing.free_port(socket.SOCK_DGRAM)
    conn = _conn(port, max_age_s=1)
    tags = testing.tags(conn, [("T", "temp")])
    with testing.run_driver(conn, tags, spec=SPEC) as run:
        assert testing.wait_for(lambda: run.sink.connected)
        send(port, {"temp": 3.5})
        assert testing.wait_for(lambda: run.sink.values.get("T") == 3.5)
        assert testing.wait_for(lambda: not run.sink.connected and run.sink.values.get("T") is None, timeout=5)
        assert "UDP" in run.sink.statuses[-1]["last_error"]
        send(port, {"temp": 4.0})                                  # data again → reconnects after the 2 s pause
        stop = threading.Event()

        def keep_sending():
            while not stop.is_set():
                send(port, {"temp": 4.0})
                time.sleep(0.1)
        th = threading.Thread(target=keep_sending, daemon=True)
        th.start()
        try:
            assert testing.wait_for(lambda: run.sink.connected and run.sink.values.get("T") == 4.0, timeout=8)
        finally:
            stop.set()
            th.join()


def test_connection_test_button():
    port = testing.free_port(socket.SOCK_DGRAM)
    conn = _conn(port)
    timer = threading.Timer(0.3, send, (port, {"temp": 1, "hum": 2}))
    timer.start()
    r = udp_json.test_once(conn, sdk.TestCtx(data_dir="."))
    assert "2" in r["msg"] and "127.0.0.1" in r["msg"]


def test_port_in_use_is_reported():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as busy:
        busy.bind(("127.0.0.1", 0))
        conn = _conn(busy.getsockname()[1])
        with pytest.raises(sdk.DriverError, match="nelze otevřít"):
            testing.poll_once(conn, testing.tags(conn, [("T", "temp")]), spec=SPEC)
