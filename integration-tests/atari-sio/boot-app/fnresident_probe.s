; Second independently loaded XEX for the resident CIO gate.  It is appended
; after the installer INITAD phase, so DOS must honour the raised MEMLO before
; loading this code at $4000.

        .export _main

HATABS = $031A
MEMLO  = $02E7
RESULT = $0B00
PROBE  = $0B40
FNCNOT = $92
TABLEPTR = $80
VECTORPTR = $82

.segment "CODE"

_main:
        ; Preserve the installer result and prove its identity.
        lda RESULT
        cmp #'N'
        beq :+
        jmp fail
:
        lda RESULT+1
        cmp #'R'
        beq :+
        jmp fail
:
        lda RESULT+2
        cmp #'I'
        beq :+
        jmp fail
:
        lda RESULT+3
        cmp #'!'
        beq :+
        jmp fail
:

        ; MEMLO must still equal the value published by the installer.
        lda MEMLO
        cmp RESULT+10
        beq :+
        jmp fail
:
        lda MEMLO+1
        cmp RESULT+11
        beq :+
        jmp fail
:

        ; Locate N: and require the retained handler-table pointer.
        ldx #0
find_n:
        lda HATABS,x
        bne :+
        jmp fail
:
        cmp #'N'
        beq found_n
        inx
        inx
        inx
        cpx #35
        bne find_n
        bne fail
found_n:
        lda HATABS+1,x
        sta TABLEPTR
        cmp RESULT+26
        beq :+
        jmp fail
:
        lda HATABS+2,x
        sta TABLEPTR+1
        cmp RESULT+27
        beq :+
        jmp fail
:

        ; Every address-minus-one vector remains inside the protected image.
        ldy #0
check_vectors:
        lda (TABLEPTR),y
        sta VECTORPTR
        iny
        lda (TABLEPTR),y
        sta VECTORPTR+1
        iny
        lda VECTORPTR
        clc
        adc #1
        sta VECTORPTR
        bcc :+
        inc VECTORPTR+1
:
        lda VECTORPTR+1
        cmp RESULT+13
        bcc fail
        cmp RESULT+15
        bcc vector_ok
        bne fail
        lda VECTORPTR
        cmp RESULT+14
        bcs fail
vector_ok:
        cpy #12
        bne check_vectors

        ; Invoke the retained OPEN vector with a real IOCB offset.  A is not
        ; meaningful for OPEN; Y must return the named FNCNOT stub status.
        ldx #$20
        jsr call_open
        cpy #FNCNOT
        beq :+
        jmp fail
:
        cpx #$20
        beq :+
        jmp fail
:

        lda #'R'
        sta PROBE
        lda #'P'
        sta PROBE+1
        lda #'R'
        sta PROBE+2
        lda #'!'
        sta PROBE+3
        lda #1
        sta PROBE+4
        lda #0
        sta PROBE+5
        jmp done

fail:
        lda #'R'
        sta PROBE
        lda #'P'
        sta PROBE+1
        lda #'F'
        sta PROBE+2
        lda #'!'
        sta PROBE+3
        lda #1
        sta PROBE+4
        lda #1
        sta PROBE+5
done:
        jmp done

; The table pointer is copied from HATABS after the N: entry is found.
call_open:
        ldy #0
        lda (TABLEPTR),y
        clc
        adc #1
        sta open_jsr+1
        iny
        lda (TABLEPTR),y
        adc #0
        sta open_jsr+2
open_jsr:
        jsr $ffff
        rts

