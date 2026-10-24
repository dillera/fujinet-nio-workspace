; Exercise the installed o65 N: OPEN vector as CIO would: X carries the IOCB
; offset and the HATABS address-minus-one vector is entered with JSR.  This is
; intentionally an independent small caller, not a BASIC acceptance fixture.
        .export _main

HATABS = $031A
IOCB   = $0340
CC65_ZP = $82
RESULT = $0680

.segment "CODE"
_main:
        ldx #$ff
        txs
        lda #0
        sta HATABS
        sta $0080
        sta $0081
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
        lda #0
        sta reentry_status
        sta failure
        sta step

        ; Install the real production o65 payload through its transient
        ; loader before calling the published HATABS entry.
        jsr $3f00

        ldx #0
fill_zp:
        txa
        eor #$a5
        sta CC65_ZP,x
        dex
        inx
        inx
        cpx #26
        bne fill_zp

        jsr setup_iocb_20
        lda #$5a
        ldx #$20
        jsr call_open
        sta RESULT+11
        stx RESULT+12
        sty RESULT+1

        ; Same IOCB is locally owned: no additional public OPEN/SIO traffic.
        lda #$6b
        ldx #$20
        jsr call_open
        sty RESULT+3

        ; Validate local input before filling the two ownership records.
        jsr setup_bad_name
        lda #$9e
        ldx #$50
        jsr call_open
        sty RESULT+6

        jsr setup_bad_mode
        lda #$af
        ldx #$60
        jsr call_open
        sty RESULT+7

        jsr setup_iocb_30
        lda #$7c
        ldx #$30
        jsr call_open
        sty RESULT+4

        ; Two resident ownership records are the cc65 public-library limit.
        jsr setup_iocb_40
        lda #$8d
        ldx #$40
        jsr call_open
        sty RESULT+5

        ; The SIOV peer made one nested call while the first public OPEN was
        ; in progress.  It must have been rejected without changing the
        ; outer caller's A/X state or any saved cc65 ZP byte.
        lda reentry_status
        sta RESULT+2
        lda failure
        sta RESULT+8
        lda step
        sta RESULT+9
        tsx
        stx RESULT+13
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
save_zp: sta RESULT+10
        lda #1
        sta RESULT
halt:   jmp halt

; Adapt a HATABS address-minus-one vector to an actual JSR target.
call_open:
        pha
        lda HATABS+1
        sta vector_load_lo+1
        sta vector_load_hi+1
        lda HATABS+2
        sta vector_load_lo+2
        sta vector_load_hi+2
        ldy #0
vector_load_lo:
        lda $ffff,y
        clc
        adc #1
        sta open_call+1
        iny
vector_load_hi:
        lda $ffff,y
        adc #0
        sta open_call+2
        pla
open_call:
        jsr $ffff
        rts

setup_iocb_20:
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
setup_iocb_30:
        ldx #$30
        lda #1
        sta IOCB+1,x
        lda #<uri_b
        sta IOCB+4,x
        lda #>uri_b
        sta IOCB+5,x
        lda #4
        sta IOCB+10,x
        rts
setup_iocb_40:
        ldx #$40
        lda #1
        sta IOCB+1,x
        lda #<uri_c
        sta IOCB+4,x
        lda #>uri_c
        sta IOCB+5,x
        lda #4
        sta IOCB+10,x
        rts
setup_bad_name:
        ldx #$50
        lda #1
        sta IOCB+1,x
        lda #<bad_name
        sta IOCB+4,x
        lda #>bad_name
        sta IOCB+5,x
        lda #4
        sta IOCB+10,x
        rts
setup_bad_mode:
        ldx #$60
        lda #1
        sta IOCB+1,x
        lda #<uri_c
        sta IOCB+4,x
        lda #>uri_c
        sta IOCB+5,x
        ; OPNIN and OPNOT are the two modes implemented by the resident
        ; handler. An unrelated CIO mode must still fail locally.
        lda #0
        sta IOCB+10,x
        rts

uri_a:   .byte "N1:fixture://a", 0
uri_b:   .byte "N1:fixture://b", 0
uri_c:   .byte "N1:fixture://c", 0
bad_name:.byte "D1:fixture://bad", 0

; The fixture peer retains only its small diagnostic state at fixed, otherwise
; unused RAM.  The production payload never treats these as protocol state.
reentry_status = $E740
failure = $E741
step = $E742
