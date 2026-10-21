        .export _main

; Story 1.3 boot acceptance payload.  $0600 is Atari user RAM; $06F0-$06F3
; is deliberately outside this small image and is read through the bridge.
SIGNATURE = $06F0
COLOR2    = $02C6
COLOR4    = $02C8
GTIA_C2   = $D018
GTIA_C4   = $D01A

.code
_main:
        lda #$42
        sta COLOR2
        sta GTIA_C2
        lda #$00
        sta COLOR4
        sta GTIA_C4
        lda #'N'
        sta SIGNATURE
        lda #'I'
        sta SIGNATURE+1
        lda #'O'
        sta SIGNATURE+2
        lda #'!'
        sta SIGNATURE+3
loop:   jmp loop
