## Goal

DNEFS-style secure deletion [RCB12], in the spirit of Apple Effaceable Storage, adapted to
microcontrollers. Only one small key area needs real erasure. It must be crash-safe without
UBI or an OS, and leave no deletion window.

## What porting DNEFS requires

- **Own atomicity.** WRITTEN → VALID commit bit, then zero, then RETIRED. Recovery at boot
  zeroes every non-current slot, and is idempotent. Same multi-state idea as SICP [KSDS19].
- **Zero now, erase later.** NOR allows 1→0 in place, so the old key is zeroed before
  `ks_update()` returns. The sector erase only reclaims space.
- **Compact state.** Each slot's state bits act as the key-state map; nothing is kept in RAM
  beyond the current slot index.
- **Workload-shaped layout.** A ratchet needs one live slot. A GGM tree later needs one slot
  per live node.

## Known limitation

Digital erasure only. Charge-trap NOR leaked over 80% of old content after sanitization,
depending on aging; floating-gate NOR did not [Mur26].
- Record the flash part of every board.
- Short key lifetimes may limit imprinting. This is an untested hypothesis, not a claim.
