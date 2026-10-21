        .export _main

; Native-v1 virtual projection guest.  It is deliberately only an SIOV
; initiator: all Q/W/P/R replies come from the production NetSIO ingress and
; AtariSioNioFrontend.  The host runner reads RESULT and the reply buffers
; through AltirraBridge and independently compares the wire trace to fixtures.

SIOV    = $E459
ddevic  = $0300
dunit   = $0301
dcomnd  = $0302
dstats  = $0303
dbuflo  = $0304
dbufhi  = $0305
dtimlo  = $0306
dunuse  = $0307
dbytlo  = $0308
dbythi  = $0309
daux1   = $030A
daux2   = $030B

RESULT  = $0800
STEP    = RESULT+4
Q_REPLY = $0810
P_READY = $0820
R_REPLY = $0830
P_IDLE  = $0850
REQUEST = $0860
COUNT   = $0870

.code
_main:
        lda #$00
        sta STEP
        ldx #5
@request:
        lda request_expected,x
        sta REQUEST,x
        dex
        bpl @request

        ; Q: wire revision 1, baseline capacity $0200.
        lda #1
        sta STEP
        lda #4
        sta COUNT
        lda #0
        sta COUNT+1
        ldx #<Q_REPLY
        ldy #>Q_REPLY
        lda #'Q'
        jsr call_sio
        cmp #1
        beq @q_sio_ok
        jmp fail
@q_sio_ok:
        ldx #0
@q:     lda Q_REPLY,x
        cmp q_expected,x
        beq @q_byte_ok
        jmp fail
@q_byte_ok:
        inx
        cpx #4
        bne @q

        ; Literal w-core-dispatch packet from nio_v1.json.
        lda #2
        sta STEP
        lda #6
        sta COUNT
        lda #0
        sta COUNT+1
        ldx #<REQUEST
        ldy #>REQUEST
        lda #'W'
        jsr call_sio
        cmp #1
        beq @w_sio_ok
        jmp fail
@w_sio_ok:

        ; P: synchronous endpoint is ready with the literal nine-byte reply.
        lda #3
        sta STEP
        lda #3
        sta COUNT
        lda #0
        sta COUNT+1
        ldx #<P_READY
        ldy #>P_READY
        lda #'P'
        jsr call_sio
        cmp #1
        bne fail
        ldx #0
@pready:
        lda P_READY,x
        cmp p_ready_expected,x
        bne fail
        inx
        cpx #3
        bne @pready

        ; R: consume the exact FujiBus response owned by the endpoint.
        lda #4
        sta STEP
        lda #9
        sta COUNT
        lda #0
        sta COUNT+1
        ldx #<R_REPLY
        ldy #>R_REPLY
        lda #'R'
        jsr call_sio
        cmp #1
        bne fail
        ldx #0
@r:     lda R_REPLY,x
        cmp r_expected,x
        bne fail
        inx
        cpx #9
        bne @r

        ; Terminal R consumed the response; P now reports canonical idle.
        lda #5
        sta STEP
        lda #3
        sta COUNT
        lda #0
        sta COUNT+1
        ldx #<P_IDLE
        ldy #>P_IDLE
        lda #'P'
        jsr call_sio
        cmp #1
        bne fail
        ldx #0
@pidle: lda P_IDLE,x
        cmp p_idle_expected,x
        bne fail
        inx
        cpx #3
        bne @pidle

        lda #'N'
        sta RESULT
        lda #'V'
        sta RESULT+1
        lda #'P'
        sta RESULT+2
        lda #'!'
        sta RESULT+3
        jmp done

fail:   lda #'N'
        sta RESULT
        lda #'V'
        sta RESULT+1
        lda #'F'
        sta RESULT+2
        lda #'!'
        sta RESULT+3
done:   jmp done

; A=command, X/Y=buffer. COUNT supplies DCB byte count.  Q/P require fixed
; AUX zero; W/R require their exact packet length.  Return Atari OS DSTATS.
call_sio:
        sta dcomnd
        lda #$7F
        sta ddevic
        lda #1
        sta dunit
        stx dbuflo
        sty dbufhi
        lda COUNT
        sta dbytlo
        sta daux1
        lda COUNT+1
        sta dbythi
        sta daux2
        lda dcomnd
        cmp #'Q'
        beq @fixed_aux
        cmp #'P'
        bne @aux_done
@fixed_aux:
        lda #0
        sta daux1
        sta daux2
@aux_done:
        lda dcomnd
        cmp #'W'
        beq @write
        lda #$40
        bne @direction_done
@write: lda #$80
@direction_done:
        sta dstats
        lda #60
        sta dtimlo
        lda #0
        sta dunuse
        jsr SIOV
        lda dstats
        rts

q_expected:       .byte 1, 0, 2, 0
p_ready_expected: .byte 2, 9, 0
r_expected:       .byte 1, 2, 9, 0, $0D, 1, 0, $AA, $55
p_idle_expected:  .byte 0, 0, 0
request_expected: .byte 1, 2, 6, 0, 9, 0
