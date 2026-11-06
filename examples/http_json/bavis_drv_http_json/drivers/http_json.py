"""HTTP JSON driver – a complete, minimal example of a BAVIS communication driver.

The device (or any web service) answers ``GET http://<host>:<port><path>`` with a JSON document. Every tag address is a dotted
path into that document: ``temperature``, ``boiler.flow.temp``, ``sensors.2.value`` (a number = index in a list).
One HTTP request per read cycle serves all tags of the connection. The driver is read-only.

What the example shows:
- a ``Driver`` subclass with ``open`` / ``close`` / ``poll`` (the base class runs the read loop, reconnects and reports state),
- ``check_address`` used by the tag table and by project validation,
- a ``test`` function behind the *Test connection* button,
- a custom connection field (``path``) stored in ``Connection.params``,
- heavy or optional imports only inside functions (here only the standard library is needed),
- operator texts in Czech (the source language of BAVIS) with translations in ``i18n/<lang>.json``."""
from __future__ import annotations

import json
import re

from bavis.sdk import Driver, DriverError, DriverSpec, FieldSpec, require_host

DEFAULT_PORT = 80
_SEGMENT = re.compile(r"^[A-Za-z0-9_\-]+$")

# operator texts = translation keys (section "srv" of i18n/<lang>.json); placeholders {0}, {1} are filled by .format()
E_EMPTY = "prázdná adresa – zadejte cestu s tečkami, např. boiler.flow.temp"
E_SEGMENT = "použijte písmena, číslice, _ a - oddělené tečkami, např. sensors.2.value"
E_HTTP = "HTTP {0} z {1}"
E_UNREACHABLE = "{0} není dostupné: {1}"
E_TOO_BIG = "dokument JSON je větší než 4 MB"
E_NOT_JSON = "odpověď není platný JSON"
M_TEST_OK = "{0}: platný JSON, {1} položek na nejvyšší úrovni"


def check_address(address: str, typ: str) -> str | None:
    """None = valid address, otherwise a message for the tag table."""
    if not address:
        return E_EMPTY
    if any(not _SEGMENT.match(seg) for seg in address.split(".")):
        return E_SEGMENT
    return None


def resolve(doc, address: str):
    """Value at a dotted path, None when the path does not exist."""
    cur = doc
    for seg in address.split("."):
        if isinstance(cur, dict) and seg in cur:
            cur = cur[seg]
        elif isinstance(cur, list) and seg.isdigit() and int(seg) < len(cur):
            cur = cur[int(seg)]
        else:
            return None
    return cur


def convert(value, typ: str):
    """JSON value → raw tag value; anything that does not fit the tag type is invalid (None)."""
    if isinstance(value, bool):
        return value if typ == "bool" else float(value)
    if isinstance(value, (int, float)):
        return bool(value) if typ == "bool" else float(value)
    if isinstance(value, str):
        if typ == "string":
            return value
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _url(conn) -> str:
    path = str((conn.params or {}).get("path") or "/")
    return f"http://{conn.host}:{conn.port or DEFAULT_PORT}{path if path.startswith('/') else '/' + path}"


def fetch(conn) -> dict:
    """GET the JSON document of the connection (DriverError with an operator-friendly text on failure)."""
    import urllib.error
    import urllib.request
    try:
        with urllib.request.urlopen(_url(conn), timeout=max(conn.timeout_ms, 100) / 1000) as r:
            body = r.read(4 * 1024 * 1024 + 1)
    except urllib.error.HTTPError as e:
        raise DriverError(E_HTTP.format(e.code, _url(conn))) from None
    except (urllib.error.URLError, OSError) as e:
        raise DriverError(E_UNREACHABLE.format(_url(conn), getattr(e, "reason", e))) from None
    if len(body) > 4 * 1024 * 1024:
        raise DriverError(E_TOO_BIG)
    try:
        return json.loads(body)
    except ValueError:
        raise DriverError(E_NOT_JSON) from None


class HttpJsonDriver(Driver):
    def poll(self) -> dict:
        doc = fetch(self.conn)
        return {t.name: convert(resolve(doc, t.address), t.type) for t in self.tags}


def test_once(conn, ctx) -> dict:
    doc = fetch(conn)
    keys = len(doc) if isinstance(doc, (dict, list)) else 0
    return {"msg": M_TEST_OK.format(_url(conn), keys)}


SPECS = [DriverSpec(
    kind="http_json", label="HTTP JSON (příklad)", category="it", order=900, transport="tcp", default_port=DEFAULT_PORT,
    id_prefix="json", make=lambda conn, tags, sink, data_dir: HttpJsonDriver(conn, tags, sink, data_dir),
    check_address=check_address, test=test_once, validate=require_host,
    summary="http://{host}:{port}",
    fields=(FieldSpec("path", "Cesta", "text", default="/", placeholder="/status.json",
                      help="Cesta k dokumentu JSON na zařízení"),),
    addr_help="Cesta v dokumentu JSON s tečkami: temperature · boiler.flow.temp · sensors.2.value",
    addr_placeholder="boiler.flow.temp", defaults={"host": "192.168.0.10"},
)]
