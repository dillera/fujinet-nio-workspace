; Control that calls the host-relocated production payload at $0700.
        .export _main
.segment "CODE"
_main:
        ldx #$ff
        txs
        ldx #$19
        lda #0
clear_zp:
        sta $82,x
        dex
        bpl clear_zp
        ; The feasibility closure runs its C stack at $9000.  Use the same
        ; known-safe stack here to distinguish a runtime-init defect from a
        ; resident-allocation-size issue.
        lda #$00
        sta $82
        lda #$90
        sta $83
        jsr $0700
        sta $0681
        lda #1
        sta $0680
halt:   jmp halt
