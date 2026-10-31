# SPDX-License-Identifier: GPL-2.0-only
"""Prepare stimulus from captured TS files and check the multiplexed output.

  python3 tb_check.py prep <ts0> <ts1> <ts2> <ts3>   -> ch0..3.hex
  python3 tb_check.py check                          -> compares out.hex with ch*.hex
"""
import sys

NPKT, PKT = 400, 188
TRUNC_CH, TRUNC_AT = 1, 100


def prep(paths):
    for ch, path in enumerate(paths):
        data = open(path, "rb").read(NPKT * PKT)
        assert len(data) == NPKT * PKT, f"{path}: too short"
        with open(f"ch{ch}.hex", "w") as f:
            f.writelines(f"{b:02x}\n" for b in data)


def check():
    expected = {}
    for ch in range(4):
        raw = bytes(int(l, 16) for l in open(f"ch{ch}.hex"))
        pkts = [raw[i * PKT:(i + 1) * PKT] for i in range(NPKT)]
        if ch == TRUNC_CH:
            del pkts[TRUNC_AT]          # the truncated packet must be dropped
        expected[ch] = pkts

    lines = open("out.hex").read().split("\n")
    drops = [l for l in lines if l.startswith("//")]
    out = bytes(int(l, 16) for l in lines if l and not l.startswith("//"))
    assert len(out) % PKT == 0, f"output length {len(out)} is not a multiple of {PKT}"

    got = {ch: [] for ch in range(4)}
    for i in range(0, len(out), PKT):
        pkt = out[i:i + PKT]
        tag = pkt[0]
        assert tag & 0x0F == 0x07 and 1 <= tag >> 4 <= 4, f"bad tag {tag:#04x} at packet {i // PKT}"
        got[(tag >> 4) - 1].append(b"\x47" + pkt[1:])

    drop_cnt = [int(x) for x in drops[0].split()[2:6]] if drops else [0] * 4
    ok = True
    for ch in range(4):
        exp, g = expected[ch], got[ch]
        # output must be the expected packets in order, minus whole dropped packets
        it = iter(exp)
        in_order = all(any(p == e for e in it) for p in g)
        missing = len(exp) - len(g)
        status = "OK" if in_order and missing == drop_cnt[ch] else "MISMATCH"
        ok &= status == "OK"
        print(f"ch{ch}: expected {len(exp)} pkts, got {len(g)}, dropped {drop_cnt[ch]} (missing {missing}), in order {in_order} -> {status}")
    print("PASS" if ok else "FAIL")
    return ok


if __name__ == "__main__":
    if sys.argv[1] == "prep":
        prep(sys.argv[2:6])
    else:
        sys.exit(0 if check() else 1)
