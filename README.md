# Applied Cryptography Project
Crash-Safe Key Erasure for Forward-Secure Encryption on Commodity Microcontrollers

Applied cryptography course project, LUMS (in progress).

Forward-secure encryption protects past messages only if a replaced key is really gone.
On microcontroller flash it usually is not. This project:

1. **measures the problem** (backbone): how much forward-secure key state survives in
   common microcontroller storage libraries;
2. **tests what already exists** (baseline): the zeroing fixes in ESP-IDF NVS (purge mode,
   `nvs_purge_all()`), Trezor's storage and boot-time zeroing, under random power cuts;
3. **builds the fix** (main contribution): DNEFS-style secure deletion brought to
   microcontrollers, a crash-safe key store on raw NOR flash.

One harness serves all three: forward-secure test firmware, a flash-dump scanner that
counts recoverable old keys, and a random power-cut rig.

> **Status (Nov 2026).** Proposal approved. ESP-IDF NVS measured in host emulation;
> other libraries, boards, power-cut tests and the key store in progress.

## 1. The problem

Every proof for forward-secure and puncturable encryption assumes a deleted key is gone.
Flash cannot be overwritten in place, so storage libraries write each update elsewhere
and only mark the old copy as erased.

First result (ESP-IDF v6.1 NVS, host emulation, 6-page partition):

| Key updates | Default NVS: old keys recoverable | Earliest recoverable epoch | Purge mode |
| ---: | ---: | ---: | ---: |
| 100 | 100 / 100 (100%) | 0 | 0 |
| 155 | 124 / 155 (80%) | 0 | 0 |
| 1000 | 132 / 1000 (13%) | 0 | 0 |
| 5000 | 133 / 5000 (2.7%) | 0 | 0 |

k_0 is never reclaimed. With a hash ratchet, an attacker can therefore recompute all
5,000 past keys.

→ [docs/1-problem.md](docs/1-problem.md)

## 2. How we tested it, and the state of the art

- **Harness:** probe firmware per storage library; `tools/stale_keys.py`; power-cut rig.
- **Library matrix:** ESP-IDF NVS (default, purge, `nvs_purge_all()`), LittleFS, STM32 EEPROM emulation,
  Zephyr ITS on ZMS, Trezor NORCOW; optionally Nordic FDS and Silicon Labs NVM3.
- **Existing fixes** (the baselines): ESP-IDF purge mode, `nvs_purge_all()`, Trezor's
  zeroing and boot-time zeroing. None documents crash behaviour during deletion.
- **Closest related work:** DNEFS/UBIFSec (Linux, NAND).

→ [docs/2-testing-and-sota.md](docs/2-testing-and-sota.md)

## 3. Our contribution

| | Claim | Role |
| --- | --- | --- |
| C1 | First systematic measurement of forward-secure key state across microcontroller storage libraries | Establishes the problem |
| C2 | First power-loss evaluation of deletion in microcontroller storage libraries | Baseline analysis |
| C3 | DNEFS-style secure deletion adapted to microcontrollers, with a power-loss argument and testing | Main contribution |

→ [docs/3-contribution.md](docs/3-contribution.md)

## Status

| Item | State |
| --- | --- |
| ESP-IDF probe, `stale_keys.py` | Done |
| ESP-IDF NVS default and purge, host emulation | Done (purge_all rows missing from CSV) |
| ESP32 boards, with and without Wi-Fi | TODO |
| LittleFS, STM32 EEPROM emulation, Zephyr ITS on ZMS, Trezor NORCOW | TODO |
| Nordic FDS, Silicon Labs NVM3 | Optional |
| Power-cut rig | TODO |
| Key store (C3) | Design draft |

## Quick start (no board)

```bash
cd firmware/esp-idf
idf.py --preview set-target linux && idf.py build
./build/stale_key_probe.elf                       # writes nvs_dump.bin here
python3 ../../tools/stale_keys.py scan nvs_dump.bin --seed lums-cs5803 --epochs 100
```

No ESP-IDF at all? Check the scanner on the committed dumps:
`python3 tools/stale_keys.py scan samples/nvs_default_100updates.bin --seed lums-cs5803 --epochs 100`.

Full instructions: [docs/reproduce.md](docs/reproduce.md).

## Layout

```
docs/                       1-problem, 2-testing-and-sota, 3-contribution, reproduce,
                            related-work-search, references.bib
firmware/common/            ratchet + SHA-256, shared by every port
firmware/esp-idf/           ESP-IDF project: probe in main/, sdkconfig overlays per mode
                            (also builds for the linux host target)
firmware/<library>/         probe ports: zephyr-zms, stm32-eeprom, trezor-norcow, littlefs (TODO)
firmware/keystore/          C3 key store (design.md for now)
tools/stale_keys.py         scanner; storage-agnostic, unchanged across ports
rig/                        power-cut rig
results/<library>-<setup>/  summary CSV, meta.json, runs/<mode>-<N>/
samples/                    100-update dumps (default, purge) and a serial log
```

## Acknowledgements

This repository was prepared with help from Claude (Anthropic).
