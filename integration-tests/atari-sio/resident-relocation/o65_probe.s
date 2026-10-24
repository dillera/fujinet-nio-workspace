; Minimal, format-only o65 probe.  The absolute LDA operand refers to DATA;
; ld65 must encode it as relocation metadata rather than as a permanently
; linked address.  It is not a resident handler and is never loaded by Atari.

        .export _o65_probe_entry

        .segment "CODE"
_o65_probe_entry:
        lda o65_probe_data
        rts

        .segment "DATA"
o65_probe_data:
        .byte $5a
