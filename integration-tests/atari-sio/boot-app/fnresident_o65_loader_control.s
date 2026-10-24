; soft65c02 control for the production bounded o65 loader.
        .export _main

.segment "CODE"
_main:
        ldx #$ff
        txs
        lda #0
        sta $031a
        sta $0080
        sta $0081
        sta $0082
        sta $0083
        lda #$00
        sta $02e7
        lda #$07
        sta $02e8
        lda #$1f
        sta $02e5
        lda #$9c
        sta $02e6
        lda #$20
        sta $0230
        lda #$9c
        sta $0231
        lda #$40
        sta $0058
        lda #$9c
        sta $0059
        jsr $3d00
        lda #1
        sta $0680
halt:   jmp halt
