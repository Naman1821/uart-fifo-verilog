# UART Controller with FIFO Buffering — RTL Design & Verification

A synthesizable **8N1 UART controller in Verilog**, verified with a **Python cocotb testbench**, linted with **Verilator**, synthesized with **Yosys**, and checked on every push by **GitHub Actions**.

```
            +-----------+     +---------+
 host ----->|  TX FIFO  |---->| uart_tx |------------------+--> uart_txd
            +-----------+     +---------+                  |
                                                 loopback  |
            +-----------+     +---------+     +-------+    |
 host <-----|  RX FIFO  |<----| uart_rx |<----|  mux  |<---+
            +-----------+     +---------+     +-------+<------- uart_rxd
                 ^                 ^
                 +---- tick16 -----+---- baud_gen (baud_div)
```

## Features

- **8N1 framing**: 1 start bit, 8 data bits (LSB first), 1 stop bit
- **16x oversampling receiver**: samples every bit in its middle; tolerates a few percent of baud-rate mismatch
- **2-flop synchronizer** on the asynchronous RX input (metastability protection)
- **Glitch rejection**: a start bit must still be low at mid-bit, short pulses are ignored
- **Run-time baud rate**: `baud = f_clk / (16 * baud_div)`
- **16-deep TX and RX FIFOs** (first-word-fall-through, parameterizable depth)
- **Sticky error flags**: `rx_overflow` and `frame_err`, cleared with `err_clr`
- **Internal loopback mode** for self-test

## Repository layout

```
rtl/        baud_gen.v  uart_tx.v  uart_rx.v  sync_fifo.v  uart_top.v
tb/         test_sync_fifo.py  test_uart.py  test_runner.py   (cocotb + pytest)
synth/      synth.ys  (Yosys script)
scripts/    mutation_check.py  (injects RTL bugs, checks the tests catch them)
docs/       DESIGN_NOTES.md   (why each design decision was made)
```

## Running it

Linux or WSL (Ubuntu):

```bash
sudo apt install iverilog verilator yosys gtkwave
pip install -r requirements.txt

make test     # 9 cocotb tests on Icarus Verilog
make waves    # same, and dumps sim_build/uart_top/uart_top.fst for GTKWave
make lint     # verilator --lint-only -Wall
make synth    # Yosys area reports in synth/
make mutate   # bug-injection check of the testbench
```

## Verification plan

| Test | What it proves |
|---|---|
| `fifo_fill_and_drain` | Writes when full and reads when empty are ignored; order is preserved |
| `fifo_random_traffic` | 2,400 cycles of random push/pop against a Python `deque` model; coverage bins for full, empty, write-while-full, read-while-empty and simultaneous read+write must all be hit |
| `loopback_multiple_baud_rates` | TX → RX through loopback at 4 baud divisors, 32 bytes each (more than the FIFO depth, so `tx_full` back-pressure is exercised) |
| `tx_frame_format` | An independent Python monitor decodes the TX line: start bit, LSB-first data, stop bit |
| `rx_back_to_back_frames` | Frames with zero idle time between them are all received |
| `framing_error_detected_and_cleared` | Stop bit = 0 → byte dropped, `frame_err` set, cleared by `err_clr` |
| `rx_overflow_keeps_oldest_data` | 19 unread bytes → oldest 16 kept, extra dropped, `rx_overflow` set |
| `glitch_is_not_a_start_bit` | A quarter-bit low pulse is ignored; the next real frame still decodes |
| `baud_mismatch_tolerance` | Sender 3% fast and 3% slow: every byte still received correctly |

Every test includes the corner bytes `0x00, 0xFF, 0x55, 0xAA, 0x01, 0x80` plus random data.

**Is the testbench actually strong?** `make mutate` injects 5 realistic bugs into the RTL (MSB-first shifting, broken FIFO full flag, level-triggered start detection, no glitch rejection, no stop-bit check). All 5 are caught.

## Results

| Check | Result |
|---|---|
| cocotb tests | 9 / 9 pass (Icarus Verilog 12, cocotb 2.x) |
| Verilator `-Wall` lint | clean, 0 warnings |
| Yosys generic synthesis | 1,092 cells, 345 flip-flops (256 of them are FIFO storage) |
| Yosys `synth_ice40` | ~370 LUT4s on Lattice iCE40 |
| Mutation check | 5 / 5 injected bugs caught |

## Roadmap

- [ ] Optional even/odd parity bit with parity-error flag
- [ ] APB slave wrapper with a register map (DATA, STATUS, CTRL, BAUD)
- [ ] Asynchronous FIFO (Gray-code pointers) for a separate host clock domain
- [ ] SystemVerilog Assertions for the FIFO invariants
