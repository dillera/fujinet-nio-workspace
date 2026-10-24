ROOT := $(abspath ../../..)
OUT := build/relocation-feasibility
APPS := $(ROOT)/repos/nio-core-apps
LIB := $(ROOT)/repos/fujinet-nio-lib
API_OUT := build/api-closure
O65_API_OUT := build/o65-api-closure
O65_RUNTIME_OUT := build/o65-api-runtime
CL65 ?= cl65

.PHONY: relocation-feasibility api-closure-map o65-relocation-metadata o65-api-closure o65-api-runtime load-run-symbols allocation-plan allocation-plan-o65 clean

relocation-feasibility:
	soft65c02_unit -b $(OUT) -i relocation_feasibility.yaml

api-closure-map: $(API_OUT)/resident-api-closure.map
	python3 resident_footprint_report.py --map $<

# ld65's supported o65 writer emits relocation metadata for a loadable cc65
# module.  This target deliberately stops at format validation: deploying an
# o65 loader is a later implementation decision, not part of this feasibility
# investigation.
o65-relocation-metadata: build/o65-probe.o65
	python3 verify_o65_probe.py $<

# Use the actual Atari archive plus cc65 Atari runtime library, but omit crt0:
# the resident module is entered by a CIO vector, not as an XEX main program.
o65-api-closure: $(O65_API_OUT)/resident-api-closure.o65
	co65 --verbose --no-output $<
	python3 verify_o65_api_closure.py --self-test
	python3 verify_o65_api_closure.py $<

o65-api-runtime: $(O65_RUNTIME_OUT)/module-a.bin $(O65_RUNTIME_OUT)/module-b.bin $(O65_RUNTIME_OUT)/runtime-control.bin $(O65_RUNTIME_OUT)/runtime-siov.xex
	soft65c02_tester -i o65_api_runtime.txt

$(O65_API_OUT)/resident-api-closure.o65: resident_api_o65.c | $(O65_API_OUT)
	$(CL65) -t atari -c -Osir -O -I $(LIB)/include -o $(O65_API_OUT)/resident_api_o65.o $<
	ld65 -C $(ROOT)/repos/cc65/cfg/module.cfg -o $@ -m $(O65_API_OUT)/resident-api-closure.map -Ln $(O65_API_OUT)/resident-api-closure.lbl $(O65_API_OUT)/resident_api_o65.o $(LIB)/build/fujinet-nio-atari.lib $(ROOT)/repos/cc65/lib/atari.lib

$(O65_RUNTIME_OUT)/module-a.bin $(O65_RUNTIME_OUT)/module-b.bin: $(O65_API_OUT)/resident-api-closure.o65 verify_o65_api_closure.py | $(O65_RUNTIME_OUT)
	python3 verify_o65_api_closure.py $< --output-a $(O65_RUNTIME_OUT)/module-a.bin --output-b $(O65_RUNTIME_OUT)/module-b.bin

$(O65_RUNTIME_OUT)/runtime-control.bin: o65_runtime_control.s o65_runtime_control.cfg | $(O65_RUNTIME_OUT)
	ca65 -t none -o $(O65_RUNTIME_OUT)/runtime-control.o o65_runtime_control.s
	ld65 -C o65_runtime_control.cfg -o $@ $(O65_RUNTIME_OUT)/runtime-control.o

$(O65_RUNTIME_OUT)/runtime-siov.xex: o65_runtime_siov.s o65_runtime_siov.cfg | $(O65_RUNTIME_OUT)
	ca65 -t none -o $(O65_RUNTIME_OUT)/runtime-siov.o o65_runtime_siov.s
	ld65 -C o65_runtime_siov.cfg -o $@ $(O65_RUNTIME_OUT)/runtime-siov.o

# This is the precise, supported ld65 load/run use-case: a segment has a
# fixed link-time run address and a distinct load image.  It is intentionally
# separate from the o65 experiment because load/run does not select a run
# address at runtime from Atari MEMLO.
load-run-symbols: build/load-run-probe.bin build/load-run-probe.lbl
	python3 verify_load_run_probe.py build/load-run-probe.bin build/load-run-probe.lbl

allocation-plan:
	python3 resident_allocation_plan.py --self-test

allocation-plan-o65: $(O65_API_OUT)/resident-api-closure.o65
	python3 resident_allocation_plan.py --memlo 0x0700 --module-size 12054 --initialized-size 10007 --result-end 0x0b28 --bootstrap 0x5600 --stage 0x5800 --stack-floor 0x941f

build/load-run-probe.bin build/load-run-probe.lbl: load_run_probe.s load_run_probe.cfg | build
	ca65 -t none -o build/load-run-probe.o load_run_probe.s
	ld65 -C load_run_probe.cfg -o build/load-run-probe.bin -Ln build/load-run-probe.lbl build/load-run-probe.o

build/o65-probe.o65: o65_probe.s | build
	cl65 -t none --config $(ROOT)/repos/cc65/cfg/module.cfg -o $@ $<

$(API_OUT)/resident-api-closure.map: resident_api_closure.c | $(API_OUT)
	$(MAKE) -C $(LIB) atari
	cl65 -t atari --config $(APPS)/makefiles/cc65-atari-resident.cfg --start-addr 0x1D00 -Osir -O -I $(LIB)/include --mapfile $@ -Ln $(API_OUT)/resident-api-closure.lbl -o $(API_OUT)/resident-api-closure.xex $< $(LIB)/build/fujinet-nio-atari.lib

$(API_OUT):
	mkdir -p $@

$(O65_API_OUT):
	mkdir -p $@

$(O65_RUNTIME_OUT):
	mkdir -p $@

build:
	mkdir -p $@

clean:
	rm -rf build
