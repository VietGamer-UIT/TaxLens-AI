# TaxLens-AI — MCP Server Strategy & Read-Only Skill Architecture

> **TaxLens-AI by Đoàn Hoàng Việt (Việt Gamer)**  
> *Model Context Protocol (MCP) Server Design — Evidence Preservation Framework*

---

## 1. What Are MCP Servers in TaxLens-AI?

In the TaxLens-AI architecture, **MCP (Model Context Protocol) Servers** are lightweight Python modules that wrap external security tools and APIs into **typed, auditable, read-only "skills"** callable by LangGraph agents.

Rather than giving an LLM agent raw shell access or unrestricted API access, each MCP server:

1. **Defines a strict Pydantic v2 input schema** — every parameter is validated before the tool executes.
2. **Enforces a read-only denylist** — dangerous write operations are rejected at the Python layer before any subprocess or HTTP call is made.
3. **Emits a structured audit log entry** at invocation time — meeting SANS FIND EVIL! traceability requirements.
4. **Returns a normalised `{"status", "tool", "data"}` envelope** — agents always receive machine-parseable output.

---

## 2. MCP Server Registry

TaxLens-AI ships three MCP servers, each registered in a central `MCP_TOOL_REGISTRY`:

| Server Module | Tools | External System |
|---|---|---|
| `forensics_mcp.py` | `run_volatility_plugin`, `run_log2timeline` | SIFT Workstation (Volatility3, Plaso) |
| `splunk_mcp.py` | `run_spl_search`, `get_notable_events` | Splunk Enterprise REST API `:8089` |
| `threat_intel_mcp.py` | `lookup_ip`, `lookup_hash` | VirusTotal v3 API, AbuseIPDB v2 API |

All tools are registered via a `@mcp_tool(name)` decorator pattern:

```python
FORENSICS_TOOL_REGISTRY: dict[str, Callable] = {}

def mcp_tool(name: str):
    def decorator(fn: Callable) -> Callable:
        FORENSICS_TOOL_REGISTRY[name] = fn
        return fn
    return decorator

@mcp_tool("run_volatility_plugin")
async def run_volatility_plugin(params: VolatilityInput) -> dict:
    ...
```

This registry-based design allows dynamic tool discovery — a necessity for the MCP protocol's `tools/list` capability negotiation.

---

## 3. Anti-Evidence-Spoliation: The Read-Only Enforcement Model

### What Is Evidence Spoliation?

In digital forensics, **evidence spoliation** refers to the destruction, alteration, or concealment of evidence in a way that prejudices an investigation. At the software level, this occurs when an IR tool:

- Writes to or modifies evidence files (e.g., `rm`, `mv`, `dd` with write flags).
- Alters system state during analysis (e.g., a memory dump tool that also clears event logs).
- Executes SPL commands in Splunk that modify index data (e.g., `outputlookup`, `delete`).

**TaxLens-AI is architected to make evidence spoliation impossible at the agent layer.**

### 3.1 Forensics MCP — File System Denylist

The `forensics_mcp.py` server enforces a **command-level write denylist** that is evaluated before any subprocess is constructed or executed:

```python
_WRITE_CMD_DENYLIST: set[str] = {
    "rm", "mv", "cp", "dd", "shred", "truncate",
    "chmod", "chown", "write", "format", "mkfs",
    "fdisk", "parted", "wipefs",
    ">", ">>",          # Shell redirect operators
    "tee", "install",
}

def _deny_write_operations(cmd_parts: list[str]) -> None:
    joined = " ".join(cmd_parts).lower()
    for token in _WRITE_CMD_DENYLIST:
        if token in joined:
            raise PermissionError(
                f"[SECURITY] Blocked write operation: '{joined}'"
            )
```

**Key design decisions:**

| Decision | Rationale |
|---|---|
| `shell=False` in subprocess | Prevents shell metacharacter injection (`&&`, `;`, `$()` ) even if a token passes the denylist |
| String-level scan (not subprocess flag) | Catches write tokens embedded in plugin arguments before the OS sees them |
| `PermissionError` → audit log | Every blocked attempt is recorded with `status=blocked` in the PostgreSQL audit trail |

### 3.2 Splunk MCP — SPL Mutation Guard

Splunk's Search Processing Language (SPL) includes several commands that can **write, delete, or exfiltrate data**. The `splunk_mcp.py` server validates all SPL queries against a mutation guard before submitting them to the Splunk REST API:

```python
class SPLSearchInput(BaseModel):
    spl_query: StrictStr

    @model_validator(mode="after")
    def validate_spl_safety(self) -> "SPLSearchInput":
        dangerous_cmds = {
            "delete",        # Deletes events from an index
            "outputlookup",  # Writes to a lookup file
            "collect",       # Writes to a summary index
            "outputcsv",     # Writes results to a CSV
            "sendemail",     # Exfiltrates results via email
        }
        lower_query = self.spl_query.lower()
        for cmd in dangerous_cmds:
            if f"| {cmd}" in lower_query or lower_query.startswith(cmd):
                raise ValueError(
                    f"SPL query contains disallowed write command: '{cmd}'"
                )
        return self
```

### 3.3 Pydantic v2 Input Validation — The First Line of Defence

Before any tool-specific denylist check, **all MCP inputs pass through Pydantic v2 validation**:

| Validation Type | Field | Example |
|---|---|---|
| `StrictStr` | All string inputs | Reject `int` passed as plugin name |
| Regex pattern | IP addresses | Must match `^\d{1,3}(\.\d{1,3}){3}$` |
| Regex pattern | File hashes | Must match `^[a-fA-F0-9]{32,64}$` |
| `model_validator` | Plugin names | No `;`, `&`, `|`, `` ` ``, `$` chars |
| `model_validator` | SPL query | No write-class commands |

---

## 4. Audit Trail Integration

Every MCP tool invocation emits a structured audit log *before* the tool executes:

```python
def _audit_log(tool: str, params: dict[str, Any]) -> None:
    entry = {
        "event":     "mcp_tool_invoked",
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "server":    "forensics_mcp",   # or splunk_mcp / threat_intel_mcp
        "tool":      tool,
        "params":    params,            # Pydantic-validated, sanitised input
    }
    logger.info(json.dumps(entry))
```

In production, the `@audit_tool_call` decorator in `audit/middleware.py` intercepts the return value and writes both the invocation and result to the PostgreSQL `audit_events` table — capturing:

- `tool_input_json` — the validated Pydantic input dict (sensitive fields redacted)
- `tool_output_json` — the full normalised response envelope
- `duration_ms` — wall-clock execution time
- `retry_attempt` — incremented on each retry (enables retry-pattern analysis)
- `sha256_state_hash` — tamper-evident state snapshot at call time

---

## 5. Mock Mode vs. Production Mode

All MCP servers ship with **realistic mock implementations** that allow the full agent workflow to be tested without access to live SIFT workstations, Splunk instances, or paid APIs.

### Switching to Production

For each tool, replace the mock call with the commented-out production skeleton:

**`forensics_mcp.py` — Volatility3:**
```python
# Replace:
result = await _mock_volatility3(params.image_path, params.plugin)

# With:
proc = await asyncio.create_subprocess_exec(
    "vol", "-f", params.image_path, params.plugin, "--output=json",
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE,
)
stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
if proc.returncode != 0:
    raise OSError(f"vol exited {proc.returncode}: {stderr.decode()}")
result = json.loads(stdout.decode())
```

**`splunk_mcp.py` — SPL Search:**
```python
# Replace the mock with the aiohttp polling lifecycle (see comments in source).
# Requires: pip install aiohttp
# Requires: SPLUNK_BASE_URL and SPLUNK_TOKEN in .env
```

**`threat_intel_mcp.py` — VirusTotal:**
```python
# Replace mock with:
# GET https://www.virustotalapi.com/api/v3/ip_addresses/{ip}
# Headers: {"x-apikey": VIRUSTOTAL_API_KEY}
```

---

## 6. Security Boundary Summary

```
                ┌─────────────────────────────────────────────┐
                │           LangGraph Agent Layer             │
                │  (LLM decides WHAT to call, not HOW)        │
                └────────────────────┬────────────────────────┘
                                     │ Pydantic v2 validated params
                ┌────────────────────▼────────────────────────┐
                │           MCP Server Layer                  │
                │  ① Pydantic strict-type validation          │
                │  ② model_validator format/safety checks     │
                │  ③ Write-op denylist scan                   │
                │  ④ Audit log emission (pre-execution)       │
                │  ⑤ No shell=True / no unsanitised strings   │
                └────────────────────┬────────────────────────┘
                                     │ Only to reach here = safe
                ┌────────────────────▼────────────────────────┐
                │        External Systems (Read-Only)         │
                │  SIFT Workstation · Splunk · VT · AbuseIPDB │
                └─────────────────────────────────────────────┘
```

The LLM agent **never directly touches external systems**. It instructs the MCP server, which enforces all security constraints before making any external call.

---

> *TaxLens-AI by Đoàn Hoàng Việt (Việt Gamer) — MCP Servers Document v1.0*
