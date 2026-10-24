; Fixture-controlled SIOV peer for the o65 public-API closure execution test.
; It validates only DCB/native carrier shape and returns literal FujiBus reply
; bytes.  It does not implement, model, or replace any public API function.

OP          = $0600
STEP        = $0601
FAIL        = $0602
WCOUNT      = $0603
PCOUNT      = $0604
RCOUNT      = $0605
PTR         = $0060
SRC         = $0062
LEN         = $0064

        .segment "RESET"
        .export peer_reset

peer_reset:
        lda #0
        sta OP
        sta STEP
        sta FAIL
        sta WCOUNT
        sta PCOUNT
        sta RCOUNT
        rts

; The production transport calls the Atari OS SIOV vector at $E459.
        .segment "SIOV"
fake_siov:
        lda $0300
        cmp #$7f
        bne bad
        lda $0302
        cmp #'W'
        beq write_frame
        cmp #'P'
        beq poll_frame
        cmp #'R'
        bne :+
        jmp read_frame
:
        jmp bad

; Keep the branch target near the DCB validation paths.  The error work can
; live after the reply tables without imposing 6502 branch-range limits.
bad:    jmp record_bad

write_frame:
        lda $0303
        cmp #$80
        bne bad
        lda $0308
        ora $0309
        beq bad
        lda $0308
        cmp $030a
        bne bad
        lda $0309
        cmp $030b
        bne bad
        jsr dcb_ptr
        ldy #0
        lda (PTR),y
        cmp #$fd
        bne bad
        iny
        lda (PTR),y
        ldx STEP
        cpx #5
        bcs bad
        cmp expected_command,x
        bne bad
        sta OP
        inc STEP
        inc WCOUNT
        lda #1
        sta $0303
        rts

poll_frame:
        lda $0303
        cmp #$40
        bne bad
        lda $0308
        cmp #3
        bne bad
        lda $0309
        ora $030a
        ora $030b
        bne bad
        jsr select_reply
        jsr dcb_ptr
        ldy #0
        lda #2
        sta (PTR),y
        iny
        lda LEN
        sta (PTR),y
        iny
        lda LEN+1
        sta (PTR),y
        inc PCOUNT
        lda #1
        sta $0303
        rts

read_frame:
        lda $0303
        cmp #$40
        beq :+
        jmp bad
:
        jsr select_reply
        lda $0308
        cmp LEN
        beq :+
        jmp bad
:
        lda $0309
        cmp LEN+1
        beq :+
        jmp bad
:
        lda $030a
        cmp LEN
        beq :+
        jmp bad
:
        lda $030b
        cmp LEN+1
        beq :+
        jmp bad
:
        jsr dcb_ptr
        ldy #0
@copy:  cpy LEN
        beq @done
        lda (SRC),y
        sta (PTR),y
        iny
        bne @copy
@done:  inc RCOUNT
        lda #1
        sta $0303
        rts

dcb_ptr:
        lda $0304
        sta PTR
        lda $0305
        sta PTR+1
        rts

select_reply:
        lda OP
        cmp #1
        beq open_reply
        cmp #2
        beq read_reply
        cmp #3
        beq write_reply
        cmp #4
        beq close_reply
        cmp #5
        beq info_reply
        jmp bad
open_reply:
        lda #<reply_open
        ldx #>reply_open
        ldy #13
        bne set_reply
read_reply:
        lda #<reply_read
        ldx #>reply_read
        ldy #22
        bne set_reply
write_reply:
        lda #<reply_write
        ldx #>reply_write
        ldy #18
        bne set_reply
close_reply:
        lda #<reply_close
        ldx #>reply_close
        ldy #9
        bne set_reply
info_reply:
        lda #<reply_info
        ldx #>reply_info
        ldy #22
set_reply:
        sta SRC
        stx SRC+1
        sty LEN
        lda #0
        sta LEN+1
        rts

record_bad:
        lda #1
        sta FAIL
        lda #0
        sta $0303
        rts

expected_command:
        .byte 1, 3, 2, 5, 4

; Literal FujiBus v1 response packets.  Byte four is the packet checksum.
reply_open:
        .byte $fd, $01, $0d, $00, $53, $00, $01, $00, $00, $00, $34, $12, $00
reply_write:
        .byte $fd, $03, $12, $00, $5e, $00, $01, $00, $00, $00, $34, $12, $00, $00, $00, $00, $04, $00
reply_read:
        .byte $fd, $02, $16, $00, $40, $00, $01, $00, $00, $00, $34, $12, $00, $00, $00, $00, $04, $00, 'R', '6', '5', '!'
reply_info:
        .byte $fd, $05, $16, $00, $2d, $00, $01, $00, $00, $00, $34, $12, $c8, $00, $04, $00, $00, $00, $00, $00, $00, $00
reply_close:
        .byte $fd, $04, $09, $00, $52, $00, $01, $34, $12
