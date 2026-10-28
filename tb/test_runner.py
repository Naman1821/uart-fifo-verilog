"""pytest entry point: builds each RTL top level with Icarus Verilog and runs
its cocotb test module.

    pytest -v tb/test_runner.py            # run everything
    WAVES=1 pytest -v tb/test_runner.py    # also dump .fst waveforms
"""

import os
import sys
from pathlib import Path

import pytest
from cocotb_tools.runner import get_runner

TB_DIR = Path(__file__).resolve().parent
ROOT = TB_DIR.parent
RTL = ROOT / "rtl"
sys.path.insert(0, str(TB_DIR))

SIM = os.getenv("SIM", "icarus")
WAVES = os.getenv("WAVES", "0") == "1"

SOURCES = {
    "sync_fifo": [RTL / "sync_fifo.v"],
    "uart_top": [
        RTL / "baud_gen.v",
        RTL / "uart_tx.v",
        RTL / "uart_rx.v",
        RTL / "sync_fifo.v",
        RTL / "uart_top.v",
    ],
}


@pytest.mark.parametrize(
    "toplevel, test_module",
    [("sync_fifo", "test_sync_fifo"), ("uart_top", "test_uart")],
)
def test_rtl(toplevel, test_module):
    build_dir = ROOT / "sim_build" / toplevel
    runner = get_runner(SIM)
    runner.build(
        sources=SOURCES[toplevel],
        hdl_toplevel=toplevel,
        build_dir=build_dir,
        always=True,
        timescale=("1ns", "1ps"),
        waves=WAVES,
    )
    runner.test(
        hdl_toplevel=toplevel,
        test_module=test_module,
        build_dir=build_dir,
        test_dir=build_dir,
        waves=WAVES,
    )
