ROOT := $(abspath ../../..)
OUT := build
CORE_XEX := $(OUT)/native-core-dispatch.xex
WRONG_R_XEX := $(OUT)/native-wrong-r-retention.xex
CFG := ../boot-app/atari-xex.cfg

.PHONY: all clean
all: $(CORE_XEX) $(WRONG_R_XEX)

$(OUT):
	mkdir -p $@

$(CORE_XEX): native_core_dispatch.s $(CFG) | $(OUT)
	cl65 -t none -C $(CFG) -o $@ $<

$(WRONG_R_XEX): native_core_dispatch.s $(CFG) | $(OUT)
	cl65 -t none --asm-define WRONG_R_RETENTION=1 -C $(CFG) -o $@ $<

clean:
	rm -rf $(OUT)
