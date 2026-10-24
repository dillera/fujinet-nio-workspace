; Separately loaded Atari program for the live resident N: OPEN/GET/CLOSE
; gate.  It deliberately enters CIOV, rather than calling the handler
; directly: CIO parses N1:, selects HATABS, and invokes resident vectors.
; It deliberately enters CIOV, rather than calling the handler directly:
; CIO parses N1:, selects HATABS, and invokes the resident OPEN vector.
        .export _main

CIOV   = $E456
IOCB   = $0340
OPEN   = $03
GETCHR = $07
CLOSE  = $0C
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
        ldx #$20
        lda #GETCHR
        sta IOCB+2,x
        jsr CIOV
        sta byte_1
        sty get_1_status
        ldx #$20
        lda #GETCHR
        sta IOCB+2,x
        jsr CIOV
        sta byte_2
        sty get_2_status
        ldx #$20
        lda #CLOSE
        sta IOCB+2,x
        jsr CIOV
        sty close_status
        ; Reopen/close the same IOCB to prove the resident slot was released.
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
        sty reopen_status
        ldx #$20
        lda #CLOSE
        sta IOCB+2,x
        jsr CIOV
        sty close_2_status
        lda #'R'
        sta RESULT
        lda #'P'
        sta RESULT+1
        lda #'R'
        sta RESULT+2
        lda #'!'
        sta RESULT+3
        lda #4
        sta RESULT+4
        lda open_status
        sta RESULT+5
        lda get_1_status
        sta RESULT+6
        lda byte_1
        sta RESULT+7
        lda get_2_status
        sta RESULT+8
        lda byte_2
        sta RESULT+9
        lda close_status
        sta RESULT+10
        lda reopen_status
        sta RESULT+11
        lda close_2_status
        sta RESULT+12
halt:   jmp halt

uri:    .byte "N1:fixture://resident-open", 0
open_status: .byte 0
get_1_status: .byte 0
byte_1: .byte 0
get_2_status: .byte 0
byte_2: .byte 0
close_status: .byte 0
reopen_status: .byte 0
close_2_status: .byte 0
