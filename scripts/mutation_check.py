"""Mutation check: is the testbench strong enough to catch real bugs?

Each mutation below copies the project to a temp folder, injects one
realistic RTL bug, and runs the full test suite. A good testbench must
FAIL on every mutant. Run from the repo root:

    python3 scripts/mutation_check.py
"""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# (name, file, original text, buggy text)
MUTATIONS = [
    ("receiver assembles bits MSB-first", "uart_rx.v",
     "shift    <= {rx_sync, shift[7:1]};",
     "shift    <= {shift[6:0], rx_sync};"),
    ("FIFO full flag ignores the extra pointer bit", "sync_fifo.v",
     "(wr_ptr[AW] != rd_ptr[AW]) &&",
     "1'b1 &&"),
    ("start bit detected on level instead of edge", "uart_rx.v",
     "wire start_edge = rx_prev & ~rx_sync;",
     "wire start_edge = ~rx_sync;"),
    ("no glitch rejection at mid start bit", "uart_rx.v",
     "if (!rx_sync) begin   // still low: real start bit",
     "if (1'b1) begin   // still low: real start bit"),
    ("stop bit never checked", "uart_rx.v",
     "if (rx_sync) begin\n                                rx_data  <= shift;",
     "if (1'b1) begin\n                                rx_data  <= shift;"),
]


def run_mutant(name, file, original, buggy):
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        shutil.copytree(ROOT / "rtl", work / "rtl")
        shutil.copytree(ROOT / "tb", work / "tb")
        target = work / "rtl" / file
        src = target.read_text()
        if original not in src:
            return "PATTERN NOT FOUND"
        target.write_text(src.replace(original, buggy, 1))
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "tb/test_runner.py"],
            cwd=work, capture_output=True, text=True, timeout=900,
        )
        return "caught" if result.returncode != 0 else "MISSED"


def main():
    missed = 0
    for name, file, original, buggy in MUTATIONS:
        status = run_mutant(name, file, original, buggy)
        missed += status != "caught"
        print(f"[{status:>7}] {file:12} {name}")
    print(f"\n{len(MUTATIONS) - missed}/{len(MUTATIONS)} injected bugs caught")
    sys.exit(1 if missed else 0)


if __name__ == "__main__":
    main()
