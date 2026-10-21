ROOT := $(abspath ../../..)
APPS := $(ROOT)/repos/nio-core-apps
PICOBOOT := $(ROOT)/repos/MyPicoDOS/picobootcode-dd.bin
OUT := build
XEX := $(OUT)/boot-acceptance.xex
ATR := $(OUT)/boot-acceptance.atr

.PHONY: all clean
all: $(ATR)

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

clean:
	rm -rf $(OUT)
