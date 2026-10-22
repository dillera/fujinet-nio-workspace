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
CAP_REQUEST = $2000
CAP_REQUEST_511_GUARD = $21ff
CAP_REQUEST_GUARD = $2200
CAP_RESPONSE_GUARD_LOW = $23ff
CAP_RESPONSE = $2400
CAP_RESPONSE_GUARD_HIGH = $2600

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

 .ifdef CAPACITY_BOUNDS
        jmp capacity_bounds
 .endif

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

 .ifdef CAPACITY_BOUNDS
; This branch stays a real SIOV client.  The fixture route is only the core
; device behind the production NetSIO ingress; it never supplies Q/W/P/R.
fail:   jmp native_fail

.macro capacity_bne_fail
        beq :+
        jmp native_fail
:
.endmacro

.macro capacity_beq_fail
        bne :+
        jmp native_fail
:
.endmacro

capacity_bounds:
        lda #$5a
        sta CAP_REQUEST-1
        sta CAP_REQUEST_511_GUARD
        sta CAP_RESPONSE_GUARD_LOW
        lda #$a5
        sta CAP_REQUEST_GUARD
        sta CAP_RESPONSE_GUARD_HIGH

        ; A parseable 511-byte raw FujiBus W: header plus patterned data.
        jsr build_w511
        lda #1
        sta STEP
        lda #$ff
        sta COUNT
        lda #1
        sta COUNT+1
        ldx #<CAP_REQUEST
        ldy #>CAP_REQUEST
        lda #'W'
        jsr call_sio
        sta STATUS+1
        cmp #1
        capacity_bne_fail
        lda CAP_REQUEST-1
        cmp #$5a
        capacity_bne_fail
        lda CAP_REQUEST_511_GUARD
        cmp #$5a
        capacity_bne_fail
        lda CAP_REQUEST_GUARD
        cmp #$a5
        capacity_bne_fail

        ; Consume the small successful 511-byte-request response before W512.
        lda #2
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
        capacity_bne_fail
        ldx #0
@capacity_p7a:
        lda P_READY,x
        cmp p_ready_7_expected,x
        capacity_bne_fail
        inx
        cpx #3
        bne @capacity_p7a
        lda #3
        sta STEP
        lda #7
        sta COUNT
        lda #0
        sta COUNT+1
        ldx #<R_AFTER
        ldy #>R_AFTER
        lda #'R'
        jsr call_sio
        sta STATUS+3
        cmp #1
        capacity_bne_fail
        ldx #0
@capacity_r7:
        lda R_AFTER,x
        cmp r_511_expected,x
        capacity_bne_fail
        inx
        cpx #7
        bne @capacity_r7

        ; The full 512-byte raw request crosses two pages without padding.
        jsr build_w512
        lda #4
        sta STEP
        lda #0
        sta COUNT
        lda #2
        sta COUNT+1
        ldx #<CAP_REQUEST
        ldy #>CAP_REQUEST
        lda #'W'
        jsr call_sio
        sta STATUS+4
        cmp #1
        capacity_bne_fail
        lda CAP_REQUEST-1
        cmp #$5a
        capacity_bne_fail
        lda CAP_REQUEST_GUARD
        cmp #$a5
        capacity_bne_fail

        lda #5
        sta STEP
        lda #3
        sta COUNT
        lda #0
        sta COUNT+1
        ldx #<P_READY
        ldy #>P_READY
        lda #'P'
        jsr call_sio
        sta STATUS+5
        cmp #1
        capacity_bne_fail
        ldx #0
@capacity_p512:
        lda P_READY,x
        cmp p_ready_512_expected,x
        capacity_bne_fail
        inx
        cpx #3
        bne @capacity_p512

        lda #6
        sta STEP
        lda #0
        sta COUNT
        lda #2
        sta COUNT+1
        ldx #<CAP_RESPONSE
        ldy #>CAP_RESPONSE
        lda #'R'
        jsr call_sio
        sta STATUS+6
        cmp #1
        capacity_bne_fail
        jsr verify_r512
        lda CAP_RESPONSE_GUARD_LOW
        cmp #$5a
        capacity_bne_fail
        lda CAP_RESPONSE_GUARD_HIGH
        cmp #$a5
        capacity_bne_fail

        lda #7
        sta STEP
        lda #3
        sta COUNT
        lda #0
        sta COUNT+1
        ldx #<P_IDLE
        ldy #>P_IDLE
        lda #'P'
        jsr call_sio
        sta STATUS+7
        cmp #1
        capacity_bne_fail
        ldx #0
@capacity_idle_after_512:
        lda P_IDLE,x
        cmp p_idle_expected,x
        capacity_bne_fail
        inx
        cpx #3
        bne @capacity_idle_after_512

        ; 513 is rejected by the endpoint before it grants a data phase.
        lda #8
        sta STEP
        lda #1
        sta COUNT
        lda #2
        sta COUNT+1
        ldx #<CAP_REQUEST
        ldy #>CAP_REQUEST
        lda #'W'
        jsr call_sio
        sta STATUS+8
        cmp #1
        capacity_beq_fail

        ; A real core response larger than 512 is atomically replaced by the
        ; bounded raw InternalError response; no partial R is permitted.
        lda #1
        sta CAP_REQUEST
        lda #7
        sta CAP_REQUEST+1
        lda #6
        sta CAP_REQUEST+2
        lda #0
        sta CAP_REQUEST+3
        lda #$0e
        sta CAP_REQUEST+4
        lda #0
        sta CAP_REQUEST+5
        lda #9
        sta STEP
        lda #6
        sta COUNT
        lda #0
        sta COUNT+1
        ldx #<CAP_REQUEST
        ldy #>CAP_REQUEST
        lda #'W'
        jsr call_sio
        sta STATUS+9
        cmp #1
        capacity_bne_fail
        lda #10
        sta STEP
        lda #3
        sta COUNT
        lda #0
        sta COUNT+1
        ldx #<P_AFTER_READY
        ldy #>P_AFTER_READY
        lda #'P'
        jsr call_sio
        sta STATUS+10
        cmp #1
        capacity_bne_fail
        ldx #0
@capacity_p7b:
        lda P_AFTER_READY,x
        cmp p_ready_7_expected,x
        capacity_bne_fail
        inx
        cpx #3
        bne @capacity_p7b
        lda #11
        sta STEP
        lda #7
        sta COUNT
        lda #0
        sta COUNT+1
        ldx #<R_AFTER
        ldy #>R_AFTER
        lda #'R'
        jsr call_sio
        sta STATUS+11
        cmp #1
        capacity_bne_fail
        ldx #0
@capacity_error:
        lda R_AFTER,x
        cmp r_bounded_error_expected,x
        capacity_bne_fail
        inx
        cpx #7
        bne @capacity_error
        lda #12
        sta STEP
        lda #3
        sta COUNT
        lda #0
        sta COUNT+1
        ldx #<P_AFTER_IDLE
        ldy #>P_AFTER_IDLE
        lda #'P'
        jsr call_sio
        sta STATUS+12
        cmp #1
        capacity_bne_fail
        ldx #0
@capacity_terminal_idle:
        lda P_AFTER_IDLE,x
        cmp p_idle_expected,x
        capacity_bne_fail
        inx
        cpx #3
        bne @capacity_terminal_idle
        jmp success

build_w511:
        lda #1
        sta CAP_REQUEST
        lda #5
        sta CAP_REQUEST+1
        lda #$ff
        sta CAP_REQUEST+2
        lda #1
        sta CAP_REQUEST+3
        lda #$d0
        sta CAP_REQUEST+4
        lda #0
        sta CAP_REQUEST+5
        ldx #6
@w511_page0:
        txa
        eor #$a5
        sta CAP_REQUEST,x
        inx
        bne @w511_page0
        ldx #0
@w511_page1:
        txa
        eor #$a4
        sta CAP_REQUEST+$100,x
        inx
        cpx #$ff
        bne @w511_page1
        rts

build_w512:
        lda #1
        sta CAP_REQUEST
        lda #6
        sta CAP_REQUEST+1
        lda #0
        sta CAP_REQUEST+2
        lda #2
        sta CAP_REQUEST+3
        lda #$2e
        sta CAP_REQUEST+4
        lda #0
        sta CAP_REQUEST+5
        ldx #6
@w512_page0:
        txa
        eor #$a5
        sta CAP_REQUEST,x
        inx
        bne @w512_page0
        ldx #0
@w512_page1:
        txa
        eor #$a4
        sta CAP_REQUEST+$100,x
        inx
        bne @w512_page1
        rts

verify_r512:
        ldx #0
@r512_header:
        lda CAP_RESPONSE,x
        cmp r_512_header_expected,x
        capacity_bne_fail
        inx
        cpx #7
        bne @r512_header
        ldx #7
@r512_page0:
        txa
        eor #$a5
        cmp CAP_RESPONSE,x
        capacity_bne_fail
        inx
        bne @r512_page0
        ldx #0
@r512_page1:
        txa
        eor #$a4
        cmp CAP_RESPONSE+$100,x
        capacity_bne_fail
        inx
        bne @r512_page1
        rts
 .endif

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

 .ifndef CAPACITY_BOUNDS
fail:
 .endif
native_fail:
        lda #'N'
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
 .ifdef CAPACITY_BOUNDS
p_ready_7_expected: .byte 2, 7, 0
p_ready_512_expected: .byte 2, 0, 2
r_511_expected: .byte 1, 5, 7, 0, $0e, 1, 0
r_bounded_error_expected: .byte 1, 7, 7, 0, $17, 1, 7
r_512_header_expected: .byte 1, 6, 0, 2, $8b, 1, 0
 .endif
