; Fixture-controlled SIOV peer for the resident CIO OPEN execution test.
; It validates the real production transport's DCB/request shape and returns
; literal FujiBus Open replies.  It is not a firmware endpoint.
        .export _main
        .macpack longbranch

DDEVIC = $0300
DUNIT  = $0301
DCOMND = $0302
DSTATS = $0303
DBUFLO = $0304
DBUFHI = $0305
DBYTLO = $0308
DBYTHI = $0309
DAUX1  = $030A
DAUX2  = $030B
HATABS = $031A
reentry_status = $E740
failure = $E741
step = $E742

.segment "SIOV"
_main:
        lda DDEVIC
        cmp #$7f
        jne bad
        lda DUNIT
        cmp #1
        jne bad
        ldx step
        cpx #0
        jeq want_w_a
        cpx #1
        jeq want_p
        cpx #2
        jeq want_r_a
        cpx #3
        jeq want_w_b
        cpx #4
        jeq want_p
        cpx #5
        jeq want_r_b
        jmp bad

want_w_a:
        jsr check_w
        jcs bad
        ; Simulate an unsafe nested foreground entry while the first OPEN is
        ; still inside fn_open().  The assembly gateway must reject it.
        lda HATABS+1
        sta nested_vector_lo+1
        sta nested_vector_hi+1
        lda HATABS+2
        sta nested_vector_lo+2
        sta nested_vector_hi+2
        ldy #0
nested_vector_lo:
        lda $ffff,y
        clc
        adc #1
        sta nested_call+1
        iny
nested_vector_hi:
        lda $ffff,y
        adc #0
        sta nested_call+2
        lda #$d1
        ldx #$70
nested_call:
        jsr $ffff
        sty reentry_status
        inc step
        jmp ok
want_w_b:
        jsr check_w
        jcs bad
        inc step
        jmp ok
want_p:
        lda DCOMND
        cmp #'P'
        jne bad
        lda DSTATS
        cmp #$40
        jne bad
        lda DBYTLO
        cmp #3
        jne bad
        lda DBYTHI
        jne bad
        lda DAUX1
        ora DAUX2
        jne bad
        lda DBUFLO
        sta write_p+1
        lda DBUFHI
        sta write_p+2
        ldy #0
        lda #2
        jsr write_p
        iny
        lda #13
        jsr write_p
        iny
        lda #0
        jsr write_p
        inc step
        jmp ok
want_r_a:
        jsr check_r
        jcs bad
        ldx #0
copy_a: lda reply_a,x
        ldy #0
r_store_a:
        sta $ffff,y
        inc r_store_a+1
        bne :+
        inc r_store_a+2
:       inx
        cpx #13
        jne copy_a
        inc step
        jmp ok
want_r_b:
        jsr check_r
        jcs bad
        ldx #0
copy_b: lda reply_b,x
        ldy #0
r_store_b:
        sta $ffff,y
        inc r_store_b+1
        bne :+
        inc r_store_b+2
:       inx
        cpx #13
        jne copy_b
        inc step
        jmp ok

check_w:
        lda DCOMND
        cmp #'W'
        beq :+
        jmp check_bad
:
        lda DSTATS
        cmp #$80
        beq :+
        jmp check_bad
:
        lda DBYTLO
        cmp #30
        jne check_bad
        lda DBYTHI
        jne check_bad
        lda DAUX1
        cmp #30
        jne check_bad
        lda DAUX2
        jne check_bad
        lda DBUFLO
        sta read_w+1
        lda DBUFHI
        sta read_w+2
        ldy #0
        jsr read_w
        cmp #$fd
        jne check_bad
        iny
        jsr read_w
        cmp #1
        jne check_bad
        iny
        jsr read_w
        cmp #30
        jne check_bad
        ldy #9
        jsr read_w
        cmp #11
        jne check_bad
        lda step
        beq check_uri_a
        cmp #3
        bne check_bad
        ldx #0
        ldy #11
check_uri_b:
        jsr read_w
        cmp uri_b,x
        bne check_bad
        inx
        iny
        cpx #11
        bne check_uri_b
        jmp check_checksum
check_uri_a:
        ldx #0
        ldy #11
check_uri_a_loop:
        jsr read_w
        cmp uri_a,x
        bne check_bad
        inx
        iny
        cpx #11
        bne check_uri_a_loop
check_checksum:
        ldy #4
        jsr read_w
        ldx step
        beq check_checksum_a
        cmp #$2f
        bne check_bad
        jmp check_ok
check_checksum_a:
        cmp #$2e
        bne check_bad
check_ok:
        clc
        rts
check_bad:
        sec
        rts

read_w:
        lda $ffff,y
        rts

write_p:
        sta $ffff,y
        rts

check_r:
        lda DCOMND
        cmp #'R'
        bne check_bad
        lda DSTATS
        cmp #$40
        bne check_bad
        lda DBYTLO
        cmp #13
        bne check_bad
        lda DBYTHI
        bne check_bad
        lda DAUX1
        cmp #13
        bne check_bad
        lda DAUX2
        bne check_bad
        lda DBUFLO
        sta r_store_a+1
        sta r_store_b+1
        lda DBUFHI
        sta r_store_a+2
        sta r_store_b+2
        clc
        rts

ok:     lda #1
        sta DSTATS
        rts
bad:    lda #1
        sta failure
        lda #$8b
        sta DSTATS
        rts

reply_a:.byte $fd,$01,$0d,$00,$53,$00,$01,$00,$00,$00,$34,$12,$00
reply_b:.byte $fd,$01,$0d,$00,$db,$00,$01,$00,$00,$00,$78,$56,$00
uri_a:  .byte "fixture://a"
uri_b:  .byte "fixture://b"
