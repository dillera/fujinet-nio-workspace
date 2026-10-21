#!/usr/bin/env python3
"""Deterministic Story 1.3 native and production-NetSIO boot gate."""
from __future__ import annotations
import argparse, hashlib, json, os, re, shutil, signal, subprocess, sys, tempfile, time
from pathlib import Path

from virtual_projection import (evidence_paths_for_boot, load_manifest,
                                scenario_result, validate_manifest,
                                write_scenario_result)

ROOT = Path(__file__).resolve().parents[2]
ATR = ROOT / "integration-tests/atari-sio/boot-app/build/boot-acceptance.atr"
TRACE_FIXTURE = ROOT / "integration-tests/atari-sio/fixtures/boot_acceptance_trace.json"
PROFILE = ROOT / "configs/atari/profiles/atari-nio-config-boot.yaml"
ALTIRRA = ROOT / "repos/AltirraSDL/build/linux-debug/src/AltirraSDL/AltirraSDL"
SDK = ROOT / "repos/AltirraSDL/src/AltirraSDL/AltirraBridge/sdk/python"
HUB = ROOT / "repos/fujinet-emulator-bridge/fujinet-bridge"
NIO = ROOT / "repos/fujinet-nio/build/atari-fujibus-netsio-debug/fujinet-nio"
SIG, LOOP = b"NIO!", 0x0624
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

def altirra_command(native, command_ack_delay_tics=None, trace_serial=False):
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
    ns=argparse.Namespace(profile=profile, emulators=ROOT/'configs/atari/emulators.yaml',symbols=None,dry_run=False,program=None,disk=[])
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

if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--timeout',type=float,default=20); ap.add_argument('--observe-native',action='store_true'); ap.add_argument('--native-only',action='store_true'); ap.add_argument('--write-evidence',action='store_true'); ap.add_argument('--evidence-dir', type=Path); ap.add_argument('--json', action='store_true'); ap.add_argument('--settle', type=float, default=0.0); ap.add_argument('--repeat', type=int, default=1); ap.add_argument('--capture-dcb', action='store_true'); ap.add_argument('--command-ack-delay-tics', type=int); ap.add_argument('--trace-serial',action='store_true'); ap.add_argument('--write-projection-results', action='store_true'); ap.add_argument('--backend', choices=('nio', 'legacy'), default='nio'); ap.add_argument('--explicit-cold-reset', dest='explicit_cold_reset', action='store_true', default=True); ap.add_argument('--no-explicit-cold-reset', dest='explicit_cold_reset', action='store_false'); a=ap.parse_args()
    def emit(value):
        print(json.dumps(value) if a.json else value)
    evidence_dir = a.evidence_dir
    if evidence_dir is None and not a.observe_native:
        evidence_dir = ROOT / 'test-evidence' / ('atari-sio-boot-' + time.strftime('%Y%m%d-%H%M%S'))
    if evidence_dir:
        evidence_dir.mkdir(parents=True, exist_ok=True)
    if a.repeat < 1:
        raise ValueError('--repeat must be positive')
    if a.write_projection_results and not a.trace_serial:
        raise ValueError('--write-projection-results requires --trace-serial for required POKEY evidence')
    if a.write_projection_results and a.backend != 'nio':
        raise ValueError('--write-projection-results only records the production netsio adapter')
    if a.observe_native:
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
