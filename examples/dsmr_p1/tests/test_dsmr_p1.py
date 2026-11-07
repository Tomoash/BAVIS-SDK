"""Tests of the P1 example against a fake P1 bridge (TCP on 127.0.0.1, port chosen by the OS) that pushes telegrams.

The connection uses ``socket://127.0.0.1:<port>`` as its serial port, like a P1-to-Wi-Fi bridge – no hardware, no pyserial."""
import socket
import threading
import time

import pytest

from bavis import sdk
from bavis.sdk import testing
from bavis_drv_dsmr_p1.drivers import dsmr_p1 as p1

SPEC = p1.SPECS[0]

BODY = ("/XMX5LGBBFG1012345678\r\n\r\n"
        "1-3:0.2.8(50)\r\n"
        "0-0:1.0.0(240101120000W)\r\n"
        "1-0:1.8.1({t1:010.3f}*kWh)\r\n"
        "1-0:1.8.2(002345.678*kWh)\r\n"
        "1-0:2.8.1(000100.000*kWh)\r\n"
        "0-0:96.14.0(0002)\r\n"
        "1-0:1.7.0({p:06.3f}*kW)\r\n"
        "1-0:32.7.0(230.1*V)\r\n"
        "0-1:24.2.1(240101115500W)(01234.567*m3)\r\n"
        "!")


def telegram(t1=1234.567, p=1.5, crc=True, broken=False) -> bytes:
    body = BODY.format(t1=t1, p=p).encode("ascii")
    check = p1.crc16(body) ^ (1 if broken else 0)
    return body + (f"{check:04X}".encode() if crc else b"") + b"\r\n"


class FakeBridge:
    """Accepts one client and sends it what the test puts into ``send()`` – like a meter behind a P1 bridge."""

    def __init__(self):
        self.srv = socket.socket()
        self.srv.bind(("127.0.0.1", 0))
        self.srv.listen(1)
        self.port = self.srv.getsockname()[1]
        self.client = None
        self.ready = threading.Event()
        threading.Thread(target=self._accept, daemon=True).start()

    def _accept(self):
        try:
            self.client, _ = self.srv.accept()
            self.ready.set()
        except OSError:
            pass

    def send(self, data: bytes, pieces=1):
        assert self.ready.wait(5)
        step = max(1, len(data) // pieces)
        for i in range(0, len(data), step):                  # a slow serial line delivers a telegram in parts
            self.client.sendall(data[i:i + step])
            time.sleep(0.01)

    def stop(self):
        for s in (self.client, self.srv):
            if s:
                s.close()


@pytest.fixture
def bridge():
    b = FakeBridge()
    yield b
    b.stop()


def _conn(port, **params):
    return testing.connection("dsmr_p1", serial_port=f"socket://127.0.0.1:{port}", poll_ms=50, params=params)


def test_spec_is_valid():
    assert sdk.check_spec(SPEC) is None


@pytest.mark.parametrize("address,ok", [("1-0:1.8.1", True), ("0-1:24.2.1", True), ("1-0:32.7.0", True), ("1.8.1", False),
                                        ("", False), ("1-0:1.8", False), ("A-0:1.8.1", False)])
def test_check_address(address, ok):
    assert (p1.check_address(address, "float64") is None) is ok


def test_crc16_is_crc16_arc():
    assert p1.crc16(b"123456789") == 0xBB3D                  # standard check value of CRC-16/ARC


def test_extract_keeps_good_telegrams_and_rejects_broken_ones():
    t = telegram()
    good, bad, rest = p1.extract(b"noise" + t[:40] + t + telegram(broken=True) + telegram(crc=False) + t[:30])
    assert good == [t[:t.index(b"!") + 1]] * 2 and len(bad) == 2 and rest == t[:30]


def test_values_from_telegrams_arriving_in_parts(bridge):
    conn = _conn(bridge.port)
    tags = testing.tags(conn, [("E1", "1-0:1.8.1", "float64"), ("P", "1-0:1.7.0"), ("TARIF", "0-0:96.14.0", "uint8"),
                               ("U1", "1-0:32.7.0"), ("GAS", "0-1:24.2.1", "float64"), ("NONE", "1-0:99.9.9"),
                               ("TIME", "0-0:1.0.0", "string")])
    with testing.run_driver(conn, tags, spec=SPEC) as run:
        bridge.send(telegram(), pieces=7)
        assert testing.wait_for(lambda: run.sink.values.get("E1") == 1234.567)
        assert run.sink.connected
        assert {k: run.sink.values[k] for k in ("P", "TARIF", "U1", "GAS", "NONE", "TIME")} == {
            "P": 1.5, "TARIF": 2, "U1": 230.1, "GAS": 1234.567, "NONE": None, "TIME": "240101120000W"}
        bridge.send(telegram(t1=1234.999, p=2.25, broken=True))           # wrong CRC → ignored
        bridge.send(telegram(t1=1235.0, p=0.75))
        assert testing.wait_for(lambda: run.sink.values.get("P") == 0.75)
        assert run.sink.values["E1"] == 1235.0
        with pytest.raises(sdk.DriverError, match="jen číst"):
            run.driver.write(tags[0], 1.0)


def test_silent_meter_is_a_connection_error(bridge):
    conn = _conn(bridge.port, max_age_s=1)
    tags = testing.tags(conn, [("P", "1-0:1.7.0")])
    with testing.run_driver(conn, tags, spec=SPEC) as run:
        assert testing.wait_for(lambda: run.sink.connected)
        assert testing.wait_for(lambda: any("telegram" in (s.get("last_error") or "") for s in run.sink.statuses), timeout=5)


def test_connection_test_button(bridge):
    threading.Timer(0.2, lambda: bridge.send(telegram())).start()
    msg = p1.test_once(_conn(bridge.port, max_age_s=3), sdk.TestCtx(data_dir="."))["msg"]
    assert msg.endswith("telegram XMX5LGBBFG1012345678, 9 hodnot")
    assert p1.validate(testing.connection("dsmr_p1")) == [("serial_port", p1.E_PORT)]
