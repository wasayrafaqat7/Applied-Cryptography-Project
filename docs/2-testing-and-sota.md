# 2. How we tested it, and the state of the art

## 2.1 One harness for all three claims

| Part | What it does | Used by |
| --- | --- | --- |
| Probe firmware (`firmware/<library>/`) | SHA-256 ratchet, state = `epoch ‖ key` stored after every step through the library's normal API; old key wiped from RAM | C1, C2, C3 |
| `tools/stale_keys.py scan` | Recomputes k_0 … k_N and searches every byte of a dump; reports count and earliest recoverable epoch | C1, C2, C3 |
| `stale_keys.py nvs` | Parses ESP-IDF NVS pages to explain *where* keys survive (a convenience; other NVS analyzers exist) | C1 |
| Power-cut rig (`rig/`) | Random power cuts in continuous mode, then dump and scan | C2, C3 |

## 2.2 Library matrix (C1)

| Library | Board | Mode(s) | Status |
| --- | --- | --- | --- |
| ESP-IDF NVS | ESP32 | default, purge, `nvs_purge_all()` | Emulation done; boards TODO |
| LittleFS | ESP32 | default | TODO |
| STM32 EEPROM emulation | STM32 Nucleo | default | TODO |
| Zephyr ITS on ZMS | Zephyr board (nRF or STM32) | default | TODO |
| Trezor NORCOW | STM32 | its own zeroing | TODO (also a C2 baseline) |
| Nordic FDS | nRF52 | default | Optional |
| Silicon Labs NVM3 | EFR32 | default | Optional (needs board) |

Per run we report:
- old keys recoverable / total;
- earliest recoverable epoch;
- whether the current key is present;
- library version and flash part.

## 2.3 ESP-IDF NVS results (host emulation, v6.1)

[full 12-row table from the previous version, unchanged]

Mechanism (`nvs_pagemanager.cpp`, `requestNewPage()`; re-check line numbers at the v6.1 tag):
- NVS reclaims only when fewer than two free pages remain.
- It then picks the page with the most entries not in use, using a strict comparison.
- Page 0 always holds the namespace record, so it never wins.

Validity:
- `scan` is a lower bound (split blobs, partial remnants).
- Emulation is not hardware.
- Wi-Fi changes the page layout.

## 2.4 Existing fixes: the baselines for C2

| Fix | How it deletes | Documented crash behaviour during deletion |
| --- | --- | --- |
| ESP-IDF NVS purge mode | Zeroes replaced or deleted entries in place | Rare `ESP_ERR_NVS_NO_FREE_PAGES` after power loss (availability). Secrecy: none. Our reading of the source: an entry is marked erased before it is zeroed (TODO: cite function) |
| `nvs_purge_all()` | One-shot zeroing of everything marked erased | None |
| Trezor storage (NORCOW) | Overwrites old EDEK and PIN check with zeros; meant to be atomic | None |
| Boot-time zeroing (e.g. [cairn28]) | Zeroes deleted slots at the next boot | Deletion window until reboot |

Hypotheses for C2:
- a power cut between marking and zeroing leaves a key behind;
- boot-time zeroing leaves keys for a whole uptime;
- purge mode occasionally fails to initialize.

## 2.5 Related work

- **Cryptography assuming erasure:** [BY03, GM15, DJSS18, BDK+21, BGP22, EPCS26,
  Chronos25, Graphene25, Diamond26, KUDOS].
- **Closest design: DNEFS / UBIFSec [RCB12].**
  - Each 4 KB data node has its own AES-128 key; all keys sit in a Key Storage Area of
    about 0.4% of capacity.
  - Deleting data marks its key deleted. A periodic purge (15 min recommended) rewrites KSA
    blocks with fresh random values in place of deleted keys, then erases the old blocks.
  - Deleted data stays recoverable until the next purge.
  - Crash safety: UBI atomic block update plus key-state checkpoints, with every
    power-loss point analysed.
  - Cost on a Nexus One: erasures rose from 21.3/h (plain UBIFS) to 40.1/h with a
    15-minute purge; purging one block took 21.2 ms.
- **Other pieces of the design, each existing separately:**
  - YAFFS zero-overwriting and deletion latency [RMCB12];
  - scrubbing [WGSS11];
  - Trezor's zeroing;
  - A/B save areas and wipe on MSP430 FRAM (SICP) [KSDS19], following the attacks in [KS18];
  - TPM-anchored puncturable deletion with crash consistency (Holepunch) [RGW+24];
  - Apple's Effaceable Storage;
  - surveys and key trees [RBC13, RRBC13].
- **Analog limits:** [Sko05, HR20, Mur26].
- **Power-fault testing method:** Zheng et al. [ZTQL13].

## 2.6 Gaps

1. No systematic measurement of forward-secure key state across microcontroller storage
   libraries. That deleted data survives is known (section 1); how much key state survives,
   and what that means for a ratchet, is not.
2. The two libraries that zero old entries in place do not document crash behaviour during
   deletion, and nobody has tested it.
3. Crash-safe, fine-grained key erasure exists for Linux on NAND (DNEFS, via UBI) and for
   PCs (Holepunch, via a TPM), but not for bare-metal MCUs on raw NOR.
