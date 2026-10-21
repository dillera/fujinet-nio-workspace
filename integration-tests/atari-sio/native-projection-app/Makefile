ROOT := $(abspath ../../..)
OUT := build
CORE_XEX := $(OUT)/native-core-dispatch.xex
WRONG_R_XEX := $(OUT)/native-wrong-r-retention.xex
RESET_XEX := $(OUT)/native-reset-to-idle.xex
CFG := ../boot-app/atari-xex.cfg
RESET_CFG := reset-atari-xex.cfg

.PHONY: all clean
all: $(CORE_XEX) $(WRONG_R_XEX) $(RESET_XEX)

$(OUT):
	mkdir -p $@

$(CORE_XEX): native_core_dispatch.s $(CFG) | $(OUT)
	cl65 -t none -C $(CFG) -o $@ $<

$(WRONG_R_XEX): native_core_dispatch.s $(CFG) | $(OUT)
	cl65 -t none --asm-define WRONG_R_RETENTION=1 -C $(CFG) -o $@ $<

$(RESET_XEX): native_core_dispatch.s $(RESET_CFG) | $(OUT)
	cl65 -t none --asm-define RESET_TO_IDLE=1 -C $(RESET_CFG) -o $@ $<

clean:
	rm -rf $(OUT)
