ROOT := $(abspath ../../..)
APPS := $(ROOT)/repos/nio-core-apps
PICOBOOT := $(ROOT)/repos/MyPicoDOS/picobootcode-dd.bin
OUT := build
XEX := $(OUT)/boot-acceptance.xex
ATR := $(OUT)/boot-acceptance.atr
RESIDENT_APP := $(APPS)/build/atari/bin/fnresident.xex
RESIDENT_PROBE := $(OUT)/fnresident-probe.xex
RESIDENT_BOOTSTRAP_INC := $(OUT)/fnresident-bootstrap.inc
RESIDENT_BOOTSTRAP := $(OUT)/fnresident-bootstrap.xex
RESIDENT_XEX := $(OUT)/fnresident-install.xex
RESIDENT_ATR := $(OUT)/fnresident-install.atr
RESIDENT_FOREIGN_XEX := $(OUT)/fnresident-foreign.xex
RESIDENT_FOREIGN_ATR := $(OUT)/fnresident-foreign.atr
RESIDENT_OWN_XEX := $(OUT)/fnresident-own.xex
RESIDENT_OWN_ATR := $(OUT)/fnresident-own.atr
RESIDENT_OVERLAP_XEX := $(OUT)/fnresident-overlap.xex
RESIDENT_OVERLAP_ATR := $(OUT)/fnresident-overlap.atr
RESIDENT_O65_MODULE := $(APPS)/build/atari/bin/fnresident-module.o65
RESIDENT_O65_LABELS := $(RESIDENT_O65_MODULE:.o65=.lbl)
RESIDENT_O65_STAGE := $(OUT)/fnresident-o65-stage.xex
RESIDENT_O65_LOADER := $(OUT)/fnresident-o65-loader.xex
RESIDENT_O65_PROBE := $(OUT)/fnresident-o65-probe.xex
RESIDENT_O65_XEX := $(OUT)/fnresident-o65-install.xex
RESIDENT_O65_ATR := $(OUT)/fnresident-o65-install.atr
RESIDENT_O65_ALTBASE_XEX := $(OUT)/fnresident-o65-altbase.xex
RESIDENT_O65_ALTBASE_ATR := $(OUT)/fnresident-o65-altbase.atr
RESIDENT_O65_OVERLAP_XEX := $(OUT)/fnresident-o65-overlap.xex
RESIDENT_O65_OVERLAP_ATR := $(OUT)/fnresident-o65-overlap.atr
RESIDENT_O65_FOREIGN_XEX := $(OUT)/fnresident-o65-foreign.xex
RESIDENT_O65_FOREIGN_ATR := $(OUT)/fnresident-o65-foreign.atr

.PHONY: all resident resident-foreign resident-own resident-overlap resident-o65 resident-o65-altbase resident-o65-overlap resident-o65-foreign resident-o65-footprint test-resident-o65 clean
all: $(ATR)
resident: $(RESIDENT_ATR)
resident-foreign: $(RESIDENT_FOREIGN_ATR)
resident-own: $(RESIDENT_OWN_ATR)
resident-overlap: $(RESIDENT_OVERLAP_ATR)
resident-o65: $(RESIDENT_O65_ATR)
resident-o65-altbase: $(RESIDENT_O65_ALTBASE_ATR)
resident-o65-overlap: $(RESIDENT_O65_OVERLAP_ATR)
resident-o65-foreign: $(RESIDENT_O65_FOREIGN_ATR)

# The N: payload uses URI-based fn_open(), not the optional TCP formatter.
# Keep its module excluded and retain the measured bounded buffers: two shared
# 512-byte packet workspaces and no second Atari recovery discard workspace.
resident-o65-footprint: $(RESIDENT_O65_MODULE)
	python3 ../resident-relocation/resident_footprint_report.py --map $(RESIDENT_O65_MODULE:.o65=.map) --max-initialized 9231 --max-bss 1387 --forbid-module fn_tcp_open.o

$(OUT):
	mkdir -p $@

$(XEX): boot_acceptance.s atari-xex.cfg | $(OUT)
	cl65 -t none -C atari-xex.cfg -o $@ $<

$(PICOBOOT):
	$(MAKE) -C $(ROOT)/repos/MyPicoDOS picobootcode-dd.bin

$(ATR): $(XEX) $(PICOBOOT) Makefile | $(OUT)
	rm -rf $(OUT)/stage
	mkdir -p $(OUT)/stage
	cp $(XEX) $(OUT)/stage/coltest.xex
	cd $(APPS) && dir2atr -m -D -B $(PICOBOOT) $(abspath $@) $(abspath $(OUT)/stage)

$(RESIDENT_APP):
	$(MAKE) -C $(APPS) -f makefiles/build.mk TARGET=atari fnresident

$(RESIDENT_PROBE): fnresident_probe.s fnresident-probe.cfg | $(OUT)
	cl65 -t none -C fnresident-probe.cfg -o $@ $<

$(RESIDENT_BOOTSTRAP_INC): $(RESIDENT_APP) ../make_resident_bootstrap_include.py | $(OUT)
	python3 ../make_resident_bootstrap_include.py --map $(RESIDENT_APP:.xex=.map) --xex $(RESIDENT_APP) --lbl $(RESIDENT_APP:.xex=.lbl) --output $@

$(RESIDENT_BOOTSTRAP): fnresident_bootstrap.s fnresident-bootstrap.cfg $(RESIDENT_BOOTSTRAP_INC) | $(OUT)
	cl65 -t none -C fnresident-bootstrap.cfg -o $@ fnresident_bootstrap.s

$(RESIDENT_XEX): $(RESIDENT_APP) $(RESIDENT_PROBE) $(RESIDENT_BOOTSTRAP) ../compose_resident_xex.py | $(OUT)
	python3 ../compose_resident_xex.py --bootstrap $(RESIDENT_BOOTSTRAP) $(RESIDENT_APP) $(RESIDENT_PROBE) $@

$(RESIDENT_FOREIGN_XEX): $(RESIDENT_APP) $(RESIDENT_PROBE) $(RESIDENT_BOOTSTRAP) ../compose_resident_xex.py | $(OUT)
	python3 ../compose_resident_xex.py --foreign-hatabs --bootstrap $(RESIDENT_BOOTSTRAP) $(RESIDENT_APP) $(RESIDENT_PROBE) $@

$(RESIDENT_OWN_XEX): $(RESIDENT_APP) $(RESIDENT_PROBE) ../compose_resident_xex.py | $(OUT)
	table=$$(sed -n 's/^al \([0-9A-F]*\) \._fnresident_handler_table$$/0x\1/p' $(RESIDENT_APP:.xex=.lbl)); test -n "$$table"; python3 ../compose_resident_xex.py --own-hatabs "$$table" $(RESIDENT_APP) $(RESIDENT_PROBE) $@

$(RESIDENT_OVERLAP_XEX): $(RESIDENT_APP) $(RESIDENT_PROBE) $(RESIDENT_BOOTSTRAP) ../compose_resident_xex.py | $(OUT)
	python3 ../compose_resident_xex.py --bootstrap $(RESIDENT_BOOTSTRAP) --repeat-bootstrap $(RESIDENT_APP) $(RESIDENT_PROBE) $@

$(RESIDENT_ATR): $(RESIDENT_XEX) $(PICOBOOT) Makefile | $(OUT)
	rm -rf $(OUT)/resident-stage
	mkdir -p $(OUT)/resident-stage
	cp $(RESIDENT_XEX) $(OUT)/resident-stage/coltest.xex
	cd $(APPS) && dir2atr -m -D -B $(PICOBOOT) $(abspath $@) $(abspath $(OUT)/resident-stage)

$(RESIDENT_FOREIGN_ATR): $(RESIDENT_FOREIGN_XEX) $(PICOBOOT) Makefile | $(OUT)
	rm -rf $(OUT)/resident-foreign-stage
	mkdir -p $(OUT)/resident-foreign-stage
	cp $(RESIDENT_FOREIGN_XEX) $(OUT)/resident-foreign-stage/coltest.xex
	cd $(APPS) && dir2atr -m -D -B $(PICOBOOT) $(abspath $@) $(abspath $(OUT)/resident-foreign-stage)

$(RESIDENT_OWN_ATR): $(RESIDENT_OWN_XEX) $(PICOBOOT) Makefile | $(OUT)
	rm -rf $(OUT)/resident-own-stage
	mkdir -p $(OUT)/resident-own-stage
	cp $(RESIDENT_OWN_XEX) $(OUT)/resident-own-stage/coltest.xex
	cd $(APPS) && dir2atr -m -D -B $(PICOBOOT) $(abspath $@) $(abspath $(OUT)/resident-own-stage)

$(RESIDENT_OVERLAP_ATR): $(RESIDENT_OVERLAP_XEX) $(PICOBOOT) Makefile | $(OUT)
	rm -rf $(OUT)/resident-overlap-stage
	mkdir -p $(OUT)/resident-overlap-stage
	cp $(RESIDENT_OVERLAP_XEX) $(OUT)/resident-overlap-stage/coltest.xex
	cd $(APPS) && dir2atr -m -D -B $(PICOBOOT) $(abspath $@) $(abspath $(OUT)/resident-overlap-stage)

$(RESIDENT_O65_MODULE):
	$(MAKE) -C $(APPS) -f makefiles/build.mk TARGET=atari fnresident-module

$(RESIDENT_O65_STAGE): $(RESIDENT_O65_MODULE) $(RESIDENT_O65_LABELS) ../make_resident_o65_image.py | $(OUT)
	python3 ../make_resident_o65_image.py --module $(RESIDENT_O65_MODULE) --labels $(RESIDENT_O65_LABELS) --stage 0x5800 --output $@

$(RESIDENT_O65_LOADER): $(APPS)/apps/platform/atari/resident/fnresident_o65_loader.s fnresident-o65-loader.cfg | $(OUT)
	cl65 -t none -C fnresident-o65-loader.cfg -o $@ $(APPS)/apps/platform/atari/resident/fnresident_o65_loader.s

$(RESIDENT_O65_PROBE): fnresident_o65_probe.s fnresident-o65-probe.cfg | $(OUT)
	cl65 -t none -C fnresident-o65-probe.cfg -o $@ fnresident_o65_probe.s

$(RESIDENT_O65_XEX): $(RESIDENT_O65_LOADER) $(RESIDENT_O65_STAGE) $(RESIDENT_O65_PROBE) ../compose_resident_o65_xex.py | $(OUT)
	python3 ../compose_resident_o65_xex.py --loader $(RESIDENT_O65_LOADER) --staged $(RESIDENT_O65_STAGE) --probe $(RESIDENT_O65_PROBE) --output $@

$(RESIDENT_O65_ALTBASE_XEX): $(RESIDENT_O65_LOADER) $(RESIDENT_O65_STAGE) $(RESIDENT_O65_PROBE) ../compose_resident_o65_xex.py | $(OUT)
	python3 ../compose_resident_o65_xex.py --memlo 0x0702 --loader $(RESIDENT_O65_LOADER) --staged $(RESIDENT_O65_STAGE) --probe $(RESIDENT_O65_PROBE) --output $@

$(RESIDENT_O65_OVERLAP_XEX): $(RESIDENT_O65_LOADER) $(RESIDENT_O65_STAGE) $(RESIDENT_O65_PROBE) ../compose_resident_o65_xex.py | $(OUT)
	python3 ../compose_resident_o65_xex.py --repeat --loader $(RESIDENT_O65_LOADER) --staged $(RESIDENT_O65_STAGE) --probe $(RESIDENT_O65_PROBE) --output $@

$(RESIDENT_O65_FOREIGN_XEX): $(RESIDENT_O65_LOADER) $(RESIDENT_O65_STAGE) $(RESIDENT_O65_PROBE) ../compose_resident_o65_xex.py | $(OUT)
	python3 ../compose_resident_o65_xex.py --foreign --loader $(RESIDENT_O65_LOADER) --staged $(RESIDENT_O65_STAGE) --probe $(RESIDENT_O65_PROBE) --output $@

$(RESIDENT_O65_ATR): $(RESIDENT_O65_XEX) $(PICOBOOT) Makefile | $(OUT)
	rm -rf $(OUT)/resident-o65-stage
	mkdir -p $(OUT)/resident-o65-stage
	cp $(RESIDENT_O65_XEX) $(OUT)/resident-o65-stage/coltest.xex
	cd $(APPS) && dir2atr -m -D -B $(PICOBOOT) $(abspath $@) $(abspath $(OUT)/resident-o65-stage)

$(RESIDENT_O65_ALTBASE_ATR): $(RESIDENT_O65_ALTBASE_XEX) $(PICOBOOT) Makefile | $(OUT)
	rm -rf $(OUT)/resident-o65-altbase-stage
	mkdir -p $(OUT)/resident-o65-altbase-stage
	cp $(RESIDENT_O65_ALTBASE_XEX) $(OUT)/resident-o65-altbase-stage/coltest.xex
	cd $(APPS) && dir2atr -m -D -B $(PICOBOOT) $(abspath $@) $(abspath $(OUT)/resident-o65-altbase-stage)

$(RESIDENT_O65_OVERLAP_ATR): $(RESIDENT_O65_OVERLAP_XEX) $(PICOBOOT) Makefile | $(OUT)
	rm -rf $(OUT)/resident-o65-overlap-stage
	mkdir -p $(OUT)/resident-o65-overlap-stage
	cp $(RESIDENT_O65_OVERLAP_XEX) $(OUT)/resident-o65-overlap-stage/coltest.xex
	cd $(APPS) && dir2atr -m -D -B $(PICOBOOT) $(abspath $@) $(abspath $(OUT)/resident-o65-overlap-stage)

$(RESIDENT_O65_FOREIGN_ATR): $(RESIDENT_O65_FOREIGN_XEX) $(PICOBOOT) Makefile | $(OUT)
	rm -rf $(OUT)/resident-o65-foreign-stage
	mkdir -p $(OUT)/resident-o65-foreign-stage
	cp $(RESIDENT_O65_FOREIGN_XEX) $(OUT)/resident-o65-foreign-stage/coltest.xex
	cd $(APPS) && dir2atr -m -D -B $(PICOBOOT) $(abspath $@) $(abspath $(OUT)/resident-o65-foreign-stage)

test-resident-o65: resident-o65 resident-o65-altbase resident-o65-overlap resident-o65-foreign resident-o65-footprint
	cl65 -t none -C fnresident-o65-direct-control.cfg -o $(OUT)/fnresident-o65-direct-control.bin fnresident_o65_direct_control.s
	cl65 -t none -C fnresident-o65-loader-control.cfg -o $(OUT)/fnresident-o65-loader-control.bin fnresident_o65_loader_control.s
	cl65 -t none -C fnresident-o65-loader-siov.cfg -o $(OUT)/fnresident-o65-loader-siov.xex fnresident_o65_loader_siov.s
	python3 ../resident-relocation/verify_o65_api_closure.py $(RESIDENT_O65_MODULE) --output-relocated $(OUT)/fnresident-o65-module-0700.bin --relocation-base 0x0700
	soft65c02_tester -i fnresident_o65_direct.txt
	soft65c02_tester -i fnresident_o65_loader.txt
	soft65c02_tester -i fnresident_o65_loader_failure.txt

clean:
	rm -rf $(OUT)
