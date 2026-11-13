# Commodore 64 on IEC with FujiNet NIO

Status: IN PROGRESS

A C64 boots from FujiNet NIO, runs the config app, and mounts images from TNFS, on the
same terms as the Atari: no legacy transport, a reserved NIO packet device, and a
standard drive frontend over `DiskService`. Implementation notes are in
`repos/fujinet-nio/docs/iec/`. The behaviour research is in
`_bmad-output/planning-artifacts/research/technical-c64-iec-bus-behaviour-2026-11-05/`.

## Clean room

No code from fujinet-firmware's IEC, drive or media layers is used. A separate reader
turned behaviour into the research record above, and the implementation was written from
that and public documents. Its media layer is not named in anything here.

## Done

- [x] Firmware (fujinet-nio #27): `IecBus`, the drive frontend, the NIO packet channel, the
      D64 image type, the CBM volume reader, NetIEC, the `c64-netiec` presets
- [x] Firmware's TNFS client accepts session 0, the first one `tnfsd` hands out (#27)
- [x] Loose `.prg` files mount as a read-only one-file disk (`ImageType::Prg`), the Atari's
      XEX path being the model (#27)
- [x] `fujinet-nio-lib` (#8): the `c64` target and its host wire test
- [x] Real D64s and a real PRG over TNFS UDP, from `tnfs://fujinet.diller.org/`: each loaded
      into the C64 byte for byte, with no timeouts in the firmware log

## In review

- [ ] `nio-config` (#6): the `c64` target, sharing the Atari app and core, and F5 to run the
      demo
- [ ] `nio-core-apps` (#1): the C64 boot disk, and the FujiNet demo on it, which reads the date
      and time over the NIO channel. The sources are in `apps/platform/c64/fujidemo/`
- [ ] Workspace (#7): acceptance in VICE (`integration-tests/c64-iec/`), and the `c64` build
      tasks

## Next

- [ ] An open file channel keeps reading its slot after the image is remounted:
      [iec-drive-remount-open-channels.md](iec-drive-remount-open-channels.md)
- [ ] Line-level IEC ingress and ESP32 board profiles for the IEC Nugget and LOLIN D32. The
      emulator path says nothing about bus timing: this needs real hardware. Section D of the
      research is the start. Both boards are classic ESP32s with quad PSRAM, and their
      fujinet-firmware releases use a 16 MB layout. The sources already compile and link for
      that chip (a 2.17 MB image, so it needs an app slot over 2 MB), but nothing drives the
      lines there yet
- [ ] Writing: SAVE, data channel writes and `S`, `N`, `V`, `R`, `C`
- [ ] Other media: D71, D81
- [ ] Config app: name drives 8-15 rather than D1-D8, and start from RUN without typing
- [ ] Core CLI utilities (`fls`, `fmount`, ...) for the C64
- [ ] Decide on a diagnostics provider for the IEC devices
- [ ] Acceptance over TNFS UDP. Docker Desktop's published UDP ports do not reach the
      daemon on macOS, so the acceptance test uses TNFS over TCP
- [ ] Reads from `tnfs://fujinet.online/`. Browsing and mounting work from a C64, but reading
      `CBM/games/jumpman.d64` failed: the firmware's parallel read-ahead (8 LSEEKs at once)
      timed out while the replies were still arriving, tagged with an earlier batch's sequence
      numbers. The same read-ahead is clean against `fujinet.diller.org`, so it may be that
      server or its latency. It is in the common TNFS client, not IEC

## Acceptance

```sh
scripts/build.sh c64
python3 integration-tests/c64-iec/run_boot_acceptance.py
```

Needs Docker for `tnfsd`, and the `vice-fn` build of VICE from the opt-in
`external/vice-fn` submodule (`scripts/build-vice-fn.sh`): see
`integration-tests/c64-iec/README.md`. Evidence, with a picture of each screen, goes to
`test-evidence/c64-iec/`.
