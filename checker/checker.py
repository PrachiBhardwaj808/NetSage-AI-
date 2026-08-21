"""
checker/checker.py
==================
Deterministic rule-based checks for NetSage AI.
These checks run independently of AI — no API calls, no LLM.
Each check returns a structured result dict.
"""

from __future__ import annotations
import ipaddress
import re
from typing import Any


# ─── Result factory ──────────────────────────────────────────────────────────

def _result(check: str, detected: bool, severity: str, evidence: str, message: str) -> dict:
    return {
        "check": check,
        "detected": detected,
        "severity": severity,
        "evidence": evidence,
        "message": message,
    }


# ─── Individual checks ───────────────────────────────────────────────────────

def check_duplicate_ip(show_output: str) -> dict:
    """
    Detects if the same IP address appears more than once in the show output.
    Works on 'show ip arp', 'show ip dhcp binding', or 'show ip interface brief'.
    """
    check_name = "duplicate_ip"
    if not show_output or not show_output.strip():
        return _result(check_name, False, "info", "No output provided", "No show output to analyse.")

    # Extract all IPv4 addresses from the output
    ip_pattern = re.compile(r'\b(\d{1,3}(?:\.\d{1,3}){3})\b')
    found: list[str] = ip_pattern.findall(show_output)

    # Filter out common non-host IPs
    skip = {"0.0.0.0", "255.255.255.255"}
    filtered = [ip for ip in found if ip not in skip]

    seen: dict[str, int] = {}
    for ip in filtered:
        seen[ip] = seen.get(ip, 0) + 1

    duplicates = {ip: cnt for ip, cnt in seen.items() if cnt > 1}
    if duplicates:
        dup_str = "; ".join(f"{ip} appears {cnt}x" for ip, cnt in duplicates.items())
        return _result(
            check_name, True, "high",
            dup_str,
            f"Duplicate IP addresses detected: {dup_str}. "
            "This may indicate IP conflict or misconfigured static assignments."
        )
    return _result(check_name, False, "info", "No duplicate IPs found", "No duplicate IP addresses detected.")


def check_wrong_subnet_mask(show_output: str, expected_prefix: int | None = None) -> dict:
    """
    Detects common wrong subnet masks in 'show ip interface brief' or 'ipconfig' output.
    Flags masks that are not byte-aligned or clearly wrong (/8, /16, /24, /25, /30 are common).
    """
    check_name = "wrong_subnet_mask"
    if not show_output or not show_output.strip():
        return _result(check_name, False, "info", "No output provided", "No show output to analyse.")

    # Look for patterns like "255.255.0.0" or "/16" to cross-check
    mask_pattern = re.compile(r'255\.\d+\.\d+\.\d+')
    cidr_pattern = re.compile(r'/(\d{1,2})\b')

    masks = mask_pattern.findall(show_output)
    cidrs = [int(m) for m in cidr_pattern.findall(show_output)]

    suspicious = []

    for mask_str in masks:
        try:
            # Validate it is a proper contiguous mask
            mask_int = int(ipaddress.ip_address(mask_str))
            # Check that it's a valid prefix mask (all 1s followed by all 0s)
            inverted = mask_int ^ 0xFFFFFFFF
            if inverted & (inverted + 1) != 0:
                suspicious.append(f"Invalid mask: {mask_str}")
        except Exception:
            suspicious.append(f"Unparseable mask: {mask_str}")

    for cidr in cidrs:
        if cidr < 8 or cidr > 30:
            suspicious.append(f"Unusual prefix length: /{cidr}")

    if expected_prefix is not None:
        for cidr in cidrs:
            if cidr != expected_prefix:
                suspicious.append(f"Expected /{expected_prefix} but found /{cidr}")

    if suspicious:
        evidence = "; ".join(suspicious)
        return _result(
            check_name, True, "medium",
            evidence,
            f"Potentially incorrect subnet mask detected: {evidence}"
        )
    return _result(check_name, False, "info", "Subnet masks appear valid", "No subnet mask issues detected.")


def check_gateway_mismatch(show_output: str) -> dict:
    """
    Detects if the configured default gateway is not in the same /24 subnet as the host IP.
    Looks for patterns from 'ipconfig' or case device_context fields.
    """
    check_name = "gateway_mismatch"
    if not show_output or not show_output.strip():
        return _result(check_name, False, "info", "No output provided", "No show output to analyse.")

    # Patterns: "IP Address: x.x.x.x" and "Default Gateway: x.x.x.x"
    ip_match = re.search(
        r'(?:IP Address|ip address)[^\d]*(\d{1,3}(?:\.\d{1,3}){3})', show_output, re.IGNORECASE
    )
    gw_match = re.search(
        r'(?:Default Gateway|default-router|gateway)[^\d]*(\d{1,3}(?:\.\d{1,3}){3})', show_output, re.IGNORECASE
    )
    mask_match = re.search(
        r'(?:Subnet Mask|subnet mask)[^\d]*(255\.\d+\.\d+\.\d+)', show_output, re.IGNORECASE
    )

    if not ip_match or not gw_match:
        return _result(check_name, False, "info", "IP or gateway not found in output",
                       "Could not extract IP/gateway from output for comparison.")

    host_ip_str = ip_match.group(1)
    gw_ip_str = gw_match.group(1)
    mask_str = mask_match.group(1) if mask_match else "255.255.255.0"

    # Skip placeholder IPs
    if host_ip_str == "0.0.0.0" or gw_ip_str == "0.0.0.0":
        return _result(
            check_name, True, "high",
            f"Host IP: {host_ip_str}, Gateway: {gw_ip_str}",
            f"Default gateway is 0.0.0.0 — not configured."
        )

    try:
        host_iface = ipaddress.IPv4Interface(f"{host_ip_str}/{mask_str}")
        gw_addr = ipaddress.IPv4Address(gw_ip_str)

        if gw_addr not in host_iface.network:
            return _result(
                check_name, True, "high",
                f"Host: {host_ip_str}/{mask_str}, Gateway: {gw_ip_str}, Network: {host_iface.network}",
                f"Default gateway {gw_ip_str} is not within the host's subnet {host_iface.network}. "
                "Host cannot ARP for the gateway."
            )
    except Exception as e:
        return _result(check_name, False, "info", str(e), "Could not parse IP/mask for comparison.")

    return _result(check_name, False, "info",
                   f"Gateway {gw_ip_str} is within {host_iface.network}",
                   "Gateway appears to be in the correct subnet.")


def check_interface_admin_down(show_output: str) -> dict:
    """
    Detects interfaces in 'administratively down' state from 'show ip interface brief'.
    """
    check_name = "interface_admin_down"
    if not show_output or not show_output.strip():
        return _result(check_name, False, "info", "No output provided", "No show output to analyse.")

    lines = show_output.splitlines()
    admin_down_interfaces = []

    for line in lines:
        if "administratively down" in line.lower():
            # Extract interface name (first token)
            parts = line.split()
            if parts:
                admin_down_interfaces.append(parts[0])

    if admin_down_interfaces:
        iface_list = ", ".join(admin_down_interfaces)
        return _result(
            check_name, True, "high",
            f"Interfaces: {iface_list} — administratively down",
            f"The following interface(s) are administratively down: {iface_list}. "
            "Run 'no shutdown' to bring them up."
        )
    return _result(check_name, False, "info", "No admin-down interfaces found",
                   "All interfaces appear to be up (no 'administratively down' state detected).")


def check_missing_vlan(show_output: str, expected_vlans: list[int] | None = None) -> dict:
    """
    Detects if expected VLANs are missing from 'show vlan brief' output.
    If expected_vlans is None, checks for any port assigned to a VLAN not in the VLAN database.
    """
    check_name = "missing_vlan"
    if not show_output or not show_output.strip():
        return _result(check_name, False, "info", "No output provided", "No show output to analyse.")

    # Extract VLAN IDs that are actually defined (lines starting with a number)
    defined_vlans: set[int] = set()
    vlan_line = re.compile(r'^(\d+)\s+\S+\s+(active|act/unsup)', re.MULTILINE)
    for m in vlan_line.finditer(show_output):
        defined_vlans.add(int(m.group(1)))

    if expected_vlans:
        missing = [v for v in expected_vlans if v not in defined_vlans]
        if missing:
            return _result(
                check_name, True, "high",
                f"Defined VLANs: {sorted(defined_vlans)}; Missing: {missing}",
                f"Expected VLAN(s) {missing} are not present in the VLAN database. "
                "Ports assigned to undefined VLANs will be inactive."
            )
        return _result(check_name, False, "info",
                       f"All expected VLANs {expected_vlans} are present",
                       "All required VLANs exist in the VLAN database.")

    # Heuristic: check for port-to-VLAN references where VLAN is not defined
    # Look for "VLAN does not exist" or "inactive" keywords
    if "inactive" in show_output.lower() or "does not exist" in show_output.lower():
        return _result(
            check_name, True, "high",
            "Output contains 'inactive' or 'does not exist' for a VLAN",
            "One or more ports reference a VLAN that does not exist in the VLAN database. "
            "Create the VLAN with 'vlan <id>' in global config."
        )

    return _result(check_name, False, "info",
                   f"VLANs defined: {sorted(defined_vlans)}",
                   "No missing VLAN issues detected in the output.")


def check_missing_route(show_output: str, destination: str | None = None) -> dict:
    """
    Detects if a destination network is absent from 'show ip route' output.
    Also flags if 'Gateway of last resort is not set' for internet-facing routers.
    """
    check_name = "missing_route"
    if not show_output or not show_output.strip():
        return _result(check_name, False, "info", "No output provided", "No show output to analyse.")

    issues = []

    # Check for missing default route
    if "gateway of last resort is not set" in show_output.lower():
        issues.append("Gateway of last resort is not set — default route is missing")

    # Check for specific destination
    if destination:
        # Normalise destination network
        dest_clean = destination.strip()
        if dest_clean not in show_output:
            issues.append(f"Destination network {dest_clean} not found in routing table")

    # Check if routing table appears empty (only directly connected)
    route_types = re.findall(r'^[CSRIBODEA]\s', show_output, re.MULTILINE)
    connected_only = all(t.strip() == 'C' for t in route_types) if route_types else False
    if connected_only and len(route_types) > 0:
        issues.append("Routing table contains only directly connected (C) routes — no static or dynamic routes")

    if issues:
        evidence = "; ".join(issues)
        return _result(
            check_name, True, "high",
            evidence,
            f"Route issue detected: {evidence}. Add required static/dynamic routes."
        )

    return _result(check_name, False, "info",
                   "Routing table contains non-connected routes",
                   "No missing route issues detected.")


# ─── Orchestrator ─────────────────────────────────────────────────────────────

def run_all_checks(case_data: dict[str, Any]) -> list[dict]:
    """
    Run all deterministic checks against a case and return results.

    Args:
        case_data: A single case row dict from cases.csv

    Returns:
        List of check result dicts
    """
    show_output = case_data.get("show_output", "")
    category = case_data.get("category", "").lower()
    results: list[dict] = []

    # Always run these checks
    results.append(check_duplicate_ip(show_output))
    results.append(check_interface_admin_down(show_output))
    results.append(check_wrong_subnet_mask(show_output))

    # Category-specific checks
    if category in ("gateway", "dhcp", "dns"):
        results.append(check_gateway_mismatch(show_output))

    if category == "vlan":
        results.append(check_missing_vlan(show_output))

    if category in ("routing", "nat"):
        results.append(check_missing_route(show_output))

    # Routing: also check for missing destination
    if category == "routing":
        expected_fault = case_data.get("expected_fault", "")
        # Try to extract a network from the expected fault
        net_match = re.search(r'(\d{1,3}(?:\.\d{1,3}){3}/\d{1,2})', expected_fault)
        if net_match:
            results.append(check_missing_route(show_output, destination=net_match.group(1)))

    return results


def format_results_for_prompt(results: list[dict]) -> str:
    """Format rule-checker results into a readable string for inclusion in the AI prompt."""
    if not results:
        return "No deterministic checks were run."

    lines = ["=== Rule Checker Results ==="]
    detected_count = sum(1 for r in results if r["detected"])
    lines.append(f"Checks run: {len(results)} | Issues detected: {detected_count}")
    lines.append("")

    for r in results:
        status = "DETECTED" if r["detected"] else "PASS"
        lines.append(f"[{status}] {r['check']} (severity: {r['severity']})")
        lines.append(f"  Evidence : {r['evidence']}")
        lines.append(f"  Message  : {r['message']}")
        lines.append("")

    return "\n".join(lines)
