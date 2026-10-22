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
R_WRONG = $0840
P_IDLE  = $0850
REQUEST = $0860
COUNT   = $0870
STATUS  = $0880
P_RETAIN = $0890
RESET_GO = $089f
REQUEST_AFTER = $08a0
P_AFTER_READY = $08b0
R_AFTER = $08c0
P_AFTER_IDLE = $08d0

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
        sta STATUS
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
        sta STATUS+1
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
        sta STATUS+2
        cmp #1
        beq @pready_sio_ok
        jmp fail
@pready_sio_ok:
        ldx #0
@pready:
        lda P_READY,x
        cmp p_ready_expected,x
        beq @pready_byte_ok
        jmp fail
@pready_byte_ok:
        inx
        cpx #3
        bne @pready

 .ifdef RESET_TO_IDLE
        ; The host injects a real NetSIO COLD_RESET only after this literal
        ; response is queued.  Waiting here keeps the Atari CPU alive: it is
        ; not an emulator reset and does not manufacture frontend state.
        lda #4
        sta STEP
@await_reset:
        lda RESET_GO
        beq @await_reset

        ; The reset discarded the accepted W response.  A poll must report
        ; canonical IDLE; never issue an R for the stale nine-byte reply.
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
        sta STATUS+3
        cmp #1
        beq @postreset_idle_sio_ok
        jmp fail
@postreset_idle_sio_ok:
        ldx #0
@postreset_idle:
        lda P_IDLE,x
        cmp p_idle_expected,x
        beq @postreset_idle_byte_ok
        jmp fail
@postreset_idle_byte_ok:
        inx
        cpx #3
        bne @postreset_idle

        ; A distinct, parseable FujiBus request must start directly with W
        ; after IDLE.  Its reply is independently literal in nio_v1.json.
        ldx #5
@request_after:
        lda request_after_expected,x
        sta REQUEST_AFTER,x
        dex
        bpl @request_after
        lda #6
        sta STEP
        lda #6
        sta COUNT
        lda #0
        sta COUNT+1
        ldx #<REQUEST_AFTER
        ldy #>REQUEST_AFTER
        lda #'W'
        jsr call_sio
        sta STATUS+4
        cmp #1
        beq @postreset_w_sio_ok
        jmp fail
@postreset_w_sio_ok:

        lda #7
        sta STEP
        lda #3
        sta COUNT
        lda #0
        sta COUNT+1
        ldx #<P_AFTER_READY
        ldy #>P_AFTER_READY
        lda #'P'
        jsr call_sio
        sta STATUS+5
        cmp #1
        beq @postreset_ready_sio_ok
        jmp fail
@postreset_ready_sio_ok:
        ldx #0
@postreset_ready:
        lda P_AFTER_READY,x
        cmp p_ready_expected,x
        beq @postreset_ready_byte_ok
        jmp fail
@postreset_ready_byte_ok:
        inx
        cpx #3
        bne @postreset_ready

        lda #8
        sta STEP
        lda #9
        sta COUNT
        lda #0
        sta COUNT+1
        ldx #<R_AFTER
        ldy #>R_AFTER
        lda #'R'
        jsr call_sio
        sta STATUS+6
        cmp #1
        beq @postreset_r_sio_ok
        jmp fail
@postreset_r_sio_ok:
        ldx #0
@postreset_r:
        lda R_AFTER,x
        cmp r_after_expected,x
        beq @postreset_r_byte_ok
        jmp fail
@postreset_r_byte_ok:
        inx
        cpx #9
        bne @postreset_r

        lda #9
        sta STEP
        lda #3
        sta COUNT
        lda #0
        sta COUNT+1
        ldx #<P_AFTER_IDLE
        ldy #>P_AFTER_IDLE
        lda #'P'
        jsr call_sio
        sta STATUS+7
        cmp #1
        beq @postreset_terminal_idle_sio_ok
        jmp fail
@postreset_terminal_idle_sio_ok:
        ldx #0
@postreset_terminal_idle:
        lda P_AFTER_IDLE,x
        cmp p_idle_expected,x
        beq @postreset_terminal_idle_byte_ok
        jmp fail
@postreset_terminal_idle_byte_ok:
        inx
        cpx #3
        bne @postreset_terminal_idle
        jmp success
 .endif

 .ifdef INTERRUPTED_R_RECOVERY
        ; This R has the correct AUX and is accepted by the endpoint.  The
        ; NetSIO relay corrupts only its delivered checksum after the endpoint
        ; emitted the literal response, so SIOV must fail after consuming it.
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
        sta STATUS+3
        cmp #1
        bne @interrupted_r_failed
        jmp fail
@interrupted_r_failed:
        ; The accepted R consumed the original reply despite guest delivery
        ; failure.  A fresh P must be canonical IDLE before a new W begins.
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
        sta STATUS+4
        cmp #1
        beq @interrupted_idle_sio_ok
        jmp fail
@interrupted_idle_sio_ok:
        ldx #0
@interrupted_idle:
        lda P_IDLE,x
        cmp p_idle_expected,x
        beq @interrupted_idle_byte_ok
        jmp fail
@interrupted_idle_byte_ok:
        inx
        cpx #3
        bne @interrupted_idle

        ; A distinct literal W starts a new core transaction only after IDLE.
        ldx #5
@interrupted_request:
        lda request_interrupted_expected,x
        sta REQUEST_AFTER,x
        dex
        bpl @interrupted_request
        lda #6
        sta STEP
        lda #6
        sta COUNT
        lda #0
        sta COUNT+1
        ldx #<REQUEST_AFTER
        ldy #>REQUEST_AFTER
        lda #'W'
        jsr call_sio
        sta STATUS+5
        cmp #1
        beq @interrupted_w_sio_ok
        jmp fail
@interrupted_w_sio_ok:

        lda #7
        sta STEP
        lda #3
        sta COUNT
        lda #0
        sta COUNT+1
        ldx #<P_AFTER_READY
        ldy #>P_AFTER_READY
        lda #'P'
        jsr call_sio
        sta STATUS+6
        cmp #1
        beq @interrupted_ready_sio_ok
        jmp fail
@interrupted_ready_sio_ok:
        ldx #0
@interrupted_ready:
        lda P_AFTER_READY,x
        cmp p_ready_expected,x
        beq @interrupted_ready_byte_ok
        jmp fail
@interrupted_ready_byte_ok:
        inx
        cpx #3
        bne @interrupted_ready

        lda #8
        sta STEP
        lda #9
        sta COUNT
        lda #0
        sta COUNT+1
        ldx #<R_AFTER
        ldy #>R_AFTER
        lda #'R'
        jsr call_sio
        sta STATUS+7
        cmp #1
        beq @interrupted_recovery_r_sio_ok
        jmp fail
@interrupted_recovery_r_sio_ok:
        ldx #0
@interrupted_recovery_r:
        lda R_AFTER,x
        cmp r_interrupted_expected,x
        beq @interrupted_recovery_r_byte_ok
        jmp fail
@interrupted_recovery_r_byte_ok:
        inx
        cpx #9
        bne @interrupted_recovery_r

        lda #9
        sta STEP
        lda #3
        sta COUNT
        lda #0
        sta COUNT+1
        ldx #<P_AFTER_IDLE
        ldy #>P_AFTER_IDLE
        lda #'P'
        jsr call_sio
        sta STATUS+8
        cmp #1
        beq @interrupted_terminal_idle_sio_ok
        jmp fail
@interrupted_terminal_idle_sio_ok:
        ldx #0
@interrupted_terminal_idle:
        lda P_AFTER_IDLE,x
        cmp p_idle_expected,x
        beq @interrupted_terminal_idle_byte_ok
        jmp fail
@interrupted_terminal_idle_byte_ok:
        inx
        cpx #3
        bne @interrupted_terminal_idle
        jmp success
 .endif

 .ifdef WRONG_R_RETENTION
        ; A wrong R AUX must NAK.  Its unsuccessful SIOV result must leave
        ; the endpoint response owned by the original accepted W.
        lda #4
        sta STEP
        lda #3
        sta COUNT
        lda #0
        sta COUNT+1
        ldx #<R_WRONG
        ldy #>R_WRONG
        lda #'R'
        jsr call_sio
        sta STATUS+3
        cmp #1
        bne @wrong_r_nak_ok
        jmp fail
@wrong_r_nak_ok:
        ; The retained response is still ready with its original length.
        lda #5
        sta STEP
        lda #3
        sta COUNT
        lda #0
        sta COUNT+1
        ldx #<P_RETAIN
        ldy #>P_RETAIN
        lda #'P'
        jsr call_sio
        sta STATUS+4
        cmp #1
        beq @pretained_sio_ok
        jmp fail
@pretained_sio_ok:
        ldx #0
@pretained:
        lda P_RETAIN,x
        cmp p_ready_expected,x
        beq @pretained_byte_ok
        jmp fail
@pretained_byte_ok:
        inx
        cpx #3
        bne @pretained

        ; The correct terminal R can now consume the unchanged response.
        lda #6
        sta STEP
 .else
        ; R: consume the exact FujiBus response owned by the endpoint.
        lda #4
        sta STEP
 .endif
        lda #9
        sta COUNT
        lda #0
        sta COUNT+1
        ldx #<R_REPLY
        ldy #>R_REPLY
        lda #'R'
        jsr call_sio
 .ifdef WRONG_R_RETENTION
        sta STATUS+5
 .else
        sta STATUS+3
 .endif
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
 .ifdef WRONG_R_RETENTION
        lda #7
 .else
        lda #5
 .endif
        sta STEP
        lda #3
        sta COUNT
        lda #0
        sta COUNT+1
        ldx #<P_IDLE
        ldy #>P_IDLE
        lda #'P'
        jsr call_sio
 .ifdef WRONG_R_RETENTION
        sta STATUS+6
 .else
        sta STATUS+4
 .endif
        cmp #1
        bne fail
        ldx #0
@pidle: lda P_IDLE,x
        cmp p_idle_expected,x
        bne fail
        inx
        cpx #3
        bne @pidle

success:
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
r_after_expected: .byte 1, 3, 9, 0, $0E, 1, 0, $33, $CC
r_interrupted_expected: .byte 1, 4, 9, 0, $0F, 1, 0, $5A, $A5
p_idle_expected:  .byte 0, 0, 0
request_expected: .byte 1, 2, 6, 0, 9, 0
request_after_expected: .byte 1, 3, 6, 0, $0A, 0
request_interrupted_expected: .byte 1, 4, 6, 0, $0B, 0
