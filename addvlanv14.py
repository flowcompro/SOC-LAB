 #!/usr/bin/env python3
"""
Cisco IOS and IOS XE VLAN Trunk Manager
Version: v14
Author: Kevin Flowers
================================================================================
COMMANDS TO RUN
================================================================================

ADD VLANs to trunks and create VLANs globally if missing
python addvlansv14.py --switches switches.txt --vlans vlans.csv --verbose

REMOVE VLANs from trunks and delete from VLAN database
This removes VLANs from trunks, deletes any SVI if present, then deletes VLANs
globally, with verification output.
python addvlansv14.py --switches switches.txt --vlans vlans.csv --remove --delete-svi --delete-vlans-global --verbose --verify

================================================================================

Key fix in v14
SVI detection is now strict and reliable.
Older versions used "show running-config interface Vlan<ID>" and searched for the string "interface Vlan".
On some switches that do not support SVIs, that command returns an error that can still contain those words.
That created false blockers and prevented "no vlan <ID>" from running.

v14 uses:
show running-config | section ^interface Vlan<ID>$

Only if the output contains a real config stanza starting with:
interface Vlan<ID>
will it be treated as an SVI that blocks VLAN deletion.

INSTRUCTIONS
================================================================================

Overview
This script connects to each switch in your inventory file, discovers trunk
ports, and then either adds or removes VLANs based on the VLAN file you provide.

In ADD mode it creates missing VLANs in the VLAN database and then adds only the
missing VLANs to each trunk allowed list.

In REMOVE mode it removes only the target VLANs from trunk allowed lists and can
optionally delete the VLAN from the VLAN database so it disappears from show vlan.

================================================================================
FILES YOU PROVIDE
================================================================================

1) Switch inventory file

TXT format
Each line is a switch IP or hostname.
Blank lines and lines starting with # are ignored.

Example switches.txt
10.192.25.14
10.192.25.10
10.192.25.12

CSV format
Must include a header with a column named ip or host.

Example switches.csv
ip
10.192.25.14
10.192.25.10

2) VLAN file

TXT format
Each line is a VLAN ID.
Blank lines and lines starting with # are ignored.

Example vlans.txt
300
999

CSV format
Must include a header with a column named vlan_id or vlan or id.
Optional name column can be name or vlan_name.

Example vlans.csv
vlan_id,name
300,test
999,NATIVE_PARKING

================================================================================
CREDENTIALS AND ENABLE MODE
================================================================================

The script will prompt for:
Username
Password
Enable secret

Enable secret is requested only once and then cached and reused for all switches.

If a switch starts at > prompt, the script will enter enable mode.
If a switch starts at # prompt, the script will continue without prompting.

================================================================================
WHAT THE SCRIPT DOES IN ADD MODE
================================================================================

Step 1  Connect to the switch and enter enable mode
Step 2  Disable terminal paging so command output does not pause
Step 3  Discover trunk ports using show interfaces trunk
Step 4  Read current VLAN database using show vlan brief
Step 5  Create only VLANs missing from the VLAN database
Step 6  For each trunk port, check the current allowed VLAN state
Step 7  Add only VLANs that are missing from that trunk port allowed list
Step 8  Save logs and move to the next switch

================================================================================
WHAT THE SCRIPT DOES IN REMOVE MODE
================================================================================

Step 1  Connect to the switch and enter enable mode
Step 2  Disable terminal paging so command output does not pause
Step 3  Discover trunk ports using show interfaces trunk
Step 4  For each trunk port, remove only the target VLANs if present
Step 5  Optional delete SVI interface Vlan<ID> if it exists
Step 6  Optional delete VLAN from VLAN database using no vlan <ID>
Step 7  Verify results and move to the next switch

================================================================================
IMPORTANT BEHAVIOR TO UNDERSTAND
================================================================================

Removing VLANs from trunk allowed lists does NOT remove the VLAN from the VLAN
database.

To fully remove a VLAN so it disappears from show vlan, you must run:
no vlan <ID>

VLAN deletion may be blocked for safety if:
An SVI interface Vlan<ID> exists
An access port references the VLAN
The VLAN still appears in trunk output

The script detects these conditions and safely skips deletion if needed.

================================================================================
SCRIPT SWITCHES AND WHAT THEY MEAN
================================================================================

--switches
Required.
Path to the switch inventory file.

--vlans
Required.
Path to the VLAN definitions file.

--verbose
Optional.
Prints per trunk port details including add_candidates or remove_candidates.

--verify
Optional.
Prints post change verification per VLAN:
exists_globally   VLAN still present in show vlan
svi_exists        interface Vlan<ID> still exists
trunk_has_vlan    VLAN still appears in trunk output

--remove
Optional.
Enables REMOVE mode.
Without this switch, the script runs in ADD mode.

--delete-svi
Optional.
REMOVE mode only.
Deletes interface Vlan<ID> if present.

--delete-vlans-global
Optional.
REMOVE mode only.
Deletes VLANs from the VLAN database using no vlan <ID>.

--dry-run
Optional.
No configuration changes are made.
The script still connects and shows what it would do.

--out
Optional.
Output directory for logs and backups.
Default is output_vlan_push.

================================================================================
OUTPUT FILES
================================================================================

Pre change backups are saved per switch under:
<out>\backups\<ip>\<timestamp>\

Session logs are saved under:
<out>\session_<ip>_<timestamp>.log

================================================================================
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import os
import re
from dataclasses import dataclass
from getpass import getpass
from typing import List, Optional, Set, Tuple, Callable

from netmiko import ConnectHandler, NetmikoTimeoutException, NetmikoAuthenticationException


@dataclass(frozen=True)
class VlanDef:
    vlan_id: int
    name: Optional[str] = None


def now_stamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d_%H%M%S")


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def is_probably_csv(path: str) -> bool:
    return path.lower().endswith(".csv")


def safe_filename(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.]+", "_", text).strip("_")


def read_switch_ips(path: str) -> List[str]:
    ips: List[str] = []
    seen = set()

    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        sample = f.read(2048)
        f.seek(0)

        if is_probably_csv(path) or ("," in sample and "ip" in sample.lower()):
            reader = csv.DictReader(f)
            if not reader.fieldnames:
                raise ValueError("Switch CSV has no header row")
            fields = [h.strip().lower() for h in reader.fieldnames]
            key = "ip" if "ip" in fields else ("host" if "host" in fields else None)
            if not key:
                raise ValueError("Switch CSV must include a column named ip or host")
            for row in reader:
                raw = (row.get(key) or "").strip()
                if raw and raw not in seen:
                    ips.append(raw)
                    seen.add(raw)
        else:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if line not in seen:
                    ips.append(line)
                    seen.add(line)

    return ips


def read_vlans(path: str) -> List[VlanDef]:
    vlans: List[VlanDef] = []
    seen = set()

    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        sample = f.read(2048)
        f.seek(0)

        if is_probably_csv(path) or ("," in sample and "vlan" in sample.lower()):
            reader = csv.DictReader(f)
            if not reader.fieldnames:
                raise ValueError("VLAN CSV has no header row")

            fields = [h.strip().lower() for h in reader.fieldnames]
            id_field = (
                "vlan_id" if "vlan_id" in fields
                else "vlan" if "vlan" in fields
                else "id" if "id" in fields
                else None
            )
            name_field = "name" if "name" in fields else ("vlan_name" if "vlan_name" in fields else None)

            if not id_field:
                raise ValueError("VLAN CSV must include vlan_id or vlan or id column")

            for row in reader:
                raw = (row.get(id_field) or "").strip()
                if not raw:
                    continue
                try:
                    vid = int(raw)
                except ValueError:
                    continue
                vname = (row.get(name_field) or "").strip() if name_field else ""
                if vid not in seen:
                    vlans.append(VlanDef(vid, vname if vname else None))
                    seen.add(vid)
        else:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.isdigit():
                    vid = int(line)
                    if vid not in seen:
                        vlans.append(VlanDef(vid))
                        seen.add(vid)

    return vlans


def parse_existing_vlans(show_vlan_brief: str) -> Set[int]:
    existing: Set[int] = set()
    for line in show_vlan_brief.splitlines():
        line = line.strip()
        if not line or line.lower().startswith("vlan"):
            continue
        m = re.match(r"^(\d+)\s+", line)
        if m:
            existing.add(int(m.group(1)))
    return existing


def build_vlan_create_cmds(vlans_to_create: List[VlanDef]) -> List[str]:
    cmds: List[str] = []
    for v in vlans_to_create:
        cmds.append(f"vlan {v.vlan_id}")
        if v.name:
            safe_name = re.sub(r"[^A-Za-z0-9 _]", "", v.name).strip()
            if safe_name:
                cmds.append(f"name {safe_name}")
        cmds.append("exit")
    return cmds


def expand_vlan_spec_to_set_or_all(spec: str) -> Optional[Set[int]]:
    raw = (spec or "").strip().lower()
    if not raw:
        return set()
    if raw == "all":
        return None
    if raw in {"1-4094", "1-4095", "1-4096"}:
        return None

    vlans: Set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            a = a.strip()
            b = b.strip()
            if a.isdigit() and b.isdigit():
                start = int(a)
                end = int(b)
                if start <= end:
                    for v in range(start, end + 1):
                        vlans.add(v)
        elif part.isdigit():
            vlans.add(int(part))
    return vlans


def chunk_vlan_list(vlans: List[int], max_len: int = 120) -> List[str]:
    chunks: List[str] = []
    current: List[str] = []
    current_len = 0

    for vid in vlans:
        s = str(vid)
        add_len = len(s) + (1 if current else 0)
        if current and (current_len + add_len) > max_len:
            chunks.append(",".join(current))
            current = [s]
            current_len = len(s)
        else:
            current_len = current_len + add_len if current else len(s)
            current.append(s)

    if current:
        chunks.append(",".join(current))

    return chunks


def parse_trunk_ports_from_show_interfaces_trunk(output: str) -> List[str]:
    trunk_ports: Set[str] = set()
    in_table = False

    for line in output.splitlines():
        raw = line.rstrip()
        if not raw:
            continue
        low = raw.lower()

        if low.startswith("port") and "mode" in low:
            in_table = True
            continue

        if not in_table:
            continue

        parts = raw.split()
        if not parts:
            continue

        if parts[0].lower() == "port":
            continue

        port = parts[0]
        if re.match(r"^(gi|te|fo|hu|tw|po|fa)\S+$", port.lower()):
            trunk_ports.add(port)

    return sorted(trunk_ports, key=lambda x: (len(x), x))


def get_allowed_vlans_for_interface(conn: ConnectHandler, iface: str) -> Optional[Set[int]]:
    out = conn.send_command(f"show interfaces {iface} switchport", use_textfsm=False)
    for line in out.splitlines():
        low = line.lower().strip()
        if low.startswith("trunking vlans allowed:"):
            spec = line.split(":", 1)[1].strip()
            return expand_vlan_spec_to_set_or_all(spec)
        if low.startswith("trunking vlans enabled:"):
            spec = line.split(":", 1)[1].strip()
            return expand_vlan_spec_to_set_or_all(spec)
    return set()


def connect_ios(ip: str, username: str, password: str, session_log: str, secret: Optional[str]) -> ConnectHandler:
    device = {
        "device_type": "cisco_ios",
        "host": ip,
        "username": username,
        "password": password,
        "secret": secret or "",
        "session_log": session_log,
        "fast_cli": False,
        "global_delay_factor": 1,
        "keepalive": 30,
        "conn_timeout": 20,
        "banner_timeout": 25,
        "auth_timeout": 25,
    }
    return ConnectHandler(**device)


def ensure_enable_mode(conn: ConnectHandler, ip: str, shared_secret: Optional[str]) -> Optional[str]:
    prompt = conn.find_prompt().strip()

    if prompt.endswith("#"):
        return shared_secret

    if prompt.endswith(">"):
        if not shared_secret:
            shared_secret = getpass("Enable secret: ")
        conn.secret = shared_secret
        conn.enable()
        prompt2 = conn.find_prompt().strip()
        if prompt2.endswith("#"):
            return shared_secret
        raise ValueError(f"{ip} enable failed. Prompt after enable attempt was: {prompt2}")

    raise ValueError(f"{ip} unexpected prompt: {prompt}")


def prep_terminal(conn: ConnectHandler) -> None:
    conn.send_command_timing("terminal length 0")
    conn.send_command_timing("terminal width 0")


def write_text_file(path: str, content: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def gather_prechange_backups(
    conn: ConnectHandler,
    out_dir: str,
    ip: str,
    run_id: str,
    vlan_ids: List[int],
    verbose: bool,
) -> str:
    base = os.path.join(out_dir, "backups", safe_filename(ip), run_id)
    ensure_dir(base)

    commands: List[Tuple[str, str, bool]] = [
        ("show_version.txt", "show version", True),
        ("show_vlan_brief.txt", "show vlan brief", False),
        ("show_interfaces_trunk.txt", "show interfaces trunk", False),
        ("show_spanning_tree_summary.txt", "show spanning-tree summary", False),
        ("show_run_vlan_section.txt", "show running-config | section ^vlan", True),
        ("show_run_interface_vlan_lines.txt", "show running-config | include interface Vlan", True),
        ("show_run_access_vlan_refs.txt", "show running-config | include switchport access vlan", True),
        ("show_run_trunk_allowed_refs.txt", "show running-config | include trunk allowed vlan", True),
    ]

    for filename, cmd, heavy in commands:
        try:
            out = conn.send_command_timing(cmd) if heavy else conn.send_command(cmd, use_textfsm=False)
        except Exception as e:
            out = f"ERROR running command: {cmd}\n{e}\n"
        write_text_file(os.path.join(base, filename), out)

    for vid in vlan_ids:
        try:
            out1 = conn.send_command_timing(f"show running-config | include vlan {vid}")
        except Exception as e:
            out1 = f"ERROR running command: show running-config | include vlan {vid}\n{e}\n"
        write_text_file(os.path.join(base, f"show_run_include_vlan_{vid}.txt"), out1)

        try:
            out2 = conn.send_command_timing(f"show running-config | section ^interface Vlan{vid}$")
        except Exception as e:
            out2 = f"ERROR running command: show running-config | section ^interface Vlan{vid}$\n{e}\n"
        write_text_file(os.path.join(base, f"show_run_section_interface_Vlan{vid}.txt"), out2)

    if verbose:
        print(f"  Pre change backups saved to: {base}")

    return base


def svi_exists(conn: ConnectHandler, vlan_id: int) -> bool:
    out = conn.send_command_timing(f"show running-config | section ^interface Vlan{vlan_id}$")
    return bool(re.search(rf"^interface Vlan{vlan_id}\b", out, flags=re.M))


def remove_svi_best_effort(conn: ConnectHandler, vlan_id: int, verbose: bool) -> bool:
    if not svi_exists(conn, vlan_id):
        return False

    attempts = [
        [f"no interface Vlan{vlan_id}"],
        [f"default interface Vlan{vlan_id}"],
    ]

    for cmdset in attempts:
        out = conn.send_config_set(cmdset, cmd_verify=False)
        bad = any(x in out.lower() for x in ["invalid input", "incomplete command", "ambiguous command"])
        if verbose and bad:
            print("  Device rejected SVI removal attempt, output follows")
            print(out.strip())
        if not svi_exists(conn, vlan_id):
            return True

    return False


def vlan_delete_blockers(conn: ConnectHandler, vlan_id: int) -> List[str]:
    blockers: List[str] = []

    if svi_exists(conn, vlan_id):
        blockers.append(f"SVI exists interface Vlan{vlan_id}")

    run_access = conn.send_command_timing(f"show running-config | include switchport access vlan {vlan_id}")
    if run_access.strip():
        blockers.append(f"Access ports reference vlan {vlan_id}")

    trunk_check = conn.send_command("show interfaces trunk | include " + str(vlan_id), use_textfsm=False)
    if trunk_check.strip():
        blockers.append("Still appears in show interfaces trunk output")

    return blockers


def verify_vlan_exists(conn: ConnectHandler, vlan_id: int) -> bool:
    vlan_out = conn.send_command("show vlan brief", use_textfsm=False)
    return vlan_id in parse_existing_vlans(vlan_out)


def build_trunk_cmds_for_mode(
    conn: ConnectHandler,
    trunk_ports: List[str],
    vlan_ids: List[int],
    mode: str,
    verbose: bool,
) -> List[str]:
    cmds: List[str] = []

    for iface in trunk_ports:
        allowed = get_allowed_vlans_for_interface(conn, iface)

        if mode == "remove":
            if allowed is None:
                candidates = vlan_ids[:]
                allowed_desc = "ALL"
            else:
                candidates = [v for v in vlan_ids if v in allowed]
                allowed_desc = "EXPLICIT"

            if verbose:
                print(f"  {iface} allowed={allowed_desc} remove_candidates={candidates}")

            if not candidates:
                continue

            cmds.append(f"interface {iface}")
            for chunk in chunk_vlan_list(candidates):
                cmds.append(f"switchport trunk allowed vlan remove {chunk}")
            cmds.append("exit")

        else:
            if allowed is None:
                candidates = []
                allowed_desc = "ALL"
            else:
                candidates = [v for v in vlan_ids if v not in allowed]
                allowed_desc = "EXPLICIT"

            if verbose:
                print(f"  {iface} allowed={allowed_desc} add_candidates={candidates}")

            if not candidates:
                continue

            cmds.append(f"interface {iface}")
            for chunk in chunk_vlan_list(candidates):
                cmds.append(f"switchport trunk allowed vlan add {chunk}")
            cmds.append("exit")

    if verbose and not cmds:
        print("  No trunk changes required")

    return cmds


def apply_changes_with_retry_and_secret_cache(
    ip: str,
    username: str,
    password: str,
    secret_in: Optional[str],
    session_log: str,
    apply_fn: Callable[[ConnectHandler, Optional[str]], Optional[str]],
) -> Optional[str]:
    secret = secret_in

    try:
        conn = connect_ios(ip, username, password, session_log, secret)
        secret = ensure_enable_mode(conn, ip, secret)
        prep_terminal(conn)
        secret = apply_fn(conn, secret)
        conn.disconnect()
        return secret
    except Exception as e:
        msg = str(e).lower()
        try:
            conn.disconnect()
        except Exception:
            pass
        if "socket is closed" not in msg:
            raise

    conn2 = connect_ios(ip, username, password, session_log, secret)
    secret = ensure_enable_mode(conn2, ip, secret)
    prep_terminal(conn2)
    secret = apply_fn(conn2, secret)
    conn2.disconnect()
    return secret


def run_switch(
    conn: ConnectHandler,
    vlan_defs: List[VlanDef],
    mode: str,
    dry_run: bool,
    verbose: bool,
    delete_vlans_global: bool,
    delete_svi: bool,
    verify: bool,
) -> None:
    vlan_ids = sorted({v.vlan_id for v in vlan_defs})

    existing_vlan_ids = parse_existing_vlans(conn.send_command("show vlan brief", use_textfsm=False))
    trunk_out = conn.send_command("show interfaces trunk", use_textfsm=False)
    trunk_ports = parse_trunk_ports_from_show_interfaces_trunk(trunk_out)

    if verbose:
        print(f"Trunks found: {len(trunk_ports)}")

    if mode == "add":
        missing_defs = [v for v in vlan_defs if v.vlan_id not in existing_vlan_ids]
        if missing_defs and verbose:
            print(f"Global VLANs to create: {[v.vlan_id for v in missing_defs]}")
        if missing_defs and not dry_run:
            conn.send_config_set(build_vlan_create_cmds(missing_defs), cmd_verify=False)

    trunk_cmds = build_trunk_cmds_for_mode(conn, trunk_ports, vlan_ids, mode, verbose)

    if dry_run:
        return

    if trunk_cmds:
        conn.send_config_set(trunk_cmds, cmd_verify=False)

    if mode == "remove" and delete_svi:
        for vid in vlan_ids:
            if svi_exists(conn, vid):
                if verbose:
                    print(f"  Deleting SVI for VLAN {vid}")
                removed = remove_svi_best_effort(conn, vid, verbose)
                if verbose and removed:
                    print(f"  SVI Vlan{vid} removed")

    if mode == "remove" and delete_vlans_global:
        for vid in vlan_ids:
            if vid not in existing_vlan_ids:
                if verbose:
                    print(f"  VLAN {vid} not present in vlan database, skipping no vlan")
                continue

            blockers = vlan_delete_blockers(conn, vid)
            if blockers:
                print(f"  Skipping no vlan {vid} due to blockers: {blockers}")
                continue

            if verbose:
                print(f"  Deleting VLAN from database: no vlan {vid}")
            out = conn.send_config_set([f"no vlan {vid}"], cmd_verify=False)

            if verbose and any(x in out.lower() for x in ["invalid input", "incomplete command", "ambiguous command"]):
                print("  Device rejected no vlan command, output follows")
                print(out.strip())

    if verify:
        for vid in vlan_ids:
            exists_after = verify_vlan_exists(conn, vid)
            trunk_after = conn.send_command("show interfaces trunk | include " + str(vid), use_textfsm=False).strip()
            svi_after = svi_exists(conn, vid)
            print(f"  VERIFY vlan={vid} exists_globally={exists_after} svi_exists={svi_after} trunk_has_vlan_text={bool(trunk_after)}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Add or remove VLANs on trunk ports across Cisco IOS and IOS XE switches")
    parser.add_argument("--switches", required=True, help="Switch inventory file txt or csv")
    parser.add_argument("--vlans", required=True, help="VLAN definitions file txt or csv")
    parser.add_argument("--out", default="output_vlan_push", help="Output directory for session logs and backups")
    parser.add_argument("--dry-run", action="store_true", help="Do not change devices, only report actions")
    parser.add_argument("--remove", action="store_true", help="Remove mode")
    parser.add_argument("--delete-vlans-global", action="store_true", help="Remove mode only, deletes VLANs from vlan database using no vlan")
    parser.add_argument("--delete-svi", action="store_true", help="Remove mode only, attempts to delete interface Vlan<ID> when it actually exists")
    parser.add_argument("--verbose", action="store_true", help="Print detailed per interface actions")
    parser.add_argument("--verify", action="store_true", help="Verify VLAN state after changes")
    args = parser.parse_args()

    ensure_dir(args.out)
    run_id = now_stamp()

    switch_ips = read_switch_ips(args.switches)
    vlan_defs = read_vlans(args.vlans)

    if not switch_ips:
        print("No switches found in the switches file")
        return 2
    if not vlan_defs:
        print("No VLANs found in the VLANs file")
        return 2

    if (args.delete_vlans_global or args.delete_svi) and not args.remove:
        print("ERROR delete-vlans-global and delete-svi can only be used with remove mode")
        return 2

    mode = "remove" if args.remove else "add"
    print(f"Mode: {mode.upper()}")
    print(f"Switches loaded: {len(switch_ips)}")
    print(f"VLANs loaded: {len(vlan_defs)}")

    username = input("Username: ").strip()
    password = getpass("Password: ")

    cached_enable_secret: Optional[str] = None
    vlan_ids = sorted({v.vlan_id for v in vlan_defs})

    for ip in switch_ips:
        session_log = os.path.join(args.out, f"session_{safe_filename(ip)}_{run_id}.log")

        try:
            def apply_fn(conn: ConnectHandler, secret: Optional[str]) -> Optional[str]:
                gather_prechange_backups(conn, args.out, ip, run_id, vlan_ids, args.verbose)
                run_switch(
                    conn=conn,
                    vlan_defs=vlan_defs,
                    mode=mode,
                    dry_run=args.dry_run,
                    verbose=args.verbose,
                    delete_vlans_global=args.delete_vlans_global,
                    delete_svi=args.delete_svi,
                    verify=args.verify,
                )
                return secret

            cached_enable_secret = apply_changes_with_retry_and_secret_cache(
                ip=ip,
                username=username,
                password=password,
                secret_in=cached_enable_secret,
                session_log=session_log,
                apply_fn=apply_fn,
            )

            print(f"{ip}: OK")

        except NetmikoAuthenticationException as e:
            print(f"{ip}: AUTH_FAIL {e}")
        except NetmikoTimeoutException as e:
            print(f"{ip}: TIMEOUT {e}")
        except Exception as e:
            print(f"{ip}: ERROR {e}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

