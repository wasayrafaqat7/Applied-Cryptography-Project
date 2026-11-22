# ESP-IDF NVS, host emulation (Linux target, v6.1)

- `host_emulation_idf6.1.csv`: default and purge sweeps, 25 to 5,000 updates, 6-page NVS.
- `meta.json`: setup for the sweep (fields not recorded at the time are `null`).
- `runs/<mode>-<N>/`: per-run `serial.log`, `nvs.bin`, `scan.json`, `meta.json` (TODO for this
  sweep; the 100-update default and purge runs are in `samples/`).

Reproduce: `docs/reproduce.md`, section 2.
