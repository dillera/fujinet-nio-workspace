; Separately loaded Atari program for the live resident N: OPEN gate.
; It deliberately enters CIOV, rather than calling the handler directly:
; CIO parses N1:, selects HATABS, and invokes the resident OPEN vector.
        .export _main

CIOV   = $E456
IOCB   = $0340
OPEN   = $03
OPNIN  = $04
RESULT = $5440

.segment "CODE"
_main:
        ldx #$20
        lda #OPEN
        sta IOCB+2,x
        lda #<uri
        sta IOCB+4,x
        lda #>uri
        sta IOCB+5,x
        lda #OPNIN
        sta IOCB+10,x
        jsr CIOV
        sty open_status
        lda #'R'
        sta RESULT
        lda #'P'
        sta RESULT+1
        lda #'R'
        sta RESULT+2
        lda #'!'
        sta RESULT+3
        lda #3
        sta RESULT+4
        lda open_status
        sta RESULT+5
halt:   jmp halt

uri:    .byte "N1:fixture://resident-open", 0
open_status: .byte 0
