"""
checker/tests.py
================
Unit tests for NetSage AI deterministic rule checker.
Run with: python -m pytest checker/tests.py -v
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from checker.checker import (
    check_duplicate_ip,
    check_wrong_subnet_mask,
    check_gateway_mismatch,
    check_interface_admin_down,
    check_missing_vlan,
    check_missing_route,
    run_all_checks,
    format_results_for_prompt,
)


# ─── check_duplicate_ip ───────────────────────────────────────────────────────

class TestDuplicateIP:

    def test_detects_duplicate(self):
        output = (
            "IP address       Client-ID              Lease expiration\n"
            "192.168.10.5     0100.aabb.ccdd.01      ...\n"
            "192.168.10.5     0100.aabb.ccdd.02      ...\n"
        )
        result = check_duplicate_ip(output)
        assert result["detected"] is True
        assert result["severity"] == "high"
        assert "192.168.10.5" in result["evidence"]

    def test_no_duplicate(self):
        output = (
            "192.168.10.5     0100.aabb.ccdd.01      ...\n"
            "192.168.10.6     0100.aabb.ccdd.02      ...\n"
        )
        result = check_duplicate_ip(output)
        assert result["detected"] is False

    def test_empty_input(self):
        result = check_duplicate_ip("")
        assert result["detected"] is False
        assert "No output provided" in result["evidence"]

    def test_none_input(self):
        result = check_duplicate_ip(None)
        assert result["detected"] is False

    def test_whitespace_only(self):
        result = check_duplicate_ip("   \n  ")
        assert result["detected"] is False


# ─── check_wrong_subnet_mask ──────────────────────────────────────────────────

class TestWrongSubnetMask:

    def test_valid_masks_pass(self):
        output = (
            "IP Address: 192.168.10.5\n"
            "Subnet Mask: 255.255.255.0\n"
            "Default Gateway: 192.168.10.1\n"
        )
        result = check_wrong_subnet_mask(output)
        assert result["detected"] is False

    def test_detects_wrong_expected_prefix(self):
        output = "ip address 192.168.10.1/16 is directly connected"
        result = check_wrong_subnet_mask(output, expected_prefix=24)
        assert result["detected"] is True

    def test_detects_unusual_prefix(self):
        output = "ip address 192.168.10.1/5"
        result = check_wrong_subnet_mask(output)
        assert result["detected"] is True
        assert "/5" in result["evidence"]

    def test_empty_input(self):
        result = check_wrong_subnet_mask("")
        assert result["detected"] is False


# ─── check_gateway_mismatch ───────────────────────────────────────────────────

class TestGatewayMismatch:

    def test_detects_mismatch(self):
        output = (
            "IP Address: 192.168.10.20\n"
            "Subnet Mask: 255.255.255.0\n"
            "Default Gateway: 192.168.20.1\n"
        )
        result = check_gateway_mismatch(output)
        assert result["detected"] is True
        assert result["severity"] == "high"
        assert "192.168.20.1" in result["evidence"]

    def test_gateway_in_correct_subnet(self):
        output = (
            "IP Address: 192.168.10.20\n"
            "Subnet Mask: 255.255.255.0\n"
            "Default Gateway: 192.168.10.1\n"
        )
        result = check_gateway_mismatch(output)
        assert result["detected"] is False

    def test_gateway_zero(self):
        output = (
            "IP Address: 192.168.10.20\n"
            "Subnet Mask: 255.255.255.0\n"
            "Default Gateway: 0.0.0.0\n"
        )
        result = check_gateway_mismatch(output)
        assert result["detected"] is True
        assert "0.0.0.0" in result["evidence"]

    def test_empty_input(self):
        result = check_gateway_mismatch("")
        assert result["detected"] is False

    def test_missing_gateway_field(self):
        output = "IP Address: 192.168.10.20\nSubnet Mask: 255.255.255.0\n"
        result = check_gateway_mismatch(output)
        assert result["detected"] is False  # cannot extract GW, returns pass


# ─── check_interface_admin_down ───────────────────────────────────────────────

class TestInterfaceAdminDown:

    def test_detects_admin_down(self):
        output = (
            "Interface              IP-Address      OK? Method Status          Protocol\n"
            "FastEthernet0/0        192.168.10.1    YES manual administratively down  down\n"
            "FastEthernet0/1        10.0.0.1        YES manual up              up\n"
        )
        result = check_interface_admin_down(output)
        assert result["detected"] is True
        assert "FastEthernet0/0" in result["evidence"]
        assert result["severity"] == "high"

    def test_no_admin_down(self):
        output = (
            "FastEthernet0/0        192.168.10.1    YES manual up              up\n"
            "FastEthernet0/1        10.0.0.1        YES manual up              up\n"
        )
        result = check_interface_admin_down(output)
        assert result["detected"] is False

    def test_empty_input(self):
        result = check_interface_admin_down("")
        assert result["detected"] is False

    def test_multiple_admin_down(self):
        output = (
            "Se0/0/0  200.0.0.1  YES manual administratively down  down\n"
            "Fa0/0    10.0.0.1   YES manual administratively down  down\n"
        )
        result = check_interface_admin_down(output)
        assert result["detected"] is True
        assert "Se0/0/0" in result["evidence"] or "Fa0/0" in result["evidence"]


# ─── check_missing_vlan ───────────────────────────────────────────────────────

class TestMissingVLAN:

    def test_detects_missing_expected_vlan(self):
        output = (
            "VLAN Name   Status    Ports\n"
            "1    default  active    Fa0/1\n"
            "10   VLAN0010 active    Fa0/2\n"
        )
        result = check_missing_vlan(output, expected_vlans=[10, 20])
        assert result["detected"] is True
        assert "20" in str(result["evidence"])

    def test_all_vlans_present(self):
        output = (
            "VLAN Name   Status    Ports\n"
            "1    default  active    Fa0/1\n"
            "10   VLAN0010 active    Fa0/2\n"
            "20   VLAN0020 active    Fa0/3\n"
        )
        result = check_missing_vlan(output, expected_vlans=[10, 20])
        assert result["detected"] is False

    def test_heuristic_detects_inactive(self):
        output = "VLAN 30 does not exist\nFa0/5 inactive"
        result = check_missing_vlan(output)
        assert result["detected"] is True

    def test_empty_input(self):
        result = check_missing_vlan("")
        assert result["detected"] is False


# ─── check_missing_route ──────────────────────────────────────────────────────

class TestMissingRoute:

    def test_detects_missing_default_route(self):
        output = (
            "Gateway of last resort is not set\n"
            "C    192.168.10.0/24 is directly connected, FastEthernet0/0\n"
        )
        result = check_missing_route(output)
        assert result["detected"] is True
        assert "gateway of last resort" in result["evidence"].lower()

    def test_detects_missing_specific_destination(self):
        output = (
            "C    192.168.10.0/24 is directly connected, FastEthernet0/0\n"
            "C    10.0.0.0/24 is directly connected, FastEthernet0/1\n"
        )
        result = check_missing_route(output, destination="192.168.30.0/24")
        assert result["detected"] is True

    def test_destination_present(self):
        output = (
            "C    192.168.10.0/24 is directly connected, FastEthernet0/0\n"
            "S    192.168.30.0/24 [1/0] via 10.0.0.2\n"
        )
        result = check_missing_route(output, destination="192.168.30.0/24")
        assert result["detected"] is False

    def test_connected_only_routes(self):
        output = (
            "Gateway of last resort is not set\n"
            "C    192.168.10.0/24 is directly connected, Fa0/0\n"
            "C    192.168.20.0/24 is directly connected, Fa0/1\n"
        )
        result = check_missing_route(output)
        assert result["detected"] is True

    def test_empty_input(self):
        result = check_missing_route("")
        assert result["detected"] is False


# ─── run_all_checks orchestrator ─────────────────────────────────────────────

class TestRunAllChecks:

    def test_returns_list(self):
        case = {
            "category": "Routing",
            "show_output": (
                "Gateway of last resort is not set\n"
                "C 192.168.10.0/24 is directly connected, Fa0/0\n"
            ),
            "expected_fault": "Static route to 192.168.30.0/24 is missing",
        }
        results = run_all_checks(case)
        assert isinstance(results, list)
        assert len(results) > 0

    def test_empty_case(self):
        results = run_all_checks({})
        assert isinstance(results, list)

    def test_vlan_category_runs_vlan_check(self):
        case = {
            "category": "VLAN",
            "show_output": "VLAN 20 does not exist\nFa0/2 inactive",
            "expected_fault": "VLAN 20 missing",
        }
        results = run_all_checks(case)
        check_names = [r["check"] for r in results]
        assert "missing_vlan" in check_names

    def test_gateway_category_runs_gateway_check(self):
        case = {
            "category": "Gateway",
            "show_output": (
                "IP Address: 192.168.10.5\n"
                "Subnet Mask: 255.255.255.0\n"
                "Default Gateway: 192.168.20.1\n"
            ),
            "expected_fault": "Wrong gateway",
        }
        results = run_all_checks(case)
        check_names = [r["check"] for r in results]
        assert "gateway_mismatch" in check_names


# ─── format_results_for_prompt ────────────────────────────────────────────────

class TestFormatResults:

    def test_format_non_empty(self):
        results = [
            {"check": "missing_route", "detected": True, "severity": "high",
             "evidence": "Gateway of last resort is not set", "message": "Default route missing."}
        ]
        text = format_results_for_prompt(results)
        assert "missing_route" in text
        assert "DETECTED" in text

    def test_format_empty(self):
        text = format_results_for_prompt([])
        assert "No deterministic checks" in text


# ─── AI JSON validation utilities (mocked) ───────────────────────────────────

class TestAIDiagnosisSchema:
    """Test that we can validate AI response dicts against required schema."""

    REQUIRED_FIELDS = [
        "root_cause", "confidence", "osi_layer", "evidence",
        "next_command", "fix_steps", "verification_steps", "reasoning_summary"
    ]

    def _make_valid(self):
        return {
            "root_cause": "Interface Fa0/0 is admin down",
            "confidence": 0.92,
            "osi_layer": "Layer 1 — Physical",
            "evidence": ["show ip interface brief shows admin down"],
            "next_command": "no shutdown",
            "fix_steps": ["R1(config-if)# no shutdown"],
            "verification_steps": ["show ip interface brief"],
            "reasoning_summary": "Interface is administratively disabled."
        }

    def test_valid_response_passes(self):
        diag = self._make_valid()
        missing = [f for f in self.REQUIRED_FIELDS if f not in diag]
        assert missing == []

    def test_detects_missing_root_cause(self):
        diag = self._make_valid()
        del diag["root_cause"]
        missing = [f for f in self.REQUIRED_FIELDS if f not in diag]
        assert "root_cause" in missing

    def test_detects_missing_confidence(self):
        diag = self._make_valid()
        del diag["confidence"]
        missing = [f for f in self.REQUIRED_FIELDS if f not in diag]
        assert "confidence" in missing

    def test_confidence_range_low(self):
        diag = self._make_valid()
        diag["confidence"] = -0.1
        assert not (0.0 <= diag["confidence"] <= 1.0)

    def test_confidence_range_high(self):
        diag = self._make_valid()
        diag["confidence"] = 1.5
        assert not (0.0 <= diag["confidence"] <= 1.0)

    def test_confidence_valid_boundary_zero(self):
        diag = self._make_valid()
        diag["confidence"] = 0.0
        assert 0.0 <= diag["confidence"] <= 1.0

    def test_confidence_valid_boundary_one(self):
        diag = self._make_valid()
        diag["confidence"] = 1.0
        assert 0.0 <= diag["confidence"] <= 1.0

    def test_invalid_json_string(self):
        """Simulate what happens when AI returns malformed JSON."""
        import json
        malformed = '{"root_cause": "missing route", "confidence": INVALID}'
        with pytest.raises(json.JSONDecodeError):
            json.loads(malformed)

    def test_empty_json_string(self):
        import json
        with pytest.raises((json.JSONDecodeError, ValueError)):
            result = json.loads("")
            if not result:
                raise ValueError("Empty JSON")

    def test_missing_api_key_returns_error_dict(self):
        """Simulate API key missing scenario."""
        def mock_diagnose_no_key(case_data, rule_results):
            api_key = ""
            if not api_key:
                return {
                    "root_cause": "API key not configured",
                    "confidence": 0.0,
                    "osi_layer": "Unknown",
                    "evidence": [],
                    "next_command": "Configure GEMINI_API_KEY in .env",
                    "fix_steps": [],
                    "verification_steps": [],
                    "reasoning_summary": "Cannot diagnose: API key missing.",
                    "error": "API key not configured"
                }

        result = mock_diagnose_no_key({}, [])
        assert result is not None
        assert result["confidence"] == 0.0
        assert "error" in result

    def test_api_failure_returns_error_dict(self):
        """Simulate API call failure."""
        def mock_diagnose_api_fail(case_data, rule_results):
            try:
                raise ConnectionError("API timeout")
            except Exception as e:
                return {
                    "root_cause": "AI diagnosis unavailable",
                    "confidence": 0.0,
                    "osi_layer": "Unknown",
                    "evidence": [],
                    "next_command": "Retry or check API status",
                    "fix_steps": [],
                    "verification_steps": [],
                    "reasoning_summary": f"API error: {str(e)}",
                    "error": str(e)
                }

        result = mock_diagnose_api_fail({}, [])
        assert "error" in result
        assert "API timeout" in result["error"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
