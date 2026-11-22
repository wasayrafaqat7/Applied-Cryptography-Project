# C3 key store: design draft

## Goal

DNEFS-style secure deletion [RCB12], in the spirit of Apple Effaceable Storage [AppleSec], adapted to
microcontrollers. Only one small key area needs real erasure. It must be crash-safe without
UBI or an OS, and leave no deletion window.

## Security definition (digital erasure)

Let e be the epoch of the last `ks_update()` that returned.

- **After an update returns:** no k_i with i ≤ e − 1 is recoverable from a full dump of the
  store; only k_e is present.
- **During an interrupted update e → e+1:** a dump contains at most {k_e, k_{e+1}}.
- **After boot recovery:** exactly one key is present, either k_e or k_{e+1}, and the store
  reports which epoch it holds.

This is the erasure assumption the forward-security proofs make, stated so the harness can
test it: `stale_keys.py scan` must report 0 recoverable old keys after every returned update
and after every recovery, across all power-cut runs.

## What porting DNEFS requires

- **Own atomicity.** WRITTEN → VALID commit bit, then zero, then RETIRED. Recovery at boot
  zeroes every non-current slot, and is idempotent. Same multi-state idea as SICP [KSDS19].
- **Zero now, erase later.** NOR allows 1→0 in place, so the old key is zeroed before
  `ks_update()` returns. The sector erase only reclaims space.
- **Compact state.** Each slot's state bits act as the key-state map; nothing is kept in RAM
  beyond the current slot index.
- **Workload-shaped layout.** A ratchet needs one live slot. A GGM tree later needs one slot
  per live node.

## Platform constraints

- **No flash encryption on the store partition.** In-place zeroing needs raw writes to the
  same physical bytes. With ESP32 flash encryption, a write goes through the cipher, so
  "zero" is not stored as zeros. Keep the store in a separate, unencrypted partition
  (it holds only ratchet state, which the design itself protects).
- **Check re-programming rules per flash part before relying on them.** The design assumes
  a byte that was already programmed can be programmed again to 0x00 without an erase.
  For each board's flash part, record from the datasheet:
  - whether re-programming already-programmed bits to 0 is allowed;
  - any limit on partial programs per page (or per word, on internal MCU flash with ECC,
    where re-programming may be forbidden outright);
  - erase endurance, to project lifetime from measured erases per update.
  If a part forbids re-programming, the fallback is zeroing by erase, which brings back a
  deletion window; state it per part.

## Known limitation

Digital erasure only. Charge-trap NOR leaked over 80% of old content after sanitization,
depending on aging; floating-gate NOR did not [Mur26].
- Record the flash part of every board.
- Short key lifetimes may limit imprinting. This is an untested hypothesis, not a claim.
