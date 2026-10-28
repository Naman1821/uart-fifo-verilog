# make test    - run all cocotb tests (Icarus Verilog)
# make waves   - same, plus .fst waveforms in sim_build/<top>/
# make lint    - Verilator lint with every warning enabled
# make synth   - Yosys synthesis, area reports in synth/
# make mutate  - inject known RTL bugs and check the tests catch them
# make all     - lint + test + synth

PYTHON ?= python3
YOSYS  ?= yosys
RTL    := rtl/baud_gen.v rtl/uart_tx.v rtl/uart_rx.v rtl/sync_fifo.v rtl/uart_top.v

.PHONY: all test waves lint synth mutate clean

all: lint test synth

test:
	$(PYTHON) -m pytest -v tb/test_runner.py

waves:
	WAVES=1 $(PYTHON) -m pytest -v tb/test_runner.py
	@echo "Open with: gtkwave sim_build/uart_top/uart_top.fst"

lint:
	verilator --lint-only -Wall --top-module uart_top $(RTL)

synth:
	$(YOSYS) -q -s synth/synth.ys
	@grep -E "Number of cells|DFF|SB_LUT4" synth/area_report.txt synth/ice40_report.txt

mutate:
	$(PYTHON) scripts/mutation_check.py

clean:
	rm -rf sim_build results.xml .pytest_cache tb/__pycache__ synth/*_report.txt
