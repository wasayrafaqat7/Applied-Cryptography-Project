# Reproducing the measurements

Everything here uses one probe (`firmware/esp-idf/`) and one scanner (`tools/stale_keys.py`,
Python 3.8+, standard library only). The seed must match on both sides: `lums-cs5803`.

## 0. Prerequisites

- ESP-IDF **v6.1** (purge modes refuse to build below v6.1.0). Default mode also builds on
  older releases, including v5.x.
- Python 3.8+.
- For hardware: an ESP32 board, USB serial, `esptool` and `parttool.py` (both ship with ESP-IDF).

## 1. Check the scanner against the committed samples (no ESP-IDF needed)

```bash
python3 tools/stale_keys.py scan samples/nvs_default_100updates.bin --seed lums-cs5803 --epochs 100
# expect: old keys recoverable 100 / 100, earliest recoverable epoch 0
python3 tools/stale_keys.py scan samples/nvs_purge_100updates.bin --seed lums-cs5803 --epochs 100
# expect: old keys recoverable 0 / 100
python3 tools/stale_keys.py nvs samples/nvs_default_100updates.bin --namespace fsk --key st --probe | tail -2
python3 tools/stale_keys.py chain --seed lums-cs5803 --epochs 3   # compare with samples/probe_default_100updates.log
```

## 2. Host emulation (Linux target, no board)

Real ESP-IDF NVS code on a file-emulated NOR partition. The dump is written to
`nvs_dump.bin` in the current directory.

```bash
cd firmware/esp-idf
idf.py --preview set-target linux
idf.py build
./build/stale_key_probe.elf | tee serial.log                 # 100 updates (Kconfig default)
PROBE_UPDATES=1000 ./build/stale_key_probe.elf | tee serial.log   # host-only override
python3 ../../tools/stale_keys.py scan nvs_dump.bin --seed lums-cs5803 \
        --epochs "$(sed -n 's/^PROBE DONE epoch=//p' serial.log)" --json scan.json
```

## 3. Modes (sdkconfig overlays)

| Mode | Overlays | What it measures |
| --- | --- | --- |
| default | `sdkconfig.defaults` | Plain `nvs_set_blob` + `nvs_commit` |
| purge | `sdkconfig.defaults;sdkconfig.purge` | `NVS_READWRITE_PURGE` (zeroes on replace) |
| purgeall | `sdkconfig.defaults;sdkconfig.purgeall` | Default updates, then one `nvs_purge_all()` |
| continuous | `sdkconfig.defaults;sdkconfig.continuous` | Updates forever; for the power-cut rig |

Use a separate build directory per mode so the configs never mix:

```bash
idf.py -B build-purge -D SDKCONFIG=build-purge/sdkconfig \
       -D SDKCONFIG_DEFAULTS="sdkconfig.defaults;sdkconfig.purge" build
```

The first serial line confirms the mode, e.g. `PROBE START idf=v6.1 mode=purge ...`.

## 4. Real ESP32 board

```bash
cd firmware/esp-idf
idf.py set-target esp32
idf.py -p PORT flash monitor            # wait for "PROBE DONE"; save the output as serial.log
parttool.py --port PORT read_partition --partition-name=nvs --output nvs.bin
esptool --port PORT flash-id            # record the flash part (older esptool: flash_id)
python3 ../../tools/stale_keys.py scan nvs.bin --seed lums-cs5803 --epochs N --json scan.json
```

Repeat with Wi-Fi enabled for the "with Wi-Fi" rows (Wi-Fi writes its own NVS entries and
changes the page layout). Leave flash encryption and secure boot off on test boards
(`sdkconfig.defaults` explains why).

## 5. Continuous mode and power cuts

- Continuous mode never erases or reformats NVS. Start a fresh run by erasing by hand:
  `parttool.py --port PORT erase_partition --partition-name=nvs`.
- After every reset it prints `PROBE RESUME epoch=...` and carries on.
- If NVS init or the state load fails (e.g. `ESP_ERR_NVS_NO_FREE_PAGES` after a cut), it
  prints `PROBE FAIL stage=<init|open|load|...> err=<name>` and halts. The rig counts that
  as a boot failure, then dumps and scans the flash as it is.
- Rig method and settings: `rig/README.md`.

## 6. Where results go

```
results/<library>-<setup>/
  <summary>.csv
  runs/<mode>-<N>/serial.log  nvs.bin  scan.json  meta.json
```

`meta.json` fields (fill in every one; use `null` only if truly unknown):

```json
{
  "library": "esp-idf-nvs",
  "idf_commit": "output of: git -C $IDF_PATH describe --always --dirty",
  "target": "esp32 | linux",
  "board": "e.g. ESP32-DevKitC V4",
  "chip_rev": "from the boot log or esptool chip-id",
  "flash_part": "from esptool flash-id (manufacturer + device id)",
  "sdkconfig_overlays": ["sdkconfig.defaults", "sdkconfig.purge"],
  "seed": "lums-cs5803",
  "updates": 100,
  "wifi": false,
  "date": "YYYY-MM-DD"
}
```
