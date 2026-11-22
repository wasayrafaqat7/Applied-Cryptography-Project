# 1. The problem

## Forward security assumes erasure

Forward-secure and puncturable schemes update the key after each message and delete the
old one [BY03, GM15, DJSS18, BGP22]. Recent IoT protocols rely on the same assumption:
Chronos [Chronos25], Graphene [Graphene25], Diamond [Diamond26] and KUDOS [KUDOS].
Every security proof assumes the deleted key is gone.

## Flash breaks that assumption

- NOR flash can only change bits from 1 to 0 without a sector erase. Storage libraries
  therefore write each update to a new location and mark the old one as erased.
- This is documented for ESP-IDF NVS [ESP-NVS] and Zephyr's storage backends, and shows
  up in practice:
  - a deleted Wi-Fi password found in ESP32 NVS [cairn28];
  - deleted data left behind by LittleFS [intWave26];
  - superseded Zephyr ITS entries that stay until garbage collection [CVE-2026-15890].
- The ESP-IDF API hides it. After 100 updates the probe logs
  `NVS_STATS used=5 free=751`: stale entries are counted as free (`Page::calcEntries`).

## Measured (ESP-IDF v6.1 NVS, host emulation)

- Every old key survives up to 150 updates. Reclaiming starts at 155 updates, matching
  (6 − 1) × 124 / 4: 4 entries per update, one page kept free.
- After that, 124–145 old keys remained at every update count we tested, up to 5,000
  (133 of 5,000 at 5,000 updates).
- **Epochs 0–30 are never reclaimed.** Garbage collection reclaims the page with the most
  entries not in use, and page 0 always holds the live namespace record, so it never wins.
  With a hash ratchet, k_0 gives every later key: no forward secrecy at all.
- We therefore report the **earliest recoverable epoch** alongside the count. For
  forward-computable ratchets, it sets the real exposure.

## Threat model

- **Attacker.** Obtains the device at a time of their choosing and reads all non-volatile
  memory: through the serial bootloader, by desoldering an external flash chip, or by
  fault injection. That includes flash erase suppression on internal MCU flash [SWO+24]
  and eFuse key extraction on ESP32 [CVE-2019-17391, AHT23].
- **Power.** May fail at any instant, including mid-update.
- **Win condition.** Recovers any key that should already have been erased, i.e. whose
  replacing update has returned. During an interrupted update, only the old and the new
  key may exist.
- **Out of scope:** side channels, copies in RAM, and analog residue in flash cells.
  - Analog recovery after sanitization has been shown on NAND [HR20] and on charge-trap
    NOR, where over 80% of old content was reconstructed with partial erases, depending on
    device aging [Mur26]. Floating-gate NOR showed no imprinting in the same study.
    Erased cells can also retain data [Sko05].
  - Our guarantee, like ESP-IDF purge mode's, is *digital* erasure.
  - We record each board's flash part (`esptool flash-id`) and state whether it is
    charge-trap.

## Why flash or NVS encryption does not close the gap

Their keys are static. Stale entries stay in flash, encrypted under a key that can be
extracted later [CVE-2019-17391, AHT23]. Silicon Labs NVM3 on Series-3 parts is the same
case: AES-GCM under a static device key.
