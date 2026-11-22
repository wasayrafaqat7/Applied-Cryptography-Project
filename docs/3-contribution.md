# 3. Our contribution

## Paper flow

1. Problem (C1 measurement).
2. Existing fixes fall short or are untested (C2 baselines).
3. Our key store (C3).
4. Evaluation of C3 against the baselines on the same harness.

## C1 (backbone): first systematic measurement of forward-secure key state across microcontroller storage libraries

- We do **not** claim to be first to show deleted data survives in MCU flash (see section 1).
- We claim the cross-library measurement, the earliest-recoverable-epoch metric, and the
  ratchet consequence: k_0 is permanent in default ESP-IDF NVS.

## C2 (baseline): first power-loss evaluation of deletion in microcontroller storage libraries

- Baselines: ESP-IDF purge mode, `nvs_purge_all()`, Trezor NORCOW, boot-time zeroing.
- Method: thousands of random power cuts per baseline, following [ZTQL13]; dump and scan
  after each batch.

## C3 (main): DNEFS-style secure deletion adapted to microcontrollers, with a power-loss argument and testing

The idea is DNEFS's [RCB12] and Apple Effaceable Storage's [AppleSec]: only one small key area ever
needs real erasure. We claim what porting it to a microcontroller requires:

| DNEFS assumption | Microcontroller reality | Our design |
| --- | --- | --- |
| UBI atomic block updates, an OS | Bare metal, raw flash | Own crash-safe slot protocol and boot-time recovery (cf. SICP [KSDS19]) |
| NAND: no re-programming, so batched purges | NOR: bits 1→0 in place | Zero the old key before the update returns; sector erase later only to reclaim space |
| Deleted data readable until next purge | Ratchet must forget immediately | No deletion window |
| MB of RAM for the key-state map | KB of RAM | Compact key-state map |
| File workload | Ratchet, later GGM tree | Key-area layout matched to the scheme's update pattern |

**C3 must beat the baselines on more than one axis**, in case they survive power cuts:

| Axis | Purge mode / NORCOW | C3 target |
| --- | --- | --- |
| Portability | ESP-IDF v6+ only / Trezor only | Any NOR MCU and older SDKs (e.g. ESP-IDF v5.x) |
| Deletion window | Unknown under power loss | None, shown under power cuts |
| Writes and wear per update | Unbounded (garbage collection) | Bounded and stated |
| Guarantee | Informal | Stated erasure guarantee that plugs into the forward-security proof's assumption |

**Evaluation (same harness):**
- recovered old keys (target 0);
- earliest recoverable epoch;
- update latency;
- energy per update;
- writes and erases per update and projected lifetime;
- boot failures per 1,000 cuts.

## Future work

GGM-tree Puncturable Key Wrapping [BGP22] on top of the key area.
