; Test-only 6502 controller for the same o65 module bytes at two bases.
; It is deliberately outside the module; production installation is out of
; scope.  The controller gives each invocation a fresh cc65 ZP scratch bank
; and software stack, then records the genuine public-API return status.

RESULT_DONE = $0680
RESULT_A    = $0681
RESULT_B    = $0682
FAIL_A      = $0683
FAIL_B      = $0684
W_A         = $0685
W_B         = $0686
P_A         = $0687
P_B         = $0688
R_A         = $0689
R_B         = $068A

PEER_FAIL   = $0602
PEER_W      = $0603
PEER_P      = $0604
PEER_R      = $0605

        .segment "CODE"
        .export runtime_control_start

runtime_control_start:
        sei
        ldx #$ff
        txs
        jsr prepare_call
        jsr $2000                    ; same o65 module, first allocation base
        sta RESULT_A
        lda PEER_FAIL
        sta FAIL_A
        lda PEER_W
        sta W_A
        lda PEER_P
        sta P_A
        lda PEER_R
        sta R_A

        jsr prepare_call
        jsr $5000                    ; identical source module at second base
        sta RESULT_B
        lda PEER_FAIL
        sta FAIL_B
        lda PEER_W
        sta W_B
        lda PEER_P
        sta P_B
        lda PEER_R
        sta R_B
        lda #1
        sta RESULT_DONE
halt:   jmp halt

prepare_call:
        ldx #25
        lda #0
@clear_zp:
        sta $0082,x                  ; cc65 module ZP relocation destination
        dex
        bpl @clear_zp
        lda #$00
        sta $0082                    ; c_sp = $9000, a resident-owned C stack
        lda #$90
        sta $0083
        jmp $e440                    ; test-only peer reset vector
