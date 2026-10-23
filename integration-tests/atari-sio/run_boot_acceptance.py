#!/usr/bin/env python3
"""Deterministic Story 1.3 native and production-NetSIO boot gate."""
from __future__ import annotations
import argparse, hashlib, json, os, re, select, shutil, signal, socket, subprocess, sys, tempfile, threading, time
from pathlib import Path

from virtual_projection import (evidence_paths_for_boot, load_manifest,
                                compare_netsio_native_core_dispatch,
                                compare_netsio_native_wrong_r_retention,
                                compare_netsio_native_reset_to_idle,
                                compare_netsio_native_interrupted_r_recovery,
                                compare_netsio_native_capacity_bounds, fixture_payload,
                                compare_altirra_embedded_native_core_dispatch,
                                compare_altirra_embedded_native_wrong_r_retention,
                                compare_altirra_embedded_native_reset_to_idle,
                                compare_altirra_embedded_native_interrupted_r_recovery,
                                compare_altirra_embedded_native_capacity_bounds,
                                ProjectionMismatch, scenario_result, validate_manifest,
                                write_scenario_result)
from fnaccept_memory_layout import layout_report, validate_runtime_snapshot

ROOT = Path(__file__).resolve().parents[2]
ATR = ROOT / "integration-tests/atari-sio/boot-app/build/boot-acceptance.atr"
NATIVE_CORE_DISPATCH_XEX = ROOT / "integration-tests/atari-sio/native-projection-app/build/native-core-dispatch.xex"
NATIVE_WRONG_R_RETENTION_XEX = ROOT / "integration-tests/atari-sio/native-projection-app/build/native-wrong-r-retention.xex"
NATIVE_RESET_TO_IDLE_XEX = ROOT / "integration-tests/atari-sio/native-projection-app/build/native-reset-to-idle.xex"
NATIVE_INTERRUPTED_R_RECOVERY_XEX = ROOT / "integration-tests/atari-sio/native-projection-app/build/native-interrupted-r-recovery.xex"
NATIVE_CAPACITY_BOUNDS_XEX = ROOT / "integration-tests/atari-sio/native-projection-app/build/native-capacity-bounds.xex"
PUBLIC_API_CLOCK_XEX = ROOT / "repos/nio-core-apps/build/atari/bin/fnaccept.xex"
TRACE_FIXTURE = ROOT / "integration-tests/atari-sio/fixtures/boot_acceptance_trace.json"
PROFILE = ROOT / "configs/atari/profiles/atari-nio-config-boot.yaml"
ALTIRRA = ROOT / "repos/AltirraSDL/build/linux-debug/src/AltirraSDL/AltirraSDL"
SDK = ROOT / "repos/AltirraSDL/src/AltirraSDL/AltirraBridge/sdk/python"
HUB = ROOT / "repos/fujinet-emulator-bridge/fujinet-bridge"
NIO = ROOT / "repos/fujinet-nio/build/atari-fujibus-netsio-debug/fujinet-nio"
NATIVE_CORE_DISPATCH = ROOT / "repos/fujinet-nio/build/atari-fujibus-netsio-debug/tests/fujinet-nio-atari-netsio-projection"
PUBLIC_API_CLOCK_ENDPOINT = ROOT / "repos/fujinet-nio/build/atari-fujibus-netsio-debug/tests/fujinet-nio-atari-netsio-clock-acceptance"
SIG, LOOP = b"NIO!", 0x0624
PROJECTION_RESULT = 0x0800
PROJECTION_Q_REPLY = 0x0810
PROJECTION_P_READY = 0x0820
PROJECTION_R_REPLY = 0x0830
PROJECTION_P_IDLE = 0x0850
PROJECTION_STATUSES = 0x0880
PROJECTION_P_RETAIN = 0x0890
PROJECTION_RESET_GO = 0x089f
PROJECTION_AFTER_READY = 0x08b0
PROJECTION_AFTER_REPLY = 0x08c0
PROJECTION_AFTER_IDLE = 0x08d0
PROJECTION_CAPACITY_REQUEST_GUARD_LOW = 0x1fff
PROJECTION_CAPACITY_REQUEST_GUARD_HIGH = 0x2200
PROJECTION_CAPACITY_RESPONSE_GUARD_LOW = 0x23ff
PROJECTION_CAPACITY_RESPONSE = 0x2400
PROJECTION_CAPACITY_RESPONSE_GUARD_HIGH = 0x2600
PUBLIC_API_RESULT = 0x0B00
PUBLIC_API_CLOCK_TIME = PUBLIC_API_RESULT + 8
PUBLIC_API_HEARTBEAT = PUBLIC_API_RESULT + 16
PUBLIC_API_CLOCK_BYTES = bytes.fromhex('08 07 06 05 04 03 02 01')
PUBLIC_API_FILE_WRITE_STATUS = PUBLIC_API_RESULT + 18
PUBLIC_API_FILE_WRITE_DEVICE_STATUS = PUBLIC_API_RESULT + 19
PUBLIC_API_FILE_WRITE_RESPONSE_LENGTH = PUBLIC_API_RESULT + 20
PUBLIC_API_FILE_WRITE_COUNT = PUBLIC_API_RESULT + 22
PUBLIC_API_FILE_READ_STATUS = PUBLIC_API_RESULT + 24
PUBLIC_API_FILE_READ_DEVICE_STATUS = PUBLIC_API_RESULT + 25
PUBLIC_API_FILE_READ_RESPONSE_LENGTH = PUBLIC_API_RESULT + 26
PUBLIC_API_FILE_READ_COUNT = PUBLIC_API_RESULT + 28
PUBLIC_API_FILE_VERIFY = PUBLIC_API_RESULT + 30
PUBLIC_API_NETWORK_OPEN_STATUS = PUBLIC_API_RESULT + 31
PUBLIC_API_NETWORK_HANDLE = PUBLIC_API_RESULT + 32
PUBLIC_API_NETWORK_WRITE_STATUS = PUBLIC_API_RESULT + 34
PUBLIC_API_NETWORK_WRITE_COUNT = PUBLIC_API_RESULT + 35
PUBLIC_API_NETWORK_READ_STATUS = PUBLIC_API_RESULT + 37
PUBLIC_API_NETWORK_READ_COUNT = PUBLIC_API_RESULT + 38
PUBLIC_API_NETWORK_READ_FLAGS = PUBLIC_API_RESULT + 40
PUBLIC_API_NETWORK_VERIFY = PUBLIC_API_RESULT + 41
PUBLIC_API_NETWORK_CLOSE_STATUS = PUBLIC_API_RESULT + 42
PUBLIC_API_NETWORK_REPLY = PUBLIC_API_RESULT + 43
PUBLIC_API_DISK_INFO_STATUS = PUBLIC_API_RESULT + 55
PUBLIC_API_DISK_FLAGS = PUBLIC_API_RESULT + 56
PUBLIC_API_DISK_SLOT = PUBLIC_API_RESULT + 57
PUBLIC_API_DISK_TYPE = PUBLIC_API_RESULT + 58
PUBLIC_API_DISK_SECTOR_SIZE = PUBLIC_API_RESULT + 59
PUBLIC_API_DISK_SECTOR_COUNT = PUBLIC_API_RESULT + 61
PUBLIC_API_DISK_LAST_ERROR = PUBLIC_API_RESULT + 65
PUBLIC_API_DISK_WRITE_STATUS = PUBLIC_API_RESULT + 66
PUBLIC_API_DISK_FLUSH_STATUS = PUBLIC_API_RESULT + 67
PUBLIC_API_DISK_READ_STATUS = PUBLIC_API_RESULT + 68
PUBLIC_API_DISK_WRITE_LENGTH = PUBLIC_API_RESULT + 69
PUBLIC_API_DISK_READ_LENGTH = PUBLIC_API_RESULT + 71
PUBLIC_API_DISK_VERIFY = PUBLIC_API_RESULT + 73
PUBLIC_API_FILE_REJECTED_W_STATUS = PUBLIC_API_RESULT + 74
PUBLIC_API_FILE_RECOVERY_ATTEMPTED = PUBLIC_API_RESULT + 75
PUBLIC_API_FILE_RECOVERY_WRITE_STATUS = PUBLIC_API_RESULT + 76
PUBLIC_API_FILE_RECOVERY_WRITE_DEVICE_STATUS = PUBLIC_API_RESULT + 77
PUBLIC_API_FILE_RECOVERY_WRITE_RESPONSE_LENGTH = PUBLIC_API_RESULT + 78
PUBLIC_API_FILE_RECOVERY_WRITE_COUNT = PUBLIC_API_RESULT + 80
PUBLIC_API_FILE_RECOVERY_VERIFY = PUBLIC_API_RESULT + 82
PUBLIC_API_FILE_FAILURE_STATUS = PUBLIC_API_RESULT + 83
PUBLIC_API_FILE_RECOVERY_KIND = PUBLIC_API_RESULT + 84
PUBLIC_API_MEMORY_SNAPSHOT = PUBLIC_API_RESULT + 0x60
PUBLIC_API_MEMORY_MAGIC = PUBLIC_API_MEMORY_SNAPSHOT
PUBLIC_API_MEMORY_VERSION = PUBLIC_API_MEMORY_SNAPSHOT + 4
PUBLIC_API_PRE_MEMLO = PUBLIC_API_MEMORY_SNAPSHOT + 5
PUBLIC_API_PRE_MEMTOP = PUBLIC_API_MEMORY_SNAPSHOT + 7
PUBLIC_API_PRE_RAMTOP = PUBLIC_API_MEMORY_SNAPSHOT + 9
PUBLIC_API_PRE_SDLSTL = PUBLIC_API_MEMORY_SNAPSHOT + 10
PUBLIC_API_PRE_SAVMSC = PUBLIC_API_MEMORY_SNAPSHOT + 12
PUBLIC_API_PRE_SDMCTL = PUBLIC_API_MEMORY_SNAPSHOT + 14
PUBLIC_API_PRE_DMACTL = PUBLIC_API_MEMORY_SNAPSHOT + 15
PUBLIC_API_HEADLESS_PROOF = PUBLIC_API_MEMORY_SNAPSHOT + 16
PUBLIC_API_FILE_URI = b'persist:///fnaccept-v1.bin'
PUBLIC_API_FILE_MARKER = b'ATARI-FILE-24'
PUBLIC_API_FILE_NAME = 'fnaccept-v1.bin'
PUBLIC_API_FILE_RECOVERY_URI = b'persist:///fnaccept-recovered-v1.bin'
PUBLIC_API_FILE_RECOVERY_MARKER = b'ATARI-FILE-RECOVERY-24'
PUBLIC_API_FILE_RECOVERY_NAME = 'fnaccept-recovered-v1.bin'
PUBLIC_API_FILE_WRITE_PAYLOAD_BYTES = 3 + len(PUBLIC_API_FILE_URI) + 4 + 2 + len(PUBLIC_API_FILE_MARKER)
PUBLIC_API_FILE_READ_PAYLOAD_BYTES = 3 + len(PUBLIC_API_FILE_URI) + 4 + 2
PUBLIC_API_FILE_RECOVERY_WRITE_PAYLOAD_BYTES = (3 + len(PUBLIC_API_FILE_RECOVERY_URI) + 4 + 2 +
                                                len(PUBLIC_API_FILE_RECOVERY_MARKER))
PUBLIC_API_FILE_RECOVERY_READ_PAYLOAD_BYTES = 3 + len(PUBLIC_API_FILE_RECOVERY_URI) + 4 + 2
PUBLIC_API_FUJIBUS_HEADER_BYTES = 5
PUBLIC_API_NETWORK_URI = b'fixture://nio-accept'
PUBLIC_API_NETWORK_WRITE_MARKER = b'NET-WRITE-24'
PUBLIC_API_NETWORK_REPLY_BYTES = b'NET-REPLY-24'
# NetworkDevice application payloads: Open(method, mode, translation,
# urlLength, URL, loginLength, passwordLength, bodyLength), then the
# documented Write/Read/Close request fields.  The public library owns the
# FujiBus header and all native-SIO framing.
PUBLIC_API_NETWORK_OPEN_PAYLOAD_BYTES = 1 + 1 + 1 + 2 + len(PUBLIC_API_NETWORK_URI) + 2 + 4 + 2
PUBLIC_API_NETWORK_WRITE_PAYLOAD_BYTES = 1 + 2 + 4 + 2 + len(PUBLIC_API_NETWORK_WRITE_MARKER)
PUBLIC_API_NETWORK_READ_PAYLOAD_BYTES = 1 + 2 + 4 + 2
PUBLIC_API_NETWORK_CLOSE_PAYLOAD_BYTES = 1 + 2
PUBLIC_API_DISK_SLOT_VALUE = 2
PUBLIC_API_DISK_LBA = 5
PUBLIC_API_DISK_SECTOR_BYTES = 128
PUBLIC_API_DISK_SECTOR_COUNT_VALUE = 16
PUBLIC_API_DISK_IMAGE_NAME = 'fnaccept-disk.atr'
PUBLIC_API_DISK_ATR_HEADER_BYTES = 16
PUBLIC_API_DISK_INFO_PAYLOAD_BYTES = 2
PUBLIC_API_DISK_WRITE_PAYLOAD_BYTES = 1 + 1 + 4 + 2 + PUBLIC_API_DISK_SECTOR_BYTES
PUBLIC_API_DISK_FLUSH_PAYLOAD_BYTES = 2
PUBLIC_API_DISK_READ_PAYLOAD_BYTES = 1 + 1 + 4 + 2

def public_api_disk_pattern(index):
    return ((index * 37) ^ 0xa5) & 0xff

PUBLIC_API_DISK_PATTERN = bytes(public_api_disk_pattern(index)
                                for index in range(PUBLIC_API_DISK_SECTOR_BYTES))
# A bridge pause can capture any instruction-boundary phase of the three-byte
# JMP $0624 loop, including the post-operand PC just before its target applies.
LOOP_PCS = {LOOP, LOOP + 1, LOOP + 2, LOOP + 3}

def legacy_paths():
    """Return the optional legacy-control pair without baking in a host path."""
    legacy_home = os.environ.get('FUJINET_LEGACY_HOME')
    if not legacy_home:
        raise RuntimeError(
            'legacy FujiNet control requires FUJINET_LEGACY_HOME to name its install directory'
        )
    dist = Path(legacy_home).expanduser() / 'dist'
    return dist / 'fujinet', dist / 'run-fujinet'

def decode_dcb(raw):
    return {
        'raw': raw.hex(),
        'device': f'0x{raw[0]:02x}', 'unit': raw[1],
        'command': f'0x{raw[2]:02x}', 'status': f'0x{raw[3]:02x}',
        'buffer': f'0x{raw[4] | (raw[5] << 8):04x}',
        'timeout': raw[6],
        'byte_count': raw[8] | (raw[9] << 8),
        'aux': raw[10] | (raw[11] << 8),
    }

def stop(ps):
    for p in ps:
        if p.poll() is None:
            os.killpg(p.pid, signal.SIGTERM)
    for p in ps:
        try: p.wait(5)
        except subprocess.TimeoutExpired:
            os.killpg(p.pid, signal.SIGKILL)
            p.wait()

def fresh_token(before, timeout=15):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        found=[p for p in Path('/tmp').glob('altirra-bridge-*.token') if p not in before]
        if found: return max(found,key=lambda p:p.stat().st_mtime)
        time.sleep(.1)
    raise RuntimeError('Altirra bridge token not created')

def wait_log(path, needle, timeout=5):
    """Wait for a sidecar readiness line without advancing emulator frames."""
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if path.exists() and needle in path.read_text(errors='replace'):
            return
        time.sleep(.05)
    raise RuntimeError(f'timed out waiting for {needle!r} in {path}')

def netsio_device_endpoint(hub_log, timeout=5):
    """Find the production endpoint's UDP address from hub capture evidence."""
    deadline = time.monotonic() + timeout
    pattern = re.compile(r'Device connected: (?P<host>[^:\s]+):(?P<port>\d+)')
    while time.monotonic() < deadline:
        if hub_log.exists():
            matches = pattern.findall(hub_log.read_text(errors='replace'))
            if matches:
                host, port = matches[0]
                return host, int(port)
        time.sleep(.05)
    raise RuntimeError('NetSIO projection endpoint did not register with the hub')

def wait_for_projection_step(token, expected_step, timeout=10):
    """Wait for the guest's stable test checkpoint without resetting its CPU."""
    sys.path[:0] = [str(SDK)]
    from altirra_bridge import AltirraBridge
    deadline = time.monotonic() + timeout
    with AltirraBridge.from_token_file(token) as bridge:
        while time.monotonic() < deadline:
            result = bridge.peek(PROJECTION_RESULT, 4)
            step = bridge.peek(PROJECTION_RESULT + 4, 1)
            if result == b'NVF!':
                raise RuntimeError(f'native projection guest failed before reset at step {step.hex()}')
            if result != b'NVP!' and step == bytes((expected_step,)):
                return
            time.sleep(.05)
    raise RuntimeError(f'native projection guest did not reach reset checkpoint {expected_step}')

def inject_netsio_device_reset(token, hub_log, nio_log, run_dir, timeout=10):
    """Inject a supported one-byte NetSIO COLD_RESET into the live endpoint.

    This is deliberately after the normal Altirra launch reset.  The raw FF
    is received by the production UDP channel and handled by NetSIO ingress;
    the bridge poke only releases the waiting guest after that captured event.
    """
    host, port = netsio_device_endpoint(hub_log, timeout)
    offset = nio_log.stat().st_size if nio_log.exists() else 0
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as peer:
        peer.sendto(b'\xff', (host, port))
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        tail = nio_log.read_text(errors='replace')[offset:] if nio_log.exists() else ''
        marker = tail.find('udp: Received 1 bytes: FF')
        if marker >= 0 and 'l_netsio: COLD_RESET' in tail[marker:]:
            event = {
                'kind': 'netsio-cold-reset',
                'wire_datagram': 'ff',
                'endpoint': f'{host}:{port}',
                'nio_log_offset': offset,
            }
            (run_dir / 'netsio-reset-event.json').write_text(json.dumps(event, indent=2) + '\n')
            sys.path[:0] = [str(SDK)]
            from altirra_bridge import AltirraBridge
            with AltirraBridge.from_token_file(token) as bridge:
                bridge.poke(PROJECTION_RESET_GO, 1)
            return event
        time.sleep(.05)
    raise RuntimeError('injected NetSIO COLD_RESET was not observed by production ingress')


class NetSioTerminalRChecksumRelay:
    """Transparent NetSIO carrier relay with one deliberate delivery fault.

    It forwards the live endpoint's complete UDP traffic to the ordinary hub.
    Only after the first correct-length native R is forwarded to the endpoint
    does it alter that response's final data checksum on its way to Altirra.
    Thus the frontend has already accepted and consumed R; the relay is not a
    Q/W/P/R peer and never fabricates any endpoint response.
    """
    def __init__(self, run_dir, listen_port=9997, hub_port=9998):
        self.run_dir = Path(run_dir)
        self.hub = ('127.0.0.1', hub_port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(('127.0.0.1', listen_port))
        self.sock.setblocking(False)
        self.endpoint = None
        self.stop_requested = threading.Event()
        self.thread = threading.Thread(target=self._run, name='netsio-r-checksum-relay', daemon=True)
        self.interrupted_r_attempts = 0
        self.post_failure_w_seen = False
        self.armed = False
        self.payload_seen = False
        self.fault_applied = False
        self.failure = None
        self.events = []

    def _record(self, event, **details):
        self.events.append({'event': event, **details})

    def start(self):
        self.thread.start()

    def _run(self):
        try:
            while not self.stop_requested.is_set():
                readable, _, _ = select.select((self.sock,), (), (), .05)
                if not readable:
                    continue
                data, source = self.sock.recvfrom(1024)
                if source[1] == self.hub[1]:
                    if self.fault_applied and len(data) >= 6 and data[0] == 0x02 and data[1:3] == b'\x7fW':
                        self.post_failure_w_seen = True
                    if len(data) >= 6 and data[0] == 0x02 and data[1:6] == bytes.fromhex('7f 52 09 00 da'):
                        if not self.post_failure_w_seen:
                            self.interrupted_r_attempts += 1
                        if self.interrupted_r_attempts == 1:
                            self.armed = True
                            self.payload_seen = False
                            self._record('first-terminal-r-forwarded', frame=data[1:6].hex(' '))
                        elif not self.post_failure_w_seen:
                            self._record('terminal-r-retry-forwarded', frame=data[1:6].hex(' '))
                        else:
                            self._record('recovery-terminal-r-forwarded', frame=data[1:6].hex(' '))
                    if self.endpoint is not None:
                        self.sock.sendto(data, self.endpoint)
                    continue

                if self.endpoint is None:
                    self.endpoint = source
                    self._record('endpoint-registered', endpoint=f'{source[0]}:{source[1]}')
                if source != self.endpoint:
                    self._record('unexpected-source', endpoint=f'{source[0]}:{source[1]}')
                    continue
                outgoing = data
                if self.armed and data and data[0] == 0x02:
                    self.payload_seen = True
                elif self.armed and self.payload_seen and len(data) == 2 and data[0] == 0x01:
                    outgoing = bytes((0x01, data[1] ^ 0x01))
                    self.armed = False
                    self.fault_applied = True
                    self._record('terminal-r-checksum-corrupted', original=f'{data[1]:02x}',
                                 delivered=f'{outgoing[1]:02x}')
                self.sock.sendto(outgoing, self.hub)
        except Exception as exc:  # recorded and surfaced by the caller.
            self.failure = str(exc)

    def stop(self):
        self.stop_requested.set()
        self.thread.join(2)
        self.sock.close()
        summary = {
            'format': 'atari-netsio-terminal-r-checksum-relay-v1',
            'interrupted_r_attempts': self.interrupted_r_attempts,
            'fault_applied': self.fault_applied,
            'failure': self.failure,
            'events': self.events,
        }
        path = self.run_dir / 'netsio-terminal-r-relay.json'
        path.write_text(json.dumps(summary, indent=2) + '\n')
        return summary, path


class NetSioRejectedFileWRelay:
    """Forward live NetSIO traffic while rejecting one logical File W.

    The public acceptance guest's first native W is Clock and its second is
    File Write.  This carrier relay changes only that command's SIO checksum
    before the production endpoint parses it.  Identical OS retries receive
    the same scoped corruption; once a different W appears, the relay becomes
    transparent so the guest's distinct recovery operation reaches the real
    endpoint.  It never manufactures a command reply or a FujiBus response.
    """
    def __init__(self, run_dir, listen_port=9997, hub_port=9998):
        self.run_dir = Path(run_dir)
        self.hub = ('127.0.0.1', hub_port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(('127.0.0.1', listen_port))
        self.sock.setblocking(False)
        self.endpoint = None
        self.endpoint_registered = threading.Event()
        self.stop_requested = threading.Event()
        self.thread = threading.Thread(target=self._run, name='netsio-rejected-file-w-relay', daemon=True)
        self.native_w_count = 0
        self.command_active = False
        self.command_bytes = []
        self.selected_aux = None
        self.rejected_attempts = []
        self.endpoint_naks = []
        self.commands_after_rejection = []
        self.recovery_w_seen = False
        self.unexpected_recovery_commands = []
        self.failure = None
        self.events = []

    def _record(self, event, **details):
        self.events.append({'event': event, **details})

    def start(self):
        self.thread.start()

    def _complete_command(self, frame):
        """Classify one reconstructed five-byte SIO command frame."""
        if len(frame) != 5 or frame[0] != 0x7f:
            return None
        command = frame[1]
        text = frame.hex(' ')
        if command == ord('W'):
            self.native_w_count += 1
            if self.selected_aux is None and self.native_w_count == 2:
                self.selected_aux = frame[2:4]
                self._record('selected-file-w', frame=text, aux=self.selected_aux.hex(' '))
            if self.selected_aux is not None and not self.recovery_w_seen:
                if frame[2:4] == self.selected_aux:
                    corrupted = frame[:-1] + bytes((frame[-1] ^ 0x01,))
                    self.rejected_attempts.append({
                        'original': text,
                        'delivered': corrupted.hex(' '),
                    })
                    self._record('file-w-checksum-corrupted',
                                 original=text, delivered=corrupted.hex(' '))
                    return corrupted[-1]
                self.recovery_w_seen = True
                self.commands_after_rejection.append(text)
                self._record('distinct-recovery-w-forwarded', frame=text)
                return None
        if self.selected_aux is not None and not self.recovery_w_seen:
            self.commands_after_rejection.append(text)
            if command in (ord('P'), ord('R')):
                self.unexpected_recovery_commands.append(text)
                self._record('unexpected-pr-before-recovery-w', frame=text)
        elif self.recovery_w_seen:
            self.commands_after_rejection.append(text)
        return None

    def _from_hub(self, data):
        """Forward NetSIO packets while editing only a command checksum byte.

        NetSIO may carry the five command bytes as one DATA_BLOCK or as
        individual DATA_BYTE packets under credit pressure.  Reconstruct only
        the command window delimited by COMMAND_ON/OFF, preserving every other
        datagram unchanged.
        """
        outgoing = bytearray(data)
        if data[:1] == b'\x11':
            self.command_bytes = []
            self.command_active = True
            return bytes(outgoing)
        if data[:1] == b'\x18':
            self.command_active = False
            return bytes(outgoing)
        if not getattr(self, 'command_active', False) or data[:1] not in (b'\x01', b'\x02'):
            return bytes(outgoing)
        # The last NetSIO byte is its sequence number, not SIO payload.
        for index in range(1, len(data) - 1):
            if len(self.command_bytes) >= 5:
                break
            self.command_bytes.append(data[index])
            if len(self.command_bytes) == 5:
                replacement = self._complete_command(bytes(self.command_bytes))
                if replacement is not None:
                    outgoing[index] = replacement
        return bytes(outgoing)

    def _run(self):
        try:
            while not self.stop_requested.is_set():
                readable, _, _ = select.select((self.sock,), (), (), .05)
                if not readable:
                    continue
                data, source = self.sock.recvfrom(1024)
                if source[1] == self.hub[1]:
                    outgoing = self._from_hub(data)
                    if self.endpoint is not None:
                        self.sock.sendto(outgoing, self.endpoint)
                    continue
                if self.endpoint is None:
                    self.endpoint = source
                    self.endpoint_registered.set()
                    self._record('endpoint-registered', endpoint=f'{source[0]}:{source[1]}')
                if source != self.endpoint:
                    self._record('unexpected-source', endpoint=f'{source[0]}:{source[1]}')
                    continue
                # Record only NAKs for the selected logical File write.  A
                # startup/control NAK is not evidence that the checksum
                # mutation reached the production endpoint.
                if (self.selected_aux is not None and not self.recovery_w_seen and
                        ((data == b'\x01N') or
                         (len(data) == 6 and data[0] == 0x81 and data[3] == ord('N')))):
                    self.endpoint_naks.append(data.hex(' '))
                    self._record('endpoint-nak-forwarded', datagram=data.hex(' '))
                self.sock.sendto(data, self.hub)
        except Exception as exc:
            self.failure = str(exc)

    def stop(self):
        self.stop_requested.set()
        self.thread.join(2)
        self.sock.close()
        summary = {
            'format': 'atari-netsio-rejected-file-w-relay-v1',
            'selected_w_ordinal': 2,
            'selected_aux': self.selected_aux.hex(' ') if self.selected_aux else None,
            'rejected_attempts': self.rejected_attempts,
            'endpoint_naks': self.endpoint_naks,
            'commands_after_rejection': self.commands_after_rejection,
            'recovery_w_seen': self.recovery_w_seen,
            'unexpected_recovery_commands': self.unexpected_recovery_commands,
            'failure': self.failure,
            'events': self.events,
        }
        path = self.run_dir / 'netsio-rejected-file-w-relay.json'
        path.write_text(json.dumps(summary, indent=2) + '\n')
        return summary, path


class NetSioReadyLengthRelay(NetSioRejectedFileWRelay):
    """Deliver one real File READY reply with a shorter, checksummed length.

    This remains a carrier relay.  The endpoint has already dispatched the
    selected File W and prepared its reply; only the three P bytes and their
    following SIO checksum are changed while travelling to Altirra.  The
    resulting R is therefore accepted by neither side: the production
    frontend NAKs it and retains the original response for public-library
    recovery on the next, distinct File operation.
    """
    def __init__(self, run_dir, listen_port=9997, hub_port=9998):
        super().__init__(run_dir, listen_port, hub_port)
        self.thread = threading.Thread(target=self._run,
                                       name='netsio-ready-length-relay', daemon=True)
        self.selected = False
        self.awaiting_ready_payload = False
        self.awaiting_ready_checksum = False
        self.ready_payload = None
        self.delivered_ready_payload = None
        self.ready_checksums = {}
        self.awaiting_recovery_ready_payload = False
        self.awaiting_recovery_ready_checksum = False
        self.recovery_ready_payload = None
        self.recovery_ready_checksum = None
        self.fault_applied = False
        self.wrong_r_attempts = []
        self.wrong_r_naks = []
        self.recovery_p_seen = False
        self.recovery_r_seen = False
        self.distinct_w_seen = False
        self.command_frames = []
        self.pending_w_payload = None
        self.w_payloads = {}
        self.w_checksums = {}
        self.awaiting_recovery_r_payload = False
        self.recovery_r_payload = None
        self.recovery_r_checksum = None

    def _complete_command(self, frame):
        if len(frame) != 5 or frame[0] != 0x7f:
            return None
        command = frame[1]
        text = frame.hex(' ')
        if command == ord('W'):
            self.native_w_count += 1
            if self.native_w_count == 2:
                self.selected = True
                self.selected_aux = frame[2:4]
                self.pending_w_payload = 'initial'
                self._record('selected-file-w', frame=text,
                             aux=self.selected_aux.hex(' '))
            elif self.selected and self.recovery_r_seen and not self.distinct_w_seen:
                self.distinct_w_seen = True
                self.pending_w_payload = 'distinct'
                self._record('distinct-file-w-forwarded', frame=text)
        if self.selected:
            self.command_frames.append(text)
            if command == ord('P'):
                if not self.fault_applied:
                    self.awaiting_ready_payload = True
                    self._record('selected-ready-p-forwarded', frame=text)
                elif self.wrong_r_attempts and not self.recovery_p_seen:
                    self.recovery_p_seen = True
                    self.awaiting_recovery_ready_payload = True
                    self._record('retained-response-p-forwarded', frame=text)
            elif command == ord('R') and self.fault_applied:
                aux = frame[2] | (frame[3] << 8)
                if not self.recovery_p_seen:
                    self.wrong_r_attempts.append(text)
                    self._record('wrong-length-r-forwarded', frame=text, aux=aux)
                elif not self.recovery_r_seen:
                    self.recovery_r_seen = True
                    self.awaiting_recovery_r_payload = True
                    self._record('retained-response-r-forwarded', frame=text, aux=aux)
        return None

    def _from_hub(self, data):
        outgoing = super()._from_hub(data)
        # Data from Altirra to the endpoint has a trailing NetSIO sequence.
        # Preserve it, but retain exact SIO W bytes/checksum for the selected
        # original and distinct File operations.
        if self.pending_w_payload and not self.command_active:
            if data[:1] == b'\x02' and len(data) > 2:
                self.w_payloads.setdefault(self.pending_w_payload, bytearray()).extend(data[1:-1])
            elif data[:1] in (b'\x01', b'\x09') and len(data) >= 2:
                self.w_checksums[self.pending_w_payload] = data[1]
                self._record('file-w-data-forwarded', which=self.pending_w_payload,
                             payload=bytes(self.w_payloads.get(self.pending_w_payload, ())).hex(' '),
                             checksum=f'{data[1]:02x}')
                self.pending_w_payload = None
        return outgoing

    def _from_endpoint(self, data):
        outgoing = bytearray(data)
        if self.awaiting_recovery_r_payload and data[:1] == b'\x02':
            self.recovery_r_payload = bytes(data[1:])
            self._record('retained-response-r-data-forwarded',
                         payload=self.recovery_r_payload.hex(' '))
        elif (self.awaiting_recovery_r_payload and self.recovery_r_payload is not None and
              len(data) == 2 and data[0] == 0x01):
            self.recovery_r_checksum = data[1]
            self.awaiting_recovery_r_payload = False
            self._record('retained-response-r-checksum-forwarded', checksum=f'{data[1]:02x}')
        if self.awaiting_ready_payload and data[:1] == b'\x02':
            # Endpoint-to-hub DATA_BLOCK consists of its type followed by SIO
            # bytes (unlike hub-to-endpoint commands, it has no trailing
            # NetSIO sequence byte).  P is exactly [state, length-lo,
            # length-hi]; reject any other payload rather than accidentally
            # mutating an unrelated endpoint reply.
            payload = bytes(data[1:])
            if len(payload) != 3 or payload[0] != 2 or not (payload[1] or payload[2]):
                self.failure = f'expected READY P payload, received {data.hex(" ")}'
                return bytes(outgoing)
            original_length = payload[1] | (payload[2] << 8)
            delivered_length = original_length - 1
            if delivered_length == 0:
                self.failure = 'cannot create a malformed zero-length READY reply'
                return bytes(outgoing)
            delivered = bytes((payload[0], delivered_length & 0xff,
                               delivered_length >> 8))
            outgoing[1:] = delivered
            self.ready_payload = payload
            self.delivered_ready_payload = delivered
            self.awaiting_ready_payload = False
            self.awaiting_ready_checksum = True
            self._record('ready-length-corrupted', original=payload.hex(' '),
                         delivered=delivered.hex(' '))
        elif self.awaiting_ready_checksum and len(data) == 2 and data[0] == 0x01:
            self.ready_checksums = {'original': data[1],
                                    'delivered': _sio_checksum(self.delivered_ready_payload)}
            outgoing[1] = self.ready_checksums['delivered']
            self.awaiting_ready_checksum = False
            self.fault_applied = True
            self._record('ready-checksum-recomputed',
                         original=f'{data[1]:02x}', delivered=f'{outgoing[1]:02x}')
        elif self.awaiting_recovery_ready_payload and data[:1] == b'\x02':
            payload = bytes(data[1:])
            if payload != self.ready_payload:
                self.failure = ('retained response P did not report the original READY bytes: ' +
                                data.hex(' '))
                return bytes(outgoing)
            self.recovery_ready_payload = payload
            self.awaiting_recovery_ready_payload = False
            self.awaiting_recovery_ready_checksum = True
            self._record('retained-response-ready-forwarded', payload=payload.hex(' '))
        elif self.awaiting_recovery_ready_checksum and len(data) == 2 and data[0] == 0x01:
            self.recovery_ready_checksum = data[1]
            self.awaiting_recovery_ready_checksum = False
            self._record('retained-response-ready-checksum-forwarded',
                         checksum=f'{data[1]:02x}')
        if (self.fault_applied and self.wrong_r_attempts and not self.recovery_p_seen and
                ((data == b'\x01N') or
                 (len(data) == 6 and data[0] == 0x81 and data[3] == ord('N')))):
            self.wrong_r_naks.append(data.hex(' '))
            self._record('wrong-length-r-nak-forwarded', datagram=data.hex(' '))
        return bytes(outgoing)

    def _run(self):
        try:
            while not self.stop_requested.is_set():
                readable, _, _ = select.select((self.sock,), (), (), .05)
                if not readable:
                    continue
                data, source = self.sock.recvfrom(1024)
                if source[1] == self.hub[1]:
                    outgoing = self._from_hub(data)
                    if self.endpoint is not None:
                        self.sock.sendto(outgoing, self.endpoint)
                    continue
                if self.endpoint is None:
                    self.endpoint = source
                    self.endpoint_registered.set()
                    self._record('endpoint-registered', endpoint=f'{source[0]}:{source[1]}')
                if source != self.endpoint:
                    self._record('unexpected-source', endpoint=f'{source[0]}:{source[1]}')
                    continue
                self.sock.sendto(self._from_endpoint(data), self.hub)
        except Exception as exc:
            self.failure = str(exc)

    def stop(self):
        self.stop_requested.set()
        self.thread.join(2)
        self.sock.close()
        summary = {
            'format': 'atari-netsio-ready-length-relay-v1',
            'selected_w_ordinal': 2,
            'selected_aux': self.selected_aux.hex(' ') if self.selected_aux else None,
            'ready_payload': self.ready_payload.hex(' ') if self.ready_payload else None,
            'delivered_ready_payload': (self.delivered_ready_payload.hex(' ')
                                        if self.delivered_ready_payload else None),
            'ready_checksums': self.ready_checksums,
            'recovery_ready_payload': (self.recovery_ready_payload.hex(' ')
                                       if self.recovery_ready_payload else None),
            'recovery_ready_checksum': self.recovery_ready_checksum,
            'wrong_r_attempts': self.wrong_r_attempts,
            'wrong_r_naks': self.wrong_r_naks,
            'recovery_p_seen': self.recovery_p_seen,
            'recovery_r_seen': self.recovery_r_seen,
            'distinct_w_seen': self.distinct_w_seen,
            'command_frames': self.command_frames,
            'w_payloads': {key: bytes(value).hex(' ') for key, value in self.w_payloads.items()},
            'w_checksums': self.w_checksums,
            'recovery_r_payload': (self.recovery_r_payload.hex(' ')
                                   if self.recovery_r_payload else None),
            'recovery_r_checksum': self.recovery_r_checksum,
            'fault_applied': self.fault_applied,
            'failure': self.failure,
            'events': self.events,
        }
        path = self.run_dir / 'netsio-ready-length-relay.json'
        path.write_text(json.dumps(summary, indent=2) + '\n')
        return summary, path


class NetSioPublicTerminalRChecksumRelay(NetSioRejectedFileWRelay):
    """Corrupt only a consumed public File Write terminal-R delivery.

    The relay selects the public guest's second native W (the original File
    Write), lets its real P(READY) and correct-length R reach the production
    endpoint, then changes only the final SIO checksum travelling back to
    Altirra.  It records any OS R retries, which must be NAKed because the
    frontend consumed the response before the downstream corruption.  The
    later public call must observe P(IDLE) before its distinct W.
    """
    def __init__(self, run_dir, listen_port=9997, hub_port=9998):
        super().__init__(run_dir, listen_port, hub_port)
        self.thread = threading.Thread(target=self._run,
                                       name='netsio-public-terminal-r-relay', daemon=True)
        self.selected = False
        self.command_frames = []
        self.pending_w_payload = None
        self.w_payloads = {}
        self.w_checksums = {}
        self.initial_p_seen = False
        self.awaiting_ready_payload = False
        self.awaiting_ready_checksum = False
        self.ready_payload = None
        self.ready_checksum = None
        self.terminal_r_forwarded = False
        self.terminal_r_frame = None
        self.terminal_r_controls = []
        self.terminal_r_response = None
        self.terminal_r_checksum = None
        self.terminal_r_delivered_checksum = None
        self.fault_applied = False
        self.terminal_r_retries = []
        self.terminal_r_retry_naks = []
        self.awaiting_idle_payload = False
        self.awaiting_idle_checksum = False
        self.idle_payload = None
        self.idle_checksum = None
        self.idle_controls = []
        self.idle_p_seen = False
        self.distinct_w_seen = False

    def _complete_command(self, frame):
        if len(frame) != 5 or frame[0] != 0x7f:
            return None
        command = frame[1]
        text = frame.hex(' ')
        if command == ord('W'):
            self.native_w_count += 1
            if self.native_w_count == 2:
                self.selected = True
                self.selected_aux = frame[2:4]
                self.pending_w_payload = 'initial'
                self._record('selected-file-w', frame=text,
                             aux=self.selected_aux.hex(' '))
            elif self.selected and self.idle_p_seen and not self.distinct_w_seen:
                self.distinct_w_seen = True
                self.pending_w_payload = 'distinct'
                self._record('distinct-file-w-forwarded', frame=text,
                             aux=frame[2:4].hex(' '))
            elif self.selected and self.fault_applied and not self.idle_p_seen:
                self._record('unexpected-w-before-idle', frame=text)
        if not self.selected:
            return None
        self.command_frames.append(text)
        if command == ord('P'):
            if not self.initial_p_seen:
                self.initial_p_seen = True
                self.awaiting_ready_payload = True
                self._record('selected-ready-p-forwarded', frame=text)
            elif self.fault_applied and not self.idle_p_seen:
                self.awaiting_idle_payload = True
                self._record('post-interruption-p-forwarded', frame=text)
        elif command == ord('R'):
            if not self.terminal_r_forwarded:
                self.terminal_r_forwarded = True
                self.terminal_r_frame = text
                self._record('accepted-terminal-r-forwarded', frame=text,
                             aux=frame[2] | (frame[3] << 8))
            elif self.fault_applied and not self.idle_p_seen:
                self.terminal_r_retries.append(text)
                self._record('consumed-terminal-r-retry-forwarded', frame=text,
                             aux=frame[2] | (frame[3] << 8))
        return None

    def _from_hub(self, data):
        outgoing = super()._from_hub(data)
        if self.pending_w_payload and not self.command_active:
            if data[:1] == b'\x02' and len(data) > 2:
                self.w_payloads.setdefault(self.pending_w_payload, bytearray()).extend(data[1:-1])
            elif data[:1] in (b'\x01', b'\x09') and len(data) >= 2:
                self.w_checksums[self.pending_w_payload] = data[1]
                self._record('file-w-data-forwarded', which=self.pending_w_payload,
                             payload=bytes(self.w_payloads.get(self.pending_w_payload, ())).hex(' '),
                             checksum=f'{data[1]:02x}')
                self.pending_w_payload = None
        return outgoing

    @staticmethod
    def _is_nak(data):
        return data == b'\x01N' or (len(data) == 6 and data[0] == 0x81 and data[3] == ord('N'))

    def _from_endpoint(self, data):
        outgoing = bytearray(data)
        if self.awaiting_ready_payload and data[:1] == b'\x02':
            payload = bytes(data[1:])
            if len(payload) != 3 or payload[0] != 2 or not (payload[1] or payload[2]):
                self.failure = f'expected initial READY P payload, received {data.hex(" ")}'
            else:
                self.ready_payload = payload
                self.awaiting_ready_payload = False
                self.awaiting_ready_checksum = True
                self._record('ready-forwarded', payload=payload.hex(' '))
        elif self.awaiting_ready_checksum and len(data) == 2 and data[0] == 0x01:
            self.ready_checksum = data[1]
            self.awaiting_ready_checksum = False
            self._record('ready-checksum-forwarded', checksum=f'{data[1]:02x}')

        if self.terminal_r_forwarded and not self.fault_applied:
            if len(data) == 6 and data[0] == 0x81 and data[2:4] == b'\x01A':
                self.terminal_r_controls.append('A')
            elif data == b'\x01C':
                self.terminal_r_controls.append('C')
            elif data[:1] == b'\x02':
                self.terminal_r_response = bytes(data[1:])
                self._record('accepted-terminal-r-response-forwarded',
                             payload=self.terminal_r_response.hex(' '))
            elif (self.terminal_r_response is not None and len(data) == 2 and
                  data[0] == 0x01):
                self.terminal_r_checksum = data[1]
                outgoing[1] ^= 0x01
                self.terminal_r_delivered_checksum = outgoing[1]
                self.fault_applied = True
                self._record('terminal-r-checksum-corrupted', original=f'{data[1]:02x}',
                             delivered=f'{outgoing[1]:02x}')

        if (self.fault_applied and self.terminal_r_retries and not self.idle_p_seen and
                self._is_nak(data)):
            self.terminal_r_retry_naks.append(data.hex(' '))
            self._record('consumed-terminal-r-retry-nak-forwarded', datagram=data.hex(' '))

        if self.awaiting_idle_payload and data[:1] == b'\x02':
            payload = bytes(data[1:])
            if payload != b'\0\0\0':
                self.failure = f'expected post-interruption P(IDLE), received {data.hex(" ")}'
            else:
                self.idle_payload = payload
                self.idle_p_seen = True
                self.awaiting_idle_payload = False
                self.awaiting_idle_checksum = True
                self._record('post-interruption-idle-forwarded', payload=payload.hex(' '))
        elif self.awaiting_idle_checksum and len(data) == 2 and data[0] == 0x01:
            self.idle_checksum = data[1]
            self.awaiting_idle_checksum = False
            self._record('post-interruption-idle-checksum-forwarded', checksum=f'{data[1]:02x}')
        if self.awaiting_idle_payload or self.awaiting_idle_checksum:
            if len(data) == 6 and data[0] == 0x81 and data[2:4] == b'\x01A':
                self.idle_controls.append('A')
            elif data == b'\x01C':
                self.idle_controls.append('C')
        return bytes(outgoing)

    def _run(self):
        try:
            while not self.stop_requested.is_set():
                readable, _, _ = select.select((self.sock,), (), (), .05)
                if not readable:
                    continue
                data, source = self.sock.recvfrom(1024)
                if source[1] == self.hub[1]:
                    outgoing = self._from_hub(data)
                    if self.endpoint is not None:
                        self.sock.sendto(outgoing, self.endpoint)
                    continue
                if self.endpoint is None:
                    self.endpoint = source
                    self.endpoint_registered.set()
                    self._record('endpoint-registered', endpoint=f'{source[0]}:{source[1]}')
                if source != self.endpoint:
                    self._record('unexpected-source', endpoint=f'{source[0]}:{source[1]}')
                    continue
                self.sock.sendto(self._from_endpoint(data), self.hub)
        except Exception as exc:
            self.failure = str(exc)

    def stop(self):
        self.stop_requested.set()
        self.thread.join(2)
        self.sock.close()
        summary = {
            'format': 'atari-netsio-public-terminal-r-checksum-relay-v1',
            'selected_w_ordinal': 2,
            'selected_aux': self.selected_aux.hex(' ') if self.selected_aux else None,
            'command_frames': self.command_frames,
            'w_payloads': {key: bytes(value).hex(' ') for key, value in self.w_payloads.items()},
            'w_checksums': self.w_checksums,
            'ready_payload': self.ready_payload.hex(' ') if self.ready_payload else None,
            'ready_checksum': self.ready_checksum,
            'terminal_r_frame': self.terminal_r_frame,
            'terminal_r_controls': self.terminal_r_controls,
            'terminal_r_response': (self.terminal_r_response.hex(' ')
                                    if self.terminal_r_response else None),
            'terminal_r_checksum': self.terminal_r_checksum,
            'terminal_r_delivered_checksum': self.terminal_r_delivered_checksum,
            'fault_applied': self.fault_applied,
            'terminal_r_retries': self.terminal_r_retries,
            'terminal_r_retry_naks': self.terminal_r_retry_naks,
            'idle_payload': self.idle_payload.hex(' ') if self.idle_payload else None,
            'idle_checksum': self.idle_checksum,
            'idle_controls': self.idle_controls,
            'idle_p_seen': self.idle_p_seen,
            'distinct_w_seen': self.distinct_w_seen,
            'failure': self.failure,
            'events': self.events,
        }
        path = self.run_dir / 'netsio-public-terminal-r-relay.json'
        path.write_text(json.dumps(summary, indent=2) + '\n')
        return summary, path


def inspect_launch(token, evidence_dir=None):
    sys.path[:0]=[str(SDK)]
    from altirra_bridge import AltirraBridge
    with AltirraBridge.from_token_file(token) as b:
        # Do not pause the machine: startup pauses can divert an XL into Self
        # Test, and a blocking pause request can itself deadlock while a raw
        # SIO custom-device callback is active.  Two live samples establish
        # that execution has entered the program's stable three-byte loop.
        signature = b.peek(0x06F0,4)
        regs = b.regs()
        raw_pc = regs['PC']
        pc = int(raw_pc.replace('$', '0x'), 0) if isinstance(raw_pc, str) else raw_pc
        dcb = b.peek(0x0300, 12)
        time.sleep(.05)
        later_regs = b.regs()
        later_raw_pc = later_regs['PC']
        later_pc = int(later_raw_pc.replace('$', '0x'), 0) if isinstance(later_raw_pc, str) else later_raw_pc
        state = {
            'pc': f'0x{pc:04x}',
            'pc_later': f'0x{later_pc:04x}',
            'signature': signature.hex(),
            'page_6': b.peek(0x0600, 40).hex(),
            # The Atari OS DCB is retained even after a failed boot attempt.
            # This records the final SIO request/result without treating the
            # custom device as a second disk implementation.
            'terminal_dcb': decode_dcb(dcb),
            'cpu': {'p': regs.get('P'), 'flags': regs.get('flags')},
        }
        if evidence_dir:
            (evidence_dir / 'screen.png').write_bytes(b.screenshot())
            (evidence_dir / 'inspection.json').write_text(json.dumps(state, indent=2) + '\n')
        if signature == SIG and pc in LOOP_PCS and later_pc in LOOP_PCS:
            result = {'signature': signature.decode(), 'pc': f'0x{pc:04x}'}
            if evidence_dir:
                result['screenshot'] = str(evidence_dir / 'screen.png')
            return result
        raise RuntimeError(
            'signature/loop not reached: '
            f'signature={signature.hex()} pc=0x{pc:04x} later_pc=0x{later_pc:04x}'
        )

def cold_reset_after_device_ready(token):
    """Restart the Atari only after the NetSIO custom device has registered."""
    sys.path[:0] = [str(SDK)]
    from altirra_bridge import AltirraBridge
    with AltirraBridge.from_token_file(token) as b:
        b.cold_reset()

def capture_first_boot_read(token):
    """Pause at the OS SIO vector and record the actual first D1 READ DCB.

    This is diagnostic-only.  It observes the real Atari OS request before
    $E459 starts it, then removes the breakpoint and resumes ordinary boot.
    """
    sys.path[:0] = [str(SDK)]
    from altirra_bridge import AltirraBridge
    with AltirraBridge.from_token_file(token) as b:
        bp = b.bp_set(0xE459)
        samples = []
        try:
            for _ in range(12):
                b.cycles(10_000_000)
                clock = b.clock()
                dcb = decode_dcb(b.peek(0x0300, 12))
                regs = b.regs()
                sample = {'clock': clock, 'dcb': dcb,
                          'pc': regs['PC'], 'p': regs['P'], 'flags': regs['flags']}
                samples.append(sample)
                if dcb['device'] == '0x31' and dcb['command'] == '0x52' and dcb['aux'] == 1:
                    # JSR has placed the caller address minus one on the 6502
                    # stack.  Break there as well, so the trace records the
                    # Atari OS SIO result (DCB + carry) after this exact read.
                    sp = int(regs['S'].replace('$', '0x'), 0)
                    ret_raw = b.peek(0x0100 + sp + 1, 2)
                    return_pc = (ret_raw[0] | (ret_raw[1] << 8)) + 1
                    b.bp_clear(bp)
                    bp = None
                    # The configured Rev.3 XL ROM classifies a non-A/C/E
                    # command response at $EA73 after preserving the received
                    # byte in $023E.  Capture that concrete failure point;
                    # do not infer NAK from hub traffic alone.
                    ack_bp = b.bp_set(0xEA73)
                    try:
                        b.cycles(10_000_000)
                        ack_clock = b.clock()
                        ack_regs = b.regs()
                        ack_sample = {
                            'clock': ack_clock,
                            'pc': ack_regs['PC'], 'p': ack_regs['P'],
                            'flags': ack_regs['flags'],
                            'received_byte': f'0x{b.peek(0x023E)[0]:02x}',
                            'sio_status': f'0x{b.peek(0x0030)[0]:02x}',
                            'dcb': decode_dcb(b.peek(0x0300, 12)),
                        }
                    finally:
                        b.bp_clear(ack_bp)
                    return_bp = b.bp_set(return_pc)
                    try:
                        b.cycles(10_000_000)
                        return_clock = b.clock()
                        return_regs = b.regs()
                        return_sample = {
                            'clock': return_clock,
                            'pc': return_regs['PC'], 'p': return_regs['P'],
                            'flags': return_regs['flags'],
                            'dcb': decode_dcb(b.peek(0x0300, 12)),
                            # The boot ROM asks for sector 1 at $0400.  Keep
                            # the returned bytes alongside the DCB result so
                            # a command/ACK failure is distinguishable from
                            # a later data or checksum failure.
                            'buffer_0400': b.peek(0x0400, 128).hex(),
                            'return_pc': f'0x{return_pc:04x}',
                        }
                    finally:
                        b.bp_clear(return_bp)
                        b.resume()
                    return {'first_d1_sector_1_read': sample,
                            'first_d1_sector_1_ack_wait': ack_sample,
                            'first_d1_sector_1_return': return_sample,
                            'preceding_siov': samples[:-1]}
                b.resume()
            raise RuntimeError('did not observe D1 sector-1 SIOV request')
        finally:
            if bp is not None:
                b.bp_clear(bp)
            b.resume()

def sha256(path):
    return hashlib.file_digest(path.open('rb'), 'sha256').hexdigest()

def first_read_trace(hub_log):
    """Extract the first D1/sector-1 response without relying on log order."""
    command = re.search(r'(?P<time>\d\d:\d\d:\d\d\.\d+) .*?31 52 01 00 84(?:\s|$)', hub_log)
    if not command:
        return {'present': False}
    tail = hub_log[command.end():]
    def event(pattern, name):
        match = re.search(r'(?P<time>\d\d:\d\d:\d\d\.\d+) .*?' + pattern, tail)
        if not match:
            raise RuntimeError(f'first sector-1 response lacks {name}')
        return match
    ack = event(r'81:SYNC_RESPONSE\[5\].*? 41 00 00', 'command ACK')
    complete = event(r'01:DATA_BYTE\[1\].*? 43(?:\s|$)', 'COMPLETE')
    payload = event(r'02:DATA_BLOCK\[128\] \+\d+ (?P<data>(?:[0-9A-F]{2} ?){128})', '128-byte payload')
    checksum = event(r'01:DATA_BYTE\[1\].*? (?P<checksum>[0-9A-F]{2})(?:\s|$)', 'checksum')
    # Restrict the checksum match to traffic after the payload; the command
    # response's COMPLETE is also a DATA_BYTE event.
    payload_end = tail[payload.end():]
    checksum = re.search(r'(?P<time>\d\d:\d\d:\d\d\.\d+) .*?< NET IN .*?01:DATA_BYTE\[1\] \+\d+ (?P<checksum>[0-9A-F]{2})(?:\s|$)', payload_end)
    if not checksum:
        raise RuntimeError('first sector-1 response lacks checksum')
    def seconds(value):
        h, m, s = value.split(':')
        return int(h) * 3600 + int(m) * 60 + float(s)
    t0 = seconds(command['time'])
    data = bytes.fromhex(payload['data'])
    computed = sum(data)
    while computed > 0xff:
        computed = (computed & 0xff) + (computed >> 8)
    return {
        'present': True, 'command_frame': '31 52 01 00 84',
        'command_at': command['time'],
        'ack': {'byte': '41', 'at': ack['time'], 'after_ms': round((seconds(ack['time']) - t0) * 1000, 3)},
        'complete': {'byte': '43', 'at': complete['time'], 'after_ms': round((seconds(complete['time']) - t0) * 1000, 3)},
        'payload': {'bytes': len(data), 'at': payload['time'], 'after_ms': round((seconds(payload['time']) - t0) * 1000, 3)},
        'checksum': {'sent': checksum['checksum'], 'computed': f'{computed:02X}',
                     'valid': int(checksum['checksum'], 16) == computed,
                     'at': checksum['time'],
                     'after_ms': round((seconds(checksum['time']) - t0) * 1000, 3)},
    }

def verify_netsio_trace(hub_log, nio_log):
    """Assert the compact, production-path SIO trace required by Story 1.3."""
    required_hub_frames = (
        '31 53 00 00 84',  # D1 STATUS
        '31 52 01 00 84',  # OS boot sector 1 (128 bytes)
        '31 52 02 00 85',  # OS boot sector 2 (128 bytes)
        '31 52 03 00 86',  # OS boot sector 3 (128 bytes)
        '31 52 69 01 ED',  # DD sector 361 (256 bytes)
    )
    for frame in required_hub_frames:
        if frame not in hub_log:
            raise RuntimeError(f'missing required D1 command frame: {frame}')
    if 'DATA_BLOCK[256]' not in hub_log[hub_log.index(required_hub_frames[-1]):]:
        raise RuntimeError('DD sector 361 lacks a following 256-byte NetSIO block')
    # The cumulative DiskService counters prove the first three transfers were
    # 128 bytes.  The OS may retry sector 1, so locate the counter immediately
    # before and after the explicit sector-361 command rather than assuming a
    # fixed request number.
    if 'read_req=3 read_sec=3 read_bytes=384' not in nio_log:
        raise RuntimeError('boot-sector byte count is not three 128-byte reads')
    events = []
    for match in re.finditer(r'Received 7 bytes: 02 31 52 ([0-9A-F]{2}) ([0-9A-F]{2}) [0-9A-F]{2} [0-9A-F]{2}|diskstats:.*?read_bytes=(\d+)', nio_log):
        if match.group(3):
            events.append(('bytes', int(match.group(3))))
        else:
            events.append(('read', int(match.group(1), 16) | (int(match.group(2), 16) << 8)))
    previous_bytes = 0
    dd_delta = None
    pending_sector = None
    for kind, value in events:
        if kind == 'read':
            pending_sector = value
        elif pending_sector is not None:
            if pending_sector == 361:
                dd_delta = value - previous_bytes
                break
            previous_bytes = value
            pending_sector = None
    if dd_delta != 256:
        raise RuntimeError('sector 361 did not complete as a 256-byte read')
    return {
        'd1_status': required_hub_frames[0],
        'boot_reads_128': list(required_hub_frames[1:4]),
        'first_dd_read_256': required_hub_frames[4],
        'diskservice_counters': {
            'after_boot_sectors': 'read_req=3 read_sec=3 read_bytes=384',
            'sector_361_delta_bytes': 256,
        },
    }

def altirra_command(native, command_ack_delay_tics=None, trace_serial=False, program=None):
    sys.path.insert(0,str(ROOT)); os.environ['ALTIRRA_BIN']=str(ALTIRRA)
    from tools.atari_emulator.altirra import build_command
    profile = PROFILE
    profile_tmp = None
    if command_ack_delay_tics is not None:
        profile_tmp = tempfile.TemporaryDirectory(prefix='story13-ack-delay-')
        text = PROFILE.read_text()
        text, changed = re.subn(r'(netsio_command_ack_delay_tics:\s*)\d+',
                                rf'\g<1>{command_ack_delay_tics}', text, count=1)
        if changed != 1:
            raise RuntimeError('Altirra profile lacks netsio_command_ack_delay_tics')
        profile = Path(profile_tmp.name) / PROFILE.name
        profile.write_text(text)
    ns=argparse.Namespace(profile=profile, emulators=ROOT/'configs/atari/emulators.yaml',symbols=None,dry_run=False,program=program,disk=[])
    cmd, env, tmp=build_command(ns)
    if native:
        while '--adddevice' in cmd:
            i=cmd.index('--adddevice'); del cmd[i:i+2]
        cmd.append(str(ATR))
    if trace_serial:
        # The caller appends the SIODATA logger after choosing its evidence
        # directory.  Debug commands start in suspend mode, so run_netsio
        # explicitly resumes once the bridge is reachable.
        cmd.extend(['--debugcmd', 'lfe SIODATA'])
    cmd.append('--bridge=tcp:127.0.0.1:0')
    merged=os.environ.copy(); merged.update(env)
    return cmd, merged, (tmp, profile_tmp)

def launch(cmd, **kwargs):
    return subprocess.Popen(cmd, start_new_session=True, **kwargs)

def cleanup_temps(temps):
    for tmp in temps:
        if tmp:
            tmp.cleanup()

def run_native(timeout, evidence_dir=None, observe=False):
    before=set(Path('/tmp').glob('altirra-bridge-*.token')); cmd,env,temps=altirra_command(True)
    p=launch(cmd,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        if observe:
            time.sleep(timeout)
            return {'observed_seconds': timeout}
        token = fresh_token(before)
        time.sleep(timeout)
        native_evidence = evidence_dir / 'native' if evidence_dir else None
        if native_evidence: native_evidence.mkdir(exist_ok=True)
        return inspect_launch(token, native_evidence)
    finally: stop([p]); cleanup_temps(temps)

def legacy_config(path):
    """Create the smallest local-SD/D1/NetSIO legacy-FujiNet control config."""
    path.write_text('''[General]
configenabled=0
boot_mode=0
fnconfig_on_spifs=0

[Host1]
type=SD
name=SD

[Mount1]
hostslot=1
path=/boot/atari/autorun.atr
mode=r

[BOIP]
enabled=1
host=127.0.0.1
port=9997
''')

def run_netsio(timeout, evidence_dir=None, settle=0.0, capture_dcb=False, command_ack_delay_tics=None, trace_serial=False, backend='nio', explicit_cold_reset=False):
    run=evidence_dir / 'netsio' if evidence_dir else Path(tempfile.mkdtemp(prefix='story13-boot-'))
    # Sidecars are launched with this directory as cwd.  Resolve it before
    # passing paths to either backend: legacy FujiNet accepts `-c`/`-s` paths
    # verbatim whereas NIO discovers its data directory relative to cwd.
    run=run.resolve(); run.mkdir(parents=True, exist_ok=True); ps=[]
    try:
        data=run/'fujinet-data'; target=data/'boot/atari/autorun.atr'; target.parent.mkdir(parents=True); shutil.copy2(ATR,target)
        if backend == 'nio':
            (data/'fujinet.yaml').write_text('boot:\n  mode: config\n  config_uri: persist:/boot/atari/autorun.atr\n  readonly: true\nnetsio:\n  enabled: true\n  host: 127.0.0.1\n  port: 9997\n')
        elif backend == 'legacy':
            legacy_fujinet, legacy_runner = legacy_paths()
            if not legacy_fujinet.is_file() or not legacy_runner.is_file():
                raise RuntimeError(f'legacy FujiNet control is unavailable: {legacy_fujinet}')
            legacy_config(run / 'legacy-fnconfig.ini')
        else:
            raise ValueError(f'unknown backend: {backend}')
        hub=(run/'hub.log').open('wb'); nio=(run/'nio.log').open('wb'); altirra_log=None
        ps.append(launch([sys.executable,'-u','-m','netsiohub','-d','--port','9996','--netsio-port','9997'],cwd=HUB,stdout=hub,stderr=subprocess.STDOUT))
        # The NIO channel's DEVICE_CONNECT is sent in its constructor.  Starting
        # it before UDP bind completes loses that one registration datagram and
        # makes every Atari STATUS request look like an absent device.
        wait_log(run/'hub.log', 'Listening for NetSIO packets on port 9997')
        if backend == 'nio':
            ps.append(launch([str(NIO)],cwd=run,stdout=nio,stderr=subprocess.STDOUT))
            ready_line = 'NetSIO protocol initialized'
        else:
            # Legacy NetSIO deliberately exits with 75 on an emulator cold
            # reset. Its supplied supervisor is therefore part of the normal
            # legacy lifecycle, not an optional convenience wrapper.
            ps.append(launch([str(legacy_runner), '-c', str(run / 'legacy-fnconfig.ini'),
                              '-s', str(data)], cwd=legacy_runner.parent,
                             stdout=nio, stderr=subprocess.STDOUT))
            ready_line = '### NetSIO initialized ###'
        wait_log(run/'nio.log', ready_line, timeout=15)
        if settle:
            # Explicitly prove config D1 projection before the optional
            # diagnostic settle; this is stronger than transport init alone.
            wait_log(run/'nio.log', 'Applied 1 boot config mount')
            time.sleep(settle)
        before=set(Path('/tmp').glob('altirra-bridge-*.token')); cmd,env,temps=altirra_command(False, command_ack_delay_tics, trace_serial)
        if trace_serial:
            cmd.extend(['--debugcmd', f'.logopen {run / "pokey-siodata.log"}'])
        altirra_log=(run/'altirra.log').open('wb')
        ps.append(launch(cmd,cwd=run,env=env,stdout=altirra_log,stderr=subprocess.STDOUT))
        token = fresh_token(before)
        if explicit_cold_reset:
            # The sidecars are already connected and the script VM has
            # installed its reset handlers. This prevents an early emulator
            # power-on race from reaching the XL ROM before NetSIO activation.
            wait_log(run / 'altirra.log', 'NetSIO Cold Reset', timeout=15)
            cold_reset_after_device_ready(token)
        if trace_serial:
            sys.path[:0] = [str(SDK)]
            from altirra_bridge import AltirraBridge
            with AltirraBridge.from_token_file(token) as b:
                b.resume()
        dcb_trace = capture_first_boot_read(token) if capture_dcb else None
        if dcb_trace:
            (run / 'first-read-dcb.json').write_text(json.dumps(dcb_trace, indent=2) + '\n')
        # The sidecars precede Altirra and the emulator must run naturally
        # through its power-on boot before inspection.  This is intentionally
        # a short wall-clock allowance, not a frame-stepping timeout.
        time.sleep(timeout)
        text=(run/'nio.log').read_text(errors='replace'); trace=(run/'hub.log').read_text(errors='replace')
        # Legacy FujiNet groups terminal one-byte phases as DATA_BLOCK[1],
        # while NIO deliberately uses DATA_BYTE.  Preserve both raw hub logs;
        # the compact strict parser describes the NIO production contract.
        first_trace = first_read_trace(trace) if backend == 'nio' else {
            'present': '31 52 01 00 84' in trace,
            'phase_grouping': 'legacy DATA_BLOCK[1] for COMPLETE/checksum',
        }
        (run / 'first-read-sio.json').write_text(json.dumps(first_trace, indent=2) + '\n')
        result=inspect_launch(token, run)
        if dcb_trace:
            result['first_read_dcb'] = dcb_trace
        result['first_read_sio'] = first_trace
        # The NIO counters are intentionally production-specific; both paths
        # retain raw hub/POKEY logs for the actual protocol comparison.
        result['trace'] = verify_netsio_trace(trace, text) if backend == 'nio' else {'backend': 'legacy'}
        result['backend'] = backend
        result['run_dir']=str(run); return result
    finally:
        if 'altirra_log' in locals() and altirra_log: altirra_log.close()
        if 'hub' in locals(): hub.close()
        if 'nio' in locals(): nio.close()
        cleanup_temps(temps) if 'temps' in locals() else None
        stop(ps)

def inspect_native_core_dispatch(token, evidence_dir, timeout, wrong_r_retention=False, reset_to_idle=False,
                                 interrupted_r_recovery=False, capacity_bounds=False):
    """Wait for the real guest XEX and capture its independently checked data."""
    sys.path[:0] = [str(SDK)]
    from altirra_bridge import AltirraBridge
    deadline = time.monotonic() + timeout
    with AltirraBridge.from_token_file(token) as bridge:
        while time.monotonic() < deadline:
            result = bridge.peek(PROJECTION_RESULT, 4)
            if result in (b'NVP!', b'NVF!'):
                state = {
                    'guest_result': result.decode('ascii'),
                    'step': bridge.peek(PROJECTION_RESULT + 4, 1).hex(),
                    'q_reply': bridge.peek(PROJECTION_Q_REPLY, 4).hex(' '),
                    'p_ready': bridge.peek(PROJECTION_P_READY, 3).hex(' '),
                    'r_reply': bridge.peek(PROJECTION_R_REPLY, 9).hex(' '),
                    'p_idle': bridge.peek(PROJECTION_P_IDLE, 3).hex(' '),
                    'terminal_dcb': decode_dcb(bridge.peek(0x0300, 12)),
                }
                if wrong_r_retention:
                    state.update({
                        'wrong_r_status': bridge.peek(PROJECTION_STATUSES + 3, 1).hex(),
                        'p_retained': bridge.peek(PROJECTION_P_RETAIN, 3).hex(' '),
                        'siov_statuses': bridge.peek(PROJECTION_STATUSES, 7).hex(' '),
                    })
                if reset_to_idle:
                    state.update({
                        'post_reset_idle': bridge.peek(PROJECTION_P_IDLE, 3).hex(' '),
                        'post_reset_ready': bridge.peek(PROJECTION_AFTER_READY, 3).hex(' '),
                        'post_reset_reply': bridge.peek(PROJECTION_AFTER_REPLY, 9).hex(' '),
                        'post_reset_terminal_idle': bridge.peek(PROJECTION_AFTER_IDLE, 3).hex(' '),
                        'siov_statuses': bridge.peek(PROJECTION_STATUSES, 8).hex(' '),
                    })
                if interrupted_r_recovery:
                    state.update({
                        'interrupted_r_status': bridge.peek(PROJECTION_STATUSES + 3, 1).hex(),
                        'post_interruption_idle': bridge.peek(PROJECTION_P_IDLE, 3).hex(' '),
                        'recovery_ready': bridge.peek(PROJECTION_AFTER_READY, 3).hex(' '),
                        'recovery_reply': bridge.peek(PROJECTION_AFTER_REPLY, 9).hex(' '),
                        'recovery_terminal_idle': bridge.peek(PROJECTION_AFTER_IDLE, 3).hex(' '),
                        'siov_statuses': bridge.peek(PROJECTION_STATUSES, 9).hex(' '),
                    })
                if capacity_bounds:
                    state.update({
                        'capacity_ready_512': bridge.peek(PROJECTION_P_READY, 3).hex(' '),
                        'capacity_idle_after_512': bridge.peek(PROJECTION_P_IDLE, 3).hex(' '),
                        'capacity_bounded_ready': bridge.peek(PROJECTION_AFTER_READY, 3).hex(' '),
                        'capacity_bounded_reply': bridge.peek(PROJECTION_AFTER_REPLY, 7).hex(' '),
                        'capacity_terminal_idle': bridge.peek(PROJECTION_AFTER_IDLE, 3).hex(' '),
                        'capacity_response': bridge.peek(PROJECTION_CAPACITY_RESPONSE, 512).hex(' '),
                        'capacity_canaries': {
                            'request_low': bridge.peek(PROJECTION_CAPACITY_REQUEST_GUARD_LOW, 1).hex(),
                            'request_high': bridge.peek(PROJECTION_CAPACITY_REQUEST_GUARD_HIGH, 1).hex(),
                            'response_low': bridge.peek(PROJECTION_CAPACITY_RESPONSE_GUARD_LOW, 1).hex(),
                            'response_high': bridge.peek(PROJECTION_CAPACITY_RESPONSE_GUARD_HIGH, 1).hex(),
                        },
                        'siov_statuses': bridge.peek(PROJECTION_STATUSES, 13).hex(' '),
                    })
                evidence_dir.joinpath('screen.png').write_bytes(bridge.screenshot())
                evidence_dir.joinpath('inspection.json').write_text(json.dumps(state, indent=2) + '\n')
                if result != b'NVP!':
                    raise RuntimeError(f"native projection guest failed at step {state['step']}")
                return state
            time.sleep(.05)
    raise RuntimeError('native projection guest did not reach a terminal result')

def run_netsio_native_core_dispatch(timeout, evidence_dir, wrong_r_retention=False, reset_to_idle=False,
                                    interrupted_r_recovery=False, capacity_bounds=False):
    """Run one literal native-v1 sequence through Altirra, hub, and NetSIO.

    This deliberately shares the deterministic boot runner's sidecars, reset
    ordering, Altirra profile, bridge, serial evidence, and cleanup.  The
    only alternate process is a real-core fixture route; it has no SIO peer.
    """
    if sum((wrong_r_retention, reset_to_idle, interrupted_r_recovery, capacity_bounds)) > 1:
        raise ValueError('native projection variants are mutually exclusive')
    scenario_id = ('native-capacity-bounds' if capacity_bounds else
                   'native-interrupted-r-recovery' if interrupted_r_recovery else
                   'native-reset-to-idle' if reset_to_idle else
                   'native-wrong-r-retention' if wrong_r_retention else 'native-core-dispatch')
    program = (NATIVE_CAPACITY_BOUNDS_XEX if capacity_bounds else
               NATIVE_INTERRUPTED_R_RECOVERY_XEX if interrupted_r_recovery else
               NATIVE_RESET_TO_IDLE_XEX if reset_to_idle else
               NATIVE_WRONG_R_RETENTION_XEX if wrong_r_retention else NATIVE_CORE_DISPATCH_XEX)
    if not program.is_file():
        raise RuntimeError(f'{scenario_id} XEX is missing: {program}')
    if not NATIVE_CORE_DISPATCH.is_file():
        raise RuntimeError(f'native-core-dispatch endpoint is missing: {NATIVE_CORE_DISPATCH}')
    run = (Path(evidence_dir) / scenario_id).resolve()
    run.mkdir(parents=True, exist_ok=True)
    ps=[]
    try:
        relay = NetSioTerminalRChecksumRelay(run) if interrupted_r_recovery else None
        if relay:
            relay.start()
        hub_port = '9998' if relay else '9997'
        hub=(run/'hub.log').open('wb'); nio=(run/'nio.log').open('wb'); altirra_log=None
        ps.append(launch([sys.executable, '-u', '-m', 'netsiohub', '-d', '--port', '9996', '--netsio-port', hub_port],
                         cwd=HUB, stdout=hub, stderr=subprocess.STDOUT))
        wait_log(run/'hub.log', f'Listening for NetSIO packets on port {hub_port}')
        endpoint_env = os.environ.copy()
        if capacity_bounds:
            # The 512-byte capture is evidence, not a sampled debug prefix.
            endpoint_env['FUJINET_FULL_PACKET_LOG'] = '1'
        ps.append(launch([str(NATIVE_CORE_DISPATCH), '--host', '127.0.0.1', '--port', '9997'],
                         cwd=run, env=endpoint_env, stdout=nio, stderr=subprocess.STDOUT))
        wait_log(run/'nio.log', 'Atari NetSIO projection initialized', timeout=15)
        before=set(Path('/tmp').glob('altirra-bridge-*.token'))
        cmd, env, temps = altirra_command(False, trace_serial=True, program=program)
        cmd.extend(['--debugcmd', f'.logopen {run / "pokey-siodata.log"}'])
        altirra_log=(run/'altirra.log').open('wb')
        ps.append(launch(cmd, cwd=run, env=env, stdout=altirra_log, stderr=subprocess.STDOUT))
        token=fresh_token(before)
        wait_log(run/'altirra.log', 'NetSIO Cold Reset', timeout=15)
        cold_reset_after_device_ready(token)
        sys.path[:0] = [str(SDK)]
        from altirra_bridge import AltirraBridge
        with AltirraBridge.from_token_file(token) as bridge:
            bridge.resume()
        reset_event = None
        if reset_to_idle:
            wait_for_projection_step(token, 4, timeout)
            reset_event = inject_netsio_device_reset(token, run / 'hub.log', run / 'nio.log', run, timeout)
        result=inspect_native_core_dispatch(token, run, timeout, wrong_r_retention, reset_to_idle,
                                            interrupted_r_recovery, capacity_bounds)
        altirra_log.flush()
        pokey = run / 'pokey-siodata.log'
        if not pokey.exists() or not pokey.stat().st_size:
            lines = [line for line in (run / 'altirra.log').read_text(errors='replace').splitlines()
                     if '[SIODATA]' in line]
            if not lines:
                raise RuntimeError('native-core-dispatch has no captured POKEY SIODATA diagnostics')
            pokey.write_text('\n'.join(lines) + '\n')
        result['run_dir']=str(run)
        if reset_event:
            result['reset_event'] = reset_event
        if relay:
            relay_summary, relay_path = relay.stop()
            relay = None
            if (relay_summary['failure'] or not relay_summary['fault_applied'] or
                    relay_summary['interrupted_r_attempts'] < 1):
                raise RuntimeError(f'interrupted-R relay did not corrupt accepted delivery: {relay_summary}')
            result['delivery_fault'] = relay_summary
            result['delivery_fault_evidence'] = str(relay_path)
        return result
    finally:
        if 'relay' in locals() and relay:
            relay.stop()
        if 'altirra_log' in locals() and altirra_log: altirra_log.close()
        if 'hub' in locals(): hub.close()
        if 'nio' in locals(): nio.close()
        cleanup_temps(temps) if 'temps' in locals() else None
        stop(ps)


def run_netsio_native_wrong_r_retention(timeout, evidence_dir):
    """Run the same production projection path with a wrong terminal R first."""
    return run_netsio_native_core_dispatch(timeout, evidence_dir, wrong_r_retention=True)


def run_netsio_native_reset_to_idle(timeout, evidence_dir):
    """Run an injected NetSIO reset while the first native reply is queued."""
    return run_netsio_native_core_dispatch(timeout, evidence_dir, reset_to_idle=True)


def run_netsio_native_interrupted_r_recovery(timeout, evidence_dir):
    """Run accepted R with only its carrier checksum invalidated in transit."""
    return run_netsio_native_core_dispatch(timeout, evidence_dir, interrupted_r_recovery=True)


def run_netsio_native_capacity_bounds(timeout, evidence_dir):
    """Run 511/512/513 packet bounds against the production NetSIO endpoint."""
    return run_netsio_native_core_dispatch(timeout, evidence_dir, capacity_bounds=True)


def _read_u16(bridge, address):
    return int.from_bytes(bridge.peek(address, 2), 'little')


def _validate_public_file_recovery_state(state):
    """A failed public exchange must stay failed while its distinct write works."""
    if (state['file_write_status'] == '00' or
            state['file_rejected_w_status'] != state['file_write_status'] or
            state['file_failure_status'] != state['file_write_status'] or
            state['file_recovery_attempted'] != '01' or
            state['file_recovery_kind'] != '01' or
            (state['file_recovery_write_status'],
             state['file_recovery_write_device_status'],
             state['file_recovery_write_response_length'],
             state['file_recovery_write_count'],
             state['file_recovery_verify']) != (
                '00', '00', 10, len(PUBLIC_API_FILE_RECOVERY_MARKER), '01')):
        raise RuntimeError(f"public API failed-File recovery mismatch: {state}")


def inspect_public_api_clock(token, evidence_dir, timeout, rejected_w_recovery=False,
                             malformed_r_recovery=False, interrupted_r_recovery=False):
    """Inspect the public Clock/File/Network guest result and execution."""
    sys.path[:0] = [str(SDK)]
    from altirra_bridge import AltirraBridge
    deadline = time.monotonic() + timeout
    with AltirraBridge.from_token_file(token) as bridge:
        while time.monotonic() < deadline:
            signature = bridge.peek(PUBLIC_API_RESULT, 4)
            if signature in (b'ADP!', b'ACF!'):
                state = {
                    'guest_result': signature.decode('ascii'),
                    'version': bridge.peek(PUBLIC_API_RESULT + 4, 1).hex(),
                    'stage': bridge.peek(PUBLIC_API_RESULT + 5, 1).hex(),
                    'init_status': bridge.peek(PUBLIC_API_RESULT + 6, 1).hex(),
                    'clock_status': bridge.peek(PUBLIC_API_RESULT + 7, 1).hex(),
                    'clock_value': bridge.peek(PUBLIC_API_CLOCK_TIME, 8).hex(' '),
                    'file_write_status': bridge.peek(PUBLIC_API_FILE_WRITE_STATUS, 1).hex(),
                    'file_write_device_status': bridge.peek(PUBLIC_API_FILE_WRITE_DEVICE_STATUS, 1).hex(),
                    'file_write_response_length': _read_u16(bridge, PUBLIC_API_FILE_WRITE_RESPONSE_LENGTH),
                    'file_write_count': _read_u16(bridge, PUBLIC_API_FILE_WRITE_COUNT),
                    'file_read_status': bridge.peek(PUBLIC_API_FILE_READ_STATUS, 1).hex(),
                    'file_read_device_status': bridge.peek(PUBLIC_API_FILE_READ_DEVICE_STATUS, 1).hex(),
                    'file_read_response_length': _read_u16(bridge, PUBLIC_API_FILE_READ_RESPONSE_LENGTH),
                    'file_read_count': _read_u16(bridge, PUBLIC_API_FILE_READ_COUNT),
                    'file_verify': bridge.peek(PUBLIC_API_FILE_VERIFY, 1).hex(),
                    'file_rejected_w_status': bridge.peek(PUBLIC_API_FILE_REJECTED_W_STATUS, 1).hex(),
                    'file_recovery_attempted': bridge.peek(PUBLIC_API_FILE_RECOVERY_ATTEMPTED, 1).hex(),
                    'file_recovery_write_status': bridge.peek(PUBLIC_API_FILE_RECOVERY_WRITE_STATUS, 1).hex(),
                    'file_recovery_write_device_status': bridge.peek(PUBLIC_API_FILE_RECOVERY_WRITE_DEVICE_STATUS, 1).hex(),
                    'file_recovery_write_response_length': _read_u16(
                        bridge, PUBLIC_API_FILE_RECOVERY_WRITE_RESPONSE_LENGTH),
                    'file_recovery_write_count': _read_u16(bridge, PUBLIC_API_FILE_RECOVERY_WRITE_COUNT),
                    'file_recovery_verify': bridge.peek(PUBLIC_API_FILE_RECOVERY_VERIFY, 1).hex(),
                    'file_failure_status': bridge.peek(PUBLIC_API_FILE_FAILURE_STATUS, 1).hex(),
                    'file_recovery_kind': bridge.peek(PUBLIC_API_FILE_RECOVERY_KIND, 1).hex(),
                    'network_open_status': bridge.peek(PUBLIC_API_NETWORK_OPEN_STATUS, 1).hex(),
                    'network_handle': _read_u16(bridge, PUBLIC_API_NETWORK_HANDLE),
                    'network_write_status': bridge.peek(PUBLIC_API_NETWORK_WRITE_STATUS, 1).hex(),
                    'network_write_count': _read_u16(bridge, PUBLIC_API_NETWORK_WRITE_COUNT),
                    'network_read_status': bridge.peek(PUBLIC_API_NETWORK_READ_STATUS, 1).hex(),
                    'network_read_count': _read_u16(bridge, PUBLIC_API_NETWORK_READ_COUNT),
                    'network_read_flags': bridge.peek(PUBLIC_API_NETWORK_READ_FLAGS, 1).hex(),
                    'network_verify': bridge.peek(PUBLIC_API_NETWORK_VERIFY, 1).hex(),
                    'network_close_status': bridge.peek(PUBLIC_API_NETWORK_CLOSE_STATUS, 1).hex(),
                    'network_reply': bridge.peek(PUBLIC_API_NETWORK_REPLY,
                                                 len(PUBLIC_API_NETWORK_REPLY_BYTES)).hex(' '),
                    'disk_info_status': bridge.peek(PUBLIC_API_DISK_INFO_STATUS, 1).hex(),
                    'disk_flags': bridge.peek(PUBLIC_API_DISK_FLAGS, 1).hex(),
                    'disk_slot': bridge.peek(PUBLIC_API_DISK_SLOT, 1).hex(),
                    'disk_type': bridge.peek(PUBLIC_API_DISK_TYPE, 1).hex(),
                    'disk_sector_size': _read_u16(bridge, PUBLIC_API_DISK_SECTOR_SIZE),
                    'disk_sector_count': int.from_bytes(
                        bridge.peek(PUBLIC_API_DISK_SECTOR_COUNT, 4), 'little'),
                    'disk_last_error': bridge.peek(PUBLIC_API_DISK_LAST_ERROR, 1).hex(),
                    'disk_write_status': bridge.peek(PUBLIC_API_DISK_WRITE_STATUS, 1).hex(),
                    'disk_flush_status': bridge.peek(PUBLIC_API_DISK_FLUSH_STATUS, 1).hex(),
                    'disk_read_status': bridge.peek(PUBLIC_API_DISK_READ_STATUS, 1).hex(),
                    'disk_write_length': _read_u16(bridge, PUBLIC_API_DISK_WRITE_LENGTH),
                    'disk_read_length': _read_u16(bridge, PUBLIC_API_DISK_READ_LENGTH),
                    'disk_verify': bridge.peek(PUBLIC_API_DISK_VERIFY, 1).hex(),
                    'memory_pre_dma': {
                        'magic': bridge.peek(PUBLIC_API_MEMORY_MAGIC, 4).decode('ascii', 'replace'),
                        'version': bridge.peek(PUBLIC_API_MEMORY_VERSION, 1)[0],
                        'memlo': _read_u16(bridge, PUBLIC_API_PRE_MEMLO),
                        'memtop': _read_u16(bridge, PUBLIC_API_PRE_MEMTOP),
                        'ramtop': bridge.peek(PUBLIC_API_PRE_RAMTOP, 1)[0],
                        'sdlstl': _read_u16(bridge, PUBLIC_API_PRE_SDLSTL),
                        'savmsc': _read_u16(bridge, PUBLIC_API_PRE_SAVMSC),
                        'sdmctl': bridge.peek(PUBLIC_API_PRE_SDMCTL, 1)[0],
                        'dmactl': bridge.peek(PUBLIC_API_PRE_DMACTL, 1)[0],
                        'dma_transition': bridge.peek(PUBLIC_API_HEADLESS_PROOF, 1)[0],
                    },
                }
                heartbeats = []
                for _ in range(4):
                    heartbeats.append(bridge.peek(PUBLIC_API_HEARTBEAT, 2).hex())
                    time.sleep(.02)
                state['heartbeats'] = heartbeats
                state['continued_execution'] = len(set(heartbeats)) > 1
                memory_report = layout_report(
                    ROOT / 'repos/nio-core-apps/build/atari/bin/fnaccept.map',
                    PUBLIC_API_CLOCK_XEX)
                state['memory_safety'] = validate_runtime_snapshot(
                    state['memory_pre_dma'], memory_report)
                evidence_dir.joinpath('screen.png').write_bytes(bridge.screenshot())
                evidence_dir.joinpath('inspection.json').write_text(json.dumps(state, indent=2) + '\n')
                if signature != b'ADP!':
                    raise RuntimeError(f"public API Clock/File/Network/Disk guest failed at stage {state['stage']}")
                if state['version'] != '06' or state['stage'] != '0e':
                    raise RuntimeError(f"public API Clock/File/Network/Disk guest has invalid result header: {state}")
                if state['init_status'] != '00' or state['clock_status'] != '00':
                    raise RuntimeError(f"public API Clock call did not succeed: {state}")
                if bytes.fromhex(state['clock_value']) != PUBLIC_API_CLOCK_BYTES:
                    raise RuntimeError(f"public API Clock value mismatch: {state['clock_value']}")
                if rejected_w_recovery or malformed_r_recovery or interrupted_r_recovery:
                    _validate_public_file_recovery_state(state)
                elif (state['file_write_status'], state['file_write_device_status'],
                      state['file_write_response_length'], state['file_write_count'],
                      state['file_recovery_attempted']) != (
                        '00', '00', 10, len(PUBLIC_API_FILE_MARKER), '00'):
                    raise RuntimeError(f"public API File write result mismatch: {state}")
                if (state['file_read_status'], state['file_read_device_status'],
                    state['file_read_response_length'], state['file_read_count'],
                    state['file_verify']) != (
                        '00', '00', 10 + (len(PUBLIC_API_FILE_RECOVERY_MARKER)
                                          if (rejected_w_recovery or malformed_r_recovery or interrupted_r_recovery)
                                          else len(PUBLIC_API_FILE_MARKER)),
                        len(PUBLIC_API_FILE_RECOVERY_MARKER)
                        if (rejected_w_recovery or malformed_r_recovery or interrupted_r_recovery)
                        else len(PUBLIC_API_FILE_MARKER), '01'):
                    raise RuntimeError(f"public API File readback result mismatch: {state}")
                if (state['network_open_status'], state['network_write_status'],
                    state['network_read_status'], state['network_close_status'],
                    state['network_write_count'], state['network_read_count'],
                    state['network_read_flags'], state['network_verify']) != (
                        '00', '00', '00', '00',
                        len(PUBLIC_API_NETWORK_WRITE_MARKER), len(PUBLIC_API_NETWORK_REPLY_BYTES),
                        '01', '01') or state['network_handle'] == 0xffff:
                    raise RuntimeError(f"public API Network call result mismatch: {state}")
                if bytes.fromhex(state['network_reply']) != PUBLIC_API_NETWORK_REPLY_BYTES:
                    raise RuntimeError(f"public API Network reply mismatch: {state}")
                if (state['disk_info_status'], state['disk_slot'],
                    state['disk_sector_size'], state['disk_sector_count'],
                    state['disk_last_error'], state['disk_write_status'],
                    state['disk_flush_status'], state['disk_read_status'],
                    state['disk_write_length'], state['disk_read_length'],
                    state['disk_verify']) != (
                        '00', f'{PUBLIC_API_DISK_SLOT_VALUE:02x}',
                        PUBLIC_API_DISK_SECTOR_BYTES, PUBLIC_API_DISK_SECTOR_COUNT_VALUE,
                        '00', '00', '00', '00',
                        PUBLIC_API_DISK_SECTOR_BYTES, PUBLIC_API_DISK_SECTOR_BYTES, '01'):
                    raise RuntimeError(f"public API Disk result mismatch: {state}")
                if (int(state['disk_flags'], 16) & 0x13) != 0x11:
                    raise RuntimeError(f"public API Disk geometry is not writable/inserted: {state}")
                if not state['continued_execution']:
                    raise RuntimeError('public API Clock/File/Network/Disk guest did not continue after its result')
                return state
            time.sleep(.05)
    raise RuntimeError('public API Clock/File guest did not reach a terminal result')


def _clock_native_commands(trace):
    commands = re.findall(r'udp: Received \d+ bytes: 02 7F ([0-9A-F]{2}) ', trace)
    expected = ['57', '50', '52'] * 11
    if commands != expected:
        raise RuntimeError(f'public API Clock/File/Network/Disk native command order is {commands}, expected {expected}')
    return commands


def _sio_checksum(data):
    total = sum(data)
    while total > 0xff:
        total = (total & 0xff) + (total >> 8)
    return total


def _validate_rejected_file_w_relay(summary):
    """Require literal malformed-W/NAK/direct-new-W relay evidence."""
    attempts = summary.get('rejected_attempts', ())
    naks = summary.get('endpoint_naks', ())
    if summary.get('failure') or not attempts or not naks:
        raise RuntimeError(f'rejected File W relay did not observe malformed command and NAK: {summary}')
    if len(naks) != len(attempts):
        raise RuntimeError(f'rejected File W physical retry/NAK count differs: {summary}')
    for attempt in attempts:
        original = bytes.fromhex(attempt['original'])
        delivered = bytes.fromhex(attempt['delivered'])
        if (len(original) != 5 or len(delivered) != 5 or original[:4] != delivered[:4] or
                original[1] != ord('W') or _sio_checksum(original[:4]) != original[4] or
                _sio_checksum(delivered[:4]) == delivered[4]):
            raise RuntimeError(f'rejected File W relay has invalid checksum mutation: {attempt}')
    commands = [bytes.fromhex(frame) for frame in summary.get('commands_after_rejection', ())]
    if (not summary.get('recovery_w_seen') or summary.get('unexpected_recovery_commands') or
            not commands or commands[0][1:2] != b'W'):
        raise RuntimeError(f'rejected File W recovery did not start directly with distinct W: {summary}')
    # The distinct Write and following Read are normal completed exchanges.
    if [command[1] for command in commands[:6]] != [ord('W'), ord('P'), ord('R'),
                                                      ord('W'), ord('P'), ord('R')]:
        raise RuntimeError(f'rejected File W recovery lacks direct W/P/R order: {summary}')


def _validate_ready_length_relay(summary):
    """Require accepted-W, bad-R retention, then P/R drain before new W."""
    if summary.get('failure') or not summary.get('fault_applied'):
        raise RuntimeError(f'ready-length relay failed to mutate a live P reply: {summary}')
    original = bytes.fromhex(summary.get('ready_payload') or '')
    delivered = bytes.fromhex(summary.get('delivered_ready_payload') or '')
    checksums = summary.get('ready_checksums', {})
    if (len(original) != 3 or len(delivered) != 3 or original[0] != 2 or delivered[0] != 2 or
            (original[1] | (original[2] << 8)) !=
            (delivered[1] | (delivered[2] << 8)) + 1 or
            checksums.get('original') != _sio_checksum(original) or
            checksums.get('delivered') != _sio_checksum(delivered)):
        raise RuntimeError(f'ready-length relay did not preserve a checksummed one-byte length fault: {summary}')
    if (bytes.fromhex(summary.get('recovery_ready_payload') or '') != original or
            summary.get('recovery_ready_checksum') != _sio_checksum(original)):
        raise RuntimeError(f'retained response P did not preserve original READY bytes: {summary}')
    frames = [bytes.fromhex(frame) for frame in summary.get('command_frames', ())]
    if len(frames) < 7 or any(len(frame) != 5 or frame[0] != 0x7f or
                              _sio_checksum(frame[:4]) != frame[4] for frame in frames):
        raise RuntimeError(f'ready-length relay captured malformed native command frames: {summary}')
    if [frame[1] for frame in frames[:2]] != [ord('W'), ord('P')]:
        raise RuntimeError(f'ready-length relay lacks selected W then P: {summary}')
    wrong_aux = delivered[1] | (delivered[2] << 8)
    right_aux = original[1] | (original[2] << 8)
    cursor = 2
    wrong_r_count = 0
    while cursor < len(frames) and frames[cursor][1] == ord('R'):
        if (frames[cursor][2] | (frames[cursor][3] << 8)) != wrong_aux:
            raise RuntimeError(f'wrong-length R did not use corrupted READY length: {summary}')
        wrong_r_count += 1
        cursor += 1
    def is_nak(datagram):
        value = bytes.fromhex(datagram)
        return value == b'\x01N' or (len(value) == 6 and value[0] == 0x81 and
                                     value[3] == ord('N'))
    if (not wrong_r_count or len(summary.get('wrong_r_naks', ())) != wrong_r_count or
            any(not is_nak(nak) for nak in summary.get('wrong_r_naks', ()) )):
        raise RuntimeError(f'wrong-length R physical attempts/NAKs are not one-to-one: {summary}')
    if cursor + 2 >= len(frames) or frames[cursor][1] != ord('P') or frames[cursor + 1][1] != ord('R'):
        raise RuntimeError(f'outstanding response was not recovered by P then R: {summary}')
    if (frames[cursor + 1][2] | (frames[cursor + 1][3] << 8)) != right_aux:
        raise RuntimeError(f'recovery terminal R did not use the original READY length: {summary}')
    if frames[cursor + 2][1] != ord('W'):
        raise RuntimeError(f'a new W did not wait for retained-response drain: {summary}')
    if (not summary.get('recovery_p_seen') or not summary.get('recovery_r_seen') or
            not summary.get('distinct_w_seen')):
        raise RuntimeError(f'ready-length recovery state was not completely observed: {summary}')
    def file_write_packet(uri, marker):
        body = bytes((1, len(uri) & 0xff, len(uri) >> 8)) + uri + b'\0\0\0\0' + \
            bytes((len(marker) & 0xff, len(marker) >> 8)) + marker
        packet = bytearray((0xfe, 4, (6 + len(body)) & 0xff, (6 + len(body)) >> 8, 0, 0)) + body
        packet[4] = _sio_checksum(packet[:4] + packet[5:])
        return bytes(packet)
    expected_w = {
        'initial': file_write_packet(PUBLIC_API_FILE_URI, PUBLIC_API_FILE_MARKER),
        'distinct': file_write_packet(PUBLIC_API_FILE_RECOVERY_URI,
                                      PUBLIC_API_FILE_RECOVERY_MARKER),
    }
    payloads = {key: bytes.fromhex(value) for key, value in summary.get('w_payloads', {}).items()}
    if (payloads != expected_w or any(summary.get('w_checksums', {}).get(key) != _sio_checksum(value)
                                      for key, value in expected_w.items())):
        raise RuntimeError(f'File W payload/checksum capture does not match literal guest operations: {summary}')
    if ((frames[0][2] | (frames[0][3] << 8)) != len(expected_w['initial']) or
            (frames[cursor + 2][2] | (frames[cursor + 2][3] << 8)) != len(expected_w['distinct'])):
        raise RuntimeError(f'File W AUX does not equal its complete captured payload length: {summary}')
    response = bytes.fromhex(summary.get('recovery_r_payload') or '')
    if (len(response) != right_aux or len(response) < 6 or response[:2] != b'\xfe\x04' or
            (response[2] | (response[3] << 8)) != len(response) or
            response[4] != _sio_checksum(response[:4] + response[5:]) or
            summary.get('recovery_r_checksum') != _sio_checksum(response)):
        raise RuntimeError(f'retained terminal-R raw packet/checksum is not exact: {summary}')


def _file_write_packet(uri, marker):
    body = (bytes((1, len(uri) & 0xff, len(uri) >> 8)) + uri + b'\0\0\0\0' +
            bytes((len(marker) & 0xff, len(marker) >> 8)) + marker)
    packet = bytearray((0xfe, 4, (6 + len(body)) & 0xff, (6 + len(body)) >> 8, 0, 0)) + body
    packet[4] = _sio_checksum(packet[:4] + packet[5:])
    return bytes(packet)


def _file_write_response(marker):
    # The production FileDevice v1 WriteFile response is a real FujiBus
    # response, not a relay fixture: status=OK followed by version, flags,
    # reserved, offset=0, and the documented written length.
    body = bytes((0, 1, 0, 0, 0, 0, 0, 0, 0, len(marker), 0))
    packet = bytearray((0xfe, 4, (6 + len(body)) & 0xff, (6 + len(body)) >> 8, 0, 1)) + body
    packet[4] = _sio_checksum(packet[:4] + packet[5:])
    return bytes(packet)


def _validate_public_terminal_r_relay(summary):
    """Require accepted-R consumption, corrupted delivery, P(IDLE), then W."""
    if summary.get('failure') or not summary.get('fault_applied'):
        raise RuntimeError(f'public terminal-R relay did not corrupt a live accepted response: {summary}')
    expected_w = {
        'initial': _file_write_packet(PUBLIC_API_FILE_URI, PUBLIC_API_FILE_MARKER),
        'distinct': _file_write_packet(PUBLIC_API_FILE_RECOVERY_URI,
                                       PUBLIC_API_FILE_RECOVERY_MARKER),
    }
    payloads = {key: bytes.fromhex(value) for key, value in summary.get('w_payloads', {}).items()}
    if (payloads != expected_w or
            any(summary.get('w_checksums', {}).get(key) != _sio_checksum(value)
                for key, value in expected_w.items())):
        raise RuntimeError(f'public terminal-R relay W payload/checksum mismatch: {summary}')
    frames = [bytes.fromhex(value) for value in summary.get('command_frames', ())]
    if (len(frames) < 5 or any(len(frame) != 5 or frame[0] != 0x7f or
                               _sio_checksum(frame[:4]) != frame[4] for frame in frames)):
        raise RuntimeError(f'public terminal-R relay captured malformed command frames: {summary}')
    if ([frame[1] for frame in frames[:3]] != [ord('W'), ord('P'), ord('R')] or
            (frames[0][2] | (frames[0][3] << 8)) != len(expected_w['initial'])):
        raise RuntimeError(f'public terminal-R relay lacks initial File W/P/R: {summary}')
    ready = bytes.fromhex(summary.get('ready_payload') or '')
    expected_response = _file_write_response(PUBLIC_API_FILE_MARKER)
    if (ready != bytes((2, len(expected_response), 0)) or
            summary.get('ready_checksum') != _sio_checksum(ready) or
            (frames[2][2] | (frames[2][3] << 8)) != len(expected_response)):
        raise RuntimeError(f'public terminal-R did not use the exact READY length: {summary}')
    response = bytes.fromhex(summary.get('terminal_r_response') or '')
    if (summary.get('terminal_r_controls') != ['A', 'C'] or response != expected_response or
            summary.get('terminal_r_checksum') != _sio_checksum(response) or
            summary.get('terminal_r_delivered_checksum') != (_sio_checksum(response) ^ 1)):
        raise RuntimeError(f'public terminal-R delivery was not accepted then checksum-corrupted: {summary}')
    cursor = 3
    retries = []
    while cursor < len(frames) and frames[cursor][1] == ord('R'):
        retries.append(frames[cursor])
        cursor += 1
    if (not retries or len(summary.get('terminal_r_retry_naks', ())) != len(retries) or
            any((frame[2] | (frame[3] << 8)) != len(expected_response) for frame in retries) or
            any(not NetSioPublicTerminalRChecksumRelay._is_nak(bytes.fromhex(value))
                for value in summary.get('terminal_r_retry_naks', ()))):
        raise RuntimeError(f'consumed terminal-R retries were not observed and NAKed one-for-one: {summary}')
    if (cursor + 1 >= len(frames) or frames[cursor][1] != ord('P') or
            frames[cursor + 1][1] != ord('W') or
            (frames[cursor][2] | (frames[cursor][3] << 8)) != 0 or
            (frames[cursor + 1][2] | (frames[cursor + 1][3] << 8)) != len(expected_w['distinct'])):
        raise RuntimeError(f'public recovery did not observe P(IDLE) before distinct W: {summary}')
    if (bytes.fromhex(summary.get('idle_payload') or '') != b'\0\0\0' or
            summary.get('idle_checksum') != 0 or summary.get('idle_controls') != ['A', 'C'] or
            not summary.get('idle_p_seen') or not summary.get('distinct_w_seen')):
        raise RuntimeError(f'public recovery P did not prove the consumed slot was IDLE: {summary}')


def run_netsio_public_api_clock(timeout, evidence_dir, rejected_w_recovery=False,
                                malformed_r_recovery=False, interrupted_r_recovery=False):
    """Run public Clock, File, Network, and Disk calls through NetSIO."""
    if sum((rejected_w_recovery, malformed_r_recovery, interrupted_r_recovery)) > 1:
        raise ValueError('public acceptance recovery faults are mutually exclusive')
    if not PUBLIC_API_CLOCK_XEX.is_file():
        raise RuntimeError(f'public API Clock XEX is missing: {PUBLIC_API_CLOCK_XEX}')
    if not PUBLIC_API_CLOCK_ENDPOINT.is_file():
        raise RuntimeError(f'public API Clock endpoint is missing: {PUBLIC_API_CLOCK_ENDPOINT}')
    run = (Path(evidence_dir) / 'public-api-clock').resolve()
    run.mkdir(parents=True, exist_ok=True)
    ps = []
    relay = None
    altirra_log = None
    try:
        relay = (NetSioPublicTerminalRChecksumRelay(run) if interrupted_r_recovery else
                 NetSioReadyLengthRelay(run) if malformed_r_recovery else
                 NetSioRejectedFileWRelay(run) if rejected_w_recovery else None)
        if relay:
            relay.start()
        hub_port = '9998' if relay else '9997'
        hub = (run / 'hub.log').open('wb')
        nio = (run / 'nio.log').open('wb')
        ps.append(launch([sys.executable, '-u', '-m', 'netsiohub', '-d', '--port', '9996', '--netsio-port', hub_port],
                         cwd=HUB, stdout=hub, stderr=subprocess.STDOUT))
        wait_log(run / 'hub.log', f'Listening for NetSIO packets on port {hub_port}')
        storage_root = run / 'fujinet-data'
        ps.append(launch([str(PUBLIC_API_CLOCK_ENDPOINT), '--host', '127.0.0.1', '--port', '9997',
                          '--storage-root', str(storage_root)],
                         cwd=run, stdout=nio, stderr=subprocess.STDOUT))
        wait_log(run / 'nio.log', 'Atari public-API Clock/File/Network/Disk acceptance initialized', timeout=15)
        if relay and not relay.endpoint_registered.wait(15):
            raise RuntimeError('public File recovery relay did not register the live production endpoint')
        before = set(Path('/tmp').glob('altirra-bridge-*.token'))
        cmd, env, temps = altirra_command(False, trace_serial=True, program=PUBLIC_API_CLOCK_XEX)
        cmd.extend(['--debugcmd', f'.logopen {run / "pokey-siodata.log"}'])
        altirra_log = (run / 'altirra.log').open('wb')
        ps.append(launch(cmd, cwd=run, env=env, stdout=altirra_log, stderr=subprocess.STDOUT))
        token = fresh_token(before)
        wait_log(run / 'altirra.log', 'NetSIO Cold Reset', timeout=15)
        if not relay:
            cold_reset_after_device_ready(token)
        sys.path[:0] = [str(SDK)]
        from altirra_bridge import AltirraBridge
        with AltirraBridge.from_token_file(token) as bridge:
            bridge.resume()
        state = inspect_public_api_clock(token, run, timeout, rejected_w_recovery,
                                         malformed_r_recovery, interrupted_r_recovery)
        altirra_log.flush()
        nio.flush()
        trace = (run / 'nio.log').read_text(errors='replace')
        state['native_commands'] = (_clock_native_commands(trace) if not (rejected_w_recovery or malformed_r_recovery or interrupted_r_recovery) else
                                    re.findall(r'udp: Received \d+ bytes: 02 7F ([0-9A-F]{2}) ', trace))
        if trace.count('ClockDevice routed request') != 1:
            raise RuntimeError('public API Clock did not produce exactly one real ClockDevice dispatch')
        expected_file_dispatches = 3 if (malformed_r_recovery or interrupted_r_recovery) else 2
        if trace.count('FileDevice routed request') != expected_file_dispatches:
            raise RuntimeError('public API File did not produce the expected real FileDevice dispatch count')
        expected_file_commands = ('FileDevice routed request 1 command=4',
                                  'FileDevice routed request 2 command=4' if (malformed_r_recovery or interrupted_r_recovery)
                                  else 'FileDevice routed request 2 command=3',
                                  'FileDevice routed request 3 command=3' if (malformed_r_recovery or interrupted_r_recovery) else None)
        if not all(item in trace for item in expected_file_commands if item):
            raise RuntimeError('public API File dispatch order was not the required Write/Read recovery sequence')
        if trace.count('NetworkDevice routed request') != 4:
            raise RuntimeError('public API Network did not produce exactly four real NetworkDevice dispatches')
        expected_network_dispatches = (
            'NetworkDevice routed request 1 command=1',
            'NetworkDevice routed request 2 command=3',
            'NetworkDevice routed request 3 command=2',
            'NetworkDevice routed request 4 command=4',
            'Network fixture open count=1 method=2 url=fixture://nio-accept',
            'Network fixture write count=1 bytes=12 valid=1',
            'Network fixture close count=1',
        )
        if not all(expected in trace for expected in expected_network_dispatches):
            raise RuntimeError('public API Network fixture did not observe the exact open/write/read/close route')
        if trace.count('DiskDevice routed request') != 4:
            raise RuntimeError('public API Disk did not produce exactly four real DiskDevice dispatches')
        expected_disk_dispatches = (
            'Disk fixture mounted slot=2 path=/fnaccept-disk.atr sector_bytes=128 sectors=16',
            'DiskDevice routed request 1 command=5',
            'DiskDevice routed request 2 command=4',
            'DiskDevice routed request 3 command=14',
            'DiskDevice routed request 4 command=3',
        )
        if not all(expected in trace for expected in expected_disk_dispatches):
            raise RuntimeError('public API Disk dispatch order was not Info/Write/Flush/Read')
        backing_name = (PUBLIC_API_FILE_RECOVERY_NAME if (rejected_w_recovery or malformed_r_recovery or interrupted_r_recovery) else
                        PUBLIC_API_FILE_NAME)
        backing_marker = (PUBLIC_API_FILE_RECOVERY_MARKER if (rejected_w_recovery or malformed_r_recovery or interrupted_r_recovery) else
                          PUBLIC_API_FILE_MARKER)
        backing_file = storage_root / backing_name
        if not backing_file.is_file() or backing_file.read_bytes() != backing_marker:
            raise RuntimeError('public API File backing store does not retain the intended guest marker')
        if rejected_w_recovery and (storage_root / PUBLIC_API_FILE_NAME).exists():
            raise RuntimeError('rejected File W unexpectedly created its original backing file')
        if malformed_r_recovery or interrupted_r_recovery:
            original = storage_root / PUBLIC_API_FILE_NAME
            if not original.is_file() or original.read_bytes() != PUBLIC_API_FILE_MARKER:
                raise RuntimeError('first File W did not persist exactly once before terminal-R failure')
            state['retained_response_backing_file'] = str(original)
            state['retained_response_backing_bytes'] = PUBLIC_API_FILE_MARKER.hex(' ')
        state['backing_file'] = str(backing_file)
        state['backing_file_bytes'] = backing_marker.hex(' ')
        disk_image = storage_root / PUBLIC_API_DISK_IMAGE_NAME
        disk_offset = PUBLIC_API_DISK_ATR_HEADER_BYTES + PUBLIC_API_DISK_LBA * PUBLIC_API_DISK_SECTOR_BYTES
        disk_bytes = disk_image.read_bytes() if disk_image.is_file() else b''
        if (len(disk_bytes) < disk_offset + PUBLIC_API_DISK_SECTOR_BYTES or
                disk_bytes[disk_offset:disk_offset + PUBLIC_API_DISK_SECTOR_BYTES] != PUBLIC_API_DISK_PATTERN):
            raise RuntimeError('public API Disk backing ATR does not retain the guest sector pattern')
        for neighbor_lba in (PUBLIC_API_DISK_LBA - 1, PUBLIC_API_DISK_LBA + 1):
            neighbor_offset = PUBLIC_API_DISK_ATR_HEADER_BYTES + neighbor_lba * PUBLIC_API_DISK_SECTOR_BYTES
            if disk_bytes[neighbor_offset:neighbor_offset + PUBLIC_API_DISK_SECTOR_BYTES] != b'\0' * PUBLIC_API_DISK_SECTOR_BYTES:
                raise RuntimeError('public API Disk backing ATR changed a neighboring sector')
        state['disk_backing_image'] = str(disk_image)
        state['disk_backing_lba'] = PUBLIC_API_DISK_LBA
        state['disk_backing_pattern'] = PUBLIC_API_DISK_PATTERN.hex(' ')
        pokey = run / 'pokey-siodata.log'
        if not pokey.exists() or not pokey.stat().st_size:
            lines = [line for line in (run / 'altirra.log').read_text(errors='replace').splitlines()
                     if '[SIODATA]' in line]
            if not lines:
                raise RuntimeError('public API Clock has no captured POKEY SIODATA diagnostics')
            pokey.write_text('\n'.join(lines) + '\n')
        state['run_dir'] = str(run)
        state['expected_clock_bytes'] = PUBLIC_API_CLOCK_BYTES.hex(' ')
        state['expected_network_write'] = PUBLIC_API_NETWORK_WRITE_MARKER.hex(' ')
        state['expected_network_reply'] = PUBLIC_API_NETWORK_REPLY_BYTES.hex(' ')
        if relay:
            relay_summary, relay_path = relay.stop()
            relay = None
            if interrupted_r_recovery:
                _validate_public_terminal_r_relay(relay_summary)
                state['interrupted_r_fault'] = relay_summary
                state['interrupted_r_fault_evidence'] = str(relay_path)
            elif malformed_r_recovery:
                _validate_ready_length_relay(relay_summary)
                state['malformed_r_fault'] = relay_summary
                state['malformed_r_fault_evidence'] = str(relay_path)
            else:
                _validate_rejected_file_w_relay(relay_summary)
                state['rejected_w_fault'] = relay_summary
                state['rejected_w_fault_evidence'] = str(relay_path)
        return state
    finally:
        if relay:
            relay.stop()
        if altirra_log:
            altirra_log.close()
        if 'hub' in locals():
            hub.close()
        if 'nio' in locals():
            nio.close()
        if 'temps' in locals():
            cleanup_temps(temps)
        stop(ps)


def run_altirra_embedded_native_core_dispatch(timeout, evidence_dir, wrong_r_retention=False,
                                              reset_to_idle=False, interrupted_r_recovery=False,
                                              capacity_bounds=False):
    """Run the native guest through Altirra's embedded production endpoint.

    The normal profile's NetSIO custom device is removed, then the actual
    fujinetnio device is added with its explicit projection-only core route.
    There is no hub, UDP endpoint, or replacement Q/W/P/R implementation.
    """
    if sum((wrong_r_retention, reset_to_idle, interrupted_r_recovery, capacity_bounds)) > 1:
        raise ValueError('embedded native projection variants are mutually exclusive')
    scenario_id = ('native-capacity-bounds' if capacity_bounds else
                   'native-interrupted-r-recovery' if interrupted_r_recovery else
                   'native-reset-to-idle' if reset_to_idle else
                   'native-wrong-r-retention' if wrong_r_retention else 'native-core-dispatch')
    program = (NATIVE_CAPACITY_BOUNDS_XEX if capacity_bounds else
               NATIVE_INTERRUPTED_R_RECOVERY_XEX if interrupted_r_recovery else
               NATIVE_RESET_TO_IDLE_XEX if reset_to_idle else
               NATIVE_WRONG_R_RETENTION_XEX if wrong_r_retention else NATIVE_CORE_DISPATCH_XEX)
    if not program.is_file():
        raise RuntimeError(f'{scenario_id} XEX is missing: {program}')
    run = (Path(evidence_dir) / scenario_id).resolve()
    run.mkdir(parents=True, exist_ok=True)
    config_dir = run / 'fujinet-data'
    config_dir.mkdir(exist_ok=True)
    before = set(Path('/tmp').glob('altirra-bridge-*.token'))
    cmd, env, temps = altirra_command(True, trace_serial=True, program=program)
    device_settings = f'fujinetnio,configdir={config_dir},projectionfixture=true'
    if interrupted_r_recovery:
        device_settings += ',projectioninterruptterminalr=true'
    cmd.extend(['--adddevice', device_settings,
                '--debugcmd', f'.logopen {run / "pokey-siodata.log"}'])
    altirra_log = (run / 'altirra.log').open('wb')
    process = None
    try:
        process = launch(cmd, cwd=run, env=env, stdout=altirra_log, stderr=subprocess.STDOUT)
        token = fresh_token(before)
        sys.path[:0] = [str(SDK)]
        from altirra_bridge import AltirraBridge
        with AltirraBridge.from_token_file(token) as bridge:
            device = bridge.device_get('fujinetnio')
            if not device.get('present') or not device.get('healthy'):
                raise RuntimeError(f'embedded fujinetnio device is not healthy: {device}')
            if (interrupted_r_recovery and
                    not device.get('settings', {}).get('projectioninterruptterminalr')):
                raise RuntimeError('embedded terminal-R delivery fault is not enabled')
            bridge.resume()
        reset_event = None
        if reset_to_idle:
            wait_for_projection_step(token, 4, timeout)
            with AltirraBridge.from_token_file(token) as bridge:
                reset_event = bridge.device_cold_reset('fujinetnio')
                if (not reset_event.get('reset') or reset_event.get('lifecycle') != 'cold' or
                        reset_event.get('tag') != 'fujinetnio' or
                        reset_event.get('path') != '/fujinetnio'):
                    raise RuntimeError(f'embedded device cold reset was not acknowledged: {reset_event}')
                # The XEX deliberately waits here.  Releasing it is separate
                # from the lifecycle call, so its next P observes only the
                # production device state after the real ColdReset.
                bridge.poke(PROJECTION_RESET_GO, 1)
            reset_event.update({'kind': 'altirra-embedded-device-cold-reset',
                                'guest_step_before_reset': 4})
            (run / 'embedded-device-reset-event.json').write_text(
                json.dumps(reset_event, indent=2) + '\n')
            wait_log(run / 'altirra.log', 'embedded FujiNet-NIO device ColdReset', timeout=timeout)
        result = inspect_native_core_dispatch(token, run, timeout,
                                              wrong_r_retention=wrong_r_retention,
                                              reset_to_idle=reset_to_idle,
                                              interrupted_r_recovery=interrupted_r_recovery,
                                              capacity_bounds=capacity_bounds)
        altirra_log.flush()
        pokey = run / 'pokey-siodata.log'
        if not pokey.exists() or not pokey.stat().st_size:
            lines = [line for line in (run / 'altirra.log').read_text(errors='replace').splitlines()
                     if '[SIODATA]' in line]
            if not lines:
                raise RuntimeError(f'embedded {scenario_id} has no captured POKEY SIODATA diagnostics')
            pokey.write_text('\n'.join(lines) + '\n')
        result['run_dir'] = str(run)
        result['embedded_device'] = device
        if reset_event:
            result['reset_event'] = reset_event
            result['reset_event_evidence'] = str(run / 'embedded-device-reset-event.json')
        if interrupted_r_recovery:
            wait_log(run / 'altirra.log',
                     'projection fault: accepted terminal R checksum 1a delivered as 1b',
                     timeout=timeout)
            fault = {
                'kind': 'altirra-embedded-terminal-r-checksum-corrupted',
                'accepted_terminal_r': True,
                'expected_checksum': '1a',
                'delivery_checksum': '1b',
                'sio_boundary': 'IATDeviceSIOInterface::SendData',
            }
            fault_path = run / 'embedded-terminal-r-fault.json'
            fault_path.write_text(json.dumps(fault, indent=2) + '\n')
            result['delivery_fault'] = fault
            result['delivery_fault_evidence'] = str(fault_path)
        return result
    finally:
        altirra_log.close()
        cleanup_temps(temps)
        if process:
            stop([process])


def run_altirra_embedded_native_wrong_r_retention(timeout, evidence_dir):
    """Run literal retained-response recovery through the embedded production device."""
    return run_altirra_embedded_native_core_dispatch(timeout, evidence_dir, wrong_r_retention=True)


def run_altirra_embedded_native_reset_to_idle(timeout, evidence_dir):
    """Reset the live embedded device after READY without resetting the guest."""
    return run_altirra_embedded_native_core_dispatch(timeout, evidence_dir, reset_to_idle=True)


def run_altirra_embedded_native_interrupted_r_recovery(timeout, evidence_dir):
    """Interrupt only accepted terminal-R checksum delivery through Altirra SIO."""
    return run_altirra_embedded_native_core_dispatch(
        timeout, evidence_dir, interrupted_r_recovery=True)


def run_altirra_embedded_native_capacity_bounds(timeout, evidence_dir):
    """Run 511/512/513 packet bounds through Altirra's embedded endpoint."""
    return run_altirra_embedded_native_core_dispatch(
        timeout, evidence_dir, capacity_bounds=True)

def write_netsio_boot_projection(run_result):
    """Write adapter-scoped virtual evidence from the existing boot lifecycle.

    This is intentionally only the stable D1/page-6 projection.  Native Q/W/P/R
    playback is a later increment; this helper supplies its shared result and
    evidence contract without manufacturing an emulator-side peer.
    """
    manifest = validate_manifest(load_manifest())
    boot = next(item for item in manifest["boot_projections"] if item["id"] == "boot-page6-config")
    run = Path(run_result["run_dir"])
    trace = run_result["trace"]
    observed = {
        "sio_commands": [trace["d1_status"], *trace["boot_reads_128"], trace["first_dd_read_256"]],
        "sio_responses": ["A", "C"],
        "page_6_signature": run_result["signature"],
        "fixture_scenario_ids": boot["scenario_ids"],
    }
    result = scenario_result("netsio", boot["id"], observed, evidence_paths_for_boot(run, "netsio"))
    path = write_scenario_result(run / "virtual-projection-results", result)
    result["result_path"] = str(path)
    return result

def write_netsio_native_core_dispatch_projection(run_result):
    """Compare production UDP capture before recording native-v1 evidence."""
    run = Path(run_result["run_dir"])
    manifest = validate_manifest(load_manifest())
    observed = compare_netsio_native_core_dispatch((run / "nio.log").read_text(errors="replace"), manifest)
    # A result may pass only because this comparison read the live production
    # capture.  Prove that a corrupted observed terminal-R checksum is rejected
    # before retaining the unmodified evidence.
    trace = (run / "nio.log").read_text(errors="replace")
    corrupted, changed = re.subn(r"(udp: Sending 2 bytes: 01 )1A$", r"\g<1>1B", trace,
                                 count=1, flags=re.MULTILINE)
    if changed != 1:
        raise RuntimeError("could not create deliberate native-core-dispatch checksum mutation")
    try:
        compare_netsio_native_core_dispatch(corrupted, manifest)
    except ProjectionMismatch:
        negative_verified = True
    else:
        raise RuntimeError("corrupted native-core-dispatch capture unexpectedly passed comparison")
    # The terminal R payload must follow COMPLETE.  Mutate only the captured
    # NetSIO datagrams to prove ordering, not merely literal checksum values,
    # participates in the production-evidence verdict.
    reordered, changed = re.subn(
        r"(?P<ack>^[^\n]*udp: Sending 6 bytes: 81 [0-9A-F]{2} 01 41 00 00\n)"
        r"(?P<complete>^[^\n]*udp: Sending 2 bytes: 01 43\n)"
        r"(?P<payload>^[^\n]*udp: Sending 10 bytes: 02 01 02 09 00 0D 01 00 AA 55\n)"
        r"(?P<checksum>^[^\n]*udp: Sending 2 bytes: 01 1A)",
        r"\g<ack>\g<payload>\g<complete>\g<checksum>", trace, count=1, flags=re.MULTILINE)
    if changed != 1:
        raise RuntimeError("could not create deliberate native-core-dispatch response-order mutation")
    try:
        compare_netsio_native_core_dispatch(reordered, manifest)
    except ProjectionMismatch:
        order_negative_verified = True
    else:
        raise RuntimeError("reordered native-core-dispatch capture unexpectedly passed comparison")
    result = scenario_result("netsio", "native-core-dispatch", observed,
                             evidence_paths_for_boot(run, "netsio"),
                             passed=run_result["guest_result"] == "NVP!")
    result["negative_checksum_mutation_rejected"] = negative_verified
    result["negative_response_order_mutation_rejected"] = order_negative_verified
    path = write_scenario_result(run / "virtual-projection-results", result)
    result["result_path"] = str(path)
    return result


def _swap_embedded_terminal_r_response(trace):
    """Move the accepted R COMPLETE after a payload byte in captured evidence."""
    payload = list(re.finditer(r'^.*\[SIODATA\].*?Receive\s+< \$AA.*\n', trace, re.MULTILINE))
    if not payload:
        raise RuntimeError('could not find embedded terminal-R payload evidence')
    payload_match = payload[-1]
    completes = [match for match in re.finditer(
        r'^.*\[SIODATA\].*?Receive\s+< \$43.*\n', trace, re.MULTILINE)
                 if match.start() < payload_match.start()]
    if not completes:
        raise RuntimeError('could not find embedded terminal-R COMPLETE evidence')
    complete_match = completes[-1]
    complete_line = trace[complete_match.start():complete_match.end()]
    payload_line = trace[payload_match.start():payload_match.end()]
    without_complete = trace[:complete_match.start()] + trace[complete_match.end():]
    adjusted_payload_start = payload_match.start() - len(complete_line)
    adjusted_payload_end = payload_match.end() - len(complete_line)
    without_both = (without_complete[:adjusted_payload_start] +
                    without_complete[adjusted_payload_end:])
    return (without_both[:complete_match.start()] + payload_line +
            without_both[complete_match.start():adjusted_payload_start] + complete_line +
            without_both[adjusted_payload_start:])


def write_altirra_embedded_native_core_dispatch_projection(run_result):
    """Write adapter-scoped evidence only after literal POKEY comparison."""
    run = Path(run_result['run_dir'])
    manifest = validate_manifest(load_manifest())
    pokey = (run / 'pokey-siodata.log').read_text(errors='replace')
    altirra = (run / 'altirra.log').read_text(errors='replace')
    observed = compare_altirra_embedded_native_core_dispatch(pokey, altirra, manifest)
    if (run_result['guest_result'] != 'NVP!' or
            run_result['q_reply'] != '01 00 02 00' or
            run_result['p_ready'] != '02 09 00' or
            run_result['r_reply'] != '01 02 09 00 0d 01 00 aa 55' or
            run_result['p_idle'] != '00 00 00'):
        raise RuntimeError('embedded native-core-dispatch guest did not preserve literal fixture state')

    corrupted, changed = re.subn(r'(Receive\s+< \$)AA', r'\g<1>AB', pokey, count=1)
    if changed != 1:
        raise RuntimeError('could not create deliberate embedded response-byte mutation')
    try:
        compare_altirra_embedded_native_core_dispatch(corrupted, altirra, manifest)
    except ProjectionMismatch:
        byte_negative_verified = True
    else:
        raise RuntimeError('corrupted embedded response byte unexpectedly passed comparison')

    reordered = _swap_embedded_terminal_r_response(pokey)
    try:
        compare_altirra_embedded_native_core_dispatch(reordered, altirra, manifest)
    except ProjectionMismatch:
        order_negative_verified = True
    else:
        raise RuntimeError('reordered embedded response unexpectedly passed comparison')

    result = scenario_result('altirra-embedded', 'native-core-dispatch', observed,
                             evidence_paths_for_boot(run, 'altirra-embedded'),
                             passed=run_result['guest_result'] == 'NVP!')
    result['negative_response_byte_mutation_rejected'] = byte_negative_verified
    result['negative_response_order_mutation_rejected'] = order_negative_verified
    path = write_scenario_result(run / 'virtual-projection-results', result)
    result['result_path'] = str(path)
    return result


def _assert_wrong_r_retention_guest_state(run_result):
    statuses = run_result["siov_statuses"].split()
    if (run_result["wrong_r_status"] == "01" or
            len(statuses) != 7 or statuses[:3] != ["01", "01", "01"] or
            statuses[4:] != ["01", "01", "01"] or
            run_result["p_retained"] != "02 09 00" or
            run_result["r_reply"] != "01 02 09 00 0d 01 00 aa 55" or
            run_result["p_idle"] != "00 00 00"):
        raise RuntimeError("guest did not retain and then consume the exact core-dispatch response")


def _embedded_wrong_r_mutation(trace, retained_response=False):
    """Corrupt only the captured rejected R or its following retained P reply."""
    wrong_r = (r"\[SIODATA\].*?SendCmd\s+\$7F.*?"
               r"\[SIODATA\].*?SendCmd\s+\$52.*?"
               r"\[SIODATA\].*?SendCmd\s+\$03.*?"
               r"\[SIODATA\].*?SendCmd\s+\$00.*?"
               r"\[SIODATA\].*?SendCmd\s+\$D4")
    if not retained_response:
        mutated, changed = re.subn(
            rf"(?s)({wrong_r}.*?Receive\s+< \$)4E", r"\g<1>45", trace, count=1)
        if changed != 1:
            raise RuntimeError("could not create deliberate embedded wrong-R NAK mutation")
        return mutated
    mutated, changed = re.subn(
        rf"(?s)({wrong_r}.*?Receive\s+< \$4E.*?"
        r"\[SIODATA\].*?SendCmd\s+\$7F.*?"
        r"\[SIODATA\].*?SendCmd\s+\$50.*?"
        r"\[SIODATA\].*?SendCmd\s+\$00.*?"
        r"\[SIODATA\].*?SendCmd\s+\$00.*?"
        r"\[SIODATA\].*?SendCmd\s+\$CF.*?"
        r"Receive\s+< \$02.*?Receive\s+< \$)09",
        r"\g<1>08", trace, count=1)
    if changed != 1:
        raise RuntimeError("could not create deliberate embedded retained-response mutation")
    return mutated


def write_altirra_embedded_native_wrong_r_retention_projection(run_result):
    """Record embedded wrong-R retention after literal POKEY comparison."""
    run = Path(run_result["run_dir"])
    manifest = validate_manifest(load_manifest())
    pokey = (run / "pokey-siodata.log").read_text(errors="replace")
    altirra = (run / "altirra.log").read_text(errors="replace")
    observed = compare_altirra_embedded_native_wrong_r_retention(pokey, altirra, manifest)
    _assert_wrong_r_retention_guest_state(run_result)

    wrong_nak = _embedded_wrong_r_mutation(pokey)
    try:
        compare_altirra_embedded_native_wrong_r_retention(wrong_nak, altirra, manifest)
    except ProjectionMismatch:
        nak_negative_verified = True
    else:
        raise RuntimeError("mutated embedded wrong-R NAK unexpectedly passed comparison")

    retained = _embedded_wrong_r_mutation(pokey, retained_response=True)
    try:
        compare_altirra_embedded_native_wrong_r_retention(retained, altirra, manifest)
    except ProjectionMismatch:
        retained_negative_verified = True
    else:
        raise RuntimeError("mutated embedded retained response unexpectedly passed comparison")

    result = scenario_result("altirra-embedded", "native-wrong-r-retention", observed,
                             evidence_paths_for_boot(run, "altirra-embedded"),
                             passed=run_result["guest_result"] == "NVP!")
    result["negative_wrong_r_nak_mutation_rejected"] = nak_negative_verified
    result["negative_retained_response_mutation_rejected"] = retained_negative_verified
    path = write_scenario_result(run / "virtual-projection-results", result)
    result["result_path"] = str(path)
    return result


def _assert_embedded_reset_to_idle_guest_state(run_result):
    statuses = run_result["siov_statuses"].split()
    if (statuses != ["01"] * 8 or
            run_result["p_ready"] != "02 09 00" or
            run_result["post_reset_idle"] != "00 00 00" or
            run_result["post_reset_ready"] != "02 09 00" or
            run_result["post_reset_reply"] != "01 03 09 00 0e 01 00 33 cc" or
            run_result["post_reset_terminal_idle"] != "00 00 00"):
        raise RuntimeError("guest did not observe embedded reset-to-idle and the distinct post-reset response")
    reset_event = run_result.get("reset_event")
    if (not reset_event or reset_event.get("kind") != "altirra-embedded-device-cold-reset" or
            reset_event.get("lifecycle") != "cold" or reset_event.get("tag") != "fujinetnio" or
            reset_event.get("path") != "/fujinetnio" or
            reset_event.get("guest_step_before_reset") != 4):
        raise RuntimeError("embedded reset-to-idle lacks a device ColdReset lifecycle event")


def _embedded_native_windows(trace):
    """Return literal native-command windows from captured POKEY diagnostics."""
    starts = list(re.finditer(r"^.*\[SIODATA\].*?SendCmd\s+\$7F.*$", trace, re.MULTILINE))
    windows = []
    for index, start in enumerate(starts):
        end = starts[index + 1].start() if index + 1 < len(starts) else len(trace)
        window = trace[start.start():end]
        command = bytes(int(value, 16) for value in re.findall(
            r"SendCmd\s+\$([0-9A-F]{2})", window)[:5])
        if len(command) != 5:
            raise RuntimeError("captured embedded native command is truncated")
        windows.append((command, start.start(), end))
    return windows


def _embedded_replace_response(trace, command, occurrence, response):
    """Alter one captured response only for a deliberate-verifier negative."""
    matching = [window for window in _embedded_native_windows(trace) if window[0] == command]
    if occurrence >= len(matching):
        raise RuntimeError("could not find captured embedded response for mutation")
    _, begin, end = matching[occurrence]
    window = trace[begin:end]
    receives = list(re.finditer(r"(Receive\s+< \$)([0-9A-F]{2})", window))
    if len(receives) != len(response):
        raise RuntimeError("captured embedded response has unexpected byte count")
    pieces = []
    cursor = 0
    for match, value in zip(receives, response):
        pieces.extend((window[cursor:match.start(2)], f"{value:02X}"))
        cursor = match.end(2)
    pieces.append(window[cursor:])
    return trace[:begin] + "".join(pieces) + trace[end:]


def _embedded_replace_w_data(trace, occurrence, payload, checksum):
    """Alter one captured W data phase for a deliberate replay negative."""
    command = bytes.fromhex("7f 57 06 00 dc")
    matching = [window for window in _embedded_native_windows(trace) if window[0] == command]
    if occurrence >= len(matching):
        raise RuntimeError("could not find captured embedded W data for mutation")
    _, begin, end = matching[occurrence]
    window = trace[begin:end]
    sends = list(re.finditer(r"(\bSend\s+\$)([0-9A-F]{2})", window))
    replacement = bytes(payload) + bytes((checksum,))
    if len(sends) != len(replacement):
        raise RuntimeError("captured embedded W data has unexpected byte count")
    pieces = []
    cursor = 0
    for match, value in zip(sends, replacement):
        pieces.extend((window[cursor:match.start(2)], f"{value:02X}"))
        cursor = match.end(2)
    pieces.append(window[cursor:])
    return trace[:begin] + "".join(pieces) + trace[end:]


def _embedded_replace_command(trace, command, occurrence, replacement):
    """Alter one captured command frame only for an embedded verifier negative."""
    matching = [window for window in _embedded_native_windows(trace) if window[0] == command]
    if occurrence >= len(matching) or len(replacement) != 5:
        raise RuntimeError("could not find captured embedded command for mutation")
    _, begin, end = matching[occurrence]
    window = trace[begin:end]
    sent = list(re.finditer(r"(SendCmd\s+\$)([0-9A-F]{2})", window))[:5]
    if len(sent) != 5:
        raise RuntimeError("captured embedded command has unexpected byte count")
    pieces = []
    cursor = 0
    for match, value in zip(sent, replacement):
        pieces.extend((window[cursor:match.start(2)], f"{value:02X}"))
        cursor = match.end(2)
    pieces.append(window[cursor:])
    return trace[:begin] + "".join(pieces) + trace[end:]


def _embedded_capacity_response_mutation(trace, duplicate=False):
    """Corrupt or duplicate a real captured byte in the 512-byte terminal R."""
    command = bytes.fromhex("7f 52 00 02 d3")
    matching = [window for window in _embedded_native_windows(trace) if window[0] == command]
    if len(matching) != 1:
        raise RuntimeError("could not find one captured embedded 512-byte R")
    _, begin, end = matching[0]
    window = trace[begin:end]
    receives = list(re.finditer(r"(Receive\s+< \$)([0-9A-F]{2})", window))
    # ACK, COMPLETE, raw packet (512), then its SIO checksum.
    if len(receives) != 515:
        raise RuntimeError("captured embedded 512-byte R has unexpected byte count")
    middle = receives[2 + 256]
    if not duplicate:
        replacement = f"{int(middle.group(2), 16) ^ 1:02X}"
        return trace[:begin] + window[:middle.start(2)] + replacement + window[middle.end(2):] + trace[end:]
    line_begin = window.rfind("\n", 0, middle.start()) + 1
    line_end = window.find("\n", middle.end())
    if line_end < 0:
        raise RuntimeError("could not duplicate captured embedded 512-byte R data")
    line = window[line_begin:line_end + 1]
    return trace[:begin] + window[:line_end + 1] + line + window[line_end + 1:] + trace[end:]


def write_altirra_embedded_native_reset_to_idle_projection(run_result):
    """Record live embedded reset only after lifecycle and POKEY verification."""
    run = Path(run_result["run_dir"])
    manifest = validate_manifest(load_manifest())
    pokey = (run / "pokey-siodata.log").read_text(errors="replace")
    altirra = (run / "altirra.log").read_text(errors="replace")
    observed = compare_altirra_embedded_native_reset_to_idle(pokey, altirra, manifest)
    _assert_embedded_reset_to_idle_guest_state(run_result)
    if "embedded FujiNet-NIO device ColdReset" not in altirra:
        raise RuntimeError("embedded reset-to-idle lacks the device ColdReset log evidence")

    # The second P is the post-reset P(IDLE).  Turning it into the stale
    # pre-reset READY reply must fail the literal comparison.
    stale_ready = _embedded_replace_response(
        pokey, bytes.fromhex("7f 50 00 00 cf"), 1, b"AC\x02\x09\x00\x0b")
    try:
        compare_altirra_embedded_native_reset_to_idle(stale_ready, altirra, manifest)
    except ProjectionMismatch:
        stale_ready_negative_verified = True
    else:
        raise RuntimeError("stale embedded READY after reset unexpectedly passed comparison")

    # The second accepted W is independently literal W2. Replaying W1 bytes
    # after reset must not satisfy the second-dispatch projection.
    replayed_w = _embedded_replace_w_data(
        pokey, 1, bytes.fromhex("01 02 06 00 09 00"), 0x12)
    try:
        compare_altirra_embedded_native_reset_to_idle(replayed_w, altirra, manifest)
    except ProjectionMismatch:
        replay_negative_verified = True
    else:
        raise RuntimeError("replayed embedded pre-reset W unexpectedly passed comparison")

    missing_reset = dict(run_result)
    missing_reset.pop("reset_event", None)
    try:
        _assert_embedded_reset_to_idle_guest_state(missing_reset)
    except RuntimeError:
        missing_reset_negative_verified = True
    else:
        raise RuntimeError("embedded projection without reset lifecycle evidence unexpectedly passed")

    result = scenario_result("altirra-embedded", "native-reset-to-idle", observed,
                             evidence_paths_for_boot(run, "altirra-embedded"),
                             passed=run_result["guest_result"] == "NVP!")
    result["reset_event"] = run_result["reset_event"]
    result["reset_event_evidence"] = run_result["reset_event_evidence"]
    result["negative_missing_reset_evidence_rejected"] = missing_reset_negative_verified
    result["negative_stale_ready_after_reset_rejected"] = stale_ready_negative_verified
    result["negative_replayed_pre_reset_w_rejected"] = replay_negative_verified
    path = write_scenario_result(run / "virtual-projection-results", result)
    result["result_path"] = str(path)
    return result


def write_netsio_native_wrong_r_retention_projection(run_result):
    """Record real wrong-R retention only after strict capture verification."""
    run = Path(run_result["run_dir"])
    manifest = validate_manifest(load_manifest())
    trace = (run / "nio.log").read_text(errors="replace")
    observed = compare_netsio_native_wrong_r_retention(trace, manifest)
    _assert_wrong_r_retention_guest_state(run_result)

    wrong_nak, changed = re.subn(
        r"(?s)(udp: Received 7 bytes: 02 7F 52 03 00 D4 [0-9A-F]{2}.*?"
        r"udp: Sending 6 bytes: 81 [0-9A-F]{2} 01 )4E( 00 00)",
        r"\g<1>45\g<2>", trace, count=1)
    if changed != 1:
        raise RuntimeError("could not create deliberate wrong-R NAK mutation")
    try:
        compare_netsio_native_wrong_r_retention(wrong_nak, manifest)
    except ProjectionMismatch:
        nak_negative_verified = True
    else:
        raise RuntimeError("mutated wrong-R NAK unexpectedly passed comparison")

    retained_length, changed = re.subn(
        r"(?s)(udp: Received 7 bytes: 02 7F 52 03 00 D4 [0-9A-F]{2}.*?"
        r"udp: Sending 6 bytes: 81 [0-9A-F]{2} 01 4E 00 00.*?"
        r"udp: Received 7 bytes: 02 7F 50 00 00 CF [0-9A-F]{2}.*?"
        r"udp: Sending 4 bytes: 02 02 )09( 00)",
        r"\g<1>08\g<2>", trace, count=1)
    if changed != 1:
        raise RuntimeError("could not create deliberate retained-response mutation")
    try:
        compare_netsio_native_wrong_r_retention(retained_length, manifest)
    except ProjectionMismatch:
        retained_negative_verified = True
    else:
        raise RuntimeError("mutated retained response unexpectedly passed comparison")

    result = scenario_result("netsio", "native-wrong-r-retention", observed,
                             evidence_paths_for_boot(run, "netsio"),
                             passed=run_result["guest_result"] == "NVP!")
    result["negative_wrong_r_nak_mutation_rejected"] = nak_negative_verified
    result["negative_retained_response_mutation_rejected"] = retained_negative_verified
    path = write_scenario_result(run / "virtual-projection-results", result)
    result["result_path"] = str(path)
    return result


def write_netsio_native_reset_to_idle_projection(run_result):
    """Record a reset only after the captured production path proves it."""
    run = Path(run_result["run_dir"])
    manifest = validate_manifest(load_manifest())
    trace = (run / "nio.log").read_text(errors="replace")
    observed = compare_netsio_native_reset_to_idle(trace, manifest)
    statuses = run_result["siov_statuses"].split()
    if (statuses != ["01"] * 8 or
            run_result["p_ready"] != "02 09 00" or
            run_result["post_reset_idle"] != "00 00 00" or
            run_result["post_reset_ready"] != "02 09 00" or
            run_result["post_reset_reply"] != "01 03 09 00 0e 01 00 33 cc" or
            run_result["post_reset_terminal_idle"] != "00 00 00"):
        raise RuntimeError("guest did not observe reset-to-idle and the distinct post-reset response")
    reset_event = run_result.get("reset_event")
    if not reset_event or reset_event.get("wire_datagram") != "ff":
        raise RuntimeError("native-reset-to-idle lacks an injected NetSIO reset event")

    # A launch-time Altirra reset is a separate two-byte lifecycle event.  The
    # one-byte incoming FF is mandatory production-path evidence for this
    # scenario; remove it only from the captured copy to prove that fact.
    missing_reset, changed = re.subn(r"^.*udp: Received 1 bytes: FF\n", "", trace,
                                     count=1, flags=re.MULTILINE)
    if changed != 1:
        raise RuntimeError("could not create deliberate missing-reset mutation")
    try:
        compare_netsio_native_reset_to_idle(missing_reset, manifest)
    except ProjectionMismatch:
        reset_negative_verified = True
    else:
        raise RuntimeError("capture without injected reset unexpectedly passed comparison")

    marker = trace.find("udp: Received 1 bytes: FF")
    corrupted_idle, changed = re.subn(r"(udp: Sending 4 bytes: 02 00 00) 00$",
                                      r"\g<1> 01", trace[marker:], count=1,
                                      flags=re.MULTILINE)
    if marker < 0 or changed != 1:
        raise RuntimeError("could not create deliberate post-reset IDLE mutation")
    try:
        compare_netsio_native_reset_to_idle(trace[:marker] + corrupted_idle, manifest)
    except ProjectionMismatch:
        idle_negative_verified = True
    else:
        raise RuntimeError("corrupted post-reset IDLE unexpectedly passed comparison")

    result = scenario_result("netsio", "native-reset-to-idle", observed,
                             evidence_paths_for_boot(run, "netsio"),
                             passed=run_result["guest_result"] == "NVP!")
    result["reset_event"] = reset_event
    result["negative_missing_reset_event_rejected"] = reset_negative_verified
    result["negative_post_reset_idle_mutation_rejected"] = idle_negative_verified
    path = write_scenario_result(run / "virtual-projection-results", result)
    result["result_path"] = str(path)
    return result


def _assert_interrupted_r_guest_state(run_result):
    statuses = run_result["siov_statuses"].split()
    if (len(statuses) != 9 or statuses[:3] != ["01", "01", "01"] or
            statuses[3] == "01" or statuses[4:] != ["01", "01", "01", "01", "01"] or
            run_result["post_interruption_idle"] != "00 00 00" or
            run_result["recovery_ready"] != "02 09 00" or
            run_result["recovery_reply"] != "01 04 09 00 0f 01 00 5a a5" or
            run_result["recovery_terminal_idle"] != "00 00 00"):
        raise RuntimeError("guest did not fail the accepted R then recover through IDLE")


def write_netsio_native_interrupted_r_recovery_projection(run_result):
    """Record accepted-R consumption despite deliberately bad guest delivery."""
    run = Path(run_result["run_dir"])
    manifest = validate_manifest(load_manifest())
    trace = (run / "nio.log").read_text(errors="replace")
    observed = compare_netsio_native_interrupted_r_recovery(trace, manifest)
    _assert_interrupted_r_guest_state(run_result)
    fault = run_result.get("delivery_fault")
    if (not fault or not fault.get("fault_applied") or fault.get("interrupted_r_attempts", 0) < 1 or
            not any(event.get("event") == "terminal-r-checksum-corrupted" and
                    event.get("original") == "1a" and event.get("delivered") == "1b"
                    for event in fault.get("events", ()))):
        raise RuntimeError("accepted terminal R has no captured checksum-delivery interruption")

    # Mutate the first post-interruption P result in the capture from IDLE to
    # READY.  A stale queued response must never satisfy native-v1 recovery.
    r_marker = trace.find("udp: Received 7 bytes: 02 7F 52 09 00 DA")
    stale_reply, changed = re.subn(r"(udp: Sending 4 bytes: 02 00 00) 00$",
                                   r"\g<1> 09", trace[r_marker:], count=1,
                                   flags=re.MULTILINE)
    if r_marker < 0 or changed != 1:
        raise RuntimeError("could not create deliberate unconsumed-response mutation")
    try:
        compare_netsio_native_interrupted_r_recovery(trace[:r_marker] + stale_reply, manifest)
    except ProjectionMismatch:
        stale_negative_verified = True
    else:
        raise RuntimeError("capture with a stale post-R response unexpectedly passed comparison")

    successful_guest = dict(run_result)
    successful_statuses = run_result["siov_statuses"].split()
    successful_statuses[3] = "01"
    successful_guest["siov_statuses"] = " ".join(successful_statuses)
    try:
        _assert_interrupted_r_guest_state(successful_guest)
    except RuntimeError:
        guest_negative_verified = True
    else:
        raise RuntimeError("successful interrupted-R guest status unexpectedly passed verification")

    result = scenario_result("netsio", "native-interrupted-r-recovery", observed,
                             evidence_paths_for_boot(run, "netsio"),
                             passed=run_result["guest_result"] == "NVP!")
    result["delivery_fault"] = fault
    result["delivery_fault_evidence"] = run_result["delivery_fault_evidence"]
    result["negative_unconsumed_response_rejected"] = stale_negative_verified
    result["negative_successful_guest_r_rejected"] = guest_negative_verified
    path = write_scenario_result(run / "virtual-projection-results", result)
    result["result_path"] = str(path)
    return result


def write_altirra_embedded_native_interrupted_r_recovery_projection(run_result):
    """Record an accepted embedded R whose checksum delivery was interrupted."""
    run = Path(run_result["run_dir"])
    manifest = validate_manifest(load_manifest())
    pokey = (run / "pokey-siodata.log").read_text(errors="replace")
    altirra = (run / "altirra.log").read_text(errors="replace")
    observed = compare_altirra_embedded_native_interrupted_r_recovery(pokey, altirra, manifest)
    _assert_interrupted_r_guest_state(run_result)
    fault = run_result.get("delivery_fault")
    interrupted_r = observed[3]
    if (not fault or fault.get("kind") != "altirra-embedded-terminal-r-checksum-corrupted" or
            not fault.get("accepted_terminal_r") or fault.get("expected_checksum") != "1a" or
            fault.get("delivery_checksum") != "1b" or
            "projection fault: accepted terminal R checksum 1a delivered as 1b" not in altirra or
            interrupted_r.get("siov_attempts", 0) < 2 or
            not interrupted_r.get("delivery_interrupted") or
            interrupted_r.get("expected_checksum") != "1a" or
            interrupted_r["response"].get("checksum") != "1b" or
            any(controls != ["N"] for controls in interrupted_r.get("consumed_retry_controls", ()) )):
        raise RuntimeError("embedded accepted terminal R lacks consumed-slot interruption evidence")

    # The P after failed guest delivery must prove endpoint consumption, not
    # merely show that the runner synthesized an IDLE state.
    stale_ready = _embedded_replace_response(
        pokey, bytes.fromhex("7f 50 00 00 cf"), 1, b"AC\x02\x09\x00\x0b")
    try:
        compare_altirra_embedded_native_interrupted_r_recovery(stale_ready, altirra, manifest)
    except ProjectionMismatch:
        stale_negative_verified = True
    else:
        raise RuntimeError("stale embedded response after accepted R unexpectedly passed comparison")

    successful_guest = dict(run_result)
    successful_statuses = run_result["siov_statuses"].split()
    successful_statuses[3] = "01"
    successful_guest["siov_statuses"] = " ".join(successful_statuses)
    try:
        _assert_interrupted_r_guest_state(successful_guest)
    except RuntimeError:
        guest_negative_verified = True
    else:
        raise RuntimeError("successful embedded interrupted-R status unexpectedly passed verification")

    result = scenario_result("altirra-embedded", "native-interrupted-r-recovery", observed,
                             evidence_paths_for_boot(run, "altirra-embedded"),
                             passed=run_result["guest_result"] == "NVP!")
    result["delivery_fault"] = fault
    result["delivery_fault_evidence"] = run_result["delivery_fault_evidence"]
    result["negative_unconsumed_response_rejected"] = stale_negative_verified
    result["negative_successful_guest_r_rejected"] = guest_negative_verified
    path = write_scenario_result(run / "virtual-projection-results", result)
    result["result_path"] = str(path)
    return result


def _capacity_response_data_mutation(trace):
    """Corrupt one captured middle byte of the 512-byte terminal R datagram."""
    prefix = "udp: Sending 513 bytes: "
    for line in trace.splitlines(keepends=True):
        position = line.find(prefix)
        if position < 0:
            continue
        data = bytes.fromhex(line[position + len(prefix):].strip())
        if len(data) == 513 and data[:7] == bytes((0x02, 0x01, 0x06, 0x00, 0x02, 0x8b, 0x01)):
            corrupted = bytearray(data)
            corrupted[260] ^= 0x01
            replacement = (line[:position] + prefix + corrupted.hex(' ').upper() +
                           ('\n' if line.endswith('\n') else ''))
            return trace.replace(line, replacement, 1)
    raise RuntimeError("could not find the captured 512-byte native R payload")


def _assert_capacity_guest_state(run_result):
    fixture_data = json.loads((ROOT / "integration-tests/atari-sio/fixtures/nio_v1.json").read_text())
    fixtures = {item["id"]: item for item in fixture_data["scenarios"]}
    expected_response = fixture_payload(fixtures["r-ready-512"]).hex(' ')
    statuses = run_result["siov_statuses"].split()
    if (len(statuses) != 13 or statuses[:8] != ["01"] * 8 or statuses[8] == "01" or
            statuses[9:] != ["01"] * 4 or
            run_result["capacity_ready_512"] != "02 00 02" or
            run_result["capacity_idle_after_512"] != "00 00 00" or
            run_result["capacity_bounded_ready"] != "02 07 00" or
            run_result["capacity_bounded_reply"] != "01 07 07 00 17 01 07" or
            run_result["capacity_terminal_idle"] != "00 00 00" or
            run_result["capacity_response"] != expected_response or
            run_result["capacity_canaries"] != {
                "request_low": "5a", "request_high": "a5",
                "response_low": "5a", "response_high": "a5"}):
        raise RuntimeError("guest did not preserve canaries and exact bounded packet results")


def write_netsio_native_capacity_bounds_projection(run_result):
    """Record only a byte-complete 511/512/513 production NetSIO execution."""
    run = Path(run_result["run_dir"])
    manifest = validate_manifest(load_manifest())
    trace = (run / "nio.log").read_text(errors="replace")
    observed = compare_netsio_native_capacity_bounds(trace, manifest)
    _assert_capacity_guest_state(run_result)

    corrupted = _capacity_response_data_mutation(trace)
    try:
        compare_netsio_native_capacity_bounds(corrupted, manifest)
    except ProjectionMismatch:
        middle_byte_negative_verified = True
    else:
        raise RuntimeError("corrupted 512-byte response unexpectedly passed comparison")

    wrong_length, changed = re.subn(
        r"(udp: Sending )513( bytes: 02 01 06 00 02 8B 01)", r"\g<1>512\g<2>",
        trace, count=1)
    if changed != 1:
        raise RuntimeError("could not create deliberate 512-byte length mutation")
    try:
        compare_netsio_native_capacity_bounds(wrong_length, manifest)
    except ProjectionMismatch:
        length_negative_verified = True
    else:
        raise RuntimeError("incorrect 512-byte response length unexpectedly passed comparison")

    marker = "udp: Sending 513 bytes: 02 01 06 00 02 8B 01"
    marker_position = trace.find(marker)
    line_start = trace.rfind("\n", 0, marker_position) + 1
    line_end = trace.find("\n", marker_position)
    if line_start < 0 or line_end < 0:
        raise RuntimeError("could not create deliberate duplicated 512-byte data mutation")
    line = trace[line_start:line_end + 1]
    duplicated = trace[:line_end + 1] + line + trace[line_end + 1:]
    try:
        compare_netsio_native_capacity_bounds(duplicated, manifest)
    except ProjectionMismatch:
        duplicate_negative_verified = True
    else:
        raise RuntimeError("duplicated 512-byte response unexpectedly passed comparison")

    result = scenario_result("netsio", "native-capacity-bounds", observed,
                             evidence_paths_for_boot(run, "netsio"),
                             passed=run_result["guest_result"] == "NVP!")
    result["negative_middle_byte_mutation_rejected"] = middle_byte_negative_verified
    result["negative_length_mutation_rejected"] = length_negative_verified
    result["negative_duplicate_data_mutation_rejected"] = duplicate_negative_verified
    path = write_scenario_result(run / "virtual-projection-results", result)
    result["result_path"] = str(path)
    return result


def write_altirra_embedded_native_capacity_bounds_projection(run_result):
    """Record byte-complete bounds evidence from Altirra's real SIO path."""
    run = Path(run_result["run_dir"])
    manifest = validate_manifest(load_manifest())
    pokey = (run / "pokey-siodata.log").read_text(errors="replace")
    altirra = (run / "altirra.log").read_text(errors="replace")
    observed = compare_altirra_embedded_native_capacity_bounds(pokey, altirra, manifest)
    _assert_capacity_guest_state(run_result)

    corrupted = _embedded_capacity_response_mutation(pokey)
    try:
        compare_altirra_embedded_native_capacity_bounds(corrupted, altirra, manifest)
    except ProjectionMismatch:
        middle_byte_negative_verified = True
    else:
        raise RuntimeError("corrupted embedded 512-byte response unexpectedly passed comparison")

    # The second P is the required P(READY, $0200). A different reported
    # length must not count as evidence even when all payload bytes remain.
    wrong_p_length = _embedded_replace_response(
        pokey, bytes.fromhex("7f 50 00 00 cf"), 1, b"AC\x02\xff\x01\x02")
    try:
        compare_altirra_embedded_native_capacity_bounds(wrong_p_length, altirra, manifest)
    except ProjectionMismatch:
        p_length_negative_verified = True
    else:
        raise RuntimeError("incorrect embedded P(READY) length unexpectedly passed comparison")

    wrong_r_length = _embedded_replace_command(
        pokey, bytes.fromhex("7f 52 00 02 d3"), 0, bytes.fromhex("7f 52 ff 01 d3"))
    try:
        compare_altirra_embedded_native_capacity_bounds(wrong_r_length, altirra, manifest)
    except ProjectionMismatch:
        r_length_negative_verified = True
    else:
        raise RuntimeError("incorrect embedded terminal-R AUX unexpectedly passed comparison")

    duplicated = _embedded_capacity_response_mutation(pokey, duplicate=True)
    try:
        compare_altirra_embedded_native_capacity_bounds(duplicated, altirra, manifest)
    except ProjectionMismatch:
        duplicate_negative_verified = True
    else:
        raise RuntimeError("duplicated embedded 512-byte response unexpectedly passed comparison")

    result = scenario_result("altirra-embedded", "native-capacity-bounds", observed,
                             evidence_paths_for_boot(run, "altirra-embedded"),
                             passed=run_result["guest_result"] == "NVP!")
    result["negative_middle_byte_mutation_rejected"] = middle_byte_negative_verified
    result["negative_p_length_mutation_rejected"] = p_length_negative_verified
    result["negative_r_length_mutation_rejected"] = r_length_negative_verified
    result["negative_duplicate_data_mutation_rejected"] = duplicate_negative_verified
    path = write_scenario_result(run / "virtual-projection-results", result)
    result["result_path"] = str(path)
    return result

if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--timeout',type=float,default=20); ap.add_argument('--observe-native',action='store_true'); ap.add_argument('--native-only',action='store_true'); ap.add_argument('--public-api-clock',action='store_true'); ap.add_argument('--public-api-rejected-w-recovery',action='store_true'); ap.add_argument('--public-api-malformed-r-recovery',action='store_true'); ap.add_argument('--public-api-interrupted-r-recovery',action='store_true'); ap.add_argument('--native-core-dispatch',action='store_true'); ap.add_argument('--native-core-dispatch-altirra-embedded',action='store_true'); ap.add_argument('--native-wrong-r-retention',action='store_true'); ap.add_argument('--native-wrong-r-retention-altirra-embedded',action='store_true'); ap.add_argument('--native-reset-to-idle',action='store_true'); ap.add_argument('--native-reset-to-idle-altirra-embedded',action='store_true'); ap.add_argument('--native-interrupted-r-recovery',action='store_true'); ap.add_argument('--native-interrupted-r-recovery-altirra-embedded',action='store_true'); ap.add_argument('--native-capacity-bounds',action='store_true'); ap.add_argument('--native-capacity-bounds-altirra-embedded',action='store_true'); ap.add_argument('--write-evidence',action='store_true'); ap.add_argument('--evidence-dir', type=Path); ap.add_argument('--json', action='store_true'); ap.add_argument('--settle', type=float, default=0.0); ap.add_argument('--repeat', type=int, default=1); ap.add_argument('--capture-dcb', action='store_true'); ap.add_argument('--command-ack-delay-tics', type=int); ap.add_argument('--trace-serial',action='store_true'); ap.add_argument('--write-projection-results', action='store_true'); ap.add_argument('--backend', choices=('nio', 'legacy'), default='nio'); ap.add_argument('--explicit-cold-reset', dest='explicit_cold_reset', action='store_true', default=True); ap.add_argument('--no-explicit-cold-reset', dest='explicit_cold_reset', action='store_false'); a=ap.parse_args()
    def emit(value):
        print(json.dumps(value) if a.json else value)
    evidence_dir = a.evidence_dir
    if evidence_dir is None and not a.observe_native:
        evidence_kind = ('atari-sio-public-api-interrupted-r-recovery-' if a.public_api_interrupted_r_recovery else
                         'atari-sio-public-api-malformed-r-recovery-' if a.public_api_malformed_r_recovery else
                         'atari-sio-public-api-rejected-w-recovery-' if a.public_api_rejected_w_recovery else
                         'atari-sio-public-api-clock-' if a.public_api_clock else
                         'atari-sio-native-capacity-bounds-altirra-embedded-' if a.native_capacity_bounds_altirra_embedded else
                         'atari-sio-native-interrupted-r-recovery-altirra-embedded-' if a.native_interrupted_r_recovery_altirra_embedded else
                         'atari-sio-native-reset-to-idle-altirra-embedded-' if a.native_reset_to_idle_altirra_embedded else
                         'atari-sio-native-wrong-r-retention-altirra-embedded-' if a.native_wrong_r_retention_altirra_embedded else
                         'atari-sio-native-core-dispatch-altirra-embedded-' if a.native_core_dispatch_altirra_embedded else
                         'atari-sio-native-capacity-bounds-' if a.native_capacity_bounds else
                         'atari-sio-native-interrupted-r-recovery-' if a.native_interrupted_r_recovery else
                         'atari-sio-native-reset-to-idle-' if a.native_reset_to_idle else
                         'atari-sio-native-wrong-r-retention-' if a.native_wrong_r_retention else
                         'atari-sio-native-core-dispatch-' if a.native_core_dispatch else 'atari-sio-boot-')
        evidence_dir = ROOT / 'test-evidence' / (evidence_kind + time.strftime('%Y%m%d-%H%M%S'))
    if evidence_dir:
        evidence_dir.mkdir(parents=True, exist_ok=True)
    if a.repeat < 1:
        raise ValueError('--repeat must be positive')
    if a.write_projection_results and not a.trace_serial:
        raise ValueError('--write-projection-results requires --trace-serial for required POKEY evidence')
    if a.write_projection_results and a.backend != 'nio':
        raise ValueError('--write-projection-results only records the production netsio adapter')
    if sum((a.public_api_clock, a.public_api_rejected_w_recovery, a.public_api_malformed_r_recovery, a.public_api_interrupted_r_recovery, a.native_core_dispatch, a.native_core_dispatch_altirra_embedded,
            a.native_reset_to_idle_altirra_embedded,
            a.native_interrupted_r_recovery_altirra_embedded,
            a.native_capacity_bounds_altirra_embedded,
            a.native_wrong_r_retention_altirra_embedded,
            a.native_wrong_r_retention, a.native_reset_to_idle,
            a.native_interrupted_r_recovery, a.native_capacity_bounds)) > 1:
        raise ValueError('choose only one native projection')
    if a.public_api_clock or a.public_api_rejected_w_recovery or a.public_api_malformed_r_recovery or a.public_api_interrupted_r_recovery:
        try:
            result = run_netsio_public_api_clock(a.timeout, evidence_dir,
                                                 rejected_w_recovery=a.public_api_rejected_w_recovery,
                                                 malformed_r_recovery=a.public_api_malformed_r_recovery,
                                                 interrupted_r_recovery=a.public_api_interrupted_r_recovery)
            result['outcome'] = 'launch'
        except Exception as exc:
            result = {'outcome': 'failure', 'evidence_dir': str(evidence_dir), 'error': str(exc)}
        (evidence_dir / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
        emit(result)
        if result['outcome'] != 'launch':
            raise SystemExit(1)
    elif a.native_capacity_bounds_altirra_embedded:
        try:
            result = run_altirra_embedded_native_capacity_bounds(a.timeout, evidence_dir)
            result['virtual_projection_result'] = write_altirra_embedded_native_capacity_bounds_projection(result)
            if result['virtual_projection_result']['status'] != 'pass':
                raise RuntimeError('embedded native-capacity-bounds evidence is '
                                   f"{result['virtual_projection_result']['status']}")
            result['outcome'] = 'launch'
        except Exception as exc:
            result = {'outcome': 'failure', 'evidence_dir': str(evidence_dir), 'error': str(exc)}
        (evidence_dir / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
        emit(result)
        if result['outcome'] != 'launch':
            raise SystemExit(1)
    elif a.native_interrupted_r_recovery_altirra_embedded:
        try:
            result = run_altirra_embedded_native_interrupted_r_recovery(a.timeout, evidence_dir)
            result['virtual_projection_result'] = write_altirra_embedded_native_interrupted_r_recovery_projection(result)
            if result['virtual_projection_result']['status'] != 'pass':
                raise RuntimeError('embedded native-interrupted-r-recovery evidence is '
                                   f"{result['virtual_projection_result']['status']}")
            result['outcome'] = 'launch'
        except Exception as exc:
            result = {'outcome': 'failure', 'evidence_dir': str(evidence_dir), 'error': str(exc)}
        (evidence_dir / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
        emit(result)
        if result['outcome'] != 'launch':
            raise SystemExit(1)
    elif a.native_reset_to_idle_altirra_embedded:
        try:
            result = run_altirra_embedded_native_reset_to_idle(a.timeout, evidence_dir)
            result['virtual_projection_result'] = write_altirra_embedded_native_reset_to_idle_projection(result)
            if result['virtual_projection_result']['status'] != 'pass':
                raise RuntimeError('embedded native-reset-to-idle evidence is '
                                   f"{result['virtual_projection_result']['status']}")
            result['outcome'] = 'launch'
        except Exception as exc:
            result = {'outcome': 'failure', 'evidence_dir': str(evidence_dir), 'error': str(exc)}
        (evidence_dir / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
        emit(result)
        if result['outcome'] != 'launch':
            raise SystemExit(1)
    elif a.native_wrong_r_retention_altirra_embedded:
        try:
            result = run_altirra_embedded_native_wrong_r_retention(a.timeout, evidence_dir)
            result['virtual_projection_result'] = write_altirra_embedded_native_wrong_r_retention_projection(result)
            if result['virtual_projection_result']['status'] != 'pass':
                raise RuntimeError('embedded native-wrong-r-retention evidence is '
                                   f"{result['virtual_projection_result']['status']}")
            result['outcome'] = 'launch'
        except Exception as exc:
            result = {'outcome': 'failure', 'evidence_dir': str(evidence_dir), 'error': str(exc)}
        (evidence_dir / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
        emit(result)
        if result['outcome'] != 'launch':
            raise SystemExit(1)
    elif a.native_core_dispatch_altirra_embedded:
        try:
            result = run_altirra_embedded_native_core_dispatch(a.timeout, evidence_dir)
            result['virtual_projection_result'] = write_altirra_embedded_native_core_dispatch_projection(result)
            if result['virtual_projection_result']['status'] != 'pass':
                raise RuntimeError('embedded native-core-dispatch evidence is '
                                   f"{result['virtual_projection_result']['status']}")
            result['outcome'] = 'launch'
        except Exception as exc:
            result = {'outcome': 'failure', 'evidence_dir': str(evidence_dir), 'error': str(exc)}
        (evidence_dir / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
        emit(result)
        if result['outcome'] != 'launch':
            raise SystemExit(1)
    elif a.native_core_dispatch:
        try:
            result = run_netsio_native_core_dispatch(a.timeout, evidence_dir)
            result['virtual_projection_result'] = write_netsio_native_core_dispatch_projection(result)
            if result['virtual_projection_result']['status'] != 'pass':
                raise RuntimeError(f"native-core-dispatch evidence is {result['virtual_projection_result']['status']}")
            result['outcome'] = 'launch'
        except Exception as exc:
            result = {'outcome': 'failure', 'evidence_dir': str(evidence_dir), 'error': str(exc)}
        (evidence_dir / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
        emit(result)
        if result['outcome'] != 'launch':
            raise SystemExit(1)
    elif a.native_wrong_r_retention:
        try:
            result = run_netsio_native_wrong_r_retention(a.timeout, evidence_dir)
            result['virtual_projection_result'] = write_netsio_native_wrong_r_retention_projection(result)
            if result['virtual_projection_result']['status'] != 'pass':
                raise RuntimeError(f"native-wrong-r-retention evidence is {result['virtual_projection_result']['status']}")
            result['outcome'] = 'launch'
        except Exception as exc:
            result = {'outcome': 'failure', 'evidence_dir': str(evidence_dir), 'error': str(exc)}
        (evidence_dir / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
        emit(result)
        if result['outcome'] != 'launch':
            raise SystemExit(1)
    elif a.native_reset_to_idle:
        try:
            result = run_netsio_native_reset_to_idle(a.timeout, evidence_dir)
            result['virtual_projection_result'] = write_netsio_native_reset_to_idle_projection(result)
            if result['virtual_projection_result']['status'] != 'pass':
                raise RuntimeError(f"native-reset-to-idle evidence is {result['virtual_projection_result']['status']}")
            result['outcome'] = 'launch'
        except Exception as exc:
            result = {'outcome': 'failure', 'evidence_dir': str(evidence_dir), 'error': str(exc)}
        (evidence_dir / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
        emit(result)
        if result['outcome'] != 'launch':
            raise SystemExit(1)
    elif a.native_interrupted_r_recovery:
        try:
            result = run_netsio_native_interrupted_r_recovery(a.timeout, evidence_dir)
            result['virtual_projection_result'] = write_netsio_native_interrupted_r_recovery_projection(result)
            if result['virtual_projection_result']['status'] != 'pass':
                raise RuntimeError(f"native-interrupted-r-recovery evidence is {result['virtual_projection_result']['status']}")
            result['outcome'] = 'launch'
        except Exception as exc:
            result = {'outcome': 'failure', 'evidence_dir': str(evidence_dir), 'error': str(exc)}
        (evidence_dir / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
        emit(result)
        if result['outcome'] != 'launch':
            raise SystemExit(1)
    elif a.native_capacity_bounds:
        try:
            result = run_netsio_native_capacity_bounds(a.timeout, evidence_dir)
            result['virtual_projection_result'] = write_netsio_native_capacity_bounds_projection(result)
            if result['virtual_projection_result']['status'] != 'pass':
                raise RuntimeError(f"native-capacity-bounds evidence is {result['virtual_projection_result']['status']}")
            result['outcome'] = 'launch'
        except Exception as exc:
            result = {'outcome': 'failure', 'evidence_dir': str(evidence_dir), 'error': str(exc)}
        (evidence_dir / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
        emit(result)
        if result['outcome'] != 'launch':
            raise SystemExit(1)
    elif a.observe_native:
        emit({'native': run_native(a.timeout, evidence_dir, observe=True)})
    elif a.native_only:
        emit({'native': run_native(a.timeout, evidence_dir)})
    else:
        runs = []
        for run_number in range(1, a.repeat + 1):
            run_dir = evidence_dir / f'run-{run_number:02d}' if a.repeat > 1 else evidence_dir
            run_dir.mkdir(parents=True, exist_ok=True)
            result = {'outcome': 'failure', 'evidence_dir': str(run_dir)}
            try:
                result['native'] = run_native(a.timeout, run_dir)
                result['netsio'] = run_netsio(a.timeout, run_dir, a.settle, a.capture_dcb, a.command_ack_delay_tics, a.trace_serial, a.backend, a.explicit_cold_reset)
                if a.write_projection_results:
                    projection_result = write_netsio_boot_projection(result['netsio'])
                    result['virtual_projection_results'] = [projection_result]
                    if projection_result['status'] != 'pass':
                        raise RuntimeError(f"virtual projection evidence is {projection_result['status']}: {projection_result['missing_evidence']}")
                result['outcome'] = 'launch'
            except Exception as exc:
                # The sidecars own their logs and run_netsio writes its
                # inspection/first-read artifacts before asserting launch.
                # Keep those paths and the completed native control in the
                # machine-readable result even when the gate fails.
                result['error'] = str(exc)
            (run_dir / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
            runs.append(result)
        result = runs[0] if a.repeat == 1 else {'runs': runs}
        if a.write_evidence and a.repeat == 1:
            evidence = {
                'format': 'atari-story-1.3-boot-v1',
                'atr_sha256': sha256(ATR),
                'signature': {'address': '0x06f0', 'before_cold_boot': '00000000', 'after_boot': '4e494f21'},
                'stable_loop_pc_range': ['0x0624', '0x0627'],
                'native': {key: value for key, value in result['native'].items() if key != 'screenshot'},
                'netsio': {key: value for key, value in result['netsio'].items() if key not in ('run_dir', 'screenshot')},
            }
            TRACE_FIXTURE.write_text(json.dumps(evidence, indent=2) + '\n')
        elif a.write_evidence:
            raise ValueError('--write-evidence is only valid for one boot; per-run evidence is retained under --evidence-dir')
        emit(result)
        if any(run['outcome'] != 'launch' for run in runs):
            raise SystemExit(1)
