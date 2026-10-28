# Design Notes

Why the design looks the way it does. Each section answers one question.

## 1. What does 8N1 mean, and what does a frame look like?

8 data bits, No parity, 1 stop bit. The line idles at 1.

```
 idle  start  b0  b1  b2  b3  b4  b5  b6  b7  stop  idle
 ‾‾‾‾‾\_____/‾‾‾\___/‾‾‾ ... (data, LSB first) .../‾‾‾‾‾‾‾‾‾‾
```

The falling edge of the start bit is the only timing reference the receiver gets, so every frame re-synchronizes the receiver.

## 2. Why oversample at 16x?

The receiver has no clock from the sender. It only knows the nominal bit time. With 16 ticks per bit it can:

- find the falling edge of the start bit to within 1/16 of a bit,
- wait 8 ticks to land in the **middle** of the start bit,
- then wait 16 ticks for the middle of each next bit.

Sampling in the middle gives the most margin on both sides of the bit.

## 3. How much baud-rate mismatch can it tolerate?

The stop bit is sampled 9.5 bit-times after the start edge. That sample must stay inside the sender's stop bit, which spans 9 to 10 of the sender's bit-times. So the sender's bit time `r` (relative to ours) must satisfy `9r < 9.5 < 10r`, i.e. roughly **-5% < error < +5.5%** in theory. Edge-detection uncertainty (up to 1 tick) eats some of that, so ±3% is tested and passes. Real systems keep the combined error under about 2%.

Baud divisor rounding also adds error. At 50 MHz and 115200 baud: `50e6 / (16 × 115200) = 27.13`, rounded to 27, giving 115741 baud, an error of 0.47%.

## 4. Why a 2-flop synchronizer on `rx`?

`rx` comes from another device with its own clock, so it can change right at our clock edge. The first flop may go **metastable** (an in-between voltage that takes time to resolve). The second flop gives it a full clock period to settle before any logic uses it. The cost is 2 cycles of latency, which is nothing compared to a bit time.

## 5. Why detect the start bit on an edge, not a level?

After a framing error the line can still be low (the stop bit was 0). If the receiver started a frame whenever the line was low, it would immediately start a fake frame in the middle of the bad one. Waiting for a **high-to-low edge** means it only starts on a real new start bit. The test `framing_error_detected_and_cleared` fails if this is changed to level detection.

## 6. How are glitches rejected?

After the start edge the receiver waits half a bit and checks the line again. If it is high, the "start bit" was a noise pulse shorter than half a bit, and the receiver goes back to idle.

## 7. How does the FIFO know full from empty?

Read and write pointers have **one extra bit** above the address bits.

- Pointers fully equal → **empty**.
- Address bits equal but the extra bit differs → the writer has gone around the buffer once more than the reader → **full**.

`count = wr_ptr - rd_ptr` works with the same modulo arithmetic. Without the extra bit, full and empty would both look like "pointers equal". The mutation check removes the extra bit from the full flag, and every test fails.

## 8. What does first-word-fall-through mean?

In a standard FIFO you assert `rd_en` and the data appears a cycle later. In a FWFT FIFO the oldest entry is **already on `rd_data`** whenever `empty` is 0, and `rd_en` just removes it. This makes the TX path simple: the transmitter sees `!empty` as "a byte is waiting" and takes it in the same cycle it pops the FIFO.

## 9. Why is the TX output registered?

`tx_next` is decoded from the state machine. Feeding that combinational signal straight to a pin could produce glitches while the state bits change. Registering it costs one cycle of delay, which applies equally to every edge, so bit widths are unchanged.

## 10. Why are the error flags sticky?

The receiver produces 1-cycle pulses. A host polling the status could easily miss a single cycle, so the top level latches errors until the host clears them. If a new error arrives in the same cycle as `err_clr`, the error wins, so nothing is lost.

## 11. Why asynchronous reset?

Asynchronous assert lets the design reach a known state even if the clock is not running yet, which is the common style in ASIC flows. In a production chip the reset release would also be synchronized to `clk`.

## 12. How is the testbench organized?

| Piece | Role |
|---|---|
| Driver (`uart_send`) | Bit-bangs frames onto `uart_rxd`, with configurable bit time and stop bit |
| Monitor (`uart_receive`) | Decodes frames from `uart_txd` without using our receiver |
| Host model (`host_write`, `host_read`) | Talks to the FIFOs like a CPU would |
| Reference model | Python `deque` for the FIFO; "bytes out == bytes in" for the UART |
| Coverage bins | Prove the random FIFO test actually reached full, empty and the corner cases |

Inputs are driven on the falling clock edge so they are stable when the DUT samples them on the rising edge.
