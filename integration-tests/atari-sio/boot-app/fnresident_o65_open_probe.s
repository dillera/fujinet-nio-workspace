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
CIOPUT = $0B
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

        ; A 128-byte output session flushes exactly one bounded public
        ; fn_write() request. The deterministic fixture checks every byte.
        ldx #$20
        lda #OPEN
        sta IOCB+2,x
        lda #<write_uri
        sta IOCB+4,x
        lda #>write_uri
        sta IOCB+5,x
        lda #$08
        sta IOCB+10,x
        jsr CIOV
        sty write_open_status
        lda #1
        sta write_put_status
        ; Keep the loop index in this IOCB's unused AUX2 field. CIOV may use
        ; its private scratch while executing, whereas the caller-owned IOCB
        ; remains stable for the lifetime of this OPEN.
        ldx #$20
        lda #0
        sta IOCB+11,x
write_loop:
        ldx #$20
        lda #'A'
        pha
        ldx #$20
        lda #CIOPUT
        sta IOCB+2,x
        pla
        jsr CIOV
        cpy #1
        beq :+
        sty write_put_status
:       ldx #$20
        inc IOCB+11,x
        lda IOCB+11,x
        cmp #128
        bne write_loop
        ldx #$20
        lda #CLOSE
        sta IOCB+2,x
        jsr CIOV
        sty write_close_status

        ; A second, short output session verifies that CLOSE flushes the
        ; partial cache once and then sends the zero-length public commit.
        ldx #$20
        lda #OPEN
        sta IOCB+2,x
        lda #<write_uri
        sta IOCB+4,x
        lda #>write_uri
        sta IOCB+5,x
        lda #$08
        sta IOCB+10,x
        jsr CIOV
        sty partial_open_status
        lda #'B'
        ldx #$20
        lda #CIOPUT
        sta IOCB+2,x
        lda #'B'
        jsr CIOV
        sty partial_put_status
        lda #'C'
        ldx #$20
        lda #CIOPUT
        sta IOCB+2,x
        lda #'C'
        jsr CIOV
        sty partial_put_status
        lda #'D'
        ldx #$20
        lda #CIOPUT
        sta IOCB+2,x
        lda #'D'
        jsr CIOV
        sty partial_put_status
        ldx #$20
        lda #CLOSE
        sta IOCB+2,x
        jsr CIOV
        sty partial_close_status
        lda #'R'
        sta RESULT
        lda #'P'
        sta RESULT+1
        lda #'R'
        sta RESULT+2
        lda #'!'
        sta RESULT+3
        lda #6
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
        lda write_open_status
        sta RESULT+13
        lda write_put_status
        sta RESULT+14
        lda write_close_status
        sta RESULT+15
        lda partial_open_status
        sta RESULT+16
        lda partial_put_status
        sta RESULT+17
        lda partial_close_status
        sta RESULT+18
halt:   jmp halt

uri:    .byte "N1:fixture://resident-open", 0
write_uri: .byte "N1:fixture://resident-write", 0
open_status: .byte 0
get_1_status: .byte 0
byte_1: .byte 0
get_2_status: .byte 0
byte_2: .byte 0
close_status: .byte 0
reopen_status: .byte 0
close_2_status: .byte 0
write_open_status: .byte 0
write_put_status: .byte 0
write_close_status: .byte 0
partial_open_status: .byte 0
partial_put_status: .byte 0
partial_close_status: .byte 0
