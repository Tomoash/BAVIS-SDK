"""Tests of the HTTP JSON example against a fake device (http.server on a port chosen by the OS)."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from bavis import sdk
from bavis.sdk import testing
from bavis_drv_http_json.drivers import http_json

DOC = {"temperature": 21.5, "on": True, "name": "boiler", "boiler": {"flow": {"temp": 55}}, "sensors": [{"value": 1}, {"value": "2.5"}]}


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        dev = self.server
        dev.paths.append(self.path)
        body = dev.body if isinstance(dev.body, bytes) else json.dumps(dev.body).encode()
        self.send_response(dev.status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture
def dev():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    srv.body, srv.status, srv.paths = DOC, 200, []
    srv.port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv
    srv.shutdown()
    srv.server_close()


def _conn(port, path="/status.json"):
    return testing.connection("http_json", port=port, params={"path": path})


def test_spec_is_valid():
    assert sdk.check_spec(http_json.SPECS[0]) is None


@pytest.mark.parametrize("address,ok", [("temperature", True), ("boiler.flow.temp", True), ("sensors.1.value", True),
                                        ("", False), ("a..b", False), ("a b", False), ("x[0]", False)])
def test_check_address(address, ok):
    assert (http_json.check_address(address, "float32") is None) is ok


def test_poll_reads_all_tags_in_one_request(dev):
    conn = _conn(dev.port)
    tags = testing.tags(conn, [("T", "temperature"), ("ON", "on", "bool"), ("FLOW", "boiler.flow.temp"),
                               ("S0", "sensors.0.value"), ("S1", "sensors.1.value"), ("NAME", "name", "string"),
                               ("MISSING", "boiler.return.temp"), ("TEXT", "name")])
    vals = testing.poll_once(conn, tags, spec=http_json.SPECS[0])
    assert vals == {"T": 21.5, "ON": True, "FLOW": 55.0, "S0": 1.0, "S1": 2.5, "NAME": "boiler", "MISSING": None, "TEXT": None}
    assert dev.paths == ["/status.json"]


def test_runs_like_in_the_engine_and_reports_errors(dev):
    conn = _conn(dev.port)
    tags = testing.tags(conn, [("T", "temperature")])
    with testing.run_driver(conn, tags, spec=http_json.SPECS[0]) as run:
        assert testing.wait_for(lambda: run.sink.connected and run.sink.values.get("T") == 21.5)
        dev.status = 500
        assert testing.wait_for(lambda: not run.sink.connected and run.sink.values.get("T") is None)
        assert "HTTP 500 z" in run.sink.statuses[-1]["last_error"]


def test_connection_test_button(dev):
    r = http_json.test_once(_conn(dev.port), sdk.TestCtx(data_dir="."))
    assert "platný JSON, 5 položek" in r["msg"]
    dev.body = b"<html>"
    with pytest.raises(sdk.DriverError, match="není platný JSON"):
        http_json.test_once(_conn(dev.port), sdk.TestCtx(data_dir="."))
    with pytest.raises(sdk.DriverError, match="není dostupné"):
        http_json.test_once(_conn(testing.free_port()), sdk.TestCtx(data_dir="."))

