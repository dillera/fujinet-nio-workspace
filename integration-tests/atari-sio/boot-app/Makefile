ROOT := $(abspath ../../..)
APPS := $(ROOT)/repos/nio-core-apps
PICOBOOT := $(ROOT)/repos/MyPicoDOS/picobootcode-dd.bin
OUT := build
XEX := $(OUT)/boot-acceptance.xex
ATR := $(OUT)/boot-acceptance.atr
RESIDENT_APP := $(APPS)/build/atari/bin/fnresident.xex
RESIDENT_PROBE := $(OUT)/fnresident-probe.xex
RESIDENT_XEX := $(OUT)/fnresident-install.xex
RESIDENT_ATR := $(OUT)/fnresident-install.atr

.PHONY: all resident clean
all: $(ATR)
resident: $(RESIDENT_ATR)

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

$(RESIDENT_XEX): $(RESIDENT_APP) $(RESIDENT_PROBE) ../compose_resident_xex.py | $(OUT)
	python3 ../compose_resident_xex.py $(RESIDENT_APP) $(RESIDENT_PROBE) $@

$(RESIDENT_ATR): $(RESIDENT_XEX) $(PICOBOOT) Makefile | $(OUT)
	rm -rf $(OUT)/resident-stage
	mkdir -p $(OUT)/resident-stage
	cp $(RESIDENT_XEX) $(OUT)/resident-stage/coltest.xex
	cd $(APPS) && dir2atr -m -D -B $(PICOBOOT) $(abspath $@) $(abspath $(OUT)/resident-stage)

clean:
	rm -rf $(OUT)
