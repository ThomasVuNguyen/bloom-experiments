#!/usr/bin/env python3
"""
Test all BloomOne MCP tools on the deployed Modal server.

Usage: python tests/test_deployed.py
"""

import json
import sys
import time
import uuid

import requests

MCP_URL = "https://thomas-15--bloomone-web.modal.run/mcp"
HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}

# Test patient data
PATIENT_ID = "test-deploy-001"
HLA_ALLELES = ["HLA-A*02:01", "HLA-B*07:02"]

# Session state
SESSION_ID = None


def mcp_request(method: str, params: dict | None = None, timeout: int = 300):
    """Send an MCP request and parse the SSE response."""
    global SESSION_ID

    payload = {
        "jsonrpc": "2.0",
        "method": method,
        "id": str(uuid.uuid4()),
    }
    if params:
        payload["params"] = params

    headers = dict(HEADERS)
    if SESSION_ID:
        headers["Mcp-Session-Id"] = SESSION_ID

    try:
        resp = requests.post(MCP_URL, json=payload, headers=headers, timeout=timeout)
        resp.raise_for_status()

        # Capture session ID from response headers
        if "mcp-session-id" in resp.headers:
            SESSION_ID = resp.headers["mcp-session-id"]

        # Parse SSE response
        text = resp.text
        results = []
        for line in text.strip().split("\n"):
            line = line.strip()
            if line.startswith("data:"):
                data = line[5:].strip()
                if data:
                    try:
                        results.append(json.loads(data))
                    except json.JSONDecodeError:
                        pass
            elif line.startswith("{"):
                try:
                    results.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

        return results
    except requests.exceptions.Timeout:
        return [{"error": "TIMEOUT", "message": f"Request timed out after {timeout}s"}]
    except requests.exceptions.HTTPError as e:
        return [{"error": f"{e.response.status_code} {e.response.reason}", "body": e.response.text[:500]}]
    except Exception as e:
        return [{"error": str(e)}]


def test_initialize():
    """Test MCP initialization."""
    print("1️⃣  Testing MCP Initialize...")
    results = mcp_request("initialize", {
        "protocolVersion": "2025-03-26",
        "capabilities": {},
        "clientInfo": {"name": "bloomone-test", "version": "1.0"},
    })
    for r in results:
        if "result" in r:
            info = r["result"].get("serverInfo", {})
            print(f"   ✅ Server: {info.get('name', '?')} v{info.get('version', '?')}")
            print(f"   Session ID: {SESSION_ID}")
            return True
        elif "error" in r:
            print(f"   ❌ Error: {r['error']}")
            return False
    print(f"   ❌ No valid response: {results}")
    return False


def test_list_tools():
    """Test listing all available tools."""
    print("\n2️⃣  Testing tools/list...")
    results = mcp_request("tools/list")
    for r in results:
        if "result" in r:
            tools = r["result"].get("tools", [])
            print(f"   ✅ {len(tools)} tools registered:")
            for t in tools:
                desc = t.get("description", "")[:60]
                print(f"      • {t['name']}: {desc}")
            return [t["name"] for t in tools]
        elif "error" in r:
            print(f"   ❌ Error: {r}")
    return []


def test_tool(tool_name: str, args: dict, timeout: int = 300):
    """Test calling a specific tool."""
    print(f"\n   Testing {tool_name}...")
    t0 = time.time()
    results = mcp_request("tools/call", {
        "name": tool_name,
        "arguments": args,
    }, timeout=timeout)
    elapsed = time.time() - t0

    for r in results:
        if "result" in r:
            content = r["result"].get("content", [])
            is_error = r["result"].get("isError", False)
            for c in content:
                if c.get("type") == "text":
                    text = c["text"]
                    if is_error:
                        print(f"   ❌ {tool_name} tool error ({elapsed:.1f}s): {text[:300]}")
                        return None
                    try:
                        data = json.loads(text)
                        print(f"   ✅ {tool_name} returned ({elapsed:.1f}s):")
                        for k, v in data.items():
                            if isinstance(v, (str, int, float, bool)):
                                print(f"      {k}: {v}")
                            elif isinstance(v, list):
                                print(f"      {k}: [{len(v)} items]")
                        return data
                    except json.JSONDecodeError:
                        preview = text[:200]
                        print(f"   ✅ {tool_name} returned ({elapsed:.1f}s): {preview}")
                        return text
        elif "error" in r:
            print(f"   ❌ {tool_name} error ({elapsed:.1f}s): {r}")
            return None

    print(f"   ❌ {tool_name} no valid response ({elapsed:.1f}s): {results[:1]}")
    return None


def main():
    start = time.time()
    print("=" * 60)
    print("🧬 BloomOne Deployed MCP Server — Integration Test")
    print("=" * 60)
    print(f"Endpoint: {MCP_URL}\n")

    # 1. Initialize
    if not test_initialize():
        print("\n❌ Server not responding. Is it deployed?")
        sys.exit(1)

    # 2. List tools
    tools = test_list_tools()
    if not tools:
        print("\n❌ No tools found.")
        sys.exit(1)

    # 3. Test cBioPortal fetch first to get data onto Modal
    print("\n" + "=" * 60)
    print("1️⃣  Stage 1: cBioPortal Data Fetch")
    print("=" * 60)
    stage1_result = test_tool("stage1_fetch_cbio", {
        "study_id": "skcm_tcga_pan_can_atlas_2018",
        "sample_id": "TCGA-BF-A3DL-01",
    }, timeout=120)

    maf_path = None
    patient_id = PATIENT_ID
    if stage1_result and isinstance(stage1_result, dict):
        maf_path = stage1_result.get("maf_path", "")
        patient_id = stage1_result.get("patient_id", PATIENT_ID)

    if not maf_path:
        print("   ⚠️  Could not fetch data. Testing remaining stages skipped.")
        _summary(start)
        return

    # 4. Stage 3: Peptide Generation
    print("\n" + "=" * 60)
    print("3️⃣  Stage 3: Peptide Generation")
    print("=" * 60)
    stage3_result = test_tool("stage3_generate_peptides", {
        "maf_path": maf_path,
        "patient_id": patient_id,
    }, timeout=600)

    if not stage3_result or not isinstance(stage3_result, dict):
        _summary(start)
        return

    peptides_path = stage3_result.get("candidates_path", "")
    if not peptides_path:
        _summary(start)
        return

    # 5. Stage 4: HLA Binding
    print("\n" + "=" * 60)
    print("4️⃣  Stage 4: HLA Binding Prediction")
    print("=" * 60)
    stage4_result = test_tool("stage4_predict_binding", {
        "peptides_path": peptides_path,
        "hla_alleles": ",".join(HLA_ALLELES),
        "patient_id": patient_id,
    }, timeout=600)

    if not stage4_result or not isinstance(stage4_result, dict):
        _summary(start)
        return

    binders = stage4_result.get("strong_binders", 0)
    if binders == 0:
        print("   ⚠️  No strong binders — stopping pipeline test here")
        _summary(start)
        return

    binders_path = stage4_result.get("predictions_path", "")

    # 6. Stage 5: Safety Filter
    print("\n" + "=" * 60)
    print("5️⃣  Stage 5: Safety Filter")
    print("=" * 60)
    stage5_result = test_tool("stage5_safety_filter", {
        "binders_path": binders_path,
        "patient_id": patient_id,
    }, timeout=600)

    if not stage5_result or not isinstance(stage5_result, dict):
        _summary(start)
        return

    safe = stage5_result.get("total_safe", 0)
    safe_path = stage5_result.get("safe_path", "")
    if safe == 0:
        print("   ⚠️  No safe candidates — using binders for remaining tests")
        safe_path = binders_path

    # 7. Stage 6: Ranking
    print("\n" + "=" * 60)
    print("6️⃣  Stage 6: Candidate Ranking")
    print("=" * 60)
    stage6_result = test_tool("stage6_rank_candidates", {
        "safe_path": safe_path,
        "patient_id": patient_id,
        "top_n": 10,
    }, timeout=60)

    if not stage6_result or not isinstance(stage6_result, dict):
        _summary(start)
        return

    ranked_path = stage6_result.get("ranked_path", "")

    # 8. Stage 7: mRNA Design
    print("\n" + "=" * 60)
    print("7️⃣  Stage 7: mRNA Construct Design")
    print("=" * 60)
    stage7_result = test_tool("stage7_design_mrna", {
        "ranked_path": ranked_path,
        "patient_id": patient_id,
        "top_n": 10,
    }, timeout=120)

    _summary(start)


def _summary(start):
    total = time.time() - start
    print("\n" + "=" * 60)
    print(f"🧬 Integration Test Complete — {total:.1f}s total")
    print("=" * 60)


if __name__ == "__main__":
    main()
