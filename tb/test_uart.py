"""cocotb tests for uart_top.v

Testbench pieces:
  * uart_send()      - driver: bit-bangs serial frames onto uart_rxd
  * uart_receive()   - monitor: decodes frames seen on uart_txd
  * host_write()     - pushes bytes into the TX FIFO (respects tx_full)
  * host_read()      - pops bytes from the RX FIFO (FWFT interface)
The scoreboard is simply "bytes in == bytes out, in order".
"""

import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge, with_timeout

CLK_NS = 10            # 100 MHz system clock
FIFO_DEPTH = 16
CORNER_BYTES = [0x00, 0xFF, 0x55, 0xAA, 0x01, 0x80]


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
async def setup(dut, baud_div, loopback=0):
    Clock(dut.clk, CLK_NS, unit="ns").start()
    dut.rst_n.value = 0
    dut.baud_div.value = baud_div
    dut.loopback_en.value = loopback
    dut.tx_wr_en.value = 0
    dut.tx_wr_data.value = 0
    dut.rx_rd_en.value = 0
    dut.err_clr.value = 0
    dut.uart_rxd.value = 1          # serial line idles high
    await ClockCycles(dut.clk, 5)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 5)
    await FallingEdge(dut.clk)


def bit_cycles(baud_div):
    return 16 * baud_div


async def uart_send(dut, byte, cycles_per_bit, stop_bit=1, idle_bits=0):
    """Driver: start bit, 8 data bits LSB first, stop bit."""
    bits = [0] + [(byte >> i) & 1 for i in range(8)] + [stop_bit]
    for b in bits:
        dut.uart_rxd.value = b
        await ClockCycles(dut.clk, cycles_per_bit)
    dut.uart_rxd.value = 1
    if idle_bits:
        await ClockCycles(dut.clk, idle_bits * cycles_per_bit)


async def uart_receive(dut, cycles_per_bit):
    """Monitor: wait for a start bit on uart_txd and decode one frame,
    sampling in the middle of every bit."""
    while int(dut.uart_txd.value) == 1:
        await FallingEdge(dut.clk)
    await ClockCycles(dut.clk, cycles_per_bit // 2)
    assert int(dut.uart_txd.value) == 0, "start bit not low at mid-bit"
    value = 0
    for i in range(8):
        await ClockCycles(dut.clk, cycles_per_bit)
        value |= int(dut.uart_txd.value) << i
    await ClockCycles(dut.clk, cycles_per_bit)
    assert int(dut.uart_txd.value) == 1, "stop bit not high"
    return value


async def host_write(dut, data):
    """Push bytes into the TX FIFO, waiting whenever it is full."""
    await FallingEdge(dut.clk)
    for b in data:
        while int(dut.tx_full.value):
            await FallingEdge(dut.clk)
        dut.tx_wr_en.value = 1
        dut.tx_wr_data.value = b
        await FallingEdge(dut.clk)
        dut.tx_wr_en.value = 0


async def host_read(dut, n):
    """Pop n bytes from the RX FIFO."""
    got = []
    await FallingEdge(dut.clk)
    while len(got) < n:
        dut.rx_rd_en.value = 0
        if not int(dut.rx_empty.value):
            got.append(int(dut.rx_rd_data.value))   # FWFT: head already visible
            dut.rx_rd_en.value = 1                  # pop it on the next edge
        await FallingEdge(dut.clk)
    dut.rx_rd_en.value = 0
    return got


def random_payload(n):
    return CORNER_BYTES + [random.randrange(256) for _ in range(n - len(CORNER_BYTES))]


def assert_no_errors(dut):
    assert int(dut.frame_err.value) == 0, "unexpected framing error"
    assert int(dut.rx_overflow.value) == 0, "unexpected RX overflow"


# --------------------------------------------------------------------------
# tests
# --------------------------------------------------------------------------
@cocotb.test(timeout_time=20, timeout_unit="ms")
async def loopback_multiple_baud_rates(dut):
    """TX -> RX through internal loopback, 32 bytes at each of 4 baud rates.
    32 bytes > FIFO depth, so this also exercises tx_full back-pressure."""
    await setup(dut, baud_div=2, loopback=1)
    for div in (2, 3, 5, 8):
        dut.baud_div.value = div
        payload = random_payload(32)
        reader = cocotb.start_soon(host_read(dut, len(payload)))
        await host_write(dut, payload)
        got = await reader
        assert got == payload, f"baud_div={div}: sent {payload}, got {got}"
        assert_no_errors(dut)
        dut._log.info("baud_div=%d: %d bytes looped back OK", div, len(payload))


@cocotb.test(timeout_time=10, timeout_unit="ms")
async def tx_frame_format(dut):
    """Monitor decodes uart_txd independently of our own receiver."""
    div = 4
    await setup(dut, baud_div=div)
    payload = random_payload(20)
    seen = []

    async def monitor():
        for _ in payload:
            seen.append(await uart_receive(dut, bit_cycles(div)))

    mon = cocotb.start_soon(monitor())
    await host_write(dut, payload)
    await mon
    assert seen == payload, f"sent {payload}, line carried {seen}"
    await ClockCycles(dut.clk, bit_cycles(div))
    assert int(dut.tx_idle.value) == 1, "tx_idle should be high after the last frame"


@cocotb.test(timeout_time=10, timeout_unit="ms")
async def rx_back_to_back_frames(dut):
    """External driver sends frames with no idle gap between them."""
    div = 4
    await setup(dut, baud_div=div)
    payload = random_payload(20)
    reader = cocotb.start_soon(host_read(dut, len(payload)))
    for b in payload:
        await uart_send(dut, b, bit_cycles(div))
    got = await with_timeout(reader, 1, "ms")
    assert got == payload
    assert_no_errors(dut)


@cocotb.test(timeout_time=10, timeout_unit="ms")
async def framing_error_detected_and_cleared(dut):
    """A frame with stop bit = 0 must be dropped and set the sticky frame_err."""
    div = 4
    await setup(dut, baud_div=div)
    await uart_send(dut, 0x3C, bit_cycles(div))
    await uart_send(dut, 0xA5, bit_cycles(div), stop_bit=0, idle_bits=2)  # bad frame
    await uart_send(dut, 0x7E, bit_cycles(div), idle_bits=1)

    got = await with_timeout(host_read(dut, 2), 1, "ms")
    assert got == [0x3C, 0x7E], f"bad frame should be dropped, got {got}"
    assert int(dut.rx_empty.value) == 1
    assert int(dut.frame_err.value) == 1, "frame_err should be set"

    dut.err_clr.value = 1
    await FallingEdge(dut.clk)
    dut.err_clr.value = 0
    await FallingEdge(dut.clk)
    assert int(dut.frame_err.value) == 0, "err_clr should clear frame_err"


@cocotb.test(timeout_time=10, timeout_unit="ms")
async def rx_overflow_keeps_oldest_data(dut):
    """Send FIFO_DEPTH + 3 bytes without reading: the first FIFO_DEPTH bytes
    are kept, the extra ones are dropped and rx_overflow is set."""
    div = 2
    await setup(dut, baud_div=div)
    payload = random_payload(FIFO_DEPTH + 3)
    for b in payload:
        await uart_send(dut, b, bit_cycles(div))
    await ClockCycles(dut.clk, 2 * bit_cycles(div))
    assert int(dut.rx_overflow.value) == 1, "rx_overflow should be set"

    got = await host_read(dut, FIFO_DEPTH)
    assert got == payload[:FIFO_DEPTH]
    await FallingEdge(dut.clk)
    assert int(dut.rx_empty.value) == 1, "dropped bytes must not appear in the FIFO"


@cocotb.test(timeout_time=10, timeout_unit="ms")
async def glitch_is_not_a_start_bit(dut):
    """A low pulse shorter than half a bit must be ignored; the receiver
    must still decode the next real frame correctly."""
    div = 4
    await setup(dut, baud_div=div)
    dut.uart_rxd.value = 0
    await ClockCycles(dut.clk, 4 * div)              # 4 ticks = quarter bit
    dut.uart_rxd.value = 1
    await ClockCycles(dut.clk, 12 * bit_cycles(div))  # longer than a frame
    assert int(dut.rx_empty.value) == 1, "glitch produced a byte"
    assert_no_errors(dut)

    await uart_send(dut, 0xC3, bit_cycles(div), idle_bits=1)
    got = await with_timeout(host_read(dut, 1), 1, "ms")
    assert got == [0xC3]


@cocotb.test(timeout_time=20, timeout_unit="ms")
async def baud_mismatch_tolerance(dut):
    """Sender clock 3% fast and 3% slow: 16x oversampling with mid-bit
    sampling must still receive every byte."""
    div = 8                                   # 128 clocks per bit
    await setup(dut, baud_div=div)
    for factor in (0.97, 1.03):
        cycles = round(bit_cycles(div) * factor)
        payload = random_payload(16)
        reader = cocotb.start_soon(host_read(dut, len(payload)))
        for b in payload:
            await uart_send(dut, b, cycles)
        got = await with_timeout(reader, 1, "ms")
        assert got == payload, f"failed at {cycles} clocks/bit"
        assert_no_errors(dut)
        dut._log.info("sender at %.0f%% speed (%d clocks/bit): OK", factor * 100, cycles)
