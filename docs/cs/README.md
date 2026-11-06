<img src="../logo.png" alt="Benešl Automation" width="180">

# Návody k BAVIS SDK

Návody jsou psané pro integrátory a vývojáře, kteří chtějí do BAVIS připojit zařízení nebo protokol, který jádro neumí.
Stačí znát Python; zdrojový kód jádra BAVIS nepotřebujete.

| # | Návod | O čem je |
| --- | --- | --- |
| 1 | [Začínáme](01-zaciname.md) | co SDK umí, co potřebujete, první balíček za pět minut |
| 2 | [První driver krok za krokem](02-prvni-driver.md) | z kostry vlastní protokol: adresy, čtení, zápis, formulář spojení, překlady |
| 3 | [Vzory driverů](03-vzory.md) | dotaz/odpověď, blokové čtení, zařízení, která posílají data sama, soubory, procházení, zápis |
| 4 | [Testování](04-testovani.md) | náhradní zařízení, pomocníci `bavis.sdk.testing`, co testovat vždy |
| 5 | [Sestavení a instalace](05-sestaveni-a-instalace.md) | `.bavispkg`, podpis, instalace, verze a kompatibilita |
| 6 | [CI a zveřejnění](06-ci-a-zverejneni.md) | GitHub Actions s obrazem Docker, vlastní repozitář balíčků, katalog, příspěvek do tohoto repa |

Referenční popis API je anglicky v [drivers.md](../drivers.md). Hotové příklady s testy jsou ve složce
[examples](../../examples/README.md).

English version of the guides: [docs/en](../en/README.md).
