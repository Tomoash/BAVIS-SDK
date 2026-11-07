"""Prometheus metrics – read the text exposition format of an exporter over HTTP(S), optionally with a bearer token.

Thousands of programs and devices publish their state as Prometheus metrics on ``http://<host>:<port>/metrics``:
node_exporter (CPU, memory, disks of a server, port 9100), windows_exporter (9182), SNMP and Modbus exporters, databases, web
servers, Home Assistant, many network devices. Reference: *Exposition formats – text-based format* in the Prometheus
documentation (prometheus.io/docs/instrumenting/exposition_formats, Apache-2.0).

Tag address = metric name, optionally with labels that select the sample:

    node_load1
    node_filesystem_avail_bytes{mountpoint="/"}
    http_requests_total{code="200"}        when several samples match, their sum is used (all methods with code 200)

What the example shows:
- a password field (``secret=True`` + ``DriverSpec.secrets``): the token is stored encrypted and never shown again,
- ``browse`` + ``items_to_tags``: import tags by browsing the metrics of the exporter (with the HELP text as a comment),
- parsing a text format that is shared by all tags – one HTTP request per read cycle, a size limit for the answer,
- ``NaN`` and infinite values returned as ``None`` (no valid value)."""
from __future__ import annotations

import math
import re

from bavis.sdk import Driver, DriverError, DriverSpec, FieldSpec, require_host

DEFAULT_PORT = 9100
MAX_BODY = 8 * 1024 * 1024
NAME_RE = r"[a-zA-Z_:][a-zA-Z0-9_:]*"
ADDR_RE = re.compile(rf"^({NAME_RE})(?:\{{(.*)\}})?$")
LABEL_RE = re.compile(r'\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*"((?:[^"\\]|\\.)*)"\s*(,|$)')
SAMPLE_RE = re.compile(rf"^({NAME_RE})(?:\{{(.*)\}})?\s+(\S+)(?:\s+-?\d+)?\s*$")

# operator texts = translation keys (section "srv" of i18n/<lang>.json); placeholders {0}, {1} are filled by .format()
E_ADDR = "adresa = název metriky, případně se štítky: node_load1 nebo http_requests_total{code=\"200\"}"
E_LABELS = "štítky ve tvaru {název=\"hodnota\", …}"
E_TYPE = "metrika je číslo – typ tagu nesmí být string"
E_HTTP = "HTTP {0} z {1}"
E_AUTH = "exportér odmítl přístup (HTTP {0}) – zkontrolujte token"
E_UNREACHABLE = "{0} není dostupné: {1}"
E_TOO_BIG = "odpověď je větší než 8 MB"
M_TEST_OK = "{0}: {1} metrik, {2} hodnot"


def _unescape(value: str) -> str:
    return re.sub(r"\\(.)", lambda m: "\n" if m.group(1) == "n" else m.group(1), value)


def parse_labels(text: str | None) -> dict[str, str]:
    """``a="1",b="x"`` → {"a": "1", "b": "x"}; ValueError for invalid syntax."""
    out, pos, text = {}, 0, (text or "").strip()
    while pos < len(text):
        m = LABEL_RE.match(text, pos)
        if not m:
            raise ValueError(E_LABELS)
        out[m.group(1)] = _unescape(m.group(2))
        pos = m.end()
    return out


def parse_address(address: str) -> tuple[str, dict[str, str]]:
    m = ADDR_RE.match((address or "").strip())
    if not m:
        raise ValueError(E_ADDR)
    return m.group(1), parse_labels(m.group(2))


def check_address(address: str, typ: str) -> str | None:
    if typ == "string":
        return E_TYPE
    try:
        parse_address(address)
    except ValueError as e:
        return str(e)
    return None


def number(text: str) -> float | None:
    """Sample value → float; NaN and ±Inf (valid in the format) → None for BAVIS."""
    try:
        value = float(text)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def parse(text: str) -> tuple[list[tuple[str, dict, float | None]], dict[str, str]]:
    """Exposition text → (samples [(name, labels, value)], HELP texts {name: text}). Invalid lines are skipped."""
    samples, help_texts = [], {}
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("#"):
            parts = line.split(None, 3)
            if len(parts) == 4 and parts[1] == "HELP":
                help_texts[parts[2]] = _unescape(parts[3])
            continue
        m = SAMPLE_RE.match(line)
        if not m:
            continue
        try:
            labels = parse_labels(m.group(2))
        except ValueError:
            continue
        samples.append((m.group(1), labels, number(m.group(3))))
    return samples, help_texts


def select(samples, name: str, labels: dict[str, str]) -> float | None:
    """Sum of the samples of ``name`` whose labels contain ``labels``; None when nothing matches or a value is invalid."""
    found = [v for n, lab, v in samples if n == name and all(lab.get(k) == x for k, x in labels.items())]
    if not found or any(v is None for v in found):
        return None
    return sum(found)


def _params(conn) -> dict:
    p = conn.params or {}
    path = str(p.get("path") or "/metrics")
    return {"scheme": "https" if p.get("scheme") == "https" else "http", "path": path if path.startswith("/") else "/" + path,
            "token": str(p.get("token") or "")}


def fetch(conn) -> str:
    """One HTTP GET of the metrics page → its text. DriverError with an operator text on any failure."""
    import urllib.error
    import urllib.request
    p = _params(conn)
    url = f"{p['scheme']}://{conn.host}:{conn.port or DEFAULT_PORT}{p['path']}"
    req = urllib.request.Request(url, headers={"Accept": "text/plain"})
    if p["token"]:
        req.add_header("Authorization", f"Bearer {p['token']}")
    try:
        with urllib.request.urlopen(req, timeout=max(conn.timeout_ms, 100) / 1000) as resp:
            body = resp.read(MAX_BODY + 1)
    except urllib.error.HTTPError as e:
        raise DriverError((E_AUTH if e.code in (401, 403) else E_HTTP).format(e.code, url)) from None
    except (urllib.error.URLError, OSError) as e:
        raise DriverError(E_UNREACHABLE.format(url, getattr(e, "reason", e))) from None
    if len(body) > MAX_BODY:
        raise DriverError(E_TOO_BIG)
    return body.decode("utf-8", "replace")


class PrometheusDriver(Driver):
    kind = "prometheus"

    def __init__(self, conn, tags, sink, data_dir="data"):
        super().__init__(conn, tags, sink, data_dir)
        self.wanted = {}
        for t in tags:
            try:
                self.wanted[t.name] = parse_address(t.address)
            except ValueError:
                self.wanted[t.name] = None

    def open(self):
        """HTTP has no permanent link – every read cycle is a new request."""

    def close(self):
        pass

    def poll(self) -> dict:
        samples, _help = parse(fetch(self.conn))
        return {name: select(samples, *w) if w else None for name, w in self.wanted.items()}


def address_of(name: str, labels: dict[str, str]) -> str:
    if not labels:
        return name
    inner = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()) if not ("\\" in v or '"' in v or "\n" in v))
    return f"{name}{{{inner}}}"


def test_once(conn, ctx) -> dict:
    samples, _help = parse(fetch(conn))
    return {"msg": M_TEST_OK.format(conn.host, len({s[0] for s in samples}), len(samples))}


def browse(conn, ctx, node_id=None) -> dict:
    """Browsing: one item per sample (metric + labels), at most 2000, with the current value and the HELP text."""
    samples, help_texts = parse(fetch(conn))
    items = [{"name": address_of(n, lab), "address": address_of(n, lab), "type": "float64", "datatype": "metric",
              "writable": False, "comment": f"{help_texts.get(n, n)[:80]} = {v}"} for n, lab, v in samples[:2000]]
    return {"items": items, "flat": True}


def tag_name(address: str) -> str:
    """``http_requests_total{code="200"}`` → ``http_requests_total_code_200`` (a valid, readable tag name)."""
    name = re.sub(r"[^A-Za-z0-9_.\-]+", "_", address.replace(":", "_")).strip("_")
    return (name if re.match(r"^[A-Za-z_]", name) else "_" + name)[:100]


def items_to_tags(items, conn_id, prefix, group, opts=None) -> dict:
    tags, used = [], set()
    for it in items:
        name = base = tag_name(prefix + str(it["address"]))
        k = 2
        while name in used:
            name, k = f"{base[:96]}_{k}", k + 1
        used.add(name)
        tags.append({"name": name, "conn": conn_id, "address": it["address"], "type": "float64", "access": "r",
                     "group": group, "desc": (it.get("comment") or "").rsplit(" = ", 1)[0] or it["address"]})
    return {"tags": tags, "skipped": [], "info": "Prometheus"}


SPECS = [DriverSpec(
    kind="prometheus", label="Prometheus exportér (HTTP, příklad)", short="Prometheus", category="it", order=900,
    transport="tcp", default_port=DEFAULT_PORT, id_prefix="prom",
    make=lambda conn, tags, sink, data_dir: PrometheusDriver(conn, tags, sink, data_dir),
    check_address=check_address, test=test_once, browse=browse, items_to_tags=items_to_tags, validate=require_host,
    secrets=("token",), summary="{scheme|http}://{host}:{port}{path|/metrics}",
    fields=(
        FieldSpec("scheme", "Protokol", "select", default="http", options=(("http", "HTTP"), ("https", "HTTPS"))),
        FieldSpec("path", "Cesta", "text", default="/metrics", placeholder="/metrics"),
        FieldSpec("token", "Token (Bearer)", "password", secret=True, default="",
                  help="Jen když exportér vyžaduje přihlášení; prázdné = bez hlavičky Authorization"),
    ),
    addr_help="Název metriky: node_load1 · se štítky: node_filesystem_avail_bytes{mountpoint=\"/\"} (víc shod = součet)",
    addr_placeholder="node_load1", defaults={"host": "192.168.0.10", "port": DEFAULT_PORT},
)]
