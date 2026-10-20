# Atari Disk SIO v1 conformance fixtures

This directory is the canonical, implementation-independent contract for the
standard Atari disk surface.  It describes virtual protocol evidence only: it
does **not** assert SIO electrical characteristics, timing, UART behaviour, or
physical-drive compatibility.

`fixtures/disk_v1.json` is the literal disk-v1 matrix.  Its stable scenario
IDs are the identifiers an adapter reports; it must not be regenerated from a
production framer.  `disk_v1.manifest.json` projects those scenarios as ordered
SIO phases for virtual consumers.

The command frame is always five literal bytes: device, command, AUX1, AUX2,
and Atari end-around-carry checksum.  Disk devices `0x31`--`0x38` route to
DiskService slots 0--7.  Sectors are one-based and map to LBA `sector - 1`.
Only READ (`0x52`), PUT (`0x50`), WRITE WITH VERIFY (`0x57`), and STATUS
(`0x53`, AUX zero) belong to v1.  `A`, `N`, `C`, and `E` are unchecksummed
control replies.  A valid READ is `A,C,data,sum`; a bad frame or unsupported
command is `N`; a syntactically valid failed disk command is deliberately
`A,E`.  PUT/WRITE accept with `A`, reject a bad incoming data sum with `N`,
then acknowledge valid data with `A` before their terminal result.

The matrix separately makes malformed frame length and checksum, and every
well-formed command outside that exact v1 set, literal `N` rejections with no
DiskService call. Valid sector commands with zero, out-of-range, or rejected
ATR geometry are instead `A,E` execution failures.

STATUS is a non-blocking inspection: it never mounts, resolves a URI, or
activates pending media.  It is always `A,C,status,sum` and retains the last
disk outcome until a successful READ/PUT/WRITE clears transient errors.  Its
four bytes are drive flags, inverted FDC state, `0x0f` timeout, and zero.
The vectors cover ready (`0xdf`), unavailable (`0x5f`), write-protect
(`0x9f`), record-not-found (`0xcf`), and lost-data (`0xdb`).

Every STATUS projection is the complete `A,C,status,sum` exchange and carries
an explicit predecessor when it asserts a retained or cleared result. STATUS
vectors also mark `ensure_mounted: false`, proving inspection does not activate
pending media. The fixture includes nonzero 128-byte data/checksum vectors and
a WRITE WITH VERIFY readback-failure case with its accepted-write postimage.

Only integral 128-byte ATR payloads and classic 256-byte ATRs are accepted.
For 256-byte media, sectors 1--3 transfer 128 bytes and later sectors transfer
256 bytes; sector 4 starts at offset 384 after the ATR header.  Ordinary
512-byte ATRs, malformed small-256, and nonintegral 128-byte descriptions are
rejected. Config mode
selects only `boot.config_uri` for D1; normal mode uses restored D1--D8 slots.

Excluded: DiskDevice/FujiBus, LegacyTransport, SLIP/padded legacy traffic,
`0x71` and `0x7f` traffic, formatting, PERCOM, high-speed SIO, non-ATR media,
emulator integration, and physical timing/electrical claims.

Run the stdlib-only validator with:

```sh
python3 -m unittest discover -s integration-tests/atari-sio/tests -v
```
