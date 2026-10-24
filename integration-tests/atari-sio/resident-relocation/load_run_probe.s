; Proves ld65's `load`/`run` semantics with generated segment symbols.  DATA
; is stored in the file's ROM area but linked for its fixed RAM run address.
; This is a staging/copy aid, not arbitrary MEMLO relocation.

        .export _load_run_probe
        .import __DATA_LOAD__, __DATA_RUN__, __DATA_SIZE__

        .segment "CODE"
_load_run_probe:
        lda load_run_data
        rts

        .segment "DATA"
load_run_data:
        .byte $5a
        .byte $a5
