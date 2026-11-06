# 6. CI a zveřejnění

[Obsah návodů](README.md) · předchozí: [Sestavení a instalace](05-sestaveni-a-instalace.md)

## Kontrola v GitHub Actions

Obraz Docker BAVIS obsahuje celé SDK, takže kontrola, testy a sestavení běží na běžném runneru `ubuntu-latest` bez instalace
BAVIS. Tento repozitář nabízí akci, která to udělá jedním krokem:

```yaml
# .github/workflows/drivers.yml ve vašem repozitáři
name: drivers
on: [push, pull_request]
jobs:
  sdk:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: Tomoash/BAVIS-SDK@main
        with:
          image: ghcr.io/tomoash/bavis:4        # obraz BAVIS 4.x
          workspace: .                          # složka s bavis_drv_<název>/ a tests/
          build: true                           # sestavit .bavispkg do <workspace>/dist/
      - uses: actions/upload-artifact@v4
        with:
          name: bavispkg
          path: dist/*.bavispkg
```

Akce spustí `bavis-sdk check --strict`, `bavis-sdk test` a s `build: true` i `bavis-sdk build` uvnitř obrazu. Celý popis vstupů je
v [action.yml](../../action.yml).

> **Stav:** obraz Docker BAVIS 4 se zveřejní s vydáním BAVIS 4.0. Do té doby akce v tomto repozitáři běží jen tam, kde je
> nastavená proměnná repozitáře `BAVIS_SDK_IMAGE` (viz [workflow příkladů](../../.github/workflows/examples.yml)).

Bez Dockeru jde totéž spustit na vlastním runneru s nainstalovaným BAVIS: `C:\BAVIS\bavis-sdk.cmd check --strict .` atd.

## Vlastní repozitář balíčků

Pro drivery, které nechcete nebo nemůžete zveřejnit (zákaznická zařízení, interní protokoly), si založte vlastní repozitář:

```
moje-drivery/
  vaha/                      pracovní složka: bavis_drv_moje_vaha/ + tests/
  hmotnostni_prutokomer/     další driver
  .github/workflows/drivers.yml
```

CI každý driver zkontroluje, otestuje a sestaví. Instalace pak balíčky berou z **vlastního katalogu**:

1. Sestavené soubory `.bavispkg` dejte do jedné složky a vytvořte seznam:

   ```
   C:\BAVIS\python\python.exe -X utf8 -m bavis catalog build dist --name "Firemní drivery"
   ```

   (Linux: `PYTHONPATH=/opt/bavis/backend /opt/bavis/venv/bin/python -X utf8 -m bavis catalog build dist …`.)
   Vznikne `dist/katalog.json` s verzí a otiskem SHA-256 každého balíčku.
2. Složku zveřejněte na adrese `https://…` (vlastní web, intranet) nebo ji dejte na sdílenou síťovou složku.
3. V instalaci BAVIS 4.0+ přidá správce v **Konfigurace → Katalog dílů → Zdroje** adresu `https://…/katalog.json` nebo
   složku a u zdroje zaškrtne **Nepodepsané balíčky**.
4. **Systém → Projekty a balíčky → Z katalogu…** pak balíčky nabídne. Instalace ověří otisk SHA-256, správce ji potvrdí a zapíše
   se do záznamu operací.

Povolujte nepodepsané balíčky jen u zdroje, který spravujete vy nebo komu plně důvěřujete – kód balíčku poběží se stejnými
právy jako BAVIS. Zdroj `http://` (bez TLS) tuto volbu nemá.

## Příspěvek do veřejného katalogu

Driver, který se hodí i ostatním, pošlete do tohoto repozitáře:

1. Založte issue s popisem zařízení nebo protokolu (šablona *Driver or device request*), ať se práce nezdvojí.
2. Driver dejte jako pracovní složku do `drivers/<název>/` (`bavis_drv_<název>/` + `tests/`), s testy a překlady. Složka
   `examples/` je vyhrazená pro ukázky, které se sem kopírují z vývoje BAVIS.
3. Pull request musí projít `bavis-sdk check --strict` a `bavis-sdk test`. Commity podepište (`git commit -s`).
4. Po kontrole driver sestavíme, podepíšeme klíčem Benešl Automation a zveřejníme v katalogu na BAVIS Central.

Pravidla jsou v [CONTRIBUTING.md](../../CONTRIBUTING.md). Bezpečnostní chyby hlaste soukromě podle
[SECURITY.md](../../SECURITY.md) na [benesl@benesl-automation.cz](mailto:benesl@benesl-automation.cz).
