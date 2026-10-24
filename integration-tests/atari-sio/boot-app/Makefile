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

.PHONY: all resident resident-foreign resident-own resident-overlap clean
all: $(ATR)
resident: $(RESIDENT_ATR)
resident-foreign: $(RESIDENT_FOREIGN_ATR)
resident-own: $(RESIDENT_OWN_ATR)
resident-overlap: $(RESIDENT_OVERLAP_ATR)

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

clean:
	rm -rf $(OUT)
