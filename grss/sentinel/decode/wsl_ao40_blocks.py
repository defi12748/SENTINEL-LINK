"""AO-40 FEC block decoder with exact symbol timing.

Runs under the *GNU Radio* Python (Linux/WSL), not the main environment.
Input: the ``clock_recovery_out.c64`` symbol dump written by gr-satellites'
BPSK demodulator. For every syncword hit we feed that one block through
gr-satellites' ``ao40_fec_deframer`` on its own, so each decoded frame is
bound to the symbol index where it started (gr-satellites' own KISS
timestamps are wall-clock and useless for offline files).

Usage: python3 wsl_ao40_blocks.py <clock_recovery_out.c64> <out.json> [threshold]
"""

import json
import sys

import numpy as np
import pmt
from gnuradio import blocks, gr
from satellites.components.deframers.ao40_fec_deframer import ao40_fec_deframer, _syncword

ROW, ROWS = 80, 65
BLOCK = ROW * ROWS  # 5200 channel symbols per AO-40 FEC block


class _Collector(gr.basic_block):
    def __init__(self):
        gr.basic_block.__init__(self, "collector", None, None)
        self.frames = []
        self.message_port_register_in(pmt.intern("in"))
        self.set_msg_handler(pmt.intern("in"), self._handle)

    def _handle(self, msg):
        self.frames.append(bytes(pmt.u8vector_elements(pmt.cdr(msg))))


def sync_hits(soft, threshold):
    sw = np.array([1.0 if c == "1" else -1.0 for c in _syncword])
    hard = np.sign(soft)
    n = len(hard) - BLOCK
    if n <= 0:
        return []
    idx = np.arange(n)[:, None] + ROW * np.arange(ROWS)[None, :]
    # correlate in chunks to bound memory
    corr = np.empty(n)
    for s in range(0, n, 200_000):
        e = min(n, s + 200_000)
        corr[s:e] = hard[idx[s:e]] @ sw
    need = ROWS - 2 * threshold
    hits, i = [], 0
    while i < n:
        if abs(corr[i]) >= need:
            j = i + int(np.argmax(np.abs(corr[i:i + ROW])))
            hits.append((j, int(np.sign(corr[j]))))
            i = j + BLOCK - ROW
        else:
            i += 1
    return hits


def decode_block(soft_block):
    tb = gr.top_block()
    src = blocks.vector_source_f(soft_block.astype(np.float32).tolist(), False)
    deframer = ao40_fec_deframer(syncword_threshold=8)
    sink = _Collector()
    tb.connect(src, deframer)
    tb.msg_connect((deframer, "out"), (sink, "in"))
    tb.run()
    return sink.frames


def main():
    sym = np.fromfile(sys.argv[1], dtype=np.complex64)
    out_path = sys.argv[2]
    threshold = int(sys.argv[3]) if len(sys.argv) > 3 else 8
    soft = np.real(sym[1:] * np.conj(sym[:-1]))
    soft = soft / (np.median(np.abs(soft)) + 1e-12)
    results = []
    for start, polarity in sync_hits(soft, threshold):
        seg = polarity * soft[max(0, start - ROW): start + BLOCK + 2 * ROW]
        frames = decode_block(seg)
        results.append({"symbol_index": int(start + 1), "decoded": [f.hex() for f in frames]})
    with open(out_path, "w") as fh:
        json.dump({"n_symbols": int(len(sym)), "blocks": results}, fh)


if __name__ == "__main__":
    main()
