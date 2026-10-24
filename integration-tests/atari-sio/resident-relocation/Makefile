ROOT := $(abspath ../../..)
OUT := build/relocation-feasibility
APPS := $(ROOT)/repos/nio-core-apps
LIB := $(ROOT)/repos/fujinet-nio-lib
API_OUT := build/api-closure

.PHONY: relocation-feasibility api-closure-map o65-relocation-metadata load-run-symbols allocation-plan clean

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

# This is the precise, supported ld65 load/run use-case: a segment has a
# fixed link-time run address and a distinct load image.  It is intentionally
# separate from the o65 experiment because load/run does not select a run
# address at runtime from Atari MEMLO.
load-run-symbols: build/load-run-probe.bin build/load-run-probe.lbl
	python3 verify_load_run_probe.py build/load-run-probe.bin build/load-run-probe.lbl

allocation-plan:
	python3 resident_allocation_plan.py --self-test

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

build:
	mkdir -p $@

clean:
	rm -rf build
