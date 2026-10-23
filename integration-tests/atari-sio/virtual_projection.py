"""Reference-only Atari native-v1 virtual projection/result helpers.

This module deliberately does not serialize or emulate Q/W/P/R.  It validates
the independent fixture references and gives both virtual adapters one result
schema and evidence policy.  Adapter playback is intentionally a later story
increment.
"""
from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent
FIXTURES = ROOT / "fixtures"
MANIFEST_PATH = FIXTURES / "nio_v1.virtual.manifest.json"
NIO_PATH = FIXTURES / "nio_v1.json"
DISK_PATH = FIXTURES / "disk_v1.json"
ADAPTERS = {"netsio", "altirra-embedded"}
OBSERVATIONS = {"command", "data", "response", "state", "client-outcome", "transport-error", "page-6-signature"}
FORBIDDEN = {"legacy-$71", "slip", "padded-read", "stream-chunking"}
REQUIRED_EVIDENCE = {
    "netsio": ("altirra_log", "hub_log", "nio_log", "pokey_siodata", "screenshot", "inspection"),
    "altirra-embedded": ("altirra_log", "pokey_siodata", "screenshot", "inspection"),
}


class ProjectionError(ValueError):
    pass


class ProjectionMismatch(AssertionError):
    pass


def load_json(path: Path):
    return json.loads(path.read_text())


def load_manifest(path: Path = MANIFEST_PATH):
    return load_json(path)


def _ids(path: Path, key: str):
    return {item["id"] for item in load_json(path)[key]}


def validate_manifest(manifest, nio_ids=None, disk_ids=None):
    """Reject non-reference projections before an adapter run can start."""
    nio_ids = _ids(NIO_PATH, "scenarios") if nio_ids is None else set(nio_ids)
    disk_ids = _ids(DISK_PATH, "scenarios") if disk_ids is None else set(disk_ids)
    if manifest.get("format") != "atari-native-nio-v1-virtual-projection":
        raise ProjectionError("unsupported virtual projection format")
    if manifest.get("fixture_authority") != "nio_v1.json" or not manifest.get("native_v1_only"):
        raise ProjectionError("projection must declare independent native-v1 authority")
    if set(manifest.get("adapters", ())) != ADAPTERS:
        raise ProjectionError("projection must name netsio and altirra-embedded independently")
    if set(manifest.get("forbidden_paths", ())) != FORBIDDEN:
        raise ProjectionError("projection must exclude every obsolete native path")

    projection_ids = set()
    for projection in manifest.get("projections", ()):
        identifier = projection.get("id")
        if not isinstance(identifier, str) or not identifier or identifier in projection_ids:
            raise ProjectionError("projection IDs must be unique nonempty strings")
        projection_ids.add(identifier)
        operations = projection.get("operations")
        if not isinstance(operations, list) or not operations:
            raise ProjectionError(f"{identifier}: ordered operations are required")
        for operation in operations:
            fixture = operation.get("fixture")
            observed = operation.get("observe")
            if fixture not in nio_ids:
                raise ProjectionError(f"{identifier}: unknown native fixture {fixture!r}")
            if not isinstance(observed, list) or not observed or not set(observed) <= OBSERVATIONS:
                raise ProjectionError(f"{identifier}: expected observations are required")

    boot_ids = set()
    for projection in manifest.get("boot_projections", ()):
        identifier = projection.get("id")
        if not isinstance(identifier, str) or not identifier or identifier in boot_ids:
            raise ProjectionError("boot projection IDs must be unique nonempty strings")
        boot_ids.add(identifier)
        if projection.get("fixture_authority") != "disk_v1.json":
            raise ProjectionError(f"{identifier}: disk fixture authority is required")
        scenario_ids = projection.get("scenario_ids")
        observed = projection.get("observe")
        if not isinstance(scenario_ids, list) or not scenario_ids or any(item not in disk_ids for item in scenario_ids):
            raise ProjectionError(f"{identifier}: unknown disk fixture reference")
        if not isinstance(observed, list) or not observed or not set(observed) <= OBSERVATIONS:
            raise ProjectionError(f"{identifier}: expected observations are required")
    if not projection_ids or not boot_ids:
        raise ProjectionError("native and D1 boot projections are both required")
    return manifest


def expected_operation_ids(projection):
    return [operation["fixture"] for operation in projection["operations"]]


def compare_observed_operations(projection, observed_operation_ids):
    expected = expected_operation_ids(projection)
    observed = list(observed_operation_ids)
    if observed != expected:
        raise ProjectionMismatch(f"{projection['id']}: expected {expected}, observed {observed}")


def expected_responses(projection, fixture_data=None):
    """Resolve expected responses only from the independent literal fixture."""
    fixture_data = load_json(NIO_PATH) if fixture_data is None else fixture_data
    scenarios = {scenario["id"]: scenario for scenario in fixture_data["scenarios"]}
    return [(operation["fixture"], scenarios[operation["fixture"]].get("reply"))
            for operation in projection["operations"]
            if "reply" in scenarios[operation["fixture"]]]


def compare_observed_responses(projection, observed_responses, fixture_data=None):
    expected = expected_responses(projection, fixture_data)
    observed = list(observed_responses)
    if observed != expected:
        raise ProjectionMismatch(f"{projection['id']}: expected responses {expected}, observed {observed}")


def sio_checksum(payload):
    """Atari end-around-carry checksum used by the literal SIO fixture."""
    total = sum(payload)
    while total > 0xff:
        total = (total & 0xff) + (total >> 8)
    return total


def native_projection_fixture_ids(projection_id, manifest=None):
    """Return a guest sequence with its common Q preflight and idle poll."""
    manifest = load_manifest() if manifest is None else manifest
    validate_manifest(manifest)
    projection = next(item for item in manifest["projections"]
                      if item["id"] == projection_id)
    ids = expected_operation_ids(projection)
    approved = {
        "native-core-dispatch": ["w-core-dispatch", "p-core-dispatch-ready", "r-core-dispatch"],
        "native-wrong-r-retention": ["w-core-dispatch", "p-core-dispatch-ready",
                                      "r-wrong-length-retains", "p-core-dispatch-ready",
                                      "r-core-dispatch"],
        "native-reset-to-idle": ["w-core-dispatch", "p-core-dispatch-ready",
                                  "reset-clears", "w-core-dispatch-after-reset",
                                  "p-core-dispatch-ready", "r-core-dispatch-after-reset"],
        "native-interrupted-r-recovery": [
            "w-core-dispatch", "p-core-dispatch-ready",
            "r-core-dispatch-interrupted-consumes", "p-idle-after-consumed-r",
            "w-core-dispatch-after-interrupted-r", "p-core-dispatch-ready",
            "r-core-dispatch-after-interrupted-r"],
        "native-capacity-bounds": [
            "w-511", "p-ready-7", "r-ready-7", "w-512", "p-ready-512",
            "r-ready-512", "p-idle-after-consumed-r", "w-513-rejected",
            "w-oversize-response", "p-ready-7", "r-bounded-error-response"],
    }
    if projection_id not in approved or ids != approved[projection_id]:
        raise ProjectionError(f"{projection_id}: projection no longer names the approved literal sequence")
    terminal_idle = ("p-idle-after-consumed-r"
                     if projection_id in {"native-interrupted-r-recovery", "native-capacity-bounds"}
                     else "reset-clears")
    return ["q-idle", *ids, terminal_idle]


def native_core_dispatch_fixture_ids(manifest=None):
    """Compatibility helper for the established core-dispatch projection."""
    return native_projection_fixture_ids("native-core-dispatch", manifest)


def _hex(value):
    return bytes.fromhex(value) if value else b""


def fixture_payload(fixture):
    """Materialize an independent raw-packet pattern named by a fixture."""
    if "payload" in fixture:
        return _hex(fixture["payload"])
    raw = fixture.get("raw_fujibus")
    if raw is None:
        return b""
    if raw.get("payload_pattern") != "packet_offset ^ (packet_offset >> 8) ^ 0xa5":
        raise ProjectionError(f"{fixture['id']}: unsupported raw-packet pattern")
    packet = bytearray((raw["device"], raw["fujibus_command"], 0, 0, 0, 0))
    if "status" in raw:
        packet[5] = 1
        packet.append(raw["status"])
    if raw["payload_offset"] != len(packet):
        raise ProjectionError(f"{fixture['id']}: raw packet offset is invalid")
    packet.extend((offset ^ (offset >> 8) ^ 0xa5) & 0xff
                  for offset in range(raw["payload_offset"],
                                      raw["payload_offset"] + raw["payload_length"]))
    packet[2:4] = len(packet).to_bytes(2, "little")
    packet[4] = sio_checksum(packet)
    if packet[4] != int(raw["packet_checksum"], 16):
        raise ProjectionError(f"{fixture['id']}: raw packet checksum differs from literal fixture")
    return bytes(packet)


def _nio_datagrams(log):
    """Extract complete UDP frames from the production NetSIO process log."""
    events = []
    pattern = re.compile(r"udp: (Received|Sending) (\d+) bytes: ([0-9A-F ]+)$", re.MULTILINE)
    for match in pattern.finditer(log):
        data = _hex(match.group(3))
        if len(data) != int(match.group(2)):
            raise ProjectionMismatch(f"NetSIO log byte-count mismatch: {match.group(0)!r}")
        events.append((match.group(1).lower(), data))
    if not events:
        raise ProjectionMismatch("NetSIO log contains no captured UDP datagrams")
    return events


def _fixture_reply(fixture, command):
    """Split an independent fixture reply into native control/data fields."""
    controls = []
    reply_payload = None
    for part in fixture["reply"]:
        if len(part) == 1:
            controls.append(ord(part))
        elif reply_payload is None:
            reply_payload = _hex(part)
        else:
            raise ProjectionError(f"{fixture['id']}: fixture has more than one response payload")
    # R keeps its literal packet bytes in the fixture request/response pair,
    # while Q and P carry their bytes directly in reply.
    payload = reply_payload if reply_payload is not None else (
        fixture_payload(fixture) if command == "R" else b"")
    checksum = (int(fixture["payload_checksum"], 16)
                if payload and "payload_checksum" in fixture else
                sio_checksum(payload) if payload else None)
    return controls, payload, checksum


def _native_response_datagrams(window):
    """Keep only NetSIO packets that encode native SIO response bytes.

    Credit and lifecycle packets deliberately remain out of this view.  Every
    SIO control, payload, or checksum packet must instead appear here exactly
    once and in order.
    """
    return [data for direction, data in window
            if direction == "sending" and data and data[0] in (0x81, 0x01, 0x02)]


def _assert_response_packets(identifier, packets, expected):
    """Compare the complete captured response packet sequence, byte by byte."""
    if len(packets) != len(expected):
        raise ProjectionMismatch(
            f"{identifier}: expected {len(expected)} native response packets, found {len(packets)}")
    for ordinal, (actual, (kind, value, aux)) in enumerate(zip(packets, expected)):
        if kind == "sync":
            if (len(actual) != 6 or actual[0] != 0x81 or actual[2] != 0x01 or
                    actual[3] != value or actual[4:6] != aux.to_bytes(2, "little")):
                raise ProjectionMismatch(
                    f"{identifier}: response packet {ordinal} is not exact {chr(value)} sync control")
        elif kind == "byte":
            if actual != bytes((0x01, value)):
                raise ProjectionMismatch(
                    f"{identifier}: response packet {ordinal} is not exact {chr(value)} control")
        elif kind == "payload":
            if actual != bytes((0x02,)) + value:
                raise ProjectionMismatch(
                    f"{identifier}: response packet {ordinal} payload differs from literal fixture")
        elif kind == "checksum":
            if actual != bytes((0x01, value)):
                raise ProjectionMismatch(
                    f"{identifier}: response packet {ordinal} checksum differs from literal fixture")
        else:  # pragma: no cover - local construction below is exhaustive.
            raise ProjectionError(f"{identifier}: unknown response packet kind {kind!r}")


def compare_netsio_native_projection(log, projection_id, manifest=None, fixture_data=None):
    """Byte-verify a real NetSIO trace for an approved guest sequence.

    This consumes the production adapter's UDP capture.  It does not create a
    peer or call the frontend; it only checks observed command, control, data,
    and checksum datagrams against the independent fixture literals.
    """
    manifest = load_manifest() if manifest is None else manifest
    fixture_data = load_json(NIO_PATH) if fixture_data is None else fixture_data
    dispatches = 2 if projection_id in {"native-reset-to-idle", "native-interrupted-r-recovery"} else \
        3 if projection_id == "native-capacity-bounds" else 1
    observed_dispatches = [int(value) for value in re.findall(
        r"core-dispatch fixture route invocation (\d+)", log)]
    if observed_dispatches != list(range(1, dispatches + 1)):
        raise ProjectionMismatch(
            f"{projection_id}: expected exactly {dispatches} real-core dispatches, "
            f"observed {observed_dispatches}")
    fixtures = {item["id"]: item for item in fixture_data["scenarios"]}
    ids = native_projection_fixture_ids(projection_id, manifest)
    events = _nio_datagrams(log)
    command_positions = [index for index, (direction, data) in enumerate(events)
                         if direction == "received" and len(data) == 7 and data[0] == 0x02
                         and data[1] == 0x7f and data[2] in b"QWPR"]

    # Atari OS SIOV retries NAKed requests before returning its NAK status.
    # Treat that bounded, contiguous burst as one logical wrong-R operation,
    # while still checking every physical command and NAK response below.
    expanded_ids = []
    position_index = 0
    for identifier in ids:
        expected_command = _hex(fixtures[identifier]["frame"])
        if identifier == "r-wrong-length-retains":
            attempts = 0
            while position_index < len(command_positions):
                observed_command = events[command_positions[position_index]][1][1:6]
                if observed_command != expected_command:
                    break
                expanded_ids.append(identifier)
                position_index += 1
                attempts += 1
            if attempts == 0:
                raise ProjectionMismatch("r-wrong-length-retains: SIOV did not issue the wrong-length R")
            continue
        if identifier == "r-core-dispatch-interrupted-consumes":
            if position_index >= len(command_positions):
                raise ProjectionMismatch("interrupted terminal R is missing")
            if events[command_positions[position_index]][1][1:6] != expected_command:
                raise ProjectionMismatch("interrupted terminal R has an unexpected command frame")
            expanded_ids.append(identifier)
            position_index += 1
            # A checksum fault can make Atari OS retry the same SIOV request.
            # Those physical retries are not new logical R operations: after
            # the accepted first R they must observe consumed-slot NAKs.
            while position_index < len(command_positions):
                observed_command = events[command_positions[position_index]][1][1:6]
                if observed_command != expected_command:
                    break
                expanded_ids.append("r-core-dispatch-consumed-nak")
                position_index += 1
            continue
        if identifier == "w-513-rejected":
            attempts = 0
            while position_index < len(command_positions):
                observed_command = events[command_positions[position_index]][1][1:6]
                if observed_command != expected_command:
                    break
                expanded_ids.append(identifier)
                position_index += 1
                attempts += 1
            if attempts == 0:
                raise ProjectionMismatch("w-513-rejected: SIOV did not issue the bounded W")
            continue
        if position_index >= len(command_positions):
            raise ProjectionMismatch(f"{identifier}: missing native command frame")
        if events[command_positions[position_index]][1][1:6] != expected_command:
            raise ProjectionMismatch(f"{identifier}: unexpected native command ordering")
        expanded_ids.append(identifier)
        position_index += 1
    if position_index != len(command_positions):
        raise ProjectionMismatch(f"unexpected extra native command frames: found {len(command_positions)}")

    if projection_id == "native-reset-to-idle":
        # The runner injects the supported one-byte NetSIO COLD_RESET.  It is
        # distinct from Altirra's normal two-byte launch reset and must land
        # after the first READY poll but before the IDLE poll that proves the
        # frontend discarded the queued response.
        reset_positions = [index for index, (direction, data) in enumerate(events)
                           if direction == "received" and data == b"\xff"]
        if len(reset_positions) != 1:
            raise ProjectionMismatch("native-reset-to-idle: missing or duplicated injected NetSIO reset")
        if not (command_positions[2] < reset_positions[0] < command_positions[3]):
            raise ProjectionMismatch("native-reset-to-idle: reset is not between READY and post-reset IDLE")
        reset_text = log[log.find("udp: Received 1 bytes: FF"):]
        if not reset_text.startswith("udp: Received 1 bytes: FF") or "l_netsio: COLD_RESET" not in reset_text:
            raise ProjectionMismatch("native-reset-to-idle: captured reset did not reach the production ingress")

    physical_observed = []
    for ordinal, (identifier, position) in enumerate(zip(expanded_ids, command_positions)):
        fixture = fixtures[identifier]
        expected_command = _hex(fixture["frame"])
        direction, command_datagram = events[position]
        if command_datagram[1:6] != expected_command:
            raise ProjectionMismatch(
                f"{identifier}: expected command {expected_command.hex(' ')}, "
                f"observed {command_datagram[1:6].hex(' ')}")
        end = command_positions[ordinal + 1] if ordinal + 1 < len(command_positions) else len(events)
        window = events[position + 1:end]
        entry = {"fixture": identifier, "command": command_datagram[1:6].hex(' ')}

        command = fixture["command"]
        controls, response_payload, response_checksum = _fixture_reply(fixture, command)
        if command == "W":
            payload = fixture_payload(fixture)
            expected_checksum = (int(fixture["payload_checksum"], 16)
                                 if payload else None)
            incoming = [data for direction, data in window
                        if direction == "received" and data and data[0] in (0x02, 0x09)]
            if controls == [ord("N")]:
                if incoming:
                    raise ProjectionMismatch(f"{identifier}: rejected W entered a data phase")
                response_packets = _native_response_datagrams(window)
                _assert_response_packets(identifier, response_packets, [("sync", ord("N"), 0)])
                entry.update({"data": "", "checksum": None,
                              "response": {"controls": ["N"], "payload": "", "checksum": None}})
            elif controls == [ord("A"), ord("C")] and not response_payload and response_checksum is None:
                data_frames = [data for data in incoming if data[0] == 0x02]
                checksum_frames = [data for data in incoming if data[0] == 0x09]
                if not data_frames or len(checksum_frames) != 1:
                    raise ProjectionMismatch(f"{identifier}: expected native data and one checksum datagram")
                # NetSIO credit flow may divide one physical SIO data phase
                # into carrier DATA_BLOCKs.  It never changes the one native
                # packet: concatenate every block (excluding its sequence
                # byte) and reject any missing, duplicate, or padded byte.
                delivered = b"".join(frame[1:-1] for frame in data_frames)
                checksum_frame = checksum_frames[0]
                if delivered != payload:
                    raise ProjectionMismatch(f"{identifier}: payload differs from literal fixture")
                if len(checksum_frame) != 4 or checksum_frame[:2] != bytes((0x09, expected_checksum)):
                    raise ProjectionMismatch(f"{identifier}: payload checksum differs from literal fixture")
                response_packets = _native_response_datagrams(window)
                _assert_response_packets(identifier, response_packets, [
                    # NetSIO's receive grant includes the SIO checksum byte; the
                    # literal W AUX remains the packet-data length.
                    ("sync", ord("A"), fixture["aux"] + 1),
                    ("sync", ord("A"), 0),
                    ("byte", ord("C"), 0),
                ])
                entry.update({"data": delivered.hex(' '), "checksum": f"{checksum_frame[1]:02x}",
                              "response": {"controls": [chr(response_packets[1][3]),
                                                        chr(response_packets[2][1])],
                                           "payload": "", "checksum": None}})
            else:
                raise ProjectionError(f"{identifier}: fixture is not an accepted or bounded-rejected W")
        else:
            if not controls:
                raise ProjectionError(f"{identifier}: projection fixture must describe a control reply")
            expected = [("sync", controls[0], 0)]
            expected.extend(("byte", control, 0) for control in controls[1:])
            if response_payload:
                expected.extend([("payload", response_payload, 0),
                                 ("checksum", response_checksum, 0)])
            response_packets = _native_response_datagrams(window)
            _assert_response_packets(identifier, response_packets, expected)
            actual_controls = [chr(response_packets[0][3])]
            actual_controls.extend(chr(packet[1]) for packet in response_packets[1:len(controls)])
            payload_index = len(controls)
            actual_payload = response_packets[payload_index][1:] if response_payload else b""
            actual_checksum = response_packets[payload_index + 1][1] if response_payload else None
            entry.update({"response": {"controls": actual_controls,
                                        "payload": actual_payload.hex(' '),
                                        "checksum": (None if actual_checksum is None
                                                     else f"{actual_checksum:02x}")}})
        physical_observed.append(entry)

    observed = []
    for entry in physical_observed:
        if entry["fixture"] in {"r-wrong-length-retains", "w-513-rejected"} and observed and \
           observed[-1]["fixture"] == entry["fixture"]:
            observed[-1]["siov_attempts"] += 1
        else:
            if entry["fixture"] in {"r-wrong-length-retains", "w-513-rejected"}:
                entry["siov_attempts"] = 1
            observed.append(entry)

    collapsed = []
    for entry in observed:
        if (entry["fixture"] == "r-core-dispatch-consumed-nak" and collapsed and
                collapsed[-1]["fixture"] == "r-core-dispatch-interrupted-consumes"):
            collapsed[-1]["siov_attempts"] = collapsed[-1].get("siov_attempts", 1) + 1
        else:
            if entry["fixture"] == "r-core-dispatch-interrupted-consumes":
                entry["siov_attempts"] = 1
            collapsed.append(entry)
    observed = collapsed

    projection = next(item for item in manifest["projections"] if item["id"] == projection_id)
    compare_observed_operations(projection, [entry["fixture"] for entry in observed[1:-1]])
    return observed


def compare_netsio_native_core_dispatch(log, manifest=None, fixture_data=None):
    """Byte-verify the established real NetSIO core-dispatch trace."""
    return compare_netsio_native_projection(log, "native-core-dispatch", manifest, fixture_data)


def compare_netsio_native_wrong_r_retention(log, manifest=None, fixture_data=None):
    """Byte-verify real wrong-length-R retention through NetSIO."""
    return compare_netsio_native_projection(log, "native-wrong-r-retention", manifest, fixture_data)


def compare_netsio_native_reset_to_idle(log, manifest=None, fixture_data=None):
    """Byte-verify the real NetSIO reset while a native response is queued."""
    return compare_netsio_native_projection(log, "native-reset-to-idle", manifest, fixture_data)


def compare_netsio_native_interrupted_r_recovery(log, manifest=None, fixture_data=None):
    """Verify an accepted terminal R that was consumed before guest failure."""
    return compare_netsio_native_projection(log, "native-interrupted-r-recovery", manifest, fixture_data)


def compare_netsio_native_capacity_bounds(log, manifest=None, fixture_data=None):
    """Byte-verify packet-native 511/512/513-byte behavior through NetSIO."""
    return compare_netsio_native_projection(log, "native-capacity-bounds", manifest, fixture_data)


_POKEY_SIODATA = re.compile(
    r"\[SIODATA\].*?\b(?P<direction>SendCmd|Send|Receive)\s+(?:<\s+)?\$(?P<byte>[0-9A-F]{2})",
    re.MULTILINE)


def _embedded_sio_events(log):
    """Read literal serial bytes emitted by Altirra's real POKEY SIO path."""
    events = [(match.group("direction"), int(match.group("byte"), 16), match.start())
              for match in _POKEY_SIODATA.finditer(log)]
    if not events:
        raise ProjectionMismatch("Altirra embedded projection has no POKEY SIODATA evidence")
    return events


def compare_altirra_embedded_native_projection(pokey_log, altirra_log, projection_id,
                                                manifest=None, fixture_data=None):
    """Byte-verify an approved native projection through Altirra's SIO device.

    The input is captured POKEY traffic, not a reconstructed protocol trace.
    The endpoint's deterministic downstream device is allowed to log only its
    real RoutingManager invocation; all command and reply bytes are compared
    to the independent literal fixture.
    """
    if projection_id not in {"native-core-dispatch", "native-wrong-r-retention",
                             "native-reset-to-idle", "native-interrupted-r-recovery",
                             "native-capacity-bounds"}:
        raise ProjectionError(f"{projection_id}: no embedded projection comparison is implemented")
    manifest = load_manifest() if manifest is None else manifest
    fixture_data = load_json(NIO_PATH) if fixture_data is None else fixture_data
    fixtures = {item["id"]: item for item in fixture_data["scenarios"]}
    ids = native_projection_fixture_ids(projection_id, manifest)
    dispatches = [int(value) for value in re.findall(
        r"core dispatch fixture route invocation (\d+)", altirra_log)]
    expected_dispatches = (
        [1, 2, 3] if projection_id == "native-capacity-bounds" else
        [1, 2] if projection_id in {
            "native-reset-to-idle", "native-interrupted-r-recovery"} else [1])
    if dispatches != expected_dispatches:
        raise ProjectionMismatch(
            f"{projection_id}: expected embedded real-core dispatches {expected_dispatches}, "
            f"observed {dispatches}")

    events = _embedded_sio_events(pokey_log)
    command_events = [(byte, position) for direction, byte, position in events
                      if direction == "SendCmd"]
    native_starts = [index for index, (byte, _) in enumerate(command_events)
                     if byte == 0x7f]
    physical_frames = []
    for start in native_starts:
        frame = bytes(byte for byte, _ in command_events[start:start + 5])
        if len(frame) != 5:
            raise ProjectionMismatch(f"{projection_id}: truncated native POKEY command frame")
        physical_frames.append((frame, command_events[start][1]))

    # Atari OS retries a NAKed SIOV request.  The retry count is deliberately
    # not prescribed, but every physical retry must be the literal wrong-R
    # frame and receive its own NAK before this is collapsed into one logical
    # fixture operation.
    expanded_ids = []
    physical_index = 0
    for identifier in ids:
        expected = _hex(fixtures[identifier]["frame"])
        if identifier in {"r-wrong-length-retains", "w-513-rejected"}:
            attempts = 0
            while physical_index < len(physical_frames) and physical_frames[physical_index][0] == expected:
                expanded_ids.append(identifier)
                physical_index += 1
                attempts += 1
            if not attempts:
                raise ProjectionMismatch(f"{identifier}: missing rejected SIOV attempt")
            continue
        if identifier == "r-core-dispatch-interrupted-consumes":
            attempts = 0
            while physical_index < len(physical_frames) and physical_frames[physical_index][0] == expected:
                expanded_ids.append(identifier if attempts == 0 else "r-core-dispatch-consumed-nak")
                physical_index += 1
                attempts += 1
            if attempts < 2:
                raise ProjectionMismatch(
                    "r-core-dispatch-interrupted-consumes: missing consumed-slot R retry")
            continue
        if physical_index >= len(physical_frames) or physical_frames[physical_index][0] != expected:
            raise ProjectionMismatch(f"{identifier}: POKEY command frame differs from literal fixture")
        expanded_ids.append(identifier)
        physical_index += 1
    if physical_index != len(physical_frames):
        raise ProjectionMismatch(f"{projection_id}: unexpected extra native command frame")

    physical_observed = []
    for ordinal, (identifier, (_, command_position)) in enumerate(
            zip(expanded_ids, physical_frames)):
        next_position = (physical_frames[ordinal + 1][1]
                         if ordinal + 1 < len(physical_frames) else float("inf"))
        window = [(direction, byte) for direction, byte, position in events
                  if command_position < position < next_position]
        if identifier == "r-core-dispatch-consumed-nak":
            fixture = fixtures["r-core-dispatch-interrupted-consumes"]
            command = "R"
            controls, payload, payload_checksum = [ord("N")], b"", None
        else:
            fixture = fixtures[identifier]
            command = fixture["command"]
            controls, payload, payload_checksum = _fixture_reply(fixture, command)
        response = [byte for direction, byte in window if direction == "Receive"]
        # The fixture's W ACK accepts its command frame.  Real SIO also has a
        # distinct data-frame ACK before terminal COMPLETE; it must follow
        # Altirra's post-data timing guard and is captured separately here.
        # A locally rejected oversized W receives NAK before the data phase;
        # unlike an accepted W it has no command/data ACK pair.
        physical_controls = ([ord("A")]
                             if command == "W" and identifier != "w-513-rejected"
                             else []) + controls
        interrupted_delivery = identifier == "r-core-dispatch-interrupted-consumes"
        delivered_checksum = (payload_checksum ^ 0x01
                              if interrupted_delivery and payload_checksum is not None
                              else payload_checksum)
        expected_response = bytes(physical_controls) + payload + (
            bytes((delivered_checksum,)) if delivered_checksum is not None else b"")
        if bytes(response) != expected_response:
            raise ProjectionMismatch(
                f"{identifier}: POKEY response bytes differ from literal fixture")
        entry = {"fixture": identifier, "command": fixture["frame"]}
        if identifier == "w-513-rejected":
            if any(direction == "Send" for direction, _ in window):
                raise ProjectionMismatch(
                    "w-513-rejected: rejected W unexpectedly entered a data phase")
            entry["data"] = ""
            entry["checksum"] = None
        elif command == "W":
            sent = bytes(byte for direction, byte in window if direction == "Send")
            expected_data = fixture_payload(fixture)
            expected_checksum = int(fixture["payload_checksum"], 16)
            if sent != expected_data + bytes((expected_checksum,)):
                raise ProjectionMismatch(
                    f"{identifier}: POKEY W data/checksum differs from literal fixture")
            entry["data"] = expected_data.hex(" ")
            entry["checksum"] = f"{expected_checksum:02x}"
        elif any(direction == "Send" for direction, _ in window):
            raise ProjectionMismatch(f"{identifier}: unexpected native outgoing data")
        entry["response"] = {
            "controls": [chr(value) for value in physical_controls],
            "payload": payload.hex(" "),
            "checksum": None if delivered_checksum is None else f"{delivered_checksum:02x}",
        }
        if interrupted_delivery:
            entry["delivery_interrupted"] = True
            entry["expected_checksum"] = f"{payload_checksum:02x}"
        physical_observed.append(entry)

    observed = []
    for entry in physical_observed:
        if entry["fixture"] == "r-core-dispatch-consumed-nak":
            if not observed or observed[-1]["fixture"] != "r-core-dispatch-interrupted-consumes":
                raise ProjectionMismatch("consumed terminal-R retry did not follow accepted terminal R")
            observed[-1]["siov_attempts"] += 1
            observed[-1]["consumed_retry_controls"].append(entry["response"]["controls"])
            continue
        if entry["fixture"] == "r-core-dispatch-interrupted-consumes":
            entry["siov_attempts"] = 1
            entry["consumed_retry_controls"] = []
        if entry["fixture"] in {"r-wrong-length-retains", "w-513-rejected"}:
            if observed and observed[-1]["fixture"] == entry["fixture"]:
                observed[-1]["siov_attempts"] += 1
                continue
            entry["siov_attempts"] = 1
        observed.append(entry)

    projection = next(item for item in manifest["projections"]
                      if item["id"] == projection_id)
    compare_observed_operations(projection, [entry["fixture"] for entry in observed[1:-1]])
    return observed


def compare_altirra_embedded_native_core_dispatch(pokey_log, altirra_log,
                                                   manifest=None, fixture_data=None):
    """Compatibility wrapper for the established embedded core projection."""
    return compare_altirra_embedded_native_projection(
        pokey_log, altirra_log, "native-core-dispatch", manifest, fixture_data)


def compare_altirra_embedded_native_wrong_r_retention(pokey_log, altirra_log,
                                                       manifest=None, fixture_data=None):
    """Byte-verify retained response state after one or more rejected R attempts."""
    return compare_altirra_embedded_native_projection(
        pokey_log, altirra_log, "native-wrong-r-retention", manifest, fixture_data)


def compare_altirra_embedded_native_reset_to_idle(pokey_log, altirra_log,
                                                   manifest=None, fixture_data=None):
    """Byte-verify embedded reset-to-idle with distinct post-reset dispatch."""
    return compare_altirra_embedded_native_projection(
        pokey_log, altirra_log, "native-reset-to-idle", manifest, fixture_data)


def compare_altirra_embedded_native_interrupted_r_recovery(pokey_log, altirra_log,
                                                            manifest=None, fixture_data=None):
    """Verify accepted R has a corrupted delivered checksum, then recovers."""
    return compare_altirra_embedded_native_projection(
        pokey_log, altirra_log, "native-interrupted-r-recovery", manifest, fixture_data)


def compare_altirra_embedded_native_capacity_bounds(pokey_log, altirra_log,
                                                     manifest=None, fixture_data=None):
    """Byte-verify the complete embedded 511/512/513-byte packet boundary."""
    return compare_altirra_embedded_native_projection(
        pokey_log, altirra_log, "native-capacity-bounds", manifest, fixture_data)


def evidence_paths_for_boot(run_dir: Path, adapter: str):
    run_dir = Path(run_dir)
    paths = {
        "altirra_log": run_dir / "altirra.log",
        "pokey_siodata": run_dir / "pokey-siodata.log",
        "screenshot": run_dir / "screen.png",
        "inspection": run_dir / "inspection.json",
    }
    if adapter == "netsio":
        paths.update({"hub_log": run_dir / "hub.log", "nio_log": run_dir / "nio.log"})
    return paths


def scenario_result(adapter, scenario_id, observed, evidence_paths, passed=True, error=None):
    """Return a machine-readable result; missing evidence is never a pass."""
    if adapter not in ADAPTERS:
        raise ProjectionError(f"unknown adapter {adapter!r}")
    if not isinstance(scenario_id, str) or not scenario_id:
        raise ProjectionError("scenario ID is required")
    normalized_paths = {name: str(Path(path)) for name, path in evidence_paths.items()}
    missing = [name for name in REQUIRED_EVIDENCE[adapter]
               if name not in normalized_paths or not Path(normalized_paths[name]).is_file()]
    status = "pass" if passed and not missing else "incomplete" if missing else "fail"
    return {
        "format": "atari-native-nio-v1-virtual-result",
        "scope": "virtual protocol/scheduling evidence only",
        "adapter": adapter,
        "scenario_id": scenario_id,
        "status": status,
        "passed": status == "pass",
        "observed": observed,
        "evidence_paths": normalized_paths,
        "missing_evidence": missing,
        "error": error,
    }


def write_scenario_result(output_dir: Path, result):
    output_dir = Path(output_dir) / result["adapter"]
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{result['scenario_id']}.json"
    path.write_text(json.dumps(result, indent=2) + "\n")
    return path
