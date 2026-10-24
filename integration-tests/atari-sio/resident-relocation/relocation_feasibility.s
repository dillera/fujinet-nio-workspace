; Story 2.5 relocation feasibility only.  This is deliberately not a CIO
; handler or a production relocator.  It proves the minimum mechanism: copy
; a code+data blob, apply its recorded absolute-word fixups, and call it via
; a HATABS-style address-minus-one vector at two distinct bases.

        .export _test_func, _test_result, _test_expected_unrelocated
        .export end_relocation

HATABS  = $031A
NENTRY  = HATABS
DST     = $80
PATCH   = $82
TARGET  = $84
VECTOR  = $86

BASE_A  = $3000
BASE_B  = $4800
BASE_C  = $5800

        .segment "BSS"
_test_result:              .res 3
_test_expected_unrelocated:.res 1

        .segment "CODE"
_test_func:
        ; A: correctly relocate code and its data to $3000.
        lda #<BASE_A
        sta DST
        lda #>BASE_A
        sta DST+1
        lda #$11
        jsr copy_blob_with_data
        jsr apply_fixups
        jsr publish_n_vector
        jsr call_n_vector
        sta _test_result

        ; B: the same blob and relocation table work at a separate base.
        lda #<BASE_B
        sta DST
        lda #>BASE_B
        sta DST+1
        lda #$22
        jsr copy_blob_with_data
        jsr apply_fixups
        jsr publish_n_vector
        jsr call_n_vector
        sta _test_result+1

        ; C: copying without the absolute-word fixup must keep reading the
        ; source blob's data ($11), rather than this destination's $77.
        lda #<BASE_C
        sta DST
        lda #>BASE_C
        sta DST+1
        lda #$77
        jsr copy_blob_with_data
        jsr publish_n_vector
        jsr call_n_vector
        sta _test_result+2
        lda #$97                    ; $77 + routine's $20 addend
        sta _test_expected_unrelocated
end_relocation:
        rts

; Copy the template and install the caller's associated data byte.
copy_blob_with_data:
        sta TARGET
        ldy #0
copy_loop:
        lda relocation_blob,y
        sta (DST),y
        iny
        cpy #relocation_blob_end-relocation_blob
        bne copy_loop
        ldy #relocation_data-relocation_blob
        lda TARGET
        sta (DST),y
        rts

; Apply all absolute-address operand fixups.  A real payload would generate
; this table from relocation metadata rather than hand-writing one entry.
apply_fixups:
        ldx #0
fixup_loop:
        clc
        lda DST
        adc relocation_fixups,x
        sta PATCH
        lda DST+1
        adc relocation_fixups+1,x
        sta PATCH+1
        clc
        lda DST
        adc #< (relocation_data-relocation_blob)
        sta TARGET
        lda DST+1
        adc #> (relocation_data-relocation_blob)
        sta TARGET+1
        ldy #0
        lda TARGET
        sta (PATCH),y
        iny
        lda TARGET+1
        sta (PATCH),y
        inx
        inx
        cpx #relocation_fixups_end-relocation_fixups
        bne fixup_loop
        rts

; Publish exactly one terminated HATABS entry.  Its pointer is routine-1.
publish_n_vector:
        lda #'N'
        sta NENTRY
        sec
        lda DST
        sbc #1
        sta NENTRY+1
        lda DST+1
        sbc #0
        sta NENTRY+2
        lda #0
        sta NENTRY+3
        sta NENTRY+4
        rts

; Model the CIO handler lookup/call convention without a second protocol peer.
call_n_vector:
        ldx #0
find_n:
        lda HATABS,x
        beq call_fail
        cmp #'N'
        beq found_n
        inx
        inx
        inx
        cpx #33
        bcc find_n
call_fail:
        lda #$ff
        rts
found_n:
        lda HATABS+1,x
        sta VECTOR
        lda HATABS+2,x
        sta VECTOR+1
        inc VECTOR
        bne :+
        inc VECTOR+1
:
        lda VECTOR
        sta call_slot+1
        lda VECTOR+1
        sta call_slot+2
call_slot:
        jsr $ffff
        rts

; This deliberately contains an absolute LDA operand.  Its relocation-table
; offset points at the two-byte operand, not at an instruction mnemonic.
relocation_blob:
relocation_routine:
        lda relocation_data
        clc
        adc #$20
        rts
relocation_data:
        .byte $11
relocation_blob_end:

relocation_fixups:
        .word relocation_routine+1-relocation_blob
relocation_fixups_end:
