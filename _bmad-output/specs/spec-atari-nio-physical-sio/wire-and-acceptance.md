# Atari NIO wire and acceptance contract

## SIO ingress planes

```text
Atari OS boot / mounted applications
  -> standard SIO D1:–D8: disk frontend
  -> internal IORequest / IOResponse
  -> DiskDevice -> DiskService -> ATR slots

Atari NIO application
  -> public fujinet-nio-lib API
  -> packet-native FujiBus
  -> SIO device 0x7F: W / P / R
  -> internal FujiBus transport -> FujinetCore -> existing services
```

The planes share physical SIO, board configuration, disk-slot state, and core DiskDevice. They do not share framing or dispatch. The disk frontend is a narrowly scoped standard Atari disk adapter, not `LegacyTransport` and not a legacy FujiNet compatibility path.

## NIO application-channel contract

| Concern | Contract |
| --- | --- |
| Address | SIO device `0x7F` is permanently the NIO application-channel address. It is unrelated to FujiBus `WireDeviceId` values such as Clock, Disk, Network, and File. |
| Request | `W` has matching AUX and DCB byte counts and carries exactly one packet-native FujiBus request plus its standard SIO checksum. Valid receipt returns ACK then COMPLETE. |
| Poll | `P` returns ACK, COMPLETE, then exactly three bytes: state (`idle`, `pending`, `ready`, or `fault`) and little-endian queued-response size. |
| Response | After `P=ready`, `R` has matching AUX and DCB byte counts equal to the reported size and returns exactly one packet-native FujiBus response plus the SIO checksum. No zero padding is used. |
| Capacity | One shared named compile-time constant initially limits a `W` or `R` payload to 512 bytes. Builds may tune it together for measured compatibility/performance. A larger packet fails with the defined NIO message-too-large transport error; no implicit segmentation exists. |
| Errors | `NAK` means malformed/rejected SIO transaction only: bad command/checksum, invalid length, bad state, or another transport rejection. It never means pending. Service failures remain encoded in the FujiBus response. |
| Recovery | Only one NIO request may be outstanding. Abort, timeout, malformed `W`, or terminal `R` failure clears pending request and queued response before another `W`; no response may leak into a later request. Client retry delay and total deadline are configurable policy, not wire constants. |

### PROC readiness notification

The default backend polls `P`. An application that owns or chains the Atari PROC (`VPRCED`) handler may opt in to notification:

- FujiNet sends a bounded, rate-limited open-drain PROC pulse when the NIO response queue transitions to ready, including a ready error response.
- The application handler may call the library's ISR-safe constant-time notification hook, which only latches a flag.
- Outside IRQ context, the client issues `P` before `R`; PROC conveys neither source, request ID, response length, nor reason on the shared SIO bus.
- False or missed pulses are harmless because the response remains queued and the polling path is complete.

## Disk bootstrap and configured drives

- Standard Atari disk device IDs `D1:`–`D8:` select the corresponding runtime DiskService slots.
- The frontend handles only the standard Atari disk commands and sector/status semantics required for ATR-backed boot and mounted-media operation. It translates them into internal DiskDevice IORequests and maps the resulting IOResponses to standard SIO replies.
- In config mode, `boot.config_uri` identifies the flashed configuration ATR prepared for the active boot slot (`D1:`). In normal mode, restored user URI-backed slots determine which disk responds.
- The configuration ATR supplies the cc65 XEX configuration and acceptance programs. It is the supported bootstrap medium; loading must not require legacy FujiNet services.

## Physical profile and measurements

- Production profile: `FN_BUILD_ATARI_FUJIBUS_SIO` on official Atari FujiNet v1 16 MB hardware.
- Standard-speed SIO is 19,200 baud. CMD gates command-frame recognition; UART data input/output carry command replies and data frames.
- Board-driven DATA OUT and PROC are open-drain and released while idle. INT, MTR, CKI, and CKO have no NIO protocol role and remain electrically benign.
- The physical fixture records board revision, Atari model, cable/peripheral topology, firmware/client commits, logic levels, idle release/no contention, command-to-ACK/COMPLETE timing, data/checksum timing, abort/reset recovery, and PROC opt-in versus polling-only behavior.

## Acceptance matrix

| Level | Required evidence | Does not prove |
| --- | --- | --- |
| Literal vectors and host tests | `0x7F` `W`/`P`/`R`, exact lengths, malformed input, recovery, and D1–D8 sector/status mappings | Atari client ABI or electrical behavior |
| Atari library build/tests | Public API, polling fallback, opt-in ISR hook, and bounded buffers | Firmware channel correctness |
| AltirraSDL | NIO command-level integration, disk boot, and guest XEX | ESP32 signals or physical timing |
| NetSIO | SIO envelope, scheduling, and regression parity | Physical SIO electronics |
| ESP32 profile build | Board configuration compiles | Real-bus interoperability |
| Real Atari + official v1 | Config ATR boot as D1, URI drive mapping, physical NIO, and recovery | Broad legacy FujiNet compatibility |

## Required guest acceptance

The cc65 XEX loaded from the configuration ATR must use the public library API and demonstrate:

1. Clock request/response.
2. Network open/write/read/close, including delayed readiness through `P` and, where available, the application-owned PROC path.
3. File persistent write/read.
4. Disk read/write against a mounted supported image.
5. Rejected/malformed or aborted NIO transaction recovery followed by a successful exchange.

The operator procedure documents flash, boot-mode choice, ATR/URI mapping, launch, diagnostics, and the physical evidence record.
