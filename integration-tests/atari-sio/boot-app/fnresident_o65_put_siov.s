; Strict SIOV fixture for the production resident PUT gateway.  It is a
; transport interceptor, not an alternate endpoint: every expected command,
; direction, count, AUX and all 128 public-write bytes are checked.
        .export _main
        .macpack longbranch
DDEVIC=$0300
DUNIT=$0301
DCOMND=$0302
DSTATS=$0303
DBUFLO=$0304
DBUFHI=$0305
DBYTLO=$0308
DBYTHI=$0309
DAUX1=$030A
DAUX2=$030B
failure=$E770
step=$E771
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
        jeq w_open
        cpx #1
        jeq p_open
        cpx #2
        jeq r_open
        cpx #3
        jeq w_write
        cpx #4
        jeq p_write
        cpx #5
        jeq r_write
        cpx #6
        jeq w_close
        cpx #7
        jeq p_close
        cpx #8
        jeq r_close
        jmp bad
w_open: lda #30
        jsr check_w
        jcs bad
        ldy #7
        jsr read_w
        cmp #3
        jne bad
        inc step
        jmp ok
w_write:lda #143
        jsr check_w
        jcs bad
        lda #2
        sta failure
        ldy #1
        jsr read_w
        cmp #3
        jne bad
        ldy #2
        jsr read_w
        cmp #143
        jne bad
        lda #3
        sta failure
        ldy #7
        jsr read_w
        cmp #$34
        jne bad
        iny
        jsr read_w
        cmp #$12
        jne bad
        lda #4
        sta failure
        ldy #13
        jsr read_w
        cmp #128
        jne bad
        iny
        jsr read_w
        jne bad
        lda #5
        sta failure
        ldy #15
        ldx #0
@bytes: jsr read_w
        cmp #'A'
        jne bad
        inx
        iny
        cpx #128
        bne @bytes
        lda #0
        sta failure
w_write_accept:
        inc step
        jmp ok
w_close:lda #9
        jsr check_w
        jcs bad
        inc step
        jmp ok
p_open: ldx #13
        jmp send_p
p_write:ldx #18
        jmp send_p
p_close:ldx #6
send_p: lda DCOMND
        cmp #'P'
        jne bad
        lda DSTATS
        cmp #$40
        jne bad
        lda DBYTLO
        cmp #3
        jne bad
        lda DBYTHI
        ora DAUX1
        ora DAUX2
        jne bad
        lda DBUFLO
        sta p_store+1
        lda DBUFHI
        sta p_store+2
        ldy #0
        lda #2
        jsr p_store
        iny
        txa
        jsr p_store
        iny
        lda #0
        jsr p_store
        inc step
        jmp ok
r_open: ldx #<reply_open
        ldy #>reply_open
        lda #13
        jmp send_r
r_write:ldx #<reply_write
        ldy #>reply_write
        lda #18
        jmp send_r
r_close:ldx #<reply_close
        ldy #>reply_close
        lda #6
send_r: sta expected_len
        jsr check_r
        jcs bad
        stx r_load+1
        sty r_load+2
        ldx #0
r_copy:
r_load: lda $ffff,x
        ldy #0
r_store:sta $ffff,y
        inc r_store+1
        bne :+
        inc r_store+2
:       inx
        cpx expected_len
        bne r_copy
        inc step
        jmp ok
check_w:sta expected_len
        lda DCOMND
        cmp #'W'
        bne bad_check
        lda DSTATS
        cmp #$80
        bne bad_check
        lda DBYTLO
        cmp expected_len
        bne bad_check
        lda DAUX1
        cmp expected_len
        bne bad_check
        lda DBYTHI
        ora DAUX2
        bne bad_check
        lda DBUFLO
        sta read_w+1
        lda DBUFHI
        sta read_w+2
        clc
        rts
check_r: lda DCOMND
        cmp #'R'
        bne bad_check
        lda DSTATS
        cmp #$40
        bne bad_check
        lda DBYTLO
        cmp expected_len
        bne bad_check
        lda DAUX1
        cmp expected_len
        bne bad_check
        lda DBYTHI
        ora DAUX2
        bne bad_check
        lda DBUFLO
        sta r_store+1
        lda DBUFHI
        sta r_store+2
        clc
        rts
read_w: lda $ffff,y
        rts
p_store:sta $ffff,y
        rts
bad_check: sec
        rts
bad:    lda failure
        bne :+
        lda #1
        sta failure
: 
        lda #$8b
        sta DSTATS
        rts
ok:     lda #1
        sta DSTATS
        rts
expected_len:.byte 0
reply_open: .byte $fd,1,13,0,$53,0,1,0,0,0,$34,$12,0
reply_write:.byte $fd,3,18,0,$da,0,1,0,0,0,$34,$12,0,0,0,0,$80,0
reply_close:.byte $fd,4,6,0,$08,0
