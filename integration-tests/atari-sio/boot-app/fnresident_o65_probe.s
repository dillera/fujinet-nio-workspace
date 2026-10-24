; Second independently loaded XEX for the dynamic o65 resident-loader gate.
; The result record is transient at $5400; the installed payload itself is
; below the loader and must survive this $4000 program load.

        .export _main
        .macpack longbranch

HATABS  = $031A
MEMLO   = $02E7
RESULT  = $5400
PROBE   = $5440
FNCNOT  = $92
TABLE   = $80
VECTOR  = $82

.segment "CODE"

_main:
        lda RESULT
        cmp #'N'
        jne fail
        lda RESULT+1
        cmp #'R'
        jne fail
        lda RESULT+2
        cmp #'I'
        jne fail
        lda RESULT+3
        cmp #'!'
        jne fail
        lda RESULT+4
        cmp #2
        jne fail
        lda RESULT+5
        cmp #0
        beq installed
        cmp #1
        jne fail
        ; A second loader invocation found the same FNR1 table and marker.
        ; It must preserve state rather than reinitializing or allocating.
        lda RESULT+6
        cmp #$ff
        jne fail
        jmp ownership_ok
installed:
        lda RESULT+6
        jne fail
ownership_ok:
        lda MEMLO
        cmp RESULT+10
        jne fail
        lda MEMLO+1
        cmp RESULT+11
        jne fail
        ldx RESULT+24
        cpx #33
        jcs fail
        lda HATABS,x
        cmp #'N'
        jne fail
        lda HATABS+1,x
        sta TABLE
        cmp RESULT+26
        jne fail
        lda HATABS+2,x
        sta TABLE+1
        cmp RESULT+27
        bne fail
        ; Verify each address-minus-one vector still targets the dynamically
        ; protected resident allocation.
        ldy #0
vectors:
        lda (TABLE),y
        sta VECTOR
        iny
        lda (TABLE),y
        sta VECTOR+1
        iny
        clc
        lda VECTOR
        adc #1
        sta VECTOR
        bcc :+
        inc VECTOR+1
:
        lda VECTOR+1
        cmp RESULT+13
        bcc fail
        bne :+
        lda VECTOR
        cmp RESULT+12
        bcc fail
:
        lda VECTOR+1
        cmp RESULT+15
        bcc vector_ok
        bne fail
        lda VECTOR
        cmp RESULT+14
        jcs fail
vector_ok:
        cpy #12
        bne vectors
        ; Directly invoke the retained OPEN stub with an IOCB offset in X.
        ldy #0
        lda (TABLE),y
        clc
        adc #1
        sta call_open+1
        iny
        lda (TABLE),y
        adc #0
        sta call_open+2
        ldx #$20
call_open:
        jsr $ffff
        cpy #FNCNOT
        bne fail
        cpx #$20
        bne fail
        lda #'R'
        sta PROBE
        lda #'P'
        sta PROBE+1
        lda #'R'
        sta PROBE+2
        lda #'!'
        sta PROBE+3
        lda #2
        sta PROBE+4
        lda #0
        sta PROBE+5
done:   jmp done

fail:   lda #'R'
        sta PROBE
        lda #'P'
        sta PROBE+1
        lda #'F'
        sta PROBE+2
        lda #'!'
        sta PROBE+3
        lda #2
        sta PROBE+4
        lda #1
        sta PROBE+5
        jmp done
