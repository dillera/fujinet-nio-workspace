# Commodore IEC bus and drive: behavioural research

Input to the C64 IEC work in fujinet-nio (`backlog/c64-iec-nio.md`), kept as the record
of what that work was built from. It describes observable behaviour only: on the bus,
on the emulator bridge and in the disk format. The implementation was written from this
and public documentation, and contains no code from the firmware it compares against.
"Firmware" below means fujinet-firmware's IEC support, read to learn the behaviour; where
it differs from a stock drive, the implementation follows stock. Section D, the line-level
protocol, is the starting point for a hardware ingress.


## How to read this

| Tag | Meaning |
|---|---|
| [KERNAL-REQUIRED] | A stock C64 KERNAL or the bus definition depends on it. Copy it. |
| [EMULATOR-BRIDGE] | Specific to the path from VICE through the OpenCBM-style bridge to TCP. |
| [FIRMWARE-CHOICE] | The existing firmware does this. A clean implementation may differ. |
| [UNVERIFIED] | Not confirmed. Check before relying on it. |

`(public: ...)` marks a fact available from public Commodore material. Prefer these over firmware behaviour. "Public ROM" means the stock C64 KERNAL 901227-03, BASIC 901226-01 and 1541 DOS 2.6 (325302-01 + 901229-05), which were disassembled to check these facts. Addresses are quoted so they can be confirmed in any public disassembly. Sources are listed at the end.

Terms:

- **stock**: a real C64 with a real 1541.
- **firmware**: the existing firmware this spec was derived from.
- **clean device**: the implementation you are writing.
- **d**: device number. **c**: channel. All examples use d = 8.
- **ST**: the KERNAL status byte at `$90`. Bit 0 write timeout, bit 1 read timeout, bit 4 verify mismatch, bit 6 EOI, bit 7 device not present (public: C64 Programmer's Reference Guide).
- **transaction path**: decoded ATN, WRITE, READ and RESET requests. **real bus**: the CLK, DATA and ATN lines.

---

## A. Bus transaction sequences

### A.1 Command bytes (public: bus documentation)

| Byte | Meaning |
|---|---|
| `$20+d` | LISTEN (d = 0 to 30). `$28` for device 8. |
| `$3F` | UNLISTEN |
| `$40+d` | TALK. `$48` for device 8. |
| `$5F` | UNTALK |
| `$60+c` | SECOND: select channel c for the data that follows |
| `$E0+c` | CLOSE channel c, sent after LISTEN |
| `$F0+c` | OPEN channel c, sent after LISTEN. The name follows as data. |

The channel is the low nibble. A stock drive ignores bit 4 of the secondary (public).

On the transaction path, a primary and its secondary arrive together in one ATN request. UNLISTEN and UNTALK arrive alone. [EMULATOR-BRIDGE]

### A.2 BASIC statements that cause no bus traffic (public ROM)

A device cannot see any of these. [KERNAL-REQUIRED]

- `OPEN 15,8,15` and any OPEN with an empty name (`$F3DB`).
- `OPEN 1,8` with no secondary (`$F3D7`). `CLOSE` of such a file also sends nothing (`$F644`). Later use sends LISTEN or TALK with no secondary, and the device should treat that as channel 0.
- `LOAD"",8` and `SAVE"",8`: the KERNAL raises `?MISSING FILE NAME` (`$F4BC`, `$F602`).
- `CLR`, `RUN`, `NEW`: the C64 forgets its open files with no CLOSE sent (`$A660`). Channels stay open on the device until re-opened, closed or reset.

### A.3 `LOAD"NAME",8`

| # | Request | The device must |
|---|---|---|
| 1 | ATN `$28 $F0` | Acknowledge. Start a new name for channel 0. Do not touch files yet. |
| 2 | Data `N A M E` | Accept every byte. Bridge: one WRITE per byte, no EOI. Real bus: normal bytes, the last with EOI. Over-long names are truncated silently, never refused. |
| 3 | ATN `$3F` | Acknowledge. The name is now complete: parse it, open the file, set the status. The result must be in effect before the next request is answered. |
| 4 | ATN `$48 $60` | Acknowledge, even if step 3 failed. Channel 0 is now the talker. Real bus: complete the role reversal (section D). |
| 5 | READ | First byte: load address low. |
| 6 | READ | Second byte: load address high. |
| 7+ | READ | Remaining bytes. The last one carries EOI. |
| n+1 | ATN `$5F` | Acknowledge. Stop talking. The file stays open and keeps its position. |
| n+2 | ATN `$28 $E0` | Acknowledge. Close channel 0. |
| n+3 | ATN `$3F` | Acknowledge. Arrives twice on the bridge (see E.3). |

What the KERNAL does with the bytes (public ROM `$F4D5` to `$F52E`). All of this is [KERNAL-REQUIRED]:

- It reads byte 1 and tests ST bit 1. If set, it raises `?FILE NOT FOUND`.
- It reads byte 2 with no test at all.
- It then loops: clear ST bit 1, test RUN/STOP, read a byte, go round again without storing if ST bit 1 is set, store, stop if ST bit 6 is set.

Consequences:

- EOI must arrive with the last byte. If the stream instead ends in an empty read, ST bit 1 is set, the byte is retried, and LOAD spins until RUN/STOP.
- The KERNAL always asks for a third byte, even if byte 1 or 2 carried EOI. A file of 1 or 2 bytes therefore spins until RUN/STOP. A stock drive behaves the same way, so the minimum loadable file is 3 bytes.
- When the KERNAL reports success, BASIC raises `?LOAD ERROR` if ST has any bit other than bit 6 set (public ROM `$E195`). A device that refused a name byte can cause this even when the data then arrives correctly.
- RUN/STOP during the loop sends `$28 $E0 $3F` with no UNTALK first (public ROM `$F4FE`, `$F633`). LISTEN must end talking.
- `VERIFY` is identical on the bus. The C64 does the comparing (public ROM).

### A.4 `LOAD"$",8`

Same requests as A.3, with the name byte `$24`. The stream is the listing in section C. Status is 00 at step 3. With no media, follow A.9 with status 74.

### A.5 `LOAD"*",8,1`

Same requests as A.3, with the name byte `$2A`. The `,1` is invisible to the device: the KERNAL overwrites the secondary with `$60` and only uses the original value to choose between the file's load address and the start of BASIC (public ROM `$F4BF`, `$F4C4`, `$F4E5`). [KERNAL-REQUIRED]

### A.6 `SAVE"NAME",8`

| # | Request | The device must |
|---|---|---|
| 1 | ATN `$28 $F1` | Acknowledge. Start a new name for channel 1. |
| 2 | Data: name bytes | Accept every byte, as in A.3. |
| 3 | ATN `$3F` | Acknowledge. Open for write. If the file exists and there is no `@`: status 63, mark the channel failed. If the media is read-only: status 26, mark failed. |
| 4 | ATN `$28 $61` | Acknowledge, even if step 3 failed. |
| 5 | Data: load address low, high, then memory | Open: accept each byte. Failed: accept none (real bus: release DATA after ATN ends). The first two bytes are ordinary file data. |
| 6 | ATN `$3F` | Acknowledge. The file is still open. |
| 7 | ATN `$28 $E1` | Acknowledge. Close and commit. Later errors can only be reported through the status channel. |
| 8 | ATN `$3F` | Acknowledge. Arrives twice on the bridge. |

- The KERNAL does not test ST during the data loop, and BASIC prints `READY.` after a refused SAVE. Only the status channel shows the failure (public ROM `$F624`, `$E15F`). [KERNAL-REQUIRED]
- RUN/STOP sends `$28 $E1 $3F` with no UNLISTEN first (public ROM `$F633`). The device must close whatever it has. [KERNAL-REQUIRED]
- A file's end is the CLOSE or UNLISTEN, never EOI. [EMULATOR-BRIDGE]

### A.7 Command channel

| Statement | Requests | The device must |
|---|---|---|
| `OPEN 15,8,15,"cmd"` | ATN `$28 $FF`, data `c m d`, ATN `$3F` | `$FF` is `$6F` ORed with `$F0`. Clear the command buffer at ATN. Accept all bytes. At UNLISTEN, if at least one byte arrived, drop one trailing CR, run the command, set the status. It must finish before the next request is answered. |
| `PRINT#15,"cmd"` | ATN `$28 $6F`, data `c m d $0D`, ATN `$3F` | Same as above. BASIC appends CR unless the statement ends in `;`. `OPEN` does not append one. |
| `INPUT#15,A,B$,C,D` | ATN `$48 $6F`, READ until the CR, ATN `$5F` | Deliver the status text. The CR carries EOI (public). |
| `GET#15,A$` | ATN `$48 $6F`, one READ, ATN `$5F`, per statement | Keep the read position across UNTALK and TALK. |
| `CLOSE 15` | ATN `$28 $EF`, ATN `$3F` (twice on the bridge) | Stock: closes every open channel (public ROM `$DAD4`, `$DAEC`). Firmware: no effect. [FIRMWARE-CHOICE] Prefer stock. |

Commands end at UNLISTEN (public: Commodore DOS runs them there, not at EOI). [KERNAL-REQUIRED]

### A.8 Data channel

| Statement | Requests | Notes |
|---|---|---|
| `OPEN 2,8,2,"NAME,S,R"` | ATN `$28 $F2`, name with suffix, ATN `$3F` | A failed open is not reported to the KERNAL. It is only visible in the status. |
| `INPUT#2,A$` | ATN `$48 $62`, READ until CR or EOI, ATN `$5F` | If data remains, the next statement resumes at the same position. |
| `GET#2,A$` | ATN `$48 $62`, one READ, ATN `$5F`, per statement | Read-ahead must survive UNTALK, or EOI will be wrong. |
| `PRINT#2,"X"` | ATN `$28 $62`, data with CR, ATN `$3F` | Failed or unopened channel: accept nothing. |
| `CLOSE 2` | ATN `$28 $E2`, ATN `$3F` (twice on the bridge) | |

- Once ST is non-zero, the KERNAL stops reading: further character reads return CR with no bus traffic (public ROM `$F1AD`). A stock C64 therefore never reads past EOI within a statement. [KERNAL-REQUIRED]
- Each new CHKIN or CHKOUT clears ST first (public ROM `$F30F`). The next `INPUT#` or `GET#` starts clean. [KERNAL-REQUIRED]
- Every `GET#`, `INPUT#` and `PRINT#` is its own TALK or LISTEN session (public).

### A.9 When the file does not exist

The goal is `?FILE NOT FOUND` on the C64 and status 62 on channel 15.

1. Treat the OPEN normally. Acknowledge the ATN, accept every name byte, acknowledge UNLISTEN.
2. At UNLISTEN: set status 62 and mark the channel failed.
3. Acknowledge the TALK. Real bus: complete the role reversal.
4. Answer the first READ with zero data bytes and the EOI flag. Real bus: release CLK as if about to send, leave DATA released, and do nothing more. The C64 times out twice, the first reading as EOI and the second as a read timeout, ending with ST = `$42` (public: "empty stream").
5. The KERNAL raises the error. **It sends no UNTALK and no CLOSE** (public ROM `$F4DE` to `$F530`, and visible in firmware logs: the channel stayed open until the next reset). The next ATN must reset talker state, and the next OPEN on that channel replaces the failed state. [KERNAL-REQUIRED]

| If the device does this | The C64 sees |
|---|---|
| Zero bytes and EOI on the first READ | `?FILE NOT FOUND`. Correct. |
| Holds the READ reply forever (bridge) | Machine frozen for the bridge timeout (30 s by default), then `?FILE NOT FOUND`. [EMULATOR-BRIDGE] |
| Returns not-present to the ATN (bridge) | The emulator ignores it. WRITEs are refused, so ST gets `$83`, and LOAD still ends in `?FILE NOT FOUND`. [EMULATOR-BRIDGE] |
| Refuses name bytes | Bridge: ST `$83`, which includes bit 1, so LOAD ends in `?FILE NOT FOUND` whatever follows. Real bus: ST bit 7, and if data then arrives, `?LOAD ERROR`. |
| Real bus: no DATA pull within 1 ms of ATN | `?DEVICE NOT PRESENT` from the check after the OPEN secondary (public ROM `$F3ED`). [KERNAL-REQUIRED] |
| Real bus: acknowledges TALK, skips the role reversal | Permanent hang. The KERNAL waits for CLK low with no timeout (public ROM `$EDD6`). [KERNAL-REQUIRED] |
| Empty read after 2 or more bytes were delivered | LOAD spins until RUN/STOP (A.3). [KERNAL-REQUIRED] |

### A.10 EOI at the end of a read

- Transaction path: set the EOI flag in the reply carrying the last data byte. [KERNAL-REQUIRED]
- The device must know a byte is the last before sending it, so hold at least one byte of read-ahead per channel. Firmware holds up to two. [FIRMWARE-CHOICE]
- Read-ahead belongs to the channel and persists across UNTALK and TALK.
- Status channel: EOI on the final CR (public). Listing: EOI on the final `$00`.
- A byte returned in a READ reply is consumed, even if the client does nothing with it. [EMULATOR-BRIDGE]
- Real bus: EOI is signalled before the last byte (section D).

### A.11 A read on a channel with no data

Applies to a channel never opened, a failed open, or a re-read after EOF. Answer at once with zero bytes and the EOI flag. Never block.

| Case | C64 result |
|---|---|
| First byte of LOAD | `?FILE NOT FOUND` |
| Mid-LOAD | Spins until RUN/STOP. Must not happen. |
| `GET#` | ST = `$42`. The returned byte is junk (uninitialised on the bridge [EMULATOR-BRIDGE], stale on a real bus). |
| `INPUT#` | Receives that one junk byte, then the KERNAL's substituted CR ends the value (public ROM `$F1AD`). |

- Status: firmware sets 61 FILE NOT OPEN for a never-opened channel, only if the status is currently 00. EOF does not change the status. [FIRMWARE-CHOICE]
- After a zero-byte reply, firmware answers further READs in that session with zero bytes without consulting the channel again, until the next ATN. [FIRMWARE-CHOICE]
- WRITE when not listening: accept 0. READ when not talking: zero bytes and EOI. [FIRMWARE-CHOICE]

### A.12 Not present versus acknowledge

| ATN primary | Reply | Notes |
|---|---|---|
| LISTEN or TALK to a served, active device number | Acknowledge | Always, whatever the media, channel or file state. Errors surface later. |
| LISTEN or TALK to any other number | Not present | A TALK to another number also ends our talking (public: every device sees it). |
| UNLISTEN, UNTALK | Acknowledge | Always, even when idle. |
| Anything else, or an empty request | Not present | [FIRMWARE-CHOICE] |

- A LISTEN or TALK with no secondary means channel 0, data. [FIRMWARE-CHOICE]
- Firmware drives answer even with nothing mounted. The exception is a drive whose host was unmounted: it is marked inactive and then answers not present. [FIRMWARE-CHOICE]
- Real bus: there is no per-device reply. Presence means someone pulled DATA within 1 ms of ATN. An absent number is detected on the next byte, after the other devices have released the bus (public ROM 1541 `$E8FD`, KERNAL `$ED47`).

### A.13 Sequences a device must tolerate

All [KERNAL-REQUIRED] unless noted.

- TALK with no later UNTALK or CLOSE (A.9).
- LISTEN while talking, TALK while listening. Each ends the other.
- UNLISTEN or UNTALK when idle. Two UNLISTENs in a row. [EMULATOR-BRIDGE]
- OPEN on a channel already open: close the old file first. `RUN` makes this routine.
- CLOSE on a channel that is not open.
- RESET at any time.
- Multi-byte WRITE and READ as well as single-byte. VICE sends single bytes, other clients may not. [EMULATOR-BRIDGE]

---

## B. Drive semantics

### B.1 Channels (public: Commodore DOS; 1541 ROM `$D87B`)

| Channel | Stock | Firmware |
|---|---|---|
| 0 | LOAD. Always read. Default type PRG. | Read by default. A `,W` could make it write. [FIRMWARE-CHOICE] |
| 1 | SAVE. Always write. Default type PRG. | Write by default. A `,R` could make it read. [FIRMWARE-CHOICE] |
| 2 to 14 | Data. Read by default. A suffix selects write, append or modify. | Read by default. Only R and W are recognised. |
| 15 | Command and status. Never holds a file. | Same. |

Channels are independent. Opening one does not disturb another. Firmware allows channels 0 to 14 to be open at once and never raises 70 NO CHANNEL. A stock drive has a limited buffer pool, so programs can see 70 there. [FIRMWARE-CHOICE]

### B.2 File names

Grammar (public): `[@][drive:]name[,type][,mode]`.

| Rule | Stock (public ROM) | Firmware |
|---|---|---|
| Drive prefix | Everything up to `:` selects the drive. `0:NAME` and `:NAME` are the same. | Strips a literal `0:`. A bare `:` strips too, but also sets the replace flag, which is a quirk. Any other `:` is treated as a path to another filesystem. |
| `@` | Only meaningful as the first byte of the name, on a write. Replaces an existing file (`$D8E1`). | Same, stripped before the drive prefix. |
| Comma arguments | Up to two, in any order. Only the first letter of each counts, so `,S,W`, `,SEQ,WRITE` and `,W` all work (`$DA09`). | Only the third comma-separated field is read, and only an exact `R` or `W`. So `NAME,W` stays in read mode, and `A` and `M` are ignored. Type letters are ignored. |
| Mode letters | R read, W write, A append, M recovery read | R, W |
| Type letters | S, P, U, L, D | none |
| `$A0` | Ends a name on disk. Illegal in a name. | Cuts the name at the first `$A0`. |
| Other illegal bytes | `,`, `:`, `=`, CR (public) | not checked |
| Empty after parsing | | `33,SYNTAX ERROR,00,00` |
| A name beginning with the letters `CD` | Ordinary name | Those two letters are dropped. Do not copy this. |

Type and existence checks (public ROM `$D8C6` to `$D965`):

- Read of a missing file: 62.
- Read where the requested or default type differs from the file's type: 64. So `LOAD"SEQFILE",8` gives status 64 and `?FILE NOT FOUND` on the C64.
- Channels 2 to 14 with no type given accept any type on read, and create SEQ on write.
- Write to an existing file with no `@`: 63.
- Firmware performs no type check, so any type loads. [FIRMWARE-CHOICE]

### B.3 Wildcards (public ROM `$C50A` to `$C535`)

Compare the pattern to the 16-byte directory name, position by position:

- `*` matches the rest. Anything after it in the pattern is ignored.
- `?` matches any byte except `$A0`.
- Any other pattern byte must equal the name byte exactly.
- When the pattern ends, the name must also end there: position 16 reached, or the next name byte is `$A0`.
- The first matching entry in directory order wins. Scratched entries (type byte `$00`) never match.

Firmware differs, and the differences are not worth copying: a pattern with a wildcard but no `*` also matches longer names, a `?` past the end of the name matches, and scratched entries can match. [FIRMWARE-CHOICE]

### B.4 `$`

- `$` as the first byte on channel 0 produces the BASIC listing (public ROM `$D7F3`, `$DA55`).
- Variants (public): `$0`, `$:PAT*`, `$0:PAT*`, and type filters such as `$:*=P`.
- `$` on channels 2 to 14 on a stock drive returns track 18 as a raw file starting at 18/0, not a listing (public ROM `$D7FF`).
- Firmware treats any name starting with `$` as a listing of the current location on any channel, and ignores the rest of the name. [FIRMWARE-CHOICE] Prefer stock if programs need it.

### B.5 What `LOAD"*"` resolves to

- Stock (public ROM `$D7C7`, `$D81C`, `$D9FA`): `*` as the first byte on channel 0 reloads the last file opened on channel 0 or 1 since power-on. If there has been none, it finds the first PRG. The memory of the last file survives `I` and disk changes. `0:*` is an ordinary pattern: the first file of any type, with a type check after.
- Firmware: the first entry whose low three type bits are non-zero, in directory order, any type. There is no last-file memory. [FIRMWARE-CHOICE]
- Recommended: first PRG after mount or reset. Last-file memory is optional, and should be cleared on mount to avoid loading from the wrong disk.

### B.6 PETSCII and case

- Bus bytes are raw PETSCII. There is no case folding. A stock C64 in its default mode sends `$41` to `$5A` for unshifted letters, and D64 names normally store the same bytes. Compare bytes directly. (public)
- Bytes from `$80` up are data and must survive. Treat them as unsigned, including in command comparisons. See F.
- Directory names from an image go to the C64 unchanged. Do not translate them.
- For host filesystems, firmware maps `$41` to `$5A` to ASCII a to z, and both `$61` to `$7A` and `$C1` to `$DA` to ASCII A to Z. The reverse maps ASCII a to z to `$41` to `$5A`, and A to Z to `$C1` to `$DA`. NUL bytes are dropped. [FIRMWARE-CHOICE]

### B.7 Status message format

Shape: `NN,<text>,TT,SS` then CR (`$0D`). There is no LF. NN, TT and SS are two decimal digits. TT and SS are `00` unless the error has a location. CR is the last byte and carries EOI (public).

Text below is decoded from the public 1541 ROM message table at `$E4FC`. The ROM puts a space before any message that starts with a shared word, which is why some have a leading space and others do not. `INPUT#15,A,B$,C,D` strips it, so most programs cannot tell. A clean device should use the stock text.

| Code | Stock message | Firmware text |
|---|---|---|
| 00 | `00, OK,00,00` | Same |
| 01 | `01, FILES SCRATCHED,NN,00` (TT = number of files) | `01,FILES SCRATCHED,NN,00` |
| 20 to 24, 27 | `23,READ ERROR,18,00` (with location) | Not produced |
| 25, 28 | `25, WRITE ERROR,TT,SS` | `25,WRITE ERROR,00,00` |
| 26 | `26, WRITE PROTECT ON,TT,SS` | `26,WRITE PROTECT,00,00` |
| 30 to 34 | `31,SYNTAX ERROR,00,00` | 31 and 33 only |
| 60 | `60, WRITE FILE OPEN,00,00` | Not produced |
| 61 | `61, FILE NOT OPEN,00,00` | `61,FILE NOT OPEN,00,00` |
| 62 | `62, FILE NOT FOUND,00,00` | `62,FILE NOT FOUND,00,00` |
| 63 | `63, FILE EXISTS,00,00` | `63,FILE EXISTS,00,00` |
| 64 | `64, FILE TYPE MISMATCH,00,00` | `64,FILE TYPE MISMATCH,00,00` |
| 65 | `65,NO BLOCK,TT,SS` | Not produced |
| 66, 67 | `66,ILLEGAL TRACK OR SECTOR,TT,SS` | Not produced |
| 70 | `70,NO CHANNEL,00,00` | Defined, never raised |
| 71 | `71,DIR ERROR,TT,SS` | Not produced |
| 72 | `72, DISK FULL,TT,SS` | Not produced |
| 73 | `73,CBM DOS V2.6 1541,00,00` | `73,<its own product name>,00,00` |
| 74 | `74,DRIVE NOT READY,00,00` | Same text |

A basic read-only drive needs 00, 26, 31, 33, 61, 62, 63, 64, 70, 73, 74, plus 66 for bad chains.

Use of 74 and 62:

- Public meaning of 74: the drive was accessed with no disk inserted, or with its door open (public: Commodore 128 manual error list). The 1541 guide's own wording was not confirmed. [UNVERIFIED]
- Firmware reports 74 when a name is not found inside a mounted image, and 62 only outside one. The C64 still prints `?FILE NOT FOUND`. Do not copy this: use 62 for a missing file and 74 for no media. [FIRMWARE-CHOICE]
- Firmware with no image mounted lists and loads from a flash directory, so it never raises 74 for missing media. [FIRMWARE-CHOICE]

### B.8 Status lifecycle

| Event | Pending status |
|---|---|
| Power-on, RESET, `UI`, `UJ` | 73 (public). The KERNAL does not read it, and the text identifies the device. |
| Successful OPEN or command | 00 |
| Failed OPEN or command | The error code |
| Message read to its end | Resets. The next read gives `00, OK,00,00`. (public) |
| Partial read, then UNTALK | Resumes where it stopped at the next TALK (public ROM). |
| New OPEN or command with an unread message | Replaces it |

- Stock resets when the last character has been fetched (public ROM `$D421`). Firmware resets when it formats the text. The difference is not visible from the bus. [FIRMWARE-CHOICE]
- Reading status does not disturb any channel.
- An empty LISTEN session on channel 15 leaves the status alone. [FIRMWARE-CHOICE]
- Optional, firmware flashes the bus LED while the status is 20 or above, excluding 73. [FIRMWARE-CHOICE]

### B.9 Commands

| Command | Stock (public) | Firmware |
|---|---|---|
| `I`, `I0` | Re-read BAM. Status 00 (ROM `$D005`). | Closes all channels, drops cached image data, status 73. Prefer stock. |
| `UI` | Soft reset. Status 73. | Status 73 only. |
| `UJ` | Hard reset. Status 73. | Same as its `I`. |
| `S:`, `S0:` | Scratch by pattern, `01, FILES SCRATCHED,NN,00`. | Same shape. Inside an image, always a count of 00. |
| `V`, `N`, `C`, `R`, `D`, `P` | Implemented | `31,SYNTAX ERROR,00,00` |
| `M-R` | Returns memory bytes on channel 15. | Status is wiped straight after, so it reads `00, OK,00,00`. |
| `M-W`, `M-E` | Write and run drive code. | Accepted with status 00. No code runs. A fast loader then hangs waiting for it. |
| `B-P`, `U1` | Block access | Partial |
| `CD...`, `MD:`, `RD:` | Not in 1541 DOS. An extension. | Directory and image navigation. [FIRMWARE-CHOICE] |
| Anything else | `31,SYNTAX ERROR,00,00` | Same |

- Maximum command or name length in firmware is 254 bytes. The rest is dropped without refusal. [FIRMWARE-CHOICE]
- A stock drive keeps at most 42 command bytes and does not store the rest (public ROM `$CFDF`).
- Firmware treats `U` followed by `$CA` as a host reset extension. [FIRMWARE-CHOICE]

### B.10 Reset

RESET closes every channel, flushing writes. It clears name and command buffers and read-ahead, and sets status 73. **It does not unmount the image.** A C64 reset followed by `LOAD"*",8` must still work. [FIRMWARE-CHOICE] Stock has no mount concept, but a disk stays in the drive across a reset, so this matches.

---

## C. Directory listing and D64 format

### C.1 Listing bytes for `LOAD"$",8`

All from the public 1541 ROM (`$EC9E` to `$ED59`, `$C6DE` to `$C7F5`), and the shape is what BASIC needs [KERNAL-REQUIRED]. Total length is 32 bytes × (entries + 2).

**Load address, 2 bytes.** Stock `$01 $04` (`$0401`). Firmware `$01 $08`. `LOAD"$",8` ignores it. `LOAD"$",8,1` uses it, and stock therefore overwrites screen memory on a C64. [FIRMWARE-CHOICE] Either works. `$0801` is friendlier.

**Every line:** link low, link high, line number low, line number high, text, `$00`.

- The link is always `$01 $01`. BASIC recomputes it after LOAD, but stops at a line whose link high byte is 0 (public ROM `$A53E`). So it must be non-zero on real lines and zero only at the end. [KERNAL-REQUIRED]
- BASIC scans each line for its `$00` terminator (public ROM `$A544`). Programs reading `$` with `GET#` rely on the same layout. [KERNAL-REQUIRED]

**Header line, 30 bytes:**

```
01 01   00 00   12 22   <name, 16>   22 20   <id, 2>  20  <dos, 2>   00
link    line 0  RVS "                " space
```

- Line number is the drive number, 0.
- `$12` is reverse on.
- Name and the 5 bytes at `$A2` to `$A6` come from 18/0, with `$A0` changed to `$20`.
- Firmware prints the device number where the disk ID belongs (`08 2A`), and always `2A`. Prefer stock. [FIRMWARE-CHOICE]

**Entry line, 32 bytes:** text field of 27 bytes plus `$00`. With L leading spaces, positions within the text field are:

| Position | Content |
|---|---|
| 0 to L-1 | Spaces. L = 3 for fewer than 10 blocks, 2 for fewer than 100, otherwise 1. |
| L | `"` |
| L+1 to L+16 | Name bytes from the directory entry |
| First `$A0` or `"` in the name, or L+17 if the name fills 16 bytes | Closing `"` |
| After the closing quote, up to L+17 | Remaining name bytes with bit 7 cleared, so `$A0` becomes a space |
| L+18 | `*` if bit 7 of the type byte is clear (splat, unclosed file), else space |
| L+19 to L+21 | Type name from the low 4 bits: `DEL`, `SEQ`, `PRG`, `USR`, `REL` |
| L+22 | `<` if bit 6 of the type byte is set (locked), else space |
| Rest to position 26 | Spaces |

The line number is the block count at entry offsets 30 and 31, low byte first. Firmware adds a 0-space case for 1000 blocks or more. [FIRMWARE-CHOICE]

Example, `"HELLO"` of 12 blocks, PRG:

```
01 01 0C 00 20 20 22 48 45 4C 4C 4F 22 20 20 20 20 20 20 20 20 20 20 20 20 50 52 47 20 20 20 00
```

**Footer line, 32 bytes:**

```
01 01  <free low> <free high>  "BLOCKS FREE."  <13 x 20>  00 00 00
```

The first `$00` ends the line. The next two are the end-of-program link. Blocks free comes from the BAM (C.3). The last byte carries EOI.

Example for 652 free: `01 01 8C 02`, then `42 4C 4F 43 4B 53 20 46 52 45 45 2E`, then 13 × `20`, then `00 00 00`.

**An image with no files must still list:** header plus `664 BLOCKS FREE.`

**Firmware listing differences. None are worth copying:** [FIRMWARE-CHOICE]

- Type field is truncated to 3 characters, so a splat file shows `*PR` and the lock mark is lost.
- Text after the first `$A0` in a name is dropped.
- Entries with low three type bits of 0 are hidden. That includes `$80` closed DEL entries, which a stock drive shows.
- Names starting with `.` are hidden.
- Extra pseudo-entries of type `NFO` follow the header, describing the host, path and image.
- An empty image gives `?FILE NOT FOUND` (see F).

### C.2 D64 sizes and geometry (public: D64.TXT)

The file has no signature. Identify it by size. Sectors are 256 bytes. Tracks start at 1, sectors at 0.

| Size in bytes | Tracks | Error bytes |
|---|---|---|
| 174848 | 35 | none |
| 175531 | 35 | 683 appended |
| 196608 | 40 | none |
| 197376 | 40 | 768 appended |
| 205312 | 42 | none |
| 206114 | 42 | 802 appended |

The 42-track sizes come from firmware, not from the public document. They follow arithmetically from the geometry. [FIRMWARE-CHOICE]

| Tracks | Sectors per track | Sectors before the first track of the range |
|---|---|---|
| 1 to 17 | 21 | 0 |
| 18 to 24 | 19 | 357 |
| 25 to 30 | 18 | 490 |
| 31 to 42 | 17 | 598 |

Byte offset = 256 × (sectors before the track + sector). Track 18 starts at `$16500`, track 25 at `$1EA00`, track 31 at `$25600`, track 36 at `$2AB00`.

Firmware ignores the error bytes and treats an unrecognised size as 35 tracks. [FIRMWARE-CHOICE]

### C.3 BAM and header: track 18, sector 0 (public: D64.TXT)

| Offset | Content |
|---|---|
| `$00`, `$01` | First directory sector. Unreliable: always start at 18/1. |
| `$02` | DOS version, normally `$41`. Other non-zero values soft write-protect. |
| `$03` | Unused |
| `$04` to `$8F` | 4 bytes per track, tracks 1 to 35: free count, then a 3-byte bitmap where a set bit means free |
| `$90` to `$9F` | Disk name, `$A0` padded |
| `$A0`, `$A1` | `$A0` |
| `$A2`, `$A3` | Disk ID |
| `$A4` | `$A0` |
| `$A5`, `$A6` | DOS type, `2A` |
| `$A7` to `$AA` | `$A0` |

Blocks free is the sum of the per-track free counts, excluding track 18. A blank 35-track disk gives 664 (683 − 19) (public).

Pitfall: firmware keeps counting past track 35 on 40 and 42 track images using the same 4-byte stride, so it reads the disk name as free counts. Read only tracks 1 to 35 unless you have detected a specific extended BAM layout. The extra entries live at different offsets in different DOS variants: `$C0`, `$AC` or `$90` (public).

### C.4 Directory (public: D64.TXT)

- Start at 18/1. Follow the link in the first two bytes of each sector. The chain ends when the link track is 0. Interleave is normally 3, but follow the links. Directories can extend off track 18.
- 8 entries per sector, 32 bytes each. A maximum of 144 on a standard disk.

| Entry offset | Content |
|---|---|
| 0, 1 | Next directory sector link. Meaningful only in the sector's first entry. |
| 2 | File type byte |
| 3, 4 | Track and sector of the file's first block |
| 5 to 20 | Name, 16 bytes, PETSCII, `$A0` padded. A 16-byte name has no terminator. |
| 21, 22 | REL side sector link |
| 23 | REL record length |
| 24 to 29 | Unused, except on GEOS disks |
| 30, 31 | Block count, low byte first |

File type byte: bits 0 to 3 are the type (0 DEL, 1 SEQ, 2 PRG, 3 USR, 4 REL, others illegal). Bit 5 is set during `@` replace. Bit 6 is locked. Bit 7 is closed. `$00` is a scratched entry, skipped everywhere. Common values: `$80` to `$84`.

### C.5 File chains (public: D64.TXT)

- Each block's first two bytes link to the next track and sector. The remaining 254 bytes are data.
- In the last block the link track is 0, and the second byte is the offset of the last used byte. Data bytes in that block = that value − 1. `$FF` means a full block.

### C.6 Pitfalls

All of these are real failure modes in the firmware. Guard against them.

- **Chain loops.** Firmware walks the whole chain when opening a file to compute its length, with no limit, so a cyclic chain hangs at OPEN. A cyclic directory lists forever and overruns C64 memory. Bound both walks by the image's sector count (and 144 entries for the directory on a standard disk). On overrun, report 66 or end the listing.
- **Bad links.** Sector numbers are valid from 0 to count − 1. Firmware accepts sector = count. Report `66,ILLEGAL TRACK OR SECTOR,TT,SS`.
- **Last-block offset below 2.** It means no data in that block. Unsigned arithmetic underflows here, and firmware does not guard it.
- **Directory block counts can be wrong.** Use the chain for length. The listing shows the directory's number, as stock does.
- **Reading a length first is not required.** Lookahead on the chain gives correct EOI without walking the file at OPEN.
- **Names:** cut at the first `$A0` or 16 bytes, whichever comes first. Firmware reads past the 16 bytes when there is no `$A0`, until it finds a zero byte.
- **Scratched entries** must not match a name.
- **A zero-length file** (first block link `00 01` or similar) gives 62 in firmware. Public DOS has no empty files.
- **REL files** have side sectors and need the `P` command. Firmware treats them as plain chains. Treat as out of scope.
- **Writes:** firmware refuses writes to files inside an image with status 26. If you implement them, the BAM bitmap and free count must be updated together.

---

## D. Line-level protocol (later hardware stage)

Lines are open collector. Low means asserted (true). Released means high (false). Never drive a line high. Bits go LSB first. On DATA, released = 1. (public)

C = controller (C64), D = device. Spec symbols and values are from the C64 Programmer's Reference Guide timing table. ROM values are cycle counts from public ROM at about 1 MHz.

Class: **S** = spec-mandated, **R** = observed in stock ROM, **T** = firmware tolerance, not mandated. Firmware values were read, not measured on hardware. [UNVERIFIED]

| # | Phase | Who does what | Spec or ROM | Firmware | Class |
|---|---|---|---|---|---|
| 1 | ATN falls | C pulls ATN (any time, even mid-byte), pulls CLK, releases DATA. Every D releases CLK and pulls DATA. | Tat ≤ 1000 µs, else device not present. C64 samples DATA about 1 ms after ATN (`$ED3D` to `$ED47`). | Immediate | S |
| 2 | Settle | D ignores the lines just after the ATN edge. | | 100 µs, then wait for CLK high | T |
| 3 | ATN byte start | C releases CLK. D releases DATA when ready. C pulls CLK when DATA reads high. No EOI under ATN. | Th 0 to ∞ | No timeout on these waits: other devices may hold DATA | S |
| 4 | Bits, D listening | D samples DATA as CLK rises. C holds about 70 µs low, about 26 µs high (`$ED66` to `$ED8B`). Sample within about 20 µs. | Ts ≥ 20, typ 70. Tv ≥ 20, typ 20. | ≤ 1000 µs per edge, else abandon the byte | S, R |
| 5 | Frame ack | D pulls DATA after bit 8. | Tf ≤ 1000 µs. C64 timer about 1024 µs, then ST bit 0 and 1 (`$ED92` to `$EDB0`). | Immediate | S |
| 6 | Not addressed | Primary is not UNLISTEN, UNTALK or our number: D releases CLK and DATA and ignores the bus until ATN rises. This makes the next byte's presence check fail for an absent number. | 1541 releases at once (`$E8FD`). | Holds DATA 150 µs, then releases | R, T |
| 7 | Secondary | As rows 3 to 5. If ATN rises with no secondary, treat as channel 0. | C64 repeats the 1 ms wait | | S |
| 8 | ATN rises | | Tr ≥ 20 µs after the frame | Waits with no timeout | S |
| 9 | Becoming listener | D keeps DATA low. C keeps CLK low until its first byte. If the channel cannot accept data, D releases DATA. C64 then sets ST bit 7 on its next byte (`$ED47`). | Stock does the same (`$EA41`). | Same | R |
| 10 | Turnaround, C | C pulls DATA, releases ATN, releases CLK. | Ttk 20, typ 30, max 100 µs | Waits ≤ 1000 µs for CLK high | S |
| 11 | Turnaround, D | D pulls CLK, releases DATA, holds before the first byte. **C64 waits for CLK low with no timeout (`$EDD6`).** | Tdc ≥ 0, Tda ≥ 80 µs | 80 µs | S |
| 12 | Talker preparing | D holds CLK low as long as it likes. C64 waits with no timeout (`$EE1B`). Slow media work belongs here. | No limit | | R |
| 13 | Between bytes | | Tbb ≥ 100 µs | 200 µs | S, T |
| 14 | Forced EOI | If DATA already reads high before D releases CLK, stock treats the next byte as last (1541 `$E919` to `$E923`). Some disk-copy programs hang if a device omits this. | ROM | Same | R |
| 15 | Ready to send | D releases CLK and waits for DATA high with no limit. This must be a tight wait: the listener's 200 µs starts when DATA goes high. | Th | Blocking wait | S |
| 16a | Next byte not last | D pulls CLK. | Tne ≤ 200, typ 40 µs | At once | S |
| 16b | Next byte is last (EOI) | D keeps CLK released. Listener pulls DATA after 200 µs or more, holds, releases. D pulls CLK at once after that. | Tye ≥ 200, typ 250. Tei ≥ 60. Try ≤ 60 µs. C64 holds about 84 µs. | ≤ 1000 µs for each DATA edge | S, T |
| 16c | Nothing to send | D leaves CLK and DATA released and stops. C64 times out twice, ST = `$42` (`$EE3E`). | Public: empty stream | Same | S |
| 17 | Bits, D talking | D pulls CLK, sets DATA, holds. Releases CLK, holds. Stock aborts if DATA reads low at the start of a bit (`$E95C`). C64 can stall about 42 µs on a video bad line. | Ts ≥ 20, typ 70. Tv ≥ 20, **≥ 60 for an external talker to a C64**. | 80 µs low, 60 µs high | S |
| 18 | Frame end, D talking | D pulls CLK, releases DATA. Listener pulls DATA. No ack is a frame error: stop talking until the next ATN. | Tf ≤ 1000 µs. Stock has no timeout (`$E987`). | ≤ 1000 µs | S |
| 19 | Listener wait | D waits for CLK high, then releases DATA when ready. Holding DATA low delays the talker without limit. | Th 0 to ∞ | | S |
| 20 | EOI detect | If CLK stays high for 200 µs after DATA is released: EOI. D pulls DATA, holds, releases, waits for CLK low. Stock starts timing only when DATA actually reads high (`$FF20`), which matters with several listeners. | Tye ≥ 200. Tei ≥ 60, **≥ 80 for an external listener**. | 200 µs. Hold 80 µs. ≤ 1000 µs for CLK. | S |
| 21 | Frame ack, D listening | D pulls DATA after bit 8. Omitting it, or pulling DATA during a byte, gives ST bits 0 and 1 (`$ED6F`, `$EDA4`). | Tf ≤ 1000 µs | Immediate | S |
| 22 | UNLISTEN, UNTALK | After the frame, C releases ATN, waits about 60 µs, releases CLK and DATA (`$EE03`). D releases too. | R | Same | R |
| 23 | Abort | ATN falling aborts everything at once. Go to row 1. A byte partly sent is lost. | | | S |
| 24 | Quick re-assert | C64 can assert ATN again a few tens of µs after release. D must not miss it. | R | Keeps interrupts off through the ATN sequence | T |
| 25 | RESET | On the falling edge, release CLK and DATA, then B.10. | | Same | R |

**EOI on the wire:** the KERNAL holds back one character and sends it with EOI when UNLISTEN, UNTALK or a new LISTEN or TALK arrives (public ROM `$ED12` to `$ED1E`). So on a real bus, the last name byte, command byte and SAVE byte all carry EOI. As listener, the C64 times the EOI gap at about 256 µs according to public documents. The exact ROM value depends on a CIA latch. [UNVERIFIED]

**Slow work versus the 1 ms rule.** The ATN response is always due, including while an OPEN or command runs after UNLISTEN, when no line is being held. A stock 1541 answers ATN in hardware. Firmware options: an extra output that does the same in hardware, or postponing OPEN and command work until the next byte wait, at the cost that a command does not run until the next bus activity. A clean design could answer ATN from an interrupt or a dedicated core. [FIRMWARE-CHOICE]

**Out of scope:** SRQ is not used by the standard C64 protocol. Fast loaders are absent on the bridge. On hardware the firmware detects JiffyDOS when CLK's rise for bit 7 of a primary is delayed by more than 200 µs, answering with an 80 µs DATA pull. [FIRMWARE-CHOICE]

---

## E. Emulator-bridge pitfalls

All [EMULATOR-BRIDGE] unless tagged otherwise.

### E.1 The path

The KERNAL's serial routines are hooked at fixed ROM addresses. Each hook makes one blocking call to the bridge, which sends one request and waits for one reply. The KERNAL's own line code does not run.

- **A stock KERNAL is required.** Each hook checks three ROM bytes when installed. A replacement KERNAL such as JiffyDOS fails this, so the unit is unreachable.
- **No fast loaders, and no line-level access.** Anything that bangs `$DD00` directly bypasses the hooks. The device does not exist on the emulated bus lines.
- The KERNAL's poll of the bus at `$EEA9` is faked to report "CLK low", so turnaround never waits.

### E.2 Bridge versus real bus

| Aspect | Real bus | Bridge |
|---|---|---|
| Primary | Separate byte, immediately | Held until the secondary arrives, then sent together. No primary alone except UNLISTEN and UNTALK. |
| No secondary | LISTEN or TALK alone | Sent as secondary `$60` just before the first data byte. If no byte follows, nothing goes out. |
| Secondary range | 5 bits | Masked to 4 bits. `$70` to `$7F` never appear. |
| Presence | DATA low within 1 ms | The ATN reply is ignored by the emulator |
| Write EOI | On the last byte | Never. The flag is always 0. |
| Write size | Byte stream | One request per byte from VICE. The bridge's own limit is 1024 bytes per request. |
| Read size | Byte stream | One request per byte from VICE. The bridge's own limit is 1024 bytes per request. |
| CLOSE | `$E0+c`, UNLISTEN | ATN with `$E0+c`, then UNLISTEN, then a second UNLISTEN |
| Who sees traffic | Every device sees every ATN byte | Only the addressed unit. UNLISTEN and UNTALK are sent only if the last addressed unit is on the hooks. |
| Device timing | µs windows | None, up to the reply timeout |

### E.3 Double UNLISTEN

The bridge sends UNLISTEN itself right after any CLOSE. The KERNAL then sends its own. Acknowledge both, and do nothing on the second.

### E.4 How ST gets set

Bits are ORed into ST, which is sticky until the next CHKIN, CHKOUT, named OPEN or LOAD.

| Event | ST bits |
|---|---|
| WRITE replied with 1 accepted | None |
| WRITE accepted anything else, or the transport failed | `$83` |
| READ returned one byte | None |
| READ returned no byte, or the transport failed | `$02` |
| EOI flag in the READ reply | `$40` added, on the same call |
| ATN not-present reply, or ATN transport failure | **None. The result is discarded.** |
| Unit not marked in use in the emulator | `$80` |

Resulting behaviour:

- In normal BASIC use, `?DEVICE NOT PRESENT` cannot be produced by a device reply, because ST is cleared just before each check. A KERNAL `LOAD` of a number the device does not serve ends in `?FILE NOT FOUND`.
- `PRINT#` to a refusing channel raises no BASIC error, and leaves ST = 131.
- A bad READ leaves junk in the returned byte (A.11).

### E.5 How long a reply can be held

- Default 30 s per reply, set by the bridge's `NETIEC_TIMEOUT` setting.
- There is no busy reply and no retry. A device that needs time simply does not answer yet.
- The whole emulated machine is frozen during the wait, including its clocks and RUN/STOP.
- On timeout the bridge closes the connection, and the operation fails as in E.4.
- The next bus operation reconnects at once. After a failed connect it waits 1 s between attempts, and fails immediately in between.
- HELLO comes first on every new connection. The firmware keeps its bus state across HELLO. Do not rely on it as a reset. [FIRMWARE-CHOICE] The bridge skips any stale reply left over before the HELLO reply.
- VICE and the device may start in either order.

### E.6 Ordering, and no polling

- Strict request and reply, one at a time, with no unsolicited traffic.
- The emulator does not poll a device. Work deferred past a reply must complete before the next request is handled, because the next request may read its result.
- Firmware replies to UNLISTEN first and then runs the OPEN or command before reading the next request. Equally valid is doing the work before replying. Threads must preserve this order. [FIRMWARE-CHOICE]
- Slow media access inside a READ just delays that reply.

### E.7 Units

- LISTEN and TALK are decoded from the top 3 bits, with a 5-bit unit. Secondary, CLOSE and OPEN are decoded from the top 4 bits. So `$30` to `$3E` are LISTEN 16 to 30 and `$50` to `$5E` are TALK 16 to 30. `$3F` and `$5F` are never a unit.
- Upstream VICE decoded 4-bit units, so 16 to 30 were unreachable until this fork changed it. See F.
- Units 12 to 30 are reached only through the hooks, and only when enabled one by one (`-realdeviceN`, or the launcher's `FUJINET_UNITS`). They have no emulated bus slot.
- Units 8 to 11 need true drive emulation off, the OpenCBM backend, and trap device on. Otherwise the KERNAL talks to the emulated bus and no request reaches the device.
- Units 0 to 3 and 31 never use the hooks.
- The device mask in the HELLO reply is logged by the bridge and does not route anything. Presence is decided per ATN.

### E.8 Reset

Every machine reset sends a RESET request, before the emulated chips reset. It is ignored if the connection is down. RESTORE does not send one. The device must apply B.10 for every device number it serves.

### E.9 What a device must do here

1. Acknowledge every ATN for a served number, and both UNLISTEN and UNTALK always.
2. End names and commands at UNLISTEN. Never wait for EOI.
3. Accept every name and command byte, one at a time.
4. Put EOI on the last byte's reply, and answer with zero bytes plus EOI when there is nothing.
5. Keep channel state across UNTALK, and survive missing UNTALK and CLOSE.
6. Finish OPEN and command work before handling the next request, inside the reply timeout.

### E.10 Testing without an emulator

The bridge ships a small tool, `netiecctl`, with `status`, `command`, `dir` and `load` subcommands. `NETIEC_TRACE=1` logs each transaction. Its name write is one multi-byte WRITE and its CLOSE has a single UNLISTEN, so it differs slightly from the KERNAL. Test with VICE as well.

---

## F. Bugs found and fixed, as requirements

### Bus and transport

- A device must end commands and names at UNLISTEN, because the bridge never delivers EOI and nothing would execute otherwise. [EMULATOR-BRIDGE]
- A bus master must decode LISTEN and TALK with a 5-bit unit, because with 4 bits units 16 to 30 were not recognised and FujiNet's network (16), clock (29) and FujiNet (30) devices could not be reached. [EMULATOR-BRIDGE]
- A FujiNet-style device must treat one LISTEN to UNLISTEN session as one message of any length, because a C64 cannot split it (each library write ends in UNLISTEN). Payloads of 304 bytes occur. [FIRMWARE-CHOICE]

### Text handling

- A device must keep name bytes from `$80` up, because on host builds a signed `char` caused shifted PETSCII bytes to be dropped, which broke later file and network operations. [KERNAL-REQUIRED]
- A device must compare command bytes as unsigned, because a comparison against `$CA` never matched otherwise. [FIRMWARE-CHOICE]
- Paths in CD, PWD and file commands to the network device must be converted from PETSCII, because `N1:` arrives as `CE 31 3A` and is otherwise not recognised as a device name. PWD results must be converted back. [FIRMWARE-CHOICE]
- Generated GUIDs must be sent in PETSCII, because ASCII lowercase changes case on the round trip through a path. [FIRMWARE-CHOICE]
- Clock strings must be sent as PETSCII on IEC. The firmware's log records this fix but not the failure it cured. [FIRMWARE-CHOICE] [UNVERIFIED]
- Raw reads and writes, host slots, directory entries and paths in FujiNet device commands (OPEN DIRECTORY, COPY FILE, NEW DISK) must not be converted, because programs supply and expect ASCII there. [FIRMWARE-CHOICE]

### Images

- A drive must read a mounted image through the same transport that mounted it, because images from network hosts otherwise neither list nor load on a host build. [FIRMWARE-CHOICE]
- Header and bytes-free text must be formatted correctly on every host, because a formatting bug garbled the disk name, ID and free line on x86-64 (`1024.00BYTES FREE.`) while appearing to work on arm64. [FIRMWARE-CHOICE]
- NEW DISK must actually write a formatted image, because a stub reported success with no file. D64, D71 and D81 images should match what `c1541 -format` writes: 664, 1328 and 3160 free, ID `FN`, DOS type `2A` (`3D` on D81). Other names get zero-filled files, and sizes of 0 or over 16 MiB are refused. [FIRMWARE-CHOICE]

### FujiNet device level

- A command with no payload must not fault, because a game quitting sends an empty WRITE APPKEY and that aborted the firmware. [FIRMWARE-CHOICE]
- Device 30 must answer clock commands, because the C64 library sends them there and not to device 29. [FIRMWARE-CHOICE]
- `$53` with a payload must be treated as the clock's GET_SOS and without one as STATUS, because the two share a command byte. [FIRMWARE-CHOICE]
- The time zone setter must skip the 2-byte length before the name, because otherwise the name is rejected as malformed. [FIRMWARE-CHOICE]

### Found but not fixed in the firmware: do not copy

- A refused FujiNet command still answers the C64 as success. A clean device should report it. Upstream sets bit `$20` of the STATUS byte on another bus as a template.
- `LOAD"$",8` on an empty image gives `?FILE NOT FOUND`. It must list a header and blocks free.
- SAVE to a file inside an image fails with status 26.
- D71 images are read with the directory on track 1 and do not list. The standard location is 18/0 and 18/1 (public).
- D81 reads its second BAM from 40/0, giving a wrong free count. The standard location is 40/2 (public).
- FujiNet's own open-directory entries (not the BASIC listing) carry a 16-bit size, so files of 64 KiB or more report a wrapped value. Widening it needs the firmware and C64 library changed together.
- All network units N1 to N8 share one device, so unit number is lost for CD, PWD, STATUS and OPEN.

---

## Items marked [UNVERIFIED]

1. Line-level firmware values in section D were read, not measured. The hardware build was not run for this spec.
2. The C64's EOI timer length. Public documents say about 256 µs. The ROM only loads the CIA timer's high byte with 1 (`$EE20`), so the true value depends on the low-byte latch. Treat the 200 µs spec figure as the threshold and allow up to 1000 µs when waiting for the listener's acknowledgement.
3. Which failure the PETSCII clock-string fix cured (section F).
4. The 1541 User's Guide's own wording for status 74. The meaning given comes from the Commodore 128 manual.

## Sources

- [C64 Programmer's Reference Guide serial timing table, as reproduced in VICE's serial.txt](https://sources.debian.org/src/vice/1.19-1etch1/doc/html/plain/serial.txt)
- [How the VIC/64 Serial Bus Works, Jim Butterfield, COMPUTE! #38](https://www.atarimagazines.com/compute/issue38/073_1_HOW_THE_VIC_64_SERIAL_BUS_WORKS.php)
- [Commodore Peripheral Bus: Standard Serial](https://www.pagetable.com/?p=1135)
- [Commodore Peripheral Bus: TALK/LISTEN layer](https://www.pagetable.com/?p=1031)
- [Commodore Peripheral Bus: Commodore DOS](https://www.pagetable.com/?p=1038)
- [D64.TXT, Peter Schepers](https://ist.uwaterloo.ca/~schepers/formats/D64.TXT)
- [Commodore 128 manual, error list](https://www.manualslib.com/manual/826608/Commodore-128.html?page=375)
- Stock C64 KERNAL 901227-03, BASIC 901226-01 and 1541 DOS 2.6 325302-01 + 901229-05 ROM images, disassembled directly.
