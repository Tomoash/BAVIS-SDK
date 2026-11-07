"""Tests of the Modbus ASCII example against a fake device behind a "converter" (TCP on 127.0.0.1, port chosen by the OS).

The connection uses ``socket://127.0.0.1:<port>`` as its serial port – exactly like a serial-to-Ethernet converter in
transparent mode – so the tests need neither hardware nor pyserial."""
import socket
import socketserver
import struct
import threading

import pytest

from bavis import sdk
from bavis.sdk import testing
from bavis_drv_modbus_ascii.drivers import modbus_ascii as mba

SPEC = mba.SPECS[0]


class _Handler(socketserver.StreamRequestHandler):
    def setup(self):
        super().setup()
        self.server.clients.append(self.connection)

    def handle(self):
        for raw in self.rfile:
            answer = self.server.answer(raw)
            if answer is not None:
                self.wfile.write(answer)


class FakeDevice(socketserver.ThreadingTCPServer):
    """Station 1 with holding registers 0–199 and input registers 0–49. Station 2 does not exist (no answer)."""
    daemon_threads = True

    def __init__(self):
        super().__init__(("127.0.0.1", 0), _Handler)
        self.port = self.server_address[1]
        self.hr = [0] * 200
        self.ir = [0] * 50
        self.requests: list[tuple[int, int, int]] = []          # (function, address, count) of every request
        self.clients: list[socket.socket] = []
        self.corrupt = False
        threading.Thread(target=self.serve_forever, daemon=True).start()

    def stop(self):
        for c in self.clients:
            try:
                c.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        self.shutdown()
        self.server_close()

    def answer(self, raw: bytes):
        body = mba.unframe(raw)
        unit, fc, data = body[0], body[1], body[2:]
        if unit != 1:
            return None
        addr, count = struct.unpack(">HH", data[:4])
        self.requests.append((fc, addr, count))
        if fc in (3, 4):
            table = self.hr if fc == 3 else self.ir
            if addr + count > len(table):
                return mba.frame(1, bytes([fc | 0x80, 2]))
            pdu = bytes([fc, 2 * count]) + struct.pack(f">{count}H", *table[addr:addr + count])
        elif fc == 6:
            self.hr[addr] = count
            pdu = bytes([fc]) + data
        elif fc == 16:
            self.hr[addr:addr + count] = struct.unpack(f">{count}H", data[5:5 + 2 * count])
            pdu = bytes([fc]) + data[:4]
        else:
            return mba.frame(1, bytes([fc | 0x80, 1]))
        out = mba.frame(1, pdu)
        return out[:-4] + b"00\r\n" if self.corrupt else out


@pytest.fixture
def dev():
    d = FakeDevice()
    yield d
    d.stop()


def _conn(port, unit=1, **params):
    return testing.connection("modbus_ascii", serial_port=f"socket://127.0.0.1:{port}", unit_id=unit, params=params)


def test_spec_is_valid():
    assert sdk.check_spec(SPEC) is None


@pytest.mark.parametrize("address,typ,ok", [("HR0", "uint16", True), ("ir65535", "int16", True), ("HR100", "float32", True),
                                            ("HR65535", "float32", False), ("HR1", "string", False), ("40001", "uint16", False),
                                            ("HR", "uint16", False), ("CO1", "bool", False)])
def test_check_address(address, typ, ok):
    assert (mba.check_address(address, typ) is None) is ok


def test_frame_and_lrc_match_the_specification():
    # read 1 holding register 0x0001 from station 0x11: LRC = -(0x11 + 0x03 + 0x00 + 0x01 + 0x00 + 0x01) & 0xFF = 0xEA
    assert mba.frame(0x11, bytes.fromhex("0300010001")) == b":110300010001EA\r\n"
    assert mba.unframe(b":110300010001EA\r\n") == bytes.fromhex("110300010001")
    with pytest.raises(sdk.DriverError):
        mba.unframe(b":110300010001EB\r\n")


def test_neighbouring_registers_are_read_in_one_request(dev):
    dev.hr[10:16] = [0xFFFF, 7, 1, *struct.unpack(">HH", struct.pack(">f", 21.5)), 0]
    dev.ir[3] = 1234
    conn = _conn(dev.port)
    tags = testing.tags(conn, [("A", "HR10", "int16"), ("B", "HR11", "uint16"), ("ON", "HR12", "bool"),
                               ("T", "HR13", "float32"), ("P", "IR3", "uint16")])
    assert testing.poll_once(conn, tags, spec=SPEC) == {"A": -1, "B": 7, "ON": True, "T": 21.5, "P": 1234}
    assert dev.requests == [(3, 10, 5), (4, 3, 1)]


def test_word_swap():
    words = mba.encode(100000, "int32", True)
    assert words == [100000 & 0xFFFF, 100000 >> 16] and mba.decode(words, "int32", True) == 100000


def test_writes_are_off_by_default_and_verified(dev):
    tags_def = [("SP", "HR20", "uint16", "rw"), ("SP32", "HR30", "float32", "rw"), ("IN", "IR1", "uint16", "rw")]
    conn = _conn(dev.port)
    tags = testing.tags(conn, tags_def)
    with testing.run_driver(conn, tags, spec=SPEC) as run:
        assert testing.wait_for(lambda: run.sink.connected)
        with pytest.raises(sdk.DriverError, match="vypnutý"):
            run.driver.write(tags[0], 5)
    conn = _conn(dev.port, allow_writes=True)
    tags = testing.tags(conn, tags_def)
    with testing.run_driver(conn, tags, spec=SPEC) as run:
        assert testing.wait_for(lambda: run.sink.connected)
        run.driver.write(tags[0], 55)
        run.driver.write(tags[1], 1.5)
        assert dev.hr[20] == 55 and struct.unpack(">f", struct.pack(">HH", *dev.hr[30:32]))[0] == 1.5
        assert (6, 20, 55) in dev.requests and (16, 30, 2) in dev.requests
        with pytest.raises(sdk.DriverError, match="nejde zapsat"):          # input registers are read only
            run.driver.write(tags[2], 1)
        assert testing.wait_for(lambda: run.sink.values.get("SP32") == 1.5)


def test_exception_answer_becomes_an_operator_message(dev):
    conn = _conn(dev.port)
    tags = testing.tags(conn, [("X", "HR199", "float32")])         # 199 + 2 registers > 200 → exception 2
    with pytest.raises(sdk.DriverError, match="neplatná adresa"):
        testing.poll_once(conn, tags, spec=SPEC)


def test_bad_checksum_and_missing_station(dev):
    conn = _conn(dev.port)
    tags = testing.tags(conn, [("A", "HR0")])
    dev.corrupt = True
    with pytest.raises(sdk.DriverError, match="LRC"):
        testing.poll_once(conn, tags, spec=SPEC)
    dev.corrupt = False
    conn = _conn(dev.port, unit=2)
    with pytest.raises(sdk.DriverError, match="neodpověděla"):
        testing.poll_once(conn, testing.tags(conn, [("A", "HR0")]), spec=SPEC)


def test_connection_test_button(dev):
    assert mba.test_once(_conn(dev.port), sdk.TestCtx(data_dir="."))["msg"] == "stanice 1 odpovídá"
    assert mba.validate(testing.connection("modbus_ascii")) == [("serial_port", mba.E_PORT)]
