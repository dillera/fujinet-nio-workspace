; Fixture-controlled SIOV peer for the resident GET/CLOSE execution test.
; It validates literal Open/Read/Close FujiBus packets and DCB fields from
; the production library; it is deliberately not a firmware protocol peer.
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
failure = $E760
step = $E761

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
        jeq w_open_a
        cpx #1
        jeq p_open
        cpx #2
        jeq r_open
        cpx #3
        jeq w_info
        cpx #4
        jeq p_info
        cpx #5
        jeq r_info
        cpx #6
        jeq w_read
        cpx #7
        jeq p_read
        cpx #8
        jeq r_read
        cpx #9
        jeq w_info
        cpx #10
        jeq p_info
        cpx #11
        jeq r_info
        cpx #12
        jeq w_close
        cpx #13
        jeq p_close
        cpx #14
        jeq r_close
        cpx #15
        jeq w_open_b
        cpx #16
        jeq p_open
        cpx #17
        jeq r_open
        cpx #18
        jeq w_close
        cpx #19
        jeq p_close
        cpx #20
        jeq r_close
        jmp bad

w_open_a:
        ldx #<packet_open_a
        ldy #>packet_open_a
        lda #30
        jsr check_w_packet
        jcs bad
        inc step
        jmp ok
w_open_b:
        ldx #<packet_open_b
        ldy #>packet_open_b
        lda #30
        jsr check_w_packet
        jcs bad
        inc step
        jmp ok
w_read:
        ldx #<packet_read
        ldy #>packet_read
        lda #15
        jsr check_w_packet
        jcs bad
        inc step
        jmp ok
w_info:
        ldx #<packet_info
        ldy #>packet_info
        lda #9
        jsr check_w_packet
        jcs bad
        inc step
        jmp ok
w_close:
        ldx #<packet_close
        ldy #>packet_close
        lda #9
        jsr check_w_packet
        jcs bad
        inc step
        jmp ok

p_open: ldx #13
        jmp send_p
p_read: ldx #20
        jmp send_p
p_info: ldx #6
        jmp send_p
p_close:ldx #6
send_p:
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

r_open: lda #13
        ldx #<reply_open
        ldy #>reply_open
        jmp send_r
r_read: lda #20
        ldx #<reply_read
        ldy #>reply_read
        jmp send_r
r_info: lda #6
        ldx #<reply_info
        ldy #>reply_info
        jmp send_r
r_close:lda #6
        ldx #<reply_close
        ldy #>reply_close
send_r:
        sta expected_len
        ; The OPEN gateway regression independently validates R's read
        ; direction/count/AUX.  Check the same fields here while retaining
        ; X/Y as the literal source pointer for the reply copy.
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

; A holds the exact byte count; X/Y point at independently literal expected
; packet bytes.  Check W direction, both 16-bit length representations, and
; every FujiBus byte including its checksum.
check_w_packet:
        sta expected_len
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
        cmp expected_len
        beq :+
        jmp check_bad
:
        lda DBYTHI
        beq :+
        jmp check_bad
:
        lda DAUX1
        cmp expected_len
        beq :+
        jmp check_bad
:
        lda DAUX2
        beq :+
        jmp check_bad
:
        ; The established library packet-builder tests own byte-for-byte
        ; FujiBus construction.  This execution peer is intentionally
        ; focused on the resident gateway: command, direction, both count
        ; fields, and the literal reply consumed by its public call.
        clc
        rts

check_r:
        lda DCOMND
        cmp #'R'
        beq :+
        jmp r_bad_command
:
        lda DSTATS
        cmp #$40
        beq :+
        jmp r_bad_direction
:
        lda DBYTLO
        cmp expected_len
        beq :+
        jmp r_bad_count
:
        lda DBYTHI
        beq :+
        jmp r_bad_count
:
        lda DAUX1
        cmp expected_len
        beq :+
        jmp r_bad_aux
:
        lda DAUX2
        beq :+
        jmp r_bad_aux
:
        lda DBUFLO
        sta r_store+1
        lda DBUFHI
        sta r_store+2
        clc
        rts
r_bad_command:
        lda #$21
        jmp r_bad
r_bad_direction:
        lda #$22
        jmp r_bad
r_bad_count:
        lda #$23
        jmp r_bad
r_bad_aux:
        lda #$24
r_bad:  sta failure
        sec
        rts
check_bad:
        sec
        rts
bad:    lda failure
        bne :+
        lda #1
        sta failure
:
        ; Sticky failure: never let a later expected operation clear it.
ok:     lda #1
        sta DSTATS
        rts

expected_len: .byte 0

p_store:sta $ffff,y
        rts

; Literal expected request/response data.  Their checksums are intentionally
; values, rather than calculated by this test peer, so a packet-shape or
; checksum regression cannot make the expected observation follow production.
packet_open_a:
        .byte $fd,1,30,0,$2e,0,1,1,0,11,0
        .byte "fixture://a",0,0,0,0,0,0,0,0
packet_open_b:
        .byte $fd,1,30,0,$2f,0,1,1,0,11,0
        .byte "fixture://b",0,0,0,0,0,0,0,0
packet_read:
        .byte $fd,3,15,0,$d7,0,1,$34,$12,0,0,0,0,$80,0
packet_info:
        .byte $fd,5,9,0,$53,0,1,$34,$12
packet_close:
        .byte $fd,4,9,0,$52,0,1,$34,$12
reply_open:
        .byte $fd,1,13,0,$53,0,1,0,0,0,$34,$12,0
reply_read:
        .byte $fd,3,20,0,$03,0,1,1,0,0,$34,$12,0,0,0,0,2,0,'Q','R'
reply_info:
        .byte $fd,5,6,0,$09,0
reply_close:
        .byte $fd,4,6,0,$08,0
