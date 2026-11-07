"""Tests of the NTP example against a fake time server (UDP on 127.0.0.1, port chosen by the OS)."""
import socket
import struct
import threading
import time

import pytest

from bavis import sdk
from bavis.sdk import testing
from bavis_drv_ntp.drivers import ntp

SPEC = ntp.SPECS[0]


class FakeTimeServer:
    """Answers client packets like an NTP server whose clock is ``offset`` seconds ahead of ours."""

    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", 0))
        self.port = self.sock.getsockname()[1]
        self.offset, self.stratum, self.leap, self.refid = 0.25, 1, 0, b"GPS\0"
        self.stray = False                   # send a foreign datagram first (must be ignored)
        self.silent = False
        self.queries = 0
        self.running = True
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self):
        while self.running:
            try:
                data, addr = self.sock.recvfrom(1024)
            except OSError:
                return
            self.queries += 1
            if self.silent:
                continue
            fields = ntp.PACKET.unpack_from(data)
            assert fields[0] & 0x07 == 3 and fields[0] >> 3 & 0x07 == 4          # client, version 4
            now = ntp.to_ntp(time.time() + self.offset)
            if self.stray:
                self.sock.sendto(ntp.PACKET.pack(0x24, 1, 0, 0, 0, 0, b"GPS\0", 0, 12345, now, now), addr)
            reply = ntp.PACKET.pack(self.leap << 6 | 4 << 3 | 4, self.stratum, 6, -20, 0x00008000, 0x00000100, self.refid,
                                    now, fields[10], now, now)
            self.sock.sendto(reply, addr)

    def stop(self):
        self.running = False
        self.sock.close()


@pytest.fixture
def server():
    s = FakeTimeServer()
    yield s
    s.stop()


@pytest.fixture
def fast(monkeypatch):
    monkeypatch.setattr(ntp, "MIN_INTERVAL_S", 0.0)                     # tests may ask often – a real server not


def _conn(port, **params):
    return testing.connection("ntp", port=port, params=params)


def test_spec_is_valid():
    assert sdk.check_spec(SPEC) is None


@pytest.mark.parametrize("address,typ,ok", [("offset_ms", "float32", True), ("SYNCED", "bool", True), ("refid", "string", True),
                                            ("refid", "float32", False), ("offset", "float32", False), ("", "float32", False)])
def test_check_address(address, typ, ok):
    assert (ntp.check_address(address, typ) is None) is ok


def test_timestamps_round_trip():
    t = 1_700_000_000.123456
    assert abs(ntp.from_ntp(ntp.to_ntp(t)) - t) < 1e-6
    assert ntp.short(0x00008000) == 500.0


def test_offset_and_server_state(server, fast):
    server.stray = True
    conn = _conn(server.port, min_interval_s=0)
    tags = testing.tags(conn, [("OFS", "offset_ms"), ("DLY", "delay_ms"), ("ST", "stratum", "uint8"), ("OK", "synced", "bool"),
                               ("REF", "refid", "string"), ("RD", "root_delay_ms"), ("NOW", "server_time", "float64")])
    v = testing.poll_once(conn, tags, spec=SPEC)
    assert 200 < v["OFS"] < 300 and 0 <= v["DLY"] < 200
    assert v["ST"] == 1 and v["OK"] is True and v["REF"] == "GPS" and v["RD"] == 500.0
    assert abs(v["NOW"] - (time.time() + 0.25)) < 1


def test_unsynchronised_server_and_kiss_code(server, fast):
    conn = _conn(server.port)
    tags = testing.tags(conn, [("OK", "synced", "bool"), ("REF", "refid", "string")])
    server.leap, server.stratum, server.refid = 3, 2, socket.inet_aton("10.0.0.5")
    assert testing.poll_once(conn, tags, spec=SPEC) == {"OK": False, "REF": "10.0.0.5"}
    server.leap, server.stratum, server.refid = 0, 0, b"RATE"
    with pytest.raises(sdk.DriverError, match="RATE"):
        testing.poll_once(conn, tags, spec=SPEC)


def test_queries_are_limited_by_the_interval(server):
    conn = testing.connection("ntp", port=server.port, poll_ms=20, params={"min_interval_s": 1})
    tags = testing.tags(conn, [("OFS", "offset_ms")])
    with testing.run_driver(conn, tags, spec=SPEC) as run:
        assert testing.wait_for(lambda: run.sink.values.get("OFS") is not None)
        time.sleep(0.5)
        assert server.queries == 1                     # many read cycles, one query (the minimum is 16 s)


def test_silent_server(server, fast):
    server.silent = True
    conn = _conn(server.port)
    with pytest.raises(sdk.DriverError, match="neodpověděl"):
        testing.poll_once(conn, testing.tags(conn, [("OFS", "offset_ms")]), spec=SPEC)
    server.silent = False
    assert "stratum 1" in ntp.test_once(conn, sdk.TestCtx(data_dir="."))["msg"]
