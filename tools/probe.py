#!/usr/bin/env python3
"""Map the MIoT properties of a Dreame dehumidifier from a real unit.

Dreame dehumidifiers (for example the DD20, dreame.dehum.u2512) have no public
MIoT spec. This tool signs in to the Dreame cloud the way the Dreamehome app
does and helps work the property map out. Run it from a computer, not inside
Home Assistant.

    python3 tools/probe.py list
    python3 tools/probe.py sweep --did <id>        # which siid/piid exist (reads only)
    python3 tools/probe.py learn --did <id>        # what each one means (reads only)
    python3 tools/probe.py learn --did <id> --step "Turn X on" --step "Turn X off"
    python3 tools/probe.py write --did <id> 2/5 55 # write one property, then read it back

sweep reads every address in a range and saves the ones that answer. learn
walks you through changing one setting at a time in the Dreamehome app and
records which properties changed. write is the only command that changes
anything on the device: it asks for confirmation and never runs actions.

Standard library only. The password is read with getpass and only its salted
hash is sent, as the app does. Reports leave out account and device
identifiers and replace text values with their length, so they can be shared.
Check them before sharing anyway.
"""

from __future__ import annotations

import argparse
import getpass
import hashlib
import json
from pathlib import Path
import re
import sys
import time
from typing import Any
import urllib.error
import urllib.parse
import urllib.request

# Public constants of the Dreamehome app, the same for every install.
SALT = "RAylYC%fmSKp7%Tq"
USER_AGENT = "Dreame_Smarthome/2.1.9 (iPhone; iOS 18.4.1; Scale/3.00)"
CLIENT_AUTH = "Basic " + "ZHJlYW1lX2FwcHYx" + "OkFQXmR2QHpAU1FZVnhOODg="
RLC = "1c80b3787b2266776bcdc481f37d8fa42ba10a30af81a6df-1"

BATCH = 8
# The cloud answers code 0 with these values for addresses the device doesn't have.
MISSING_SERVICE = -4005
MISSING_PROPERTY = -4001
MISSING = {MISSING_PROPERTY, MISSING_SERVICE}

# Keys of the device record that identify the user or the unit.
PRIVATE_KEYS = re.compile(
    r"^id$|did|mac|ip|sn|serial|uid|name|bind|owner|master|token|key|lat|lon|address|ssid|wifi|property|status|time",
    re.I,
)
NUMERIC_TEXT = re.compile(r"^[\d._]{1,16}$")

LEARN_STEPS = (
    "Turn the dehumidifier ON",
    "Turn the dehumidifier OFF (standby)",
    "Turn it ON again",
    "Select the FIRST mode in the app (write its name in the note)",
    "Select the SECOND mode (write its name)",
    "Select the THIRD mode (write its name)",
    "Select any other mode, if there is one (write its name)",
    "Set the target humidity to 45%",
    "Set the target humidity to 55%",
    "Change the fan speed to LOW (if the current mode allows it)",
    "Change the fan speed to HIGH",
    "Turn the child lock ON",
    "Turn the child lock OFF",
    "Toggle the key / button sound",
    "Toggle the display or light",
    "Toggle the plasma / antibacterial / ion function",
    "Toggle the swing / louver, if there is one",
    "Set a timer (write the hours)",
    "Cancel the timer",
    "Toggle any other setting you see in the app (write its name)",
)


def post(url: str, headers: dict[str, str], body: bytes) -> dict[str, Any]:
    request = urllib.request.Request(url, data=body, headers={"User-Agent": USER_AGENT, **headers}, method="POST")  # noqa: S310
    with urllib.request.urlopen(request, timeout=45) as response:  # noqa: S310 - fixed https URL
        return json.loads(response.read())


def redact_record(value: Any) -> Any:
    """Keep the shape and the catalog data of the device record, drop identifiers."""
    if isinstance(value, str) and value.startswith(("{", "[")):
        try:
            return redact_record(json.loads(value))
        except ValueError:
            return f"<string, {len(value)} chars>"
    if isinstance(value, dict):
        return {k: ("<redacted>" if PRIVATE_KEYS.search(k) else redact_record(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_record(v) for v in value]
    return value


def redact_value(value: Any) -> Any:
    """Hide text values (serials, place names...); keep their type and length."""
    if isinstance(value, str) and value and not NUMERIC_TEXT.match(value):
        return f"<string, {len(value)} chars>"
    return value


def parse_address(text: str) -> tuple[int, int]:
    siid, piid = (int(part) for part in text.split("/"))
    return siid, piid


class Cloud:
    def __init__(self, region: str) -> None:
        self.base = f"https://{region}.iot.dreame.tech:13267"
        self.headers: dict[str, str] = {}
        self.did = ""
        self.prefix = ""

    def login(self) -> None:
        form = urllib.parse.urlencode(
            {
                "platform": "IOS",
                "scope": "all",
                "grant_type": "password",
                "username": input("Dreamehome email: "),
                "password": hashlib.md5((getpass.getpass("Password: ") + SALT).encode()).hexdigest(),  # noqa: S324
                "type": "account",
            }
        ).encode()
        try:
            result = post(
                f"{self.base}/dreame-auth/oauth/token",
                {
                    "Authorization": CLIENT_AUTH,
                    "Tenant-Id": "000000",
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Dreame-Rlc": RLC,
                },
                form,
            )
        except urllib.error.HTTPError as err:
            sys.exit(f"Sign-in failed with HTTP {err.code}. Check the email, password and --region.")
        if "access_token" not in result:
            sys.exit(f"Sign-in failed: {result.get('error_description') or result.get('msg') or 'no token'}")
        self.headers = {
            "Authorization": CLIENT_AUTH,
            "Tenant-Id": result.get("tenant_id", "000000"),
            "Dreame-Auth": result["access_token"],
            "Content-Type": "application/json",
        }

    def devices(self) -> list[dict[str, Any]]:
        return post(f"{self.base}/dreame-user-iot/iotuserbind/device/listV2", self.headers, b"{}")["data"]["page"][
            "records"
        ]

    def select(self, did: str) -> dict[str, Any]:
        device = next((d for d in self.devices() if str(d.get("did")) == did), None)
        if device is None:
            sys.exit("No device with that ID on this account.")
        self.did = did
        host = device.get("bindDomain")
        self.prefix = f"-{host.split('.')[0]}" if host else ""
        return device

    def command(self, method: str, params: Any) -> Any:
        payload = {"did": self.did, "id": 1, "data": {"did": self.did, "id": 1, "method": method, "params": params}}
        try:
            body = post(
                f"{self.base}/dreame-iot-com{self.prefix}/device/sendCommand",
                self.headers,
                json.dumps(payload).encode(),
            )
        except (urllib.error.URLError, TimeoutError):
            return None
        data = body.get("data")
        if body.get("code") != 0 or not isinstance(data, dict):
            return None
        return data.get("result")

    def read(self, addresses: list[tuple[int, int]]) -> dict[tuple[int, int], Any] | None:
        """Read a batch. None means the request failed or timed out."""
        result = self.command("get_properties", [{"did": self.did, "siid": s, "piid": p} for s, p in addresses])
        if not isinstance(result, list):
            return None
        return {(i["siid"], i["piid"]): i.get("value") for i in result if i.get("code") == 0}

    def read_many(self, addresses: list[tuple[int, int]]) -> dict[tuple[int, int], Any]:
        values: dict[tuple[int, int], Any] = {}
        for start in range(0, len(addresses), BATCH):
            batch = addresses[start : start + BATCH]
            result = self.read(batch)
            if result is None:
                time.sleep(1)
                result = self.read(batch)  # reads are safe to retry
            values.update(result or {})
            time.sleep(0.3)
        return values


def cmd_list(cloud: Cloud, _args: argparse.Namespace) -> None:
    for device in cloud.devices():
        print(f"{device.get('did')}  {device.get('model')}  {device.get('customName') or ''}")


def cmd_sweep(cloud: Cloud, args: argparse.Namespace) -> None:
    device = cloud.select(args.did)
    print(f"Sweeping {device.get('model')}: siid 1-{args.max_siid}, piid 1-{args.max_piid}. Reads only.")
    found: dict[str, Any] = {}
    failed: list[str] = []
    for siid in range(1, args.max_siid + 1):
        for start in range(1, args.max_piid + 1, BATCH):
            batch = [(siid, p) for p in range(start, min(start + BATCH, args.max_piid + 1))]
            result = cloud.read(batch)
            if result is None:
                # Retry one at a time, so one bad address doesn't hide the others.
                result = {}
                for address in batch:
                    single = cloud.read([address])
                    if single is None:
                        failed.append(f"{address[0]}/{address[1]}")
                    else:
                        result.update(single)
                    time.sleep(0.3)
            for (s, p), value in result.items():
                if value not in MISSING:
                    found[f"{s}/{p}"] = redact_value(value)
            time.sleep(0.3)
        print(f"  siid {siid}: {sum(k.startswith(f'{siid}/') for k in found)} properties")
    report = {
        "model": device.get("model"),
        "firmware": device.get("ver"),
        "range": {"max_siid": args.max_siid, "max_piid": args.max_piid},
        "properties": found,
        "timed_out": failed,
        "device_record": redact_record(device),
    }
    Path(args.out).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(f"\n{len(found)} properties found. Report written to {args.out}. Check it before sharing.")


def _known_addresses(report: str) -> list[tuple[int, int]]:
    try:
        properties = json.loads(Path(report).read_text())["properties"]
    except (OSError, ValueError, KeyError):
        sys.exit(f"Run sweep first: {report} is missing or unreadable.")
    return sorted(parse_address(k) for k, v in properties.items() if v not in MISSING)


def cmd_learn(cloud: Cloud, args: argparse.Namespace) -> None:
    device = cloud.select(args.did)
    addresses = _known_addresses(args.report)
    print(f"Learning {device.get('model')} from {len(addresses)} properties. Reads only.")
    print("For each step: do it in the Dreamehome app, wait until the unit reacts, then press Enter.")
    print("Type a note before Enter to name what you did (a mode name, the timer hours...).")
    print("Type s to skip a step, q to stop and save.\n")
    before = cloud.read_many(addresses)
    steps: list[dict[str, Any]] = []
    plan = tuple(args.step) if args.step else LEARN_STEPS
    for number, text in enumerate(plan, 1):
        answer = input(f"[{number}/{len(plan)}] {text}: ").strip()
        if answer.lower() == "q":
            break
        if answer.lower() == "s":
            continue
        time.sleep(2)
        # An address missing from either read failed to answer: carry its last value
        # forward instead of reporting it as a change.
        after = {**before, **cloud.read_many(addresses)}
        changes = {
            f"{s}/{p}": [redact_value(before.get((s, p))), redact_value(value)]
            for (s, p), value in after.items()
            if (s, p) in before and before[(s, p)] != value
        }
        for key, (old, new) in changes.items():
            print(f"    {key}: {old} -> {new}")
        if not changes:
            print("    nothing changed")
        steps.append({"step": text, "note": answer, "changes": changes})
        before = after
    report = {"model": device.get("model"), "firmware": device.get("ver"), "steps": steps}
    Path(args.out).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(f"\nSaved to {args.out}. Check the notes before sharing: they are saved as you typed them.")


def cmd_write(cloud: Cloud, args: argparse.Namespace) -> None:
    device = cloud.select(args.did)
    siid, piid = parse_address(args.address)
    value: Any = json.loads(args.value)
    current = (cloud.read([(siid, piid)]) or {}).get((siid, piid))
    print(f"{device.get('model')} {siid}/{piid} is now {redact_value(current)!r}.")
    if input(f"Write {value!r} to {siid}/{piid}? [y/N] ").strip().lower() != "y":
        sys.exit("Nothing written.")
    result = cloud.command("set_properties", [{"did": cloud.did, "siid": siid, "piid": piid, "value": value}])
    print(f"  reply: {json.dumps(result)}")
    time.sleep(3)
    print(f"  read back: {redact_value((cloud.read([(siid, piid)]) or {}).get((siid, piid)))!r}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--region", default="eu", help="us, eu, sg, ru, kr or cn (default eu)")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="list the devices on the account")
    sweep = sub.add_parser("sweep", help="find which properties exist (reads only)")
    sweep.add_argument("--did", required=True)
    sweep.add_argument("--max-siid", type=int, default=12)
    sweep.add_argument("--max-piid", type=int, default=40)
    sweep.add_argument("--out", default="sweep-report.json")
    learn = sub.add_parser("learn", help="find what each property means (reads only)")
    learn.add_argument("--did", required=True)
    learn.add_argument("--report", default="sweep-report.json", help="sweep report to take the addresses from")
    learn.add_argument("--out", default="learn-report.json")
    learn.add_argument(
        "--step", action="append", help="a step of your own, instead of the built-in list (repeat for more)"
    )
    write = sub.add_parser("write", help="write one property and read it back")
    write.add_argument("--did", required=True)
    write.add_argument("address", help="siid/piid, for example 2/5")
    write.add_argument("value", help="JSON value, for example 55 or true")
    args = parser.parse_args()

    cloud = Cloud(args.region)
    cloud.login()
    {"list": cmd_list, "sweep": cmd_sweep, "learn": cmd_learn, "write": cmd_write}[args.command](cloud, args)


if __name__ == "__main__":
    main()
