"""cocotb tests for sync_fifo.v

The FIFO is checked against a Python reference model (collections.deque).
Inputs are driven on the falling clock edge so they are stable when the
DUT samples them on the next rising edge.
"""

import random
from collections import Counter, deque

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge

DEPTH = 16


async def reset(dut):
    Clock(dut.clk, 10, unit="ns").start()
    dut.rst_n.value = 0
    dut.wr_en.value = 0
    dut.rd_en.value = 0
    dut.wr_data.value = 0
    await ClockCycles(dut.clk, 3)
    dut.rst_n.value = 1
    await FallingEdge(dut.clk)


def check_outputs(dut, model):
    """Compare DUT flags and head-of-queue with the model."""
    assert int(dut.empty.value) == (len(model) == 0), "empty flag mismatch"
    assert int(dut.full.value) == (len(model) == DEPTH), "full flag mismatch"
    assert int(dut.count.value) == len(model), "count mismatch"
    if model:
        assert int(dut.rd_data.value) == model[0], "FWFT head mismatch"


@cocotb.test()
async def fifo_fill_and_drain(dut):
    """Directed: overfill (extra writes dropped), then over-drain (extra reads ignored)."""
    await reset(dut)
    model = deque()

    # Write DEPTH + 4 bytes: the last 4 must be dropped, not overwrite data
    for i in range(DEPTH + 4):
        check_outputs(dut, model)
        dut.wr_en.value = 1
        dut.wr_data.value = (0xA0 + i) & 0xFF
        if len(model) < DEPTH:
            model.append((0xA0 + i) & 0xFF)
        await FallingEdge(dut.clk)
    dut.wr_en.value = 0
    await FallingEdge(dut.clk)
    check_outputs(dut, model)
    assert int(dut.full.value) == 1

    # Read DEPTH + 4 times: data must come out in order, extra reads ignored
    for _ in range(DEPTH + 4):
        check_outputs(dut, model)
        dut.rd_en.value = 1
        if model:
            model.popleft()
        await FallingEdge(dut.clk)
    dut.rd_en.value = 0
    await FallingEdge(dut.clk)
    check_outputs(dut, model)
    assert int(dut.empty.value) == 1


@cocotb.test()
async def fifo_random_traffic(dut):
    """Constrained-random push/pop in three phases (fill-heavy, balanced,
    drain-heavy), checked every cycle, with coverage bins that must all be hit."""
    await reset(dut)
    model = deque()
    cov = Counter()

    for write_prob in (0.8, 0.5, 0.2):
        for _ in range(800):
            check_outputs(dut, model)

            wr = random.random() < write_prob
            rd = random.random() < (1.0 - write_prob)
            data = random.randrange(256)

            was_full = len(model) == DEPTH
            was_empty = len(model) == 0

            # functional coverage bins
            cov["full"] += was_full
            cov["empty"] += was_empty
            cov["write_while_full"] += wr and was_full
            cov["read_while_empty"] += rd and was_empty
            cov["read_and_write_same_cycle"] += wr and rd and not was_full and not was_empty

            dut.wr_en.value = int(wr)
            dut.rd_en.value = int(rd)
            dut.wr_data.value = data

            # update the model exactly the way the hardware will on this edge
            if rd and not was_empty:
                model.popleft()
            if wr and not was_full:
                model.append(data)

            await FallingEdge(dut.clk)

    dut.wr_en.value = 0
    dut.rd_en.value = 0

    dut._log.info("FIFO coverage: %s", dict(cov))
    missing = [b for b in ("full", "empty", "write_while_full", "read_while_empty",
                           "read_and_write_same_cycle") if cov[b] == 0]
    assert not missing, f"coverage holes: {missing}"
