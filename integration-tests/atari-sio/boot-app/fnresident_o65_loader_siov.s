; fn_init may reach the Atari SIOV vector while establishing transport state.
; The loader unit has no endpoint exchange to validate, so return a successful
; DSTATS value from a minimal vector rather than executing unmapped ROM.
        .segment "SIOV"
        lda #1
        sta $0303
        rts
