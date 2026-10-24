; Compare the production Atari-side o65 loader byte-for-byte with the
; checked-in host reference relocation at the same $0700 base.  The reference
; image is loaded by soft65c02 at $6000; it is test data, not loader input.
        .export _main

RESULT = $06C0

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
        sta RESULT
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
        jsr $3800

        lda #<$0700
        sta actual+1
        lda #>$0700
        sta actual+2
        lda #<$9000
        sta expected+1
        lda #>$9000
        sta expected+2
        ; fn_init() deliberately mutates initialized library state. Compare
        ; the complete relocated TEXT closure; DATA/BSS lifecycle is covered
        ; by the loader/runtime tests below.
        lda #<$2a16
        sta remaining
        lda #>$2a16
        sta remaining+1
        lda #0
        sta offset
        sta offset+1
loop:
actual: lda $ffff
        sta seen
expected: lda $ffff
        cmp seen
        bne mismatch
        inc actual+1
        bne :+
        inc actual+2
:
        inc expected+1
        bne :+
        inc expected+2
:
        inc offset
        bne :+
        inc offset+1
:
        lda remaining
        bne :+
        dec remaining+1
:
        dec remaining
        lda remaining
        ora remaining+1
        bne loop
        lda #1
        sta RESULT
        jmp halt
mismatch:
        lda offset
        sta RESULT+1
        lda offset+1
        sta RESULT+2
        lda seen
        sta RESULT+3
        lda expected+1
        sta RESULT+4
halt:   jmp halt

remaining: .word 0
offset:    .word 0
seen:      .byte 0
