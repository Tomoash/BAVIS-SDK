"""Tests of the SCPI example against a fake power supply (socketserver on 127.0.0.1, port chosen by the OS)."""
import socket
import socketserver
import threading

import pytest

from bavis import sdk
from bavis.sdk import testing
from bavis_drv_scpi.drivers import scpi

SPEC = scpi.SPECS[0]


class _Handler(socketserver.StreamRequestHandler):
    def setup(self):
        super().setup()
        self.server.clients.append(self.connection)

    def handle(self):
        dev = self.server
        for raw in self.rfile:
            line = raw.decode("ascii").strip()
            dev.log.append(line)
            answer = dev.answer(line)
            if answer is not None:
                self.wfile.write((answer + "\n").encode("ascii"))


class FakePowerSupply(socketserver.ThreadingTCPServer):
    """A one-channel power supply: VOLT / CURR / OUTP settings, MEAS:VOLT? / MEAS:CURR? measurements, an error queue."""
    daemon_threads = True

    def __init__(self):
        super().__init__(("127.0.0.1", 0), _Handler)
        self.port = self.server_address[1]
        self.state = {"VOLT": 5.0, "CURR": 0.5, "OUTP": 0}
        self.errors: list[str] = []
        self.log: list[str] = []
        self.clients: list[socket.socket] = []
        threading.Thread(target=self.serve_forever, daemon=True).start()

    def stop(self):
        """The instrument disappears: close the open connections and stop listening."""
        for c in self.clients:
            try:
                c.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        self.shutdown()
        self.server_close()

    def answer(self, line: str):
        head, _, arg = line.partition(" ")
        if head == "*IDN?":
            return "FAKE,PSU-1,0001,1.0"
        if head == "SYST:ERR?":
            return self.errors.pop(0) if self.errors else '+0,"No error"'
        if head == "MEAS:VOLT?":
            return f"{self.state['VOLT'] if self.state['OUTP'] else 0.0:+.8E}"
        if head == "MEAS:CURR?":
            return "+9.91000000E+37"                          # overload → no valid value
        if head.endswith("?") and head[:-1] in self.state:
            v = self.state[head[:-1]]
            return str(v) if head == "OUTP?" else f"{v:+.8E}"
        if head in self.state and arg:
            if head == "VOLT" and float(arg) > 30:
                self.errors.append('-222,"Data out of range"')
            else:
                self.state[head] = int(arg) if head == "OUTP" else float(arg)
            return None
        self.errors.append('-113,"Undefined header"')
        return None if not head.endswith("?") else ""


@pytest.fixture
def psu():
    dev = FakePowerSupply()
    yield dev
    dev.stop()


def _conn(port, **params):
    return testing.connection("scpi", port=port, params=params)


def test_spec_is_valid():
    assert sdk.check_spec(SPEC) is None


@pytest.mark.parametrize("address,ok", [("MEAS:VOLT?", True), ("meas:volt? (@1,2)", True), ("VOLT", True), ("*IDN?", True),
                                        ("", False), ("VOLT 5", False), ("MEAS VOLT?", False), ("1VOLT", False)])
def test_check_address(address, ok):
    assert (scpi.check_address(address, "float32") is None) is ok


def test_read_command_and_decode():
    assert scpi.read_command("volt") == "VOLT?" and scpi.read_command("MEAS:VOLT? (@2)") == "MEAS:VOLT? (@2)"
    assert scpi.decode("+1.25000000E+01", "float32") == 12.5 and scpi.decode("ON", "bool") is True
    assert scpi.decode("9.91E+37", "float32") is None and scpi.decode('"abc"', "string") == "abc"


def test_poll_reads_settings_and_measurements(psu):
    psu.state["OUTP"] = 1
    conn = _conn(psu.port)
    tags = testing.tags(conn, [("U", "MEAS:VOLT?"), ("I", "MEAS:CURR?"), ("U_SET", "VOLT", "float32", "rw"),
                               ("ON", "OUTP", "bool", "rw")])
    assert testing.poll_once(conn, tags, spec=SPEC) == {"U": 5.0, "I": None, "U_SET": 5.0, "ON": True}
    assert psu.log == ["MEAS:VOLT?", "MEAS:CURR?", "VOLT?", "OUTP?"]


def test_writes_are_off_by_default_and_checked(psu):
    conn = _conn(psu.port)
    tags = testing.tags(conn, [("U_SET", "VOLT", "float32", "rw"), ("U", "MEAS:VOLT?", "float32", "rw")])
    with testing.run_driver(conn, tags, spec=SPEC) as run:
        assert testing.wait_for(lambda: run.sink.connected)
        with pytest.raises(sdk.DriverError, match="vypnutý"):
            run.driver.write(tags[0], 12.0)
    conn = _conn(psu.port, allow_writes=True)
    with testing.run_driver(conn, tags, spec=SPEC) as run:
        assert testing.wait_for(lambda: run.sink.connected)
        run.driver.write(tags[0], 12.0)
        assert psu.state["VOLT"] == 12.0 and "VOLT 12.0" in psu.log
        with pytest.raises(sdk.DriverError, match="Data out of range"):     # the instrument refused the value
            run.driver.write(tags[0], 50.0)
        with pytest.raises(sdk.DriverError, match="dotaz"):                 # a query is never written
            run.driver.write(tags[1], 1.0)
        assert testing.wait_for(lambda: run.sink.values.get("U_SET") == 12.0)


def test_lost_instrument_disconnects_and_tags_lose_values(psu):
    conn = _conn(psu.port)
    tags = testing.tags(conn, [("U_SET", "VOLT")])
    with testing.run_driver(conn, tags, spec=SPEC) as run:
        assert testing.wait_for(lambda: run.sink.values.get("U_SET") == 5.0)
        psu.stop()
        assert testing.wait_for(lambda: not run.sink.connected, timeout=10)
        assert run.sink.values["U_SET"] is None


def test_connection_test_button(psu):
    r = scpi.test_once(_conn(psu.port), sdk.TestCtx(data_dir="."))
    assert r["msg"].endswith("FAKE,PSU-1,0001,1.0")
    with pytest.raises(sdk.DriverError):
        scpi.test_once(_conn(testing.free_port()), sdk.TestCtx(data_dir="."))
