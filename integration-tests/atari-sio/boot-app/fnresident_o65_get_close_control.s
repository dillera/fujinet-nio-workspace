; Exercise GET and CLOSE through the installed o65 HATABS vectors.  The
; companion SIOV peer checks the production library's Open/Read/Close packet
; exchanges; this program checks CIO register ownership and local slot reuse.
        .export _main

HATABS  = $031A
IOCB    = $0340
CC65_ZP = $82
RESULT  = $06A0

.segment "CODE"
_main:
        ldx #$ff
        txs
        lda #0
        sta HATABS
        sta $0080
        sta $0081
        sta failure
        sta step
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

        jsr $3f00
        ldx #0
fill_zp:
        txa
        eor #$a5
        sta CC65_ZP,x
        inx
        cpx #26
        bne fill_zp

        jsr setup_a
        lda #$5a
        ldx #$20
        jsr call_open
        sty RESULT+1

        lda #$4b
        ldx #$20
        jsr call_status
        sta RESULT+17
        stx RESULT+18
        sty RESULT+19

        lda #$11
        ldx #$20
        jsr call_get
        sta RESULT+3
        stx RESULT+12
        sty RESULT+2
        lda #$22
        ldx #$20
        jsr call_get
        sta RESULT+5
        sty RESULT+4
        lda #$33
        ldx #$20
        jsr call_get
        sta RESULT+7
        sty RESULT+6
        lda #$3c
        ldx #$20
        jsr call_status
        sta RESULT+20
        stx RESULT+21
        sty RESULT+22
        lda #$7c
        ldx #$20
        jsr call_close
        sta RESULT+13
        stx RESULT+14
        sty RESULT+8

        ; Closing releases both the public-library and CIO ownership slots.
        ; A second OPEN on the same IOCB must go directly to a new W.
        jsr setup_b
        lda #$6d
        ldx #$20
        jsr call_open
        sty RESULT+9
        lda #$8e
        ldx #$20
        jsr call_close
        sty RESULT+10

        lda failure
        sta RESULT+11
        lda step
        sta RESULT+15
        ldx #0
check_zp:
        txa
        eor #$a5
        cmp CC65_ZP,x
        bne bad_zp
        inx
        cpx #26
        bne check_zp
        lda #0
        beq save_zp
bad_zp: lda #1
save_zp: sta RESULT+16
        lda #1
        sta RESULT
halt:   jmp halt

call_open:
        ldy #0
        jmp call_vector
call_close:
        ldy #2
        jmp call_vector
call_status:
        ldy #8
        jmp call_vector
call_get:
        ldy #4
call_vector:
        sty vector_offset
        pha
        lda HATABS+1
        sta vector_load_lo+1
        sta vector_load_hi+1
        lda HATABS+2
        sta vector_load_lo+2
        sta vector_load_hi+2
        ldy vector_offset
vector_load_lo:
        lda $ffff,y
        clc
        adc #1
        sta vector_call+1
        iny
vector_load_hi:
        lda $ffff,y
        adc #0
        sta vector_call+2
        pla
vector_call:
        jsr $ffff
        rts

setup_a:
        ldx #$20
        lda #1
        sta IOCB+1,x
        lda #<uri_a
        sta IOCB+4,x
        lda #>uri_a
        sta IOCB+5,x
        lda #4
        sta IOCB+10,x
        rts
setup_b:
        ldx #$20
        lda #1
        sta IOCB+1,x
        lda #<uri_b
        sta IOCB+4,x
        lda #>uri_b
        sta IOCB+5,x
        lda #4
        sta IOCB+10,x
        rts

uri_a:  .byte "N1:fixture://a", 0
uri_b:  .byte "N1:fixture://b", 0
vector_offset: .byte 0

failure = $E760
step = $E761
