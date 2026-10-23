# Atari SIO v1 conformance fixtures

This directory is the canonical, implementation-independent contract for the
standard Atari disk surface and native NIO application channel. It describes
virtual protocol evidence only: it does **not** assert SIO electrical
characteristics, timing, UART behaviour, or physical-drive compatibility.

`fixtures/disk_v1.json` is the literal disk-v1 matrix.  Its stable scenario
IDs are the identifiers an adapter reports; it must not be regenerated from a
production framer. `disk_v1.manifest.json` projects those scenarios as ordered
SIO phases for virtual consumers.

`fixtures/nio_v1.json` is the literal native packet-NIO v1 matrix for SIO
address `0x7f`. It fixes the client-visible `Q`/`W`/`P`/`R` command, AUX, DCB
count, control reply, state, capacity, rejection, timeout, recovery, and reset
vectors. It is independent of the library assembly and firmware endpoint.
`Q` and `P` counts are client/fixture expectations; physical SIO exposes their
AUX and serial bytes, not the Atari DCB count. The matrix uses symbolic control
bytes (`A`, `C`, `N`, and `E`) and literal packet/state byte strings, rather
than claiming physical timing or device implementation details.

`fixtures/nio_v1.virtual.manifest.json` is the reference-only virtual
projection. It contains stable fixture IDs, ordered operations, and required
observation categories for each native family, plus the existing D1 page-6
boot references. It does not repeat wire bytes, generate responses, or permit
legacy `$71`, SLIP, padded-read, or stream evidence. Client-only malformed-peer
or timeout observations remain explicit instead of being manufactured by the
synchronous production endpoint.

`virtual_projection.py` supplies the shared machine-readable result schema for
`netsio` and `altirra-embedded`. A result always names one adapter and one
scenario, records observed SIO commands/responses and evidence paths, and is
`incomplete` if required evidence is absent. The boot gate can write its D1
result through that schema without becoming a second emulator runner:

```sh
python3 integration-tests/atari-sio/run_boot_acceptance.py \
  --trace-serial --capture-dcb --explicit-cold-reset \
  --write-projection-results
```

The focused `native-core-dispatch` NetSIO execution uses the same Altirra,
hub, bridge, reset, and evidence lifecycle. Its small Atari XEX invokes real
SIOV Q/W/P/R calls; its process-side route is a real `FujinetCore` device only
so the independently literal FujiBus request has a deterministic response.
It does not emulate an SIO peer or call the frontend directly. The runner
compares captured production UDP traffic, including every command/control/data
checksum, against `nio_v1.json`, records the stable scenario result, and proves
a deliberately corrupted observed checksum is rejected.

```sh
source "$NIO_WORKSPACE/scripts/env.sh"
cmake --build repos/fujinet-nio/build/atari-fujibus-netsio-debug \
  --target fujinet-nio-atari-netsio-projection
make -C integration-tests/atari-sio/native-projection-app all
python3 integration-tests/atari-sio/run_boot_acceptance.py \
  --native-core-dispatch --timeout 20
```

The matching embedded projection uses the same XEX, inspection, screenshot,
and POKEY evidence lifecycle, but removes the NetSIO custom device and starts
AltirraSDL's `fujinetnio` device directly.  Its explicit
`projectionfixture=true` setting only registers the deterministic downstream
`VirtualDevice` used by the literal core-dispatch packet; native Q/W/P/R still
travels through the production `AtariSioNioFrontend` and the embedded
`FujinetCore::routingManager()`.  The result is independently recorded as
`altirra-embedded` and compares every captured POKEY command, data, control,
payload, and checksum byte with `nio_v1.json`.

```sh
source "$NIO_WORKSPACE/scripts/env.sh"
cmake --build repos/AltirraSDL/build/linux-debug \
  --target AltirraSDL altirra-fujinet-nio-sio-test
make -C integration-tests/atari-sio/native-projection-app all
python3 integration-tests/atari-sio/run_boot_acceptance.py \
  --native-core-dispatch-altirra-embedded --timeout 30
```

The embedded wrong-R projection uses the same production device and POKEY
capture path. It records every physical Atari OS retry as a literal rejected
R/NAK exchange, then reports their count as one logical
`native-wrong-r-retention` operation before proving the unchanged READY reply,
correct terminal R, and IDLE poll.

```sh
python3 integration-tests/atari-sio/run_boot_acceptance.py \
  --native-wrong-r-retention-altirra-embedded --timeout 30
```

The embedded reset projection pauses the same guest after its first READY
poll, invokes the installed `fujinetnio` device's actual `ColdReset()` through
the Altirra control bridge, then releases the guest.  It requires recorded
lifecycle evidence as well as the post-reset P(IDLE), distinct W2 dispatch,
terminal R, and final P(IDLE) POKEY trace.

```sh
python3 integration-tests/atari-sio/run_boot_acceptance.py \
  --native-reset-to-idle-altirra-embedded --timeout 30
```

The embedded interrupted-R projection enables a projection-only Altirra SIO
scheduler fault after the production frontend has accepted and consumed the
first terminal R. It sends the literal R payload with its checksum deliberately
corrupted, so the guest records a failed SIOV call and its physical retries
receive NAK from the now-consumed endpoint. The captured POKEY trace must then
show P(IDLE), a distinct second core dispatch, and the exact second response.

```sh
python3 integration-tests/atari-sio/run_boot_acceptance.py \
  --native-interrupted-r-recovery-altirra-embedded --timeout 30
```

The embedded capacity projection sends the independent 511- and 512-byte raw
FujiBus packets through the same production endpoint, verifies every byte of
the patterned 512-byte response and its SIO checksum, and records the actual
Atari OS retries for the pre-data 513-byte W NAK.  It also requires the
bounded InternalError response for an oversized core reply; its POKEY capture
comparison rejects missing, extra, duplicate, or reordered bytes.

```sh
python3 integration-tests/atari-sio/run_boot_acceptance.py \
  --native-capacity-bounds-altirra-embedded --timeout 45
```

The config boot READ vectors are pinned source-image goldens, unlike the
synthetic framing vectors elsewhere in the matrix.  They come from
`repos/nio-core-apps/build/atari/disk/boot/autorun.atr`, whose SHA-256 is
recorded in `source_image`.  To reproduce them without an adapter, verify the
hash and extract the ATR payload slices after its 16-byte header: sectors 1--3
are 128 bytes at offsets 16, 144, and 272; sector 4 is 256 bytes at offset 400.

```sh
sha256sum repos/nio-core-apps/build/atari/disk/boot/autorun.atr
od -An -v -tx1 -j 16 -N 128 repos/nio-core-apps/build/atari/disk/boot/autorun.atr
od -An -v -tx1 -j 400 -N 256 repos/nio-core-apps/build/atari/disk/boot/autorun.atr
```

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

Excluded: DiskDevice/FujiBus service implementation, LegacyTransport,
SLIP/padded legacy traffic, `0x71` traffic, formatting, PERCOM, high-speed
SIO, non-ATR media, emulator integration, and physical timing/electrical
claims.

Run the stdlib-only validator with:

```sh
python3 -m unittest discover -s integration-tests/atari-sio/tests -v
```
