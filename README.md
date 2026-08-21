# NetSage AI

**Evidence-driven AI troubleshooting assistant for Cisco Packet Tracer network problems**

---

## 1. Project Overview

NetSage AI is a structured network diagnostics assistant that combines:
- **32 realistic Cisco/Packet Tracer troubleshooting cases** across 8 categories
- **Deterministic Python rule checking** (no AI) for common fault patterns
- **Gemini AI diagnosis** producing structured JSON evidence reports
- **Mandatory human review** (Accept / Edit / Reject) before any fix is applied
- **Streamlit dashboard** with 5 pages including a Responsible AI accountability page

---

## 2. Problem Statement

Network engineers troubleshooting Cisco labs face unstructured, trial-and-error workflows. There is no systematic evidence collection or AI assistance to accelerate root-cause identification. AI tools used without human oversight risk misdiagnosis and unsafe configuration changes.

NetSage AI solves this with a structured evidence → rule → AI → human review pipeline.

---

## 3. Features

| Feature | Description |
|---|---|
| 32-case dataset | VLAN, Gateway, DHCP, DNS, Routing, ACL, NAT, Wireless |
| Rule checker | 6 deterministic checks — no AI dependency |
| Gemini AI diagnosis | Structured JSON with root cause, confidence, evidence |
| Human review | Accept / Edit / Reject workflow — mandatory before fix |
| Review logging | Full audit trail in CSV with reviewer + timestamp |
| Dashboard | Metrics, charts, corrected cases |
| Responsible AI page | Agreement rate, 5+ corrected AI diagnoses |
| Case Explorer | Browse, search, filter all 32 cases |

---

## 4. Architecture

```
Network Evidence (show outputs)
        │
        ▼
Rule Checker (checker/checker.py)
  ├── duplicate_ip
  ├── wrong_subnet_mask
  ├── gateway_mismatch
  ├── interface_admin_down
  ├── missing_vlan
  └── missing_route
        │
        ▼
AI Diagnosis (ai/diagnosis.py)
  Sends case + rule results → Gemini API
  Returns structured JSON
        │
        ▼
Human Review (Streamlit UI)
  Accept / Edit / Reject
  Saved to data/reviews.csv
        │
        ▼
Dashboard (app/streamlit_app.py)
  Statistics | Agreement Rate | Responsible AI
```

---

## 5. Tech Stack

| Component | Technology |
|---|---|
| Language | Python 3.11+ |
| Web UI | Streamlit |
| AI | Google Gemini (google-generativeai) |
| Data | Pandas + CSV |
| Charts | Matplotlib |
| Config | python-dotenv |
| Tests | pytest |

---

## 6. Dataset

`data/cases.csv` — 32 cases, 15 columns each:

| Column | Description |
|---|---|
| case_id | e.g. CASE-001 |
| category | VLAN / Gateway / DHCP / DNS / Routing / ACL / NAT / Wireless |
| title | Short problem title |
| symptom | User-reported symptom |
| topology | Device path description |
| device_context | Relevant device/config context |
| show_commands | Cisco IOS commands used |
| show_output | Realistic IOS command output |
| expected_fault | The actual root cause |
| osi_layer | OSI layer affected |
| concept | Networking concept tested |
| severity | critical / high / medium |
| expected_next_command | Best next diagnostic command |
| expected_fix | Exact IOS fix commands |
| verification_command | How to verify the fix |

**Category distribution:** VLAN×4, Gateway×4, DHCP×4, DNS×4, Routing×5, ACL×4, NAT×3, Wireless×4 = **32 total**

---

## 7. AI Prompting

The system prompt (`prompts/diagnose_prompt.md`) instructs the AI to:
1. Analyze symptom, topology, show outputs, and rule checker results
2. Return **only valid JSON** — no markdown, no preamble
3. Never invent evidence not in the provided show outputs
4. Never claim a fix is complete without verification
5. State confidence honestly (0.0–1.0 scale)
6. Cite exact lines from show command output as evidence

---

## 8. Rule Checker

Six deterministic checks in `checker/checker.py`:

| Check | What it detects |
|---|---|
| `duplicate_ip` | Same IP appears more than once in output |
| `wrong_subnet_mask` | Invalid or unexpected prefix length |
| `gateway_mismatch` | Gateway not in same subnet as host |
| `interface_admin_down` | `administratively down` interfaces |
| `missing_vlan` | VLAN referenced but not in VLAN database |
| `missing_route` | Default route absent or destination unreachable |

Each returns: `{check, detected, severity, evidence, message}`

---

## 9. Human Review

All reviews are saved to `data/reviews.csv`:

| Column | Description |
|---|---|
| case_id | Which case was reviewed |
| ai_root_cause | AI's diagnosis |
| ai_confidence | 0.0–1.0 float |
| human_decision | Accepted / Edited / Rejected |
| human_correction | Engineer's corrected diagnosis (if edited/rejected) |
| review_reason | Explanation for the decision |
| reviewer | Engineer's name |
| timestamp | ISO datetime |

---

## 10. Responsible AI

The Responsible AI page shows:
- **AI Agreement Rate** = Accepted ÷ Total Reviewed × 100
- All cases where AI was **Edited or Rejected** with the human's correction
- Pre-seeded with 5 corrected cases (CASE-012, CASE-021, CASE-024, CASE-028, CASE-031)

---

## 11. Dashboard

5 Streamlit pages:

| Page | Content |
|---|---|
| Dashboard | Total cases, review counts, agreement rate, charts |
| Troubleshoot Case | Full diagnostic workflow |
| Review History | Filterable review log |
| Responsible AI | Agreement rate + corrected cases |
| Case Explorer | Searchable/filterable case browser |

---

## 12. Installation

```bash
# Clone
git clone https://github.com/your-username/NetSage-AI.git
cd NetSage-AI

# Create virtual environment (recommended)
python -m venv venv
venv\Scripts\activate     # Windows
# or
source venv/bin/activate  # Linux/Mac

# Install dependencies
pip install -r requirements.txt
```

---

## 13. Environment Variables

```bash
# Copy the template
cp .env.example .env

# Edit .env and add your Gemini API key
GEMINI_API_KEY=your_actual_key_here
GEMINI_MODEL=gemini-1.5-flash   # optional
```

Get a free Gemini API key at: https://aistudio.google.com/

---

## 14. How to Run

```bash
# Run the Streamlit app
streamlit run app/streamlit_app.py

# Run tests
python -m pytest checker/tests.py -v
```

---

## 15. Example Diagnosis

**Input Case:** CASE-017 — Missing Static Route

**Rule Checker Output:**
```
[DETECTED] missing_route (severity: high)
  Evidence : Gateway of last resort is not set; 192.168.30.0/24 not in routing table
  Message  : Route issue detected. Add required static/dynamic routes.
```

**AI Diagnosis (JSON):**
```json
{
  "root_cause": "Static route to 192.168.30.0/24 is missing from R1's routing table",
  "confidence": 0.91,
  "osi_layer": "Layer 3 — Network",
  "evidence": [
    "show ip route shows only directly connected routes (C) — no static or dynamic entries",
    "192.168.30.0/24 is absent from the routing table",
    "Rule checker confirms: gateway of last resort is not set"
  ],
  "next_command": "show ip route on R2 to verify return path",
  "fix_steps": ["R1(config)# ip route 192.168.30.0 255.255.255.0 10.0.0.2"],
  "verification_steps": ["show ip route | include 192.168.30", "ping 192.168.30.10 from PC"],
  "reasoning_summary": "The routing table on R1 contains only directly connected networks. 192.168.30.0/24 is absent. Adding a static route via next-hop 10.0.0.2 should restore reachability."
}
```

**Human Review:** Accepted — AI correctly identified the issue with evidence.

---

## 16. Team Contributions

| Member | Contribution |
|---|---|
| Prachi Bhardwaj | Project lead, architecture, case design, AI integration |

---

## 17. Future Improvements

- Add real-time Packet Tracer integration via API or file export
- Support OpenAI GPT-4 as an alternative AI provider
- Implement OSPF, BGP, STP case categories
- Add PDF report export for completed troubleshooting sessions
- Extend rule checker with ACL and NAT-specific deterministic checks
- Add multi-engineer review workflow with approvals
