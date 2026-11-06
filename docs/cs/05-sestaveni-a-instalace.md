# 5. Sestavení a instalace

[Obsah návodů](README.md) · předchozí: [Testování](04-testovani.md) · další: [CI a zveřejnění](06-ci-a-zverejneni.md)

## Sestavení

```
bavis-sdk build <pracovní složka> [--version 1.2.0] [--out soubor.bavispkg] [--key klic.pem]
```

`build` nejdřív spustí `check` a při chybě nic nesestaví. Bez `--out` vznikne
`<pracovní složka>/dist/drv_<název>-<verze>.bavispkg`. Na konci vypíše souhrn manifestu a **SHA-256** souboru (hodí se do
katalogu, viz [CI a zveřejnění](06-ci-a-zverejneni.md)):

```
bavis_drv_moje_vaha 1.0.0: drivers moje_vaha; SDK package (sdk_api 1.0)
  OK
  built C:\vyvoj\vaha\dist\drv_moje_vaha-1.0.0.bavispkg
  drv_moje_vaha 1.0.0, drivers moje_vaha, core 4.0.0–4.99999, sdk_api 1.0, UNSIGNED (installs only with packages.allow_unsigned: true)
  SHA-256 3f2a…
```

Sestavení importuje moduly driverů a odmítne balíček s rozbitým modulem, neplatným `DriverSpec` nebo druhem, který už jádro
má. Do manifestu (`bavispkg.json`) zapíše druhy, `core_min`, `core_max` a u balíčku SDK také `sdk_api`.

## Verze

* Verze balíčku je `__version__` v `bavis_drv_<název>/__init__.py` (`MAJOR.MINOR.PATCH`), `--version` ji při sestavení přepíše.
* Vydaná verze se nemění – oprava je nová verze (`1.0.1`). Verze se porovnávají číselně (`1.10.0` > `1.9.0`).
* `core_min` = verze BAVIS, kterou jste sestavovali. Balíček sestavený na BAVIS 4.1 se nenačte na 4.0 – sestavujte na nejstarší
  verzi, kterou chcete podporovat.
* `sdk_api` = verze SDK API. U balíčku SDK se `core_max` nehlídá, dokud jádro podporuje hlavní verzi SDK (1.x). Balíček
  postavený pro SDK 1.1 se nenačte na jádře, které umí jen 1.0.

## Podpis

Balíček obsahuje kód, který běží uvnitř BAVIS se stejnými právy jako jádro. Proto instalace přijímá:

| Balíček | Kde se nainstaluje |
| --- | --- |
| **podepsaný klíčem Benešl Automation** | kdekoli – takhle vycházejí balíčky z veřejného katalogu |
| **nepodepsaný, z vašeho katalogu** (BAVIS 4.0+) | v instalaci, kde správce u vašeho zdroje katalogu povolil *Nepodepsané balíčky*; soubor musí mít přesně SHA-256 ze seznamu `katalog.json`, správce instalaci potvrdí a zapíše se do záznamu operací |
| **nepodepsaný, nahraný ručně** | jen ve vývojovém režimu (`packages: {allow_unsigned: true}` v `config.yaml`) – na vlastním vývojovém počítači |

`--key` podepíše balíček klíčem Ed25519, který jádro zná jako klíč dodavatele (klíč aktualizací). Jiný klíč sestavení odmítne.
Chcete-li balíček do veřejného katalogu, pošlete ho jako pull request do tohoto repozitáře – po kontrole ho podepíšeme a
zveřejníme (viz [CI a zveřejnění](06-ci-a-zverejneni.md)).

## Instalace

1. **Systém → Projekty a balíčky → Nahrát balíček…** (nebo **Z katalogu…**).
2. Náhled ukáže název, verzi, drivery, verzi jádra, podpis a u nepodepsaného balíčku z katalogu zdroj a otisk.
3. **Instalovat** (s e-podpisem `pkg_install`, pokud ho instalace vyžaduje).

Nový balíček se načte hned a jeho drivery jsou k dispozici pro všechny projekty. Nová verze už načteného balíčku čeká na restart
aplikace. Balíček jde odinstalovat, jen když jeho drivery nepoužívá žádné spojení.

Chyby načtení (rozbitý modul, duplicitní druh) ukazuje **Systém → O aplikaci → Moduly**; driver jádra se stejným druhem vždy
zůstává.

## Docker

V obrazu Docker leží nainstalované balíčky ve svazku dat (`/data/packages`). Instalace přes rozhraní funguje stejně jako jinde;
obraz se aktualizuje celý (nový tag obrazu), ne souborem `.whu`.
