; Fixed-location bootstrap for the independently linked resident image.
;
; The normal MyPicoDOS COM loader accepts explicit XEX destinations without
; consulting MEMLO.  Consequently a later copy of the installer must stage
; the linked $1D00 image elsewhere and decide ownership before copying it.
; This is NIO-specific lifecycle code, not a port of a legacy NDEV relocator.

        .include "build/fnresident-bootstrap.inc"

        .export _main

HATABS = $031A
SRC    = $80
DST    = $82

.segment "CODE"

_main:
        ; Existing N: ownership (including a foreign owner) must be decided
        ; by the installed image before staged bytes can touch $1D00.
        ldx #0
scan_hatabs:
        lda HATABS,x
        beq install
        cmp #'N'
        bne next_hatabs
        lda HATABS+1,x
        cmp #<RESIDENT_TABLE
        bne foreign
        lda HATABS+2,x
        cmp #>RESIDENT_TABLE
        bne foreign
        jmp run_installed
next_hatabs:
        inx
        inx
        inx
        cpx #33
        bcc scan_hatabs
        ; A full table without N: still needs the image copied so resident
        ; main can report its documented no-slot outcome.
        jmp install
run_installed:
        jmp RESIDENT_ENTRY

foreign:
        ; Do not copy the staged image: a foreign N: may itself own $1D00.
        ; Publish the subset of the versioned result required to prove that
        ; no initialization, MEMLO update, or HATABS replacement occurred.
        lda #'N'
        sta $0B00
        lda #'R'
        sta $0B01
        lda #'I'
        sta $0B02
        lda #'!'
        sta $0B03
        lda #1
        sta $0B04
        lda #4
        sta $0B05
        lda #$ff
        sta $0B06
        lda #$92
        sta $0B07
        lda $02E7
        sta $0B08
        sta $0B0A
        lda $02E8
        sta $0B09
        sta $0B0B
        rts

install:
        lda #<RESIDENT_STAGE
        sta SRC
        lda #>RESIDENT_STAGE
        sta SRC+1
        lda #<RESIDENT_START
        sta DST
        lda #>RESIDENT_START
        sta DST+1
copy_image:
        ldy #0
        lda (SRC),y
        sta (DST),y
        jsr advance
        lda DST+1
        cmp #>RESIDENT_IMAGE_END
        bne copy_image
        lda DST
        cmp #<RESIDENT_IMAGE_END
        bne copy_image

        lda #<RESIDENT_BSS_START
        sta DST
        lda #>RESIDENT_BSS_START
        sta DST+1
        lda #0
clear_bss:
        ldy #0
        lda #0
        sta (DST),y
        inc DST
        bne :+
        inc DST+1
:
        lda DST+1
        cmp #>RESIDENT_END
        bne clear_bss
        lda DST
        cmp #<RESIDENT_END
        bne clear_bss
        jmp RESIDENT_ENTRY

advance:
        inc SRC
        bne :+
        inc SRC+1
:
        inc DST
        bne :+
        inc DST+1
:
        rts
