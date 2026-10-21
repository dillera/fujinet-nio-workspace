ROOT := $(abspath ../../..)
OUT := build
XEX := $(OUT)/native-core-dispatch.xex
CFG := ../boot-app/atari-xex.cfg

.PHONY: all clean
all: $(XEX)

$(OUT):
	mkdir -p $@

$(XEX): native_core_dispatch.s $(CFG) | $(OUT)
	cl65 -t none -C $(CFG) -o $@ $<

clean:
	rm -rf $(OUT)
