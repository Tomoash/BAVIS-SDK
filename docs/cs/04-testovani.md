# 4. Testování

[Obsah návodů](README.md) · předchozí: [Vzory driverů](03-vzory.md) · další: [Sestavení a instalace](05-sestaveni-a-instalace.md)

Každý driver má testy, které běží **bez skutečného zařízení**: místo něj odpovídá *náhradní zařízení* – malý server ve stejném
procesu, který mluví stejným protokolem. Díky tomu testy běží na notebooku, v CI i při kontrole příspěvku.

## Spuštění

```
bavis-sdk test <pracovní složka>                      # pytest proti jádru této instalace
bavis-sdk test <pracovní složka> -- -k zapis -x -v    # parametry pytest za --
```

`test` dá na cestu importu jádro BAVIS a pracovní složku; `tests/conftest.py` z kostry přidá složku s balíčkem, takže jádro
váš driver najde stejně jako po instalaci (`sdk.lookup_driver("moje_vaha")`, `validate_project` …).

## Pomocníci `bavis.sdk.testing`

```python
from bavis.sdk import testing

def test_cte_a_zapisuje(dev):
    conn = testing.connection("moje_vaha", port=dev.port, params={"station": 1})
    tags = testing.tags(conn, [("W1", "W1"), ("W2", "W2", "float32", "rw")])
    assert testing.poll_once(conn, tags) == {"W1": 12.5, "W2": 0.0}
    with testing.run_driver(conn, tags) as run:                  # jako v enginu: vlastní vlákno, znovupřipojení, stav
        assert testing.wait_for(lambda: run.sink.connected and run.sink.values.get("W1") == 12.5)
        run.driver.write(tags[1], 3.0)
```

| Pomocník | K čemu |
| --- | --- |
| `connection(driver, port=…, params=…)` | spojení s krátkými časy pro testy (perioda 50 ms, timeout 1 s) |
| `tags(conn, [(název, adresa[, typ[, přístup]]) …])` | tagy spojení (výchozí typ `float32`, přístup `r`) |
| `poll_once(conn, tags, spec=None, data_dir=".")` | jeden cyklus: `open()`, `poll()`, `close()` → slovník hodnot |
| `run_driver(conn, tags, spec=None, data_dir=".")` | driver ve vlastním vlákně jako v enginu; `.sink` zaznamenává hodnoty a stavy, `.driver` je instance |
| `RecordingSink` | náhrada enginu: `values` (poslední hodnoty), `batches` (každé volání), `statuses`, `connected` |
| `wait_for(podmínka, timeout=5)` | čekání na podmínku místo pevného `sleep` |
| `free_port()` / `free_port(socket.SOCK_DGRAM)` | volný port TCP / UDP vybraný systémem |

`spec` předejte, když chcete testovat konkrétní popis (`spec=moje_vaha.SPECS[0]`); bez něj se použije registrovaný druh.

## Náhradní zařízení

TCP zařízení – `socketserver` na `127.0.0.1` a portu `0` (vybere systém):

```python
class FakeDevice(socketserver.ThreadingTCPServer):
    daemon_threads = True

    def __init__(self):
        super().__init__(("127.0.0.1", 0), Handler)
        self.port = self.server_address[1]
        self.regs = {"W1": "12.5"}
        threading.Thread(target=self.serve_forever, daemon=True).start()
```

HTTP zařízení – `http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)` (příklad `http_json`). UDP – test sám posílá
datagramy na port z `free_port(socket.SOCK_DGRAM)` (příklad `udp_json`). Soubory – `tmp_path` z pytest (příklad `csv_file`).

Aby šlo otestovat výpadek, ať si náhradní zařízení pamatuje otevřená spojení a umí je zavřít (`stop()` v kostře a v příkladu
`scpi`) – samotné `shutdown()` serveru už otevřená spojení nezavře.

## Co testovat vždy

1. **Popis je platný**: `assert sdk.check_spec(SPECS[0]) is None`.
2. **Adresy**: platné i neplatné příklady pro `check_address` (parametrizovaný test).
3. **Čtení**: `poll_once` vrátí očekávané hodnoty všech typů, neznámá adresa = `None` jen u toho tagu.
4. **Životní cyklus**: v `run_driver` se spojení připojí, po výpadku zařízení se ukáže jako odpojené a tagy ztratí hodnotu
   (`None`), a po návratu zařízení se připojí znovu.
5. **Zápis**: zápis dojde do zařízení, odmítnutý zápis vyhodí `DriverError`, zápis do tagu jen pro čtení se odmítne.
6. **Test spojení**: úspěch i chyba (nedostupné zařízení – port z `free_port()`, na kterém nic neposlouchá).
7. **Pole spojení**: `validate_project` s výchozími a špatnými hodnotami polí (kostra to ukazuje v
   `test_spec_registered_with_params_field`).

## Pravidla

* **Žádné pevné porty** – testy běží paralelně a na sdílených strojích CI. `check` pevný port v testech hlásí.
* **Žádné `sleep` na odhad** – `testing.wait_for(...)` s rozumným timeoutem.
* **Žádný hardware ani internet** – test, který potřebuje skutečné zařízení, do repozitáře nepatří (popište ho v README driveru
  jako ruční zkoušku).
* Funkce driveru, které začínají `test` (např. `test_once`), importujte pod jiným jménem
  (`from … import test_once as spojeni_test`), jinak by je pytest spustil jako test.
