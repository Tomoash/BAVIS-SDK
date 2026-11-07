"""Tests of the Prometheus example against a fake exporter (http.server on 127.0.0.1, port chosen by the OS)."""
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from bavis import sdk
from bavis.sdk import testing
from bavis_drv_prometheus.drivers import prometheus as prom

SPEC = prom.SPECS[0]

METRICS = """\
# HELP node_load1 1m load average.
# TYPE node_load1 gauge
node_load1 0.42
# HELP node_filesystem_avail_bytes Filesystem space available to non-root users in bytes.
# TYPE node_filesystem_avail_bytes gauge
node_filesystem_avail_bytes{device="/dev/sda1",fstype="ext4",mountpoint="/"} 1.2345e+10
node_filesystem_avail_bytes{device="/dev/sdb1",fstype="ext4",mountpoint="/data"} 5e+09
# HELP http_requests_total Requests by code and method.
# TYPE http_requests_total counter
http_requests_total{code="200",method="get"} 1027 1395066363000
http_requests_total{code="200",method="post"} 3
http_requests_total{code="500",method="get"} 2
temperature_celsius{sensor="a \\"quoted\\" name"} NaN
process_start_time_seconds 1.7e+09
"""


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        dev = self.server
        dev.seen.append((self.path, self.headers.get("Authorization")))
        if dev.token and self.headers.get("Authorization") != f"Bearer {dev.token}":
            self.send_response(401)
            self.end_headers()
            return
        body = dev.body.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture
def exporter():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    srv.body, srv.token, srv.seen = METRICS, "", []
    srv.port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv
    srv.shutdown()
    srv.server_close()


def _conn(port, **params):
    return testing.connection("prometheus", port=port, params=params)


def test_spec_is_valid():
    assert sdk.check_spec(SPEC) is None


@pytest.mark.parametrize("address,ok", [("node_load1", True), ('node_filesystem_avail_bytes{mountpoint="/"}', True),
                                        ('x{a="1", b="2"}', True), ("job:rate5m", True), ("", False), ("1abc", False),
                                        ("x{a=1}", False), ('x{a="1"', False)])
def test_check_address(address, ok):
    assert (prom.check_address(address, "float64") is None) is ok


def test_parse_handles_labels_timestamps_escapes_and_nan():
    samples, help_texts = prom.parse(METRICS)
    assert ("http_requests_total", {"code": "200", "method": "get"}, 1027.0) in samples
    assert ("temperature_celsius", {"sensor": 'a "quoted" name'}, None) in samples
    assert help_texts["node_load1"] == "1m load average."


def test_poll_selects_samples_by_labels(exporter):
    conn = _conn(exporter.port)
    tags = testing.tags(conn, [("LOAD", "node_load1"), ("ROOT", 'node_filesystem_avail_bytes{mountpoint="/"}', "float64"),
                               ("OK", 'http_requests_total{code="200"}', "uint32"), ("ALL", "http_requests_total"),
                               ("TEMP", "temperature_celsius"), ("NONE", 'node_load1{x="y"}')])
    assert testing.poll_once(conn, tags, spec=SPEC) == {"LOAD": 0.42, "ROOT": 1.2345e10, "OK": 1030.0, "ALL": 1032.0,
                                                        "TEMP": None, "NONE": None}
    assert exporter.seen == [("/metrics", None)]                    # one request serves all tags


def test_token_is_sent_and_a_wrong_token_is_reported(exporter):
    exporter.token = "s3cret"
    tags = [("LOAD", "node_load1")]
    conn = _conn(exporter.port, token="s3cret", path="metrics")
    assert testing.poll_once(conn, testing.tags(conn, tags), spec=SPEC) == {"LOAD": 0.42}
    assert exporter.seen[-1] == ("/metrics", "Bearer s3cret")
    conn = _conn(exporter.port, token="wrong")
    with pytest.raises(sdk.DriverError, match="token"):
        testing.poll_once(conn, testing.tags(conn, tags), spec=SPEC)
    assert "token" in SPEC.secrets


def test_browse_and_import(exporter):
    conn = _conn(exporter.port)
    ctx = sdk.TestCtx(data_dir=".")
    assert prom.test_once(conn, ctx)["msg"] == "127.0.0.1: 5 metrik, 8 hodnot"
    items = prom.browse(conn, ctx)["items"]
    root = next(i for i in items if 'mountpoint="/"' in i["address"])
    assert root["address"] == 'node_filesystem_avail_bytes{device="/dev/sda1",fstype="ext4",mountpoint="/"}'
    assert prom.check_address(root["address"], "float64") is None
    out = prom.items_to_tags([root, root], "c1", "srv_", "Server")["tags"]
    assert [t["name"] for t in out] == ["srv_node_filesystem_avail_bytes_device_dev_sda1_fstype_ext4_mountpoint",
                                        "srv_node_filesystem_avail_bytes_device_dev_sda1_fstype_ext4_mountpoint_2"]
    assert out[0]["desc"] == "Filesystem space available to non-root users in bytes."


def test_unreachable_exporter_disconnects():
    conn = _conn(testing.free_port())
    tags = testing.tags(conn, [("LOAD", "node_load1")])
    with testing.run_driver(conn, tags, spec=SPEC) as run:
        assert testing.wait_for(lambda: any(s.get("last_error") for s in run.sink.statuses))
        assert not run.sink.connected
