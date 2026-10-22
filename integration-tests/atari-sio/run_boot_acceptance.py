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
                                ProjectionMismatch, scenario_result, validate_manifest,
                                write_scenario_result)

ROOT = Path(__file__).resolve().parents[2]
ATR = ROOT / "integration-tests/atari-sio/boot-app/build/boot-acceptance.atr"
NATIVE_CORE_DISPATCH_XEX = ROOT / "integration-tests/atari-sio/native-projection-app/build/native-core-dispatch.xex"
NATIVE_WRONG_R_RETENTION_XEX = ROOT / "integration-tests/atari-sio/native-projection-app/build/native-wrong-r-retention.xex"
NATIVE_RESET_TO_IDLE_XEX = ROOT / "integration-tests/atari-sio/native-projection-app/build/native-reset-to-idle.xex"
NATIVE_INTERRUPTED_R_RECOVERY_XEX = ROOT / "integration-tests/atari-sio/native-projection-app/build/native-interrupted-r-recovery.xex"
NATIVE_CAPACITY_BOUNDS_XEX = ROOT / "integration-tests/atari-sio/native-projection-app/build/native-capacity-bounds.xex"
TRACE_FIXTURE = ROOT / "integration-tests/atari-sio/fixtures/boot_acceptance_trace.json"
PROFILE = ROOT / "configs/atari/profiles/atari-nio-config-boot.yaml"
ALTIRRA = ROOT / "repos/AltirraSDL/build/linux-debug/src/AltirraSDL/AltirraSDL"
SDK = ROOT / "repos/AltirraSDL/src/AltirraSDL/AltirraBridge/sdk/python"
HUB = ROOT / "repos/fujinet-emulator-bridge/fujinet-bridge"
NIO = ROOT / "repos/fujinet-nio/build/atari-fujibus-netsio-debug/fujinet-nio"
NATIVE_CORE_DISPATCH = ROOT / "repos/fujinet-nio/build/atari-fujibus-netsio-debug/tests/fujinet-nio-atari-netsio-projection"
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


def run_altirra_embedded_native_core_dispatch(timeout, evidence_dir):
    """Run the native guest through Altirra's embedded production endpoint.

    The normal profile's NetSIO custom device is removed, then the actual
    fujinetnio device is added with its explicit projection-only core route.
    There is no hub, UDP endpoint, or replacement Q/W/P/R implementation.
    """
    if not NATIVE_CORE_DISPATCH_XEX.is_file():
        raise RuntimeError(f'native-core-dispatch XEX is missing: {NATIVE_CORE_DISPATCH_XEX}')
    run = (Path(evidence_dir) / 'native-core-dispatch').resolve()
    run.mkdir(parents=True, exist_ok=True)
    config_dir = run / 'fujinet-data'
    config_dir.mkdir(exist_ok=True)
    before = set(Path('/tmp').glob('altirra-bridge-*.token'))
    cmd, env, temps = altirra_command(True, trace_serial=True, program=NATIVE_CORE_DISPATCH_XEX)
    cmd.extend(['--adddevice',
                f'fujinetnio,configdir={config_dir},projectionfixture=true',
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
            bridge.resume()
        result = inspect_native_core_dispatch(token, run, timeout)
        altirra_log.flush()
        pokey = run / 'pokey-siodata.log'
        if not pokey.exists() or not pokey.stat().st_size:
            lines = [line for line in (run / 'altirra.log').read_text(errors='replace').splitlines()
                     if '[SIODATA]' in line]
            if not lines:
                raise RuntimeError('embedded native-core-dispatch has no captured POKEY SIODATA diagnostics')
            pokey.write_text('\n'.join(lines) + '\n')
        result['run_dir'] = str(run)
        result['embedded_device'] = device
        return result
    finally:
        altirra_log.close()
        cleanup_temps(temps)
        if process:
            stop([process])

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


def write_netsio_native_wrong_r_retention_projection(run_result):
    """Record real wrong-R retention only after strict capture verification."""
    run = Path(run_result["run_dir"])
    manifest = validate_manifest(load_manifest())
    trace = (run / "nio.log").read_text(errors="replace")
    observed = compare_netsio_native_wrong_r_retention(trace, manifest)
    statuses = run_result["siov_statuses"].split()
    if (run_result["wrong_r_status"] == "01" or
            len(statuses) != 7 or statuses[:3] != ["01", "01", "01"] or
            statuses[4:] != ["01", "01", "01"] or
            run_result["p_retained"] != "02 09 00" or
            run_result["r_reply"] != "01 02 09 00 0d 01 00 aa 55" or
            run_result["p_idle"] != "00 00 00"):
        raise RuntimeError("guest did not retain and then consume the exact core-dispatch response")

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

if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--timeout',type=float,default=20); ap.add_argument('--observe-native',action='store_true'); ap.add_argument('--native-only',action='store_true'); ap.add_argument('--native-core-dispatch',action='store_true'); ap.add_argument('--native-core-dispatch-altirra-embedded',action='store_true'); ap.add_argument('--native-wrong-r-retention',action='store_true'); ap.add_argument('--native-reset-to-idle',action='store_true'); ap.add_argument('--native-interrupted-r-recovery',action='store_true'); ap.add_argument('--native-capacity-bounds',action='store_true'); ap.add_argument('--write-evidence',action='store_true'); ap.add_argument('--evidence-dir', type=Path); ap.add_argument('--json', action='store_true'); ap.add_argument('--settle', type=float, default=0.0); ap.add_argument('--repeat', type=int, default=1); ap.add_argument('--capture-dcb', action='store_true'); ap.add_argument('--command-ack-delay-tics', type=int); ap.add_argument('--trace-serial',action='store_true'); ap.add_argument('--write-projection-results', action='store_true'); ap.add_argument('--backend', choices=('nio', 'legacy'), default='nio'); ap.add_argument('--explicit-cold-reset', dest='explicit_cold_reset', action='store_true', default=True); ap.add_argument('--no-explicit-cold-reset', dest='explicit_cold_reset', action='store_false'); a=ap.parse_args()
    def emit(value):
        print(json.dumps(value) if a.json else value)
    evidence_dir = a.evidence_dir
    if evidence_dir is None and not a.observe_native:
        evidence_kind = ('atari-sio-native-core-dispatch-altirra-embedded-' if a.native_core_dispatch_altirra_embedded else
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
    if sum((a.native_core_dispatch, a.native_core_dispatch_altirra_embedded,
            a.native_wrong_r_retention, a.native_reset_to_idle,
            a.native_interrupted_r_recovery, a.native_capacity_bounds)) > 1:
        raise ValueError('choose only one native projection')
    if a.native_core_dispatch_altirra_embedded:
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
