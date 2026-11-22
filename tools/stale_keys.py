#!/usr/bin/env python3
"""
stale_keys.py - count old forward-secure keys left in a flash dump.

Two independent ways to look at a dump:

  scan   Structure-agnostic. Recomputes the probe's hash ratchet
         (k_0 = SHA-256("fsk-probe/seed/v1|" + seed),
          k_{i+1} = SHA-256("fsk-probe/next/v1|" + k_i))
         and searches every byte of the dump for every k_i. Works on any
         storage library (NVS, LittleFS, EEPROM emulation, raw partitions) and
         on full-flash dumps. This is the ground-truth number for the paper.

  nvs    Parses ESP-IDF NVS (Non-Volatile Storage) pages and lists every item,
         including entries marked "erased" that still hold data and entries
         that were zeroed by purge mode. Use it to explain *why* keys survive.

  chain  Prints the first keys of the ratchet, to check against the probe's
         serial log ("PROBE UPD epoch=... key_prefix=...").

Only the Python standard library is needed (Python 3.8+).

Examples
  python stale_keys.py scan nvs.bin --seed lums-cs5803 --epochs 100
  python stale_keys.py nvs nvs.bin --namespace fsk --key st --probe
  python stale_keys.py nvs flash_4MB.bin --offset 0x9000 --size 0x6000 --show-all
"""
import argparse
import hashlib
import json
import struct
import sys
import zlib

# --------------------------------------------------------------------------
# Ratchet (must match firmware/main/ratchet.c)
# --------------------------------------------------------------------------
SEED_LABEL = b"fsk-probe/seed/v1|"
NEXT_LABEL = b"fsk-probe/next/v1|"
KEY_LEN = 32


def ratchet_chain(seed: str, last_epoch: int):
    """Return [k_0, k_1, ..., k_last_epoch]."""
    keys = [hashlib.sha256(SEED_LABEL + seed.encode()).digest()]
    for _ in range(last_epoch):
        keys.append(hashlib.sha256(NEXT_LABEL + keys[-1]).digest())
    return keys


def find_all(haystack: bytes, needle: bytes):
    out, start = [], 0
    while True:
        i = haystack.find(needle, start)
        if i < 0:
            return out
        out.append(i)
        start = i + 1


def read_dump(path, offset=0, size=None):
    with open(path, "rb") as f:
        data = f.read()
    if offset or size:
        end = len(data) if size is None else offset + size
        if end > len(data):
            sys.exit(f"error: offset+size (0x{end:x}) is past the end of the dump (0x{len(data):x})")
        data = data[offset:end]
    return data


# --------------------------------------------------------------------------
# scan
# --------------------------------------------------------------------------
def cmd_scan(args):
    dump = read_dump(args.dump, args.offset, args.size)
    max_epoch = args.epochs if args.epochs is not None else args.max_epochs
    keys = ratchet_chain(args.seed, max_epoch)

    # index keys by their first 4 bytes, then walk the dump once
    by_prefix = {}
    for epoch, k in enumerate(keys):
        by_prefix.setdefault(k[:4], []).append(epoch)
    hits = {}
    for prefix, epochs in by_prefix.items():
        for off in find_all(dump, prefix):
            window = dump[off:off + KEY_LEN]
            for e in epochs:
                if window == keys[e]:
                    hits.setdefault(e, []).append(off + args.offset)

    if args.epochs is not None:
        current = args.epochs
    else:
        current = max(hits) if hits else None

    if current is None:
        print("No ratchet key found at all. Check --seed, --offset/--size, or whether the dump is encrypted.")
        return 1

    old_total = current  # epochs 0 .. current-1 should all be gone
    recovered = sorted(e for e in hits if e < current)
    newer = sorted(e for e in hits if e > current)
    live_found = current in hits

    print(f"dump: {args.dump}  ({len(dump)} bytes scanned, base offset 0x{args.offset:x})")
    print(f"seed: {args.seed!r}   current epoch: {current}"
          + ("" if args.epochs is not None else "  (guessed: highest key found)"))
    print(f"current key present:   {'yes' if live_found else 'NO'}")
    pct = 100.0 * len(recovered) / old_total if old_total else 0.0
    print(f"old keys recoverable:  {len(recovered)} / {old_total}  ({pct:.1f}%)")
    if newer:
        print(f"keys newer than current epoch found: {newer[:10]}{' ...' if len(newer) > 10 else ''}"
              "  (is --epochs right?)")
    if recovered:
        earliest = recovered[0]
        exposed = current - earliest
        print(f"earliest recoverable:  epoch {earliest}  -> with a hash ratchet every key from epoch "
              f"{earliest} to {current} can be recomputed ({exposed} of {old_total} past epochs exposed)")
        missing = sorted(set(range(old_total)) - set(recovered))
        print(f"recovered epochs: {compress_ranges(recovered)}")
        if missing:
            print(f"gone epochs:      {compress_ranges(missing)}")
        if args.verbose:
            for e in recovered:
                offs = ", ".join(f"0x{o:x}" for o in hits[e])
                print(f"  epoch {e:6d}  key {keys[e][:4].hex()}..  at {offs}")

    if args.json:
        result = {
            "dump": args.dump,
            "seed": args.seed,
            "current_epoch": current,
            "current_key_present": live_found,
            "old_total": old_total,
            "old_recovered": len(recovered),
            "earliest_recoverable_epoch": recovered[0] if recovered else None,
            "past_epochs_exposed_by_forward_hashing": (current - recovered[0]) if recovered else 0,
            "recovered_epochs": recovered,
            "offsets": {str(e): hits[e] for e in sorted(hits)},
        }
        with open(args.json, "w") as f:
            json.dump(result, f, indent=2)
        print(f"wrote {args.json}")
    return 0


def compress_ranges(nums):
    if not nums:
        return "-"
    parts, start, prev = [], nums[0], nums[0]
    for n in nums[1:]:
        if n == prev + 1:
            prev = n
            continue
        parts.append(f"{start}" if start == prev else f"{start}-{prev}")
        start = prev = n
    parts.append(f"{start}" if start == prev else f"{start}-{prev}")
    return ", ".join(parts)


# --------------------------------------------------------------------------
# NVS layout (ESP-IDF components/nvs_flash, format version 0xfe)
# --------------------------------------------------------------------------
PAGE_SIZE = 4096
ENTRY_SIZE = 32
ENTRY_COUNT = 126
ENTRY_DATA_OFFSET = 64

PAGE_STATES = {
    0xFFFFFFFF: "EMPTY",
    0xFFFFFFFE: "ACTIVE",
    0xFFFFFFFC: "FULL",
    0xFFFFFFF8: "FREEING",
    0xFFFFFFF0: "CORRUPT",
    0x00000000: "INVALID",
}
ENTRY_STATES = {0b11: "empty", 0b10: "written", 0b00: "erased", 0b01: "illegal"}

TYPES = {
    0x01: "u8", 0x11: "i8", 0x02: "u16", 0x12: "i16", 0x04: "u32", 0x14: "i32",
    0x08: "u64", 0x18: "i64", 0x24: "float", 0x28: "double",
    0x21: "str", 0x41: "blob(v1)", 0x42: "blob_data", 0x48: "blob_index",
}
VARIABLE = {0x21, 0x41, 0x42}
PRIMITIVE_FMT = {0x01: "<B", 0x11: "<b", 0x02: "<H", 0x12: "<h", 0x04: "<I", 0x14: "<i",
                 0x08: "<Q", 0x18: "<q", 0x24: "<f", 0x28: "<d"}


def nvs_crc(b: bytes) -> int:
    # esp_rom_crc32_le(0xffffffff, ...) == zlib.crc32(..., 0xffffffff)
    return zlib.crc32(b, 0xFFFFFFFF) & 0xFFFFFFFF


def parse_nvs(part: bytes):
    pages = []
    for pidx in range(len(part) // PAGE_SIZE):
        page = part[pidx * PAGE_SIZE:(pidx + 1) * PAGE_SIZE]
        state_word, seq = struct.unpack_from("<II", page, 0)
        version = page[8]
        bitmap = page[32:64]
        states = []
        for c in bitmap:
            for shift in (0, 2, 4, 6):
                states.append(ENTRY_STATES[(c >> shift) & 3])
        states = states[:ENTRY_COUNT]
        pinfo = {
            "index": pidx,
            "state": PAGE_STATES.get(state_word, f"0x{state_word:08x}"),
            "seq": None if seq == 0xFFFFFFFF else seq,
            "version": version,
            "items": [],
            "counts": {"written": 0, "erased": 0, "empty": 0, "illegal": 0, "zeroed": 0},
        }
        for s in states:
            pinfo["counts"][s] += 1

        i = 0
        while i < ENTRY_COUNT:
            raw = page[ENTRY_DATA_OFFSET + i * ENTRY_SIZE: ENTRY_DATA_OFFSET + (i + 1) * ENTRY_SIZE]
            st = states[i]
            if st == "empty" or raw == b"\xff" * ENTRY_SIZE:
                i += 1
                continue
            if raw == b"\x00" * ENTRY_SIZE:
                pinfo["counts"]["zeroed"] += 1
                i += 1
                continue
            ns, dtype, span, chunk = raw[0], raw[1], raw[2], raw[3]
            (hcrc,) = struct.unpack_from("<I", raw, 4)
            key = raw[8:24].split(b"\x00", 1)[0].decode("latin-1")
            data8 = raw[24:32]
            header_ok = nvs_crc(raw[0:4] + raw[8:32]) == hcrc
            if not header_ok or dtype not in TYPES or span == 0 or i + span > ENTRY_COUNT:
                # not a valid item header (e.g. a data entry we landed on, or garbage)
                pinfo["items"].append({"entry": i, "state": st, "valid": False, "raw": raw.hex()})
                i += 1
                continue
            item = {
                "entry": i, "state": st, "valid": True, "ns_index": ns, "type": TYPES[dtype],
                "type_code": dtype, "span": span, "chunk_index": chunk, "key": key,
            }
            if dtype in VARIABLE:
                size, _res, dcrc = struct.unpack_from("<HHI", data8, 0)
                payload = b"".join(
                    page[ENTRY_DATA_OFFSET + j * ENTRY_SIZE: ENTRY_DATA_OFFSET + (j + 1) * ENTRY_SIZE]
                    for j in range(i + 1, i + span))[:size]
                item["size"] = size
                item["payload"] = payload
                item["data_ok"] = (len(payload) == size and nvs_crc(payload) == dcrc)
            elif dtype == 0x48:
                total, count, start = struct.unpack_from("<IBB", data8, 0)
                item["size"] = total
                item["chunk_count"] = count
                item["chunk_start"] = start
            elif dtype in PRIMITIVE_FMT:
                (val,) = struct.unpack_from(PRIMITIVE_FMT[dtype], data8, 0)
                item["value"] = val
            pinfo["items"].append(item)
            i += span
        pages.append(pinfo)

    # namespace table: items in namespace 0 of type u8 map name -> index
    ns_names = {0: "(namespaces)"}
    for p in pages:
        for it in p["items"]:
            if it.get("valid") and it["ns_index"] == 0 and it["type_code"] == 0x01:
                ns_names[it["value"]] = it["key"]
    return pages, ns_names


def fmt_value(it, probe):
    if "payload" in it:
        pl = it["payload"]
        if probe and len(pl) == 4 + KEY_LEN:
            epoch = struct.unpack_from("<I", pl, 0)[0]
            return f"epoch={epoch} key={pl[4:8].hex()}..", epoch
        if it["type"] == "str":
            return repr(pl.rstrip(b"\x00").decode("utf-8", "replace")), None
        return pl[:16].hex() + (".." if len(pl) > 16 else ""), None
    if "value" in it:
        return str(it["value"]), None
    if it["type"] == "blob_index":
        return f"size={it['size']} chunks={it['chunk_count']} start=0x{it['chunk_start']:02x}", None
    return "", None


def cmd_nvs(args):
    part = read_dump(args.dump, args.offset, args.size)
    if len(part) % PAGE_SIZE:
        print(f"warning: {len(part)} bytes is not a whole number of 4 KB pages; trailing bytes ignored")
    pages, ns_names = parse_nvs(part)

    print(f"NVS partition: {len(pages)} pages of 4 KB")
    print(f"{'page':>4} {'state':<8} {'seq':>5}  written  erased  zeroed  empty")
    tot = {"written": 0, "erased": 0, "zeroed": 0, "empty": 0}
    for p in pages:
        c = p["counts"]
        for k in tot:
            tot[k] += c[k]
        seq = "-" if p["seq"] is None else str(p["seq"])
        print(f"{p['index']:>4} {p['state']:<8} {seq:>5}  {c['written']:7d} {c['erased']:7d} {c['zeroed']:7d} {c['empty']:6d}")
    print(f"{'all':>4} {'':<8} {'':>5}  {tot['written']:7d} {tot['erased']:7d} {tot['zeroed']:7d} {tot['empty']:6d}")
    print("(zeroed = entry slots overwritten with 0x00, e.g. by purge mode; counted per 32-byte slot)")
    print()

    rows = []
    for p in pages:
        for it in p["items"]:
            if not it.get("valid"):
                continue
            ns = ns_names.get(it["ns_index"], f"#{it['ns_index']}")
            if args.namespace and ns != args.namespace:
                continue
            if args.key and it["key"] != args.key:
                continue
            if not args.show_all and args.key is None and args.namespace is None and it["ns_index"] == 0:
                continue
            val, epoch = fmt_value(it, args.probe)
            rows.append((p, it, ns, val, epoch))

    live = [r for r in rows if r[1]["state"] == "written"]
    stale = [r for r in rows if r[1]["state"] == "erased"]
    stale_intact = [r for r in stale if r[1].get("data_ok", True)]

    print(f"{'page':>4} {'entry':>5} {'state':<8} {'namespace':<12} {'key':<15} {'type':<11} value")
    for p, it, ns, val, _ in rows:
        flag = "" if it.get("data_ok", True) else "  [data CRC mismatch]"
        print(f"{p['index']:>4} {it['entry']:>5} {it['state']:<8} {ns:<12} {it['key']:<15} {it['type']:<11} {val}{flag}")
    print()
    print(f"items shown: {len(rows)}   live (written): {len(live)}   "
          f"stale (erased but still readable): {len(stale_intact)}")

    if args.probe:
        live_ep = sorted(r[4] for r in live if r[4] is not None)
        stale_ep = sorted(r[4] for r in stale_intact if r[4] is not None)
        print(f"probe state blobs: live epoch(s) {compress_ranges(live_ep)}; "
              f"stale epochs still in flash: {len(stale_ep)} -> {compress_ranges(stale_ep)}")

    if args.json:
        out = []
        for p, it, ns, val, epoch in rows:
            d = {k: v for k, v in it.items() if k != "payload"}
            d.update(page=p["index"], namespace=ns, value=val, epoch=epoch)
            if "payload" in it:
                d["payload_hex"] = it["payload"].hex()
            out.append(d)
        with open(args.json, "w") as f:
            json.dump({"pages": [{k: v for k, v in p.items() if k != "items"} for p in pages],
                       "items": out}, f, indent=2)
        print(f"wrote {args.json}")
    return 0


# --------------------------------------------------------------------------
# chain
# --------------------------------------------------------------------------
def cmd_chain(args):
    for e, k in enumerate(ratchet_chain(args.seed, args.epochs)):
        print(f"epoch {e:6d}  {k.hex()}")
    return 0


def int_auto(s):
    return int(s, 0)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add_region(p, default_offset=0):
        p.add_argument("--offset", type=int_auto, default=default_offset,
                       help="start of the region inside the dump (e.g. 0x9000 for NVS in a full-flash dump)")
        p.add_argument("--size", type=int_auto, default=None, help="region size (default: to end of file)")

    s = sub.add_parser("scan", help="count recoverable ratchet keys anywhere in a dump")
    s.add_argument("dump")
    s.add_argument("--seed", required=True, help="same seed as CONFIG_PROBE_SEED")
    s.add_argument("--epochs", type=int, default=None,
                   help="current epoch (from 'PROBE DONE epoch=N'); if omitted, the highest key found is used")
    s.add_argument("--max-epochs", type=int, default=5000, help="search limit when --epochs is not given")
    s.add_argument("--json", help="also write results to this JSON file")
    s.add_argument("-v", "--verbose", action="store_true", help="list every recovered key with its offsets")
    add_region(s)
    s.set_defaults(func=cmd_scan)

    n = sub.add_parser("nvs", help="parse ESP-IDF NVS pages, including erased and zeroed entries")
    n.add_argument("dump")
    n.add_argument("--namespace", help="only show this namespace (e.g. fsk)")
    n.add_argument("--key", help="only show this key (e.g. st)")
    n.add_argument("--probe", action="store_true", help="decode 36-byte probe state blobs (epoch + key)")
    n.add_argument("--show-all", action="store_true", help="also show namespace-table entries")
    n.add_argument("--json", help="also write parsed items to this JSON file")
    add_region(n)
    n.set_defaults(func=cmd_nvs)

    c = sub.add_parser("chain", help="print the ratchet keys for a seed")
    c.add_argument("--seed", required=True)
    c.add_argument("--epochs", type=int, default=5)
    c.set_defaults(func=cmd_chain)

    args = ap.parse_args()
    try:
        sys.exit(args.func(args))
    except BrokenPipeError:  # e.g. piped into `head`
        sys.exit(0)


if __name__ == "__main__":
    main()
