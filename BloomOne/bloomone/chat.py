"""
BloomOne AI Chat — Gemini 2.5 Flash tool-calling orchestrator.

Provides tool definitions (OpenAI function-calling format), a tool
executor that calls BloomOne stage functions directly, and a chat loop
that handles multi-round tool calling until the LLM produces a final
text response.
"""

from __future__ import annotations

import json
import traceback
from typing import Generator

from bloomone.config import BLOOMONE_VERSION


# ── System Prompt ────────────────────────────────────────────────────────────

SYSTEM_PROMPT = f"""\
You are BloomOne v{BLOOMONE_VERSION}, an AI research assistant for personalized \
neoantigen vaccine design.

You help researchers transform tumor DNA into personalized mRNA neoantigen \
vaccine constructs through a 7-stage computational pipeline.

## Pipeline Stages (run sequentially)

| Stage | Tool | What It Does |
|-------|------|-------------|
| 1 | stage1_fetch_cbio / stage1_fetch_tcga | Fetch patient mutations |
| 3 | stage3_generate_peptides | Generate 8-11mer mutant peptides |
| 4 | stage4_predict_binding | Predict HLA-I binding (MHCflurry) |
| 5 | stage5_safety_filter | Remove self-matching peptides |
| 6 | stage6_rank_candidates | Score & rank candidates |
| 7 | stage7_design_mrna | Design mRNA vaccine constructs |

Stage 2 (Strelka2 mutation calling) is automatically skipped when MAF data \
is available (cBioPortal, TCGA MAF, or user-uploaded MAF).

## Critical Rules

1. **HLA alleles are REQUIRED** for Stage 4. If the user hasn't provided \
them, you MUST ask before proceeding. \
Format: HLA-A*02:01,HLA-B*07:02,HLA-C*07:01. \
cBioPortal does NOT provide HLA alleles — always ask.

2. **Data flow**: Each stage produces a file path used by the next stage. \
Read the `next_action` field in each tool response for exactly what to do next.

3. **Research use only**: Always remind users that ALL outputs are for \
RESEARCH USE ONLY and not validated for clinical use.

4. After the pipeline completes, present a clear summary:
   - Pipeline funnel: mutations → peptides → binders → safe → ranked → mRNA
   - Top candidates (gene, mutation, peptide, IC50)
   - Any warnings

## Quick Start

- For TCGA/cBioPortal: ask for case/sample ID + HLA alleles
- For local files: ask for MAF path + HLA alleles
- Demo: case TCGA-BF-A3DL-01, study skcm_tcga_pan_can_atlas_2018

Be concise and scientific. Show progress as you run each stage.
"""

# ── Tool Definitions (OpenAI function-calling format) ────────────────────────

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "stage1_fetch_cbio",
            "description": (
                "Stage 1: Fetch pre-called somatic mutations from cBioPortal. "
                "Returns MAF data (skips Stage 2). "
                "WARNING: cBioPortal does NOT provide HLA alleles — ask the user."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "study_id": {
                        "type": "string",
                        "description": (
                            "cBioPortal study ID "
                            "(e.g. 'skcm_tcga_pan_can_atlas_2018')"
                        ),
                    },
                    "sample_id": {
                        "type": "string",
                        "description": (
                            "Sample barcode (e.g. 'TCGA-BF-A3DL-01')"
                        ),
                    },
                },
                "required": ["study_id", "sample_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stage1_fetch_tcga",
            "description": (
                "Stage 1: Fetch data from TCGA via GDC API. "
                "Downloads MAF (skips Stage 2) or BAM (requires Stage 2). "
                "Does NOT provide HLA alleles."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "case_id": {
                        "type": "string",
                        "description": "TCGA case ID (e.g. 'TCGA-BF-A3DL-01')",
                    },
                    "data_type": {
                        "type": "string",
                        "description": (
                            "GDC data type "
                            "(default: 'Masked Somatic Mutation')"
                        ),
                    },
                },
                "required": ["case_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stage3_generate_peptides",
            "description": (
                "Stage 3: Generate 8-11mer mutant peptides from somatic "
                "mutations in a MAF file. Uses sliding window + Ensembl VEP."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "maf_path": {
                        "type": "string",
                        "description": "Path to MAF file from Stage 1 or 2",
                    },
                    "patient_id": {
                        "type": "string",
                        "description": "Patient identifier",
                    },
                    "tpm_path": {
                        "type": "string",
                        "description": (
                            "Optional RNA-seq TPM file for expression filtering"
                        ),
                    },
                },
                "required": ["maf_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stage4_predict_binding",
            "description": (
                "Stage 4: Predict HLA-I binding affinity for candidate "
                "peptides using MHCflurry 2.0 or IEDB NetMHCpan. "
                "Filters to strong binders (IC50 < 500nM or rank < 0.5%)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "peptides_path": {
                        "type": "string",
                        "description": (
                            "Path to peptide candidates TSV from Stage 3"
                        ),
                    },
                    "hla_alleles": {
                        "type": "string",
                        "description": (
                            "Comma-separated HLA-I alleles "
                            "(e.g. 'HLA-A*02:01,HLA-B*07:02')"
                        ),
                    },
                    "patient_id": {
                        "type": "string",
                        "description": "Patient identifier",
                    },
                },
                "required": ["peptides_path", "hla_alleles"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stage5_safety_filter",
            "description": (
                "Stage 5: Remove peptides that match healthy human proteins. "
                "Checks against the UniProt human reviewed proteome (~20k proteins)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "binders_path": {
                        "type": "string",
                        "description": (
                            "Path to binding predictions TSV from Stage 4"
                        ),
                    },
                    "patient_id": {
                        "type": "string",
                        "description": "Patient identifier",
                    },
                },
                "required": ["binders_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stage6_rank_candidates",
            "description": (
                "Stage 6: Score and rank safe neoantigen candidates. "
                "Composite: IC50 rank (50%) + VAF (30%) + TPM (20% optional). "
                "Selects top N candidates for mRNA design."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "safe_path": {
                        "type": "string",
                        "description": (
                            "Path to safe candidates TSV from Stage 5"
                        ),
                    },
                    "patient_id": {
                        "type": "string",
                        "description": "Patient identifier",
                    },
                    "tpm_path": {
                        "type": "string",
                        "description": (
                            "Optional RNA-seq TPM file for expression weighting"
                        ),
                    },
                    "top_n": {
                        "type": "integer",
                        "description": (
                            "Number of top candidates to select (default 20)"
                        ),
                    },
                },
                "required": ["safe_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stage7_design_mrna",
            "description": (
                "Stage 7: Design mRNA vaccine constructs from ranked candidates. "
                "Includes codon optimization, tPA signal peptide, AAY linker, "
                "beta/alpha-globin UTRs, poly-A tail, and polytope construct. "
                "Output is ready for wet lab synthesis review."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ranked_path": {
                        "type": "string",
                        "description": (
                            "Path to ranked candidates TSV from Stage 6"
                        ),
                    },
                    "patient_id": {
                        "type": "string",
                        "description": "Patient identifier",
                    },
                    "top_n": {
                        "type": "integer",
                        "description": (
                            "Number of constructs to design (default 20)"
                        ),
                    },
                },
                "required": ["ranked_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_full_pipeline",
            "description": (
                "Run the complete pipeline from MAF to mRNA (Stages 3→7) "
                "in a single call. Use when you have both a MAF file and "
                "HLA alleles ready. For data fetching, use stage1 tools first."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "maf_path": {
                        "type": "string",
                        "description": "Path to MAF file with somatic mutations",
                    },
                    "hla_alleles": {
                        "type": "string",
                        "description": "Comma-separated HLA-I alleles",
                    },
                    "patient_id": {
                        "type": "string",
                        "description": "Patient identifier (default: patient_001)",
                    },
                    "tpm_path": {
                        "type": "string",
                        "description": "Optional RNA-seq TPM file",
                    },
                    "top_n": {
                        "type": "integer",
                        "description": (
                            "Number of top candidates (default 20)"
                        ),
                    },
                },
                "required": ["maf_path", "hla_alleles"],
            },
        },
    },
]


# ── Result Summarization ────────────────────────────────────────────────────


def summarize_result(result: dict, max_items: int = 5) -> dict:
    """Trim large lists in tool results to avoid token overflow."""
    trimmed = {}
    for key, value in result.items():
        if isinstance(value, list) and len(value) > max_items:
            trimmed[key] = value[:max_items]
            trimmed[f"_{key}_count"] = len(value)
            trimmed[f"_{key}_note"] = (
                f"Showing first {max_items} of {len(value)} — "
                f"full data saved to output file"
            )
        else:
            trimmed[key] = value
    return trimmed


# ── Tool Executor ────────────────────────────────────────────────────────────

# Status labels for UI
TOOL_LABELS = {
    "stage1_fetch_cbio": "📥 Stage 1: Fetching from cBioPortal",
    "stage1_fetch_tcga": "📥 Stage 1: Fetching from TCGA/GDC",
    "stage3_generate_peptides": "🧬 Stage 3: Generating peptides",
    "stage4_predict_binding": "🔬 Stage 4: Predicting HLA binding",
    "stage5_safety_filter": "🛡️ Stage 5: Safety filtering",
    "stage6_rank_candidates": "📊 Stage 6: Ranking candidates",
    "stage7_design_mrna": "💉 Stage 7: Designing mRNA constructs",
    "run_full_pipeline": "🚀 Running full pipeline (Stages 3→7)",
}


def execute_tool(name: str, arguments: dict) -> dict:
    """Execute a BloomOne pipeline tool by name and return the result."""
    try:
        if name == "stage1_fetch_cbio":
            from bloomone.stages.stage1_ingest import fetch_cbio_data

            result = fetch_cbio_data(
                study_id=arguments["study_id"],
                sample_id=arguments["sample_id"],
            )
            return summarize_result(result.model_dump())

        elif name == "stage1_fetch_tcga":
            from bloomone.stages.stage1_ingest import fetch_tcga_data

            result = fetch_tcga_data(
                case_id=arguments["case_id"],
                data_type=arguments.get(
                    "data_type", "Masked Somatic Mutation"
                ),
            )
            return summarize_result(result.model_dump())

        elif name == "stage3_generate_peptides":
            from bloomone.stages.stage3_peptides import generate_peptides

            result = generate_peptides(
                maf_path=arguments["maf_path"],
                patient_id=arguments.get("patient_id"),
                tpm_path=arguments.get("tpm_path"),
            )
            return summarize_result(result.model_dump())

        elif name == "stage4_predict_binding":
            from bloomone.stages.stage4_binding import predict_binding

            alleles = [
                a.strip()
                for a in arguments["hla_alleles"].split(",")
                if a.strip()
            ]
            result = predict_binding(
                peptides_path=arguments["peptides_path"],
                hla_alleles=alleles,
                patient_id=arguments.get("patient_id"),
            )
            return summarize_result(result.model_dump())

        elif name == "stage5_safety_filter":
            from bloomone.stages.stage5_safety import filter_self_similarity

            result = filter_self_similarity(
                binders_path=arguments["binders_path"],
                patient_id=arguments.get("patient_id"),
            )
            return summarize_result(result.model_dump())

        elif name == "stage6_rank_candidates":
            from bloomone.stages.stage6_ranking import rank_candidates

            result = rank_candidates(
                safe_path=arguments["safe_path"],
                tpm_path=arguments.get("tpm_path"),
                patient_id=arguments.get("patient_id"),
                top_n=arguments.get("top_n", 20),
            )
            return summarize_result(result.model_dump())

        elif name == "stage7_design_mrna":
            from bloomone.stages.stage7_mrna import design_mrna

            result = design_mrna(
                ranked_path=arguments["ranked_path"],
                patient_id=arguments.get("patient_id"),
                top_n=arguments.get("top_n", 20),
            )
            return summarize_result(result.model_dump())

        elif name == "run_full_pipeline":
            return _run_full_pipeline(arguments)

        else:
            return {"error": f"Unknown tool: {name}"}

    except Exception as e:
        return {
            "error": f"Tool '{name}' failed: {str(e)}",
            "traceback": traceback.format_exc(),
            "suggestion": "Check the input parameters and try again.",
        }


def _run_full_pipeline(arguments: dict) -> dict:
    """Run stages 3→7 sequentially and return a combined result."""
    from bloomone.stages.stage3_peptides import generate_peptides
    from bloomone.stages.stage4_binding import predict_binding
    from bloomone.stages.stage5_safety import filter_self_similarity
    from bloomone.stages.stage6_ranking import rank_candidates
    from bloomone.stages.stage7_mrna import design_mrna

    maf_path = arguments["maf_path"]
    alleles = [
        a.strip()
        for a in arguments["hla_alleles"].split(",")
        if a.strip()
    ]
    patient_id = arguments.get("patient_id", "patient_001")
    tpm_path = arguments.get("tpm_path")
    top_n = arguments.get("top_n", 20)

    pep = generate_peptides(
        maf_path=maf_path, patient_id=patient_id, tpm_path=tpm_path
    )
    bind = predict_binding(
        peptides_path=pep.candidates_path,
        hla_alleles=alleles,
        patient_id=patient_id,
    )
    safe = filter_self_similarity(
        binders_path=bind.predictions_path, patient_id=patient_id
    )
    rank = rank_candidates(
        safe_path=safe.safe_path,
        tpm_path=tpm_path,
        patient_id=patient_id,
        top_n=top_n,
    )
    mrna = design_mrna(
        ranked_path=rank.ranked_path,
        patient_id=patient_id,
        top_n=top_n,
    )

    return {
        "patient_id": patient_id,
        "summary": (
            f"Pipeline complete. "
            f"{pep.total_candidates} peptides → "
            f"{bind.strong_binders} strong binders → "
            f"{safe.total_safe} safe → "
            f"top {rank.total_ranked} ranked → "
            f"{mrna.total_designed} mRNA constructs designed."
        ),
        "stages_completed": [3, 4, 5, 6, 7],
        "output_paths": {
            "peptides": pep.candidates_path,
            "binding": bind.predictions_path,
            "safety": safe.safe_path,
            "ranked": rank.ranked_path,
            "mrna": mrna.constructs_path,
        },
        "top_candidates": [
            {
                "rank": c.rank,
                "gene": c.gene,
                "mutation": c.hgvsp_short,
                "peptide": c.peptide,
                "ic50_nM": c.ic50,
                "gc_percent": c.gc_content,
                "mrna_length_nt": c.full_length,
            }
            for c in mrna.constructs[:5]
        ],
        "polytope_length_nt": mrna.polytope_length,
        "warnings": (
            pep.warnings
            + bind.warnings
            + safe.warnings
            + rank.warnings
            + mrna.warnings
        ),
        "research_use_only": True,
    }


# ── Chat Loop ────────────────────────────────────────────────────────────────


def run_chat_turn(
    client,
    messages: list[dict],
    model: str = "google/gemma-4-31b-it:free",
    max_rounds: int = 10,
) -> Generator[dict, None, None]:
    """
    Run one chat turn with multi-round tool calling.

    Sends messages to the LLM, handles tool calls, feeds results back,
    and repeats until the LLM produces a text response.

    Modifies ``messages`` in place — after exhausting the generator,
    ``messages`` contains the full conversation including tool calls.

    Yields dicts of the form:
        {"type": "status", "content": "🧬 Stage 3: ..."}
        {"type": "text",   "content": "Here are the results..."}
        {"type": "error",  "content": "Something went wrong"}
    """
    for _ in range(max_rounds):
        # ── Call the LLM ─────────────────────────────────────────────
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
                temperature=0.3,
            )
        except Exception as e:
            yield {"type": "error", "content": f"LLM request failed: {e}"}
            return

        choice = response.choices[0]
        assistant_msg = choice.message

        # Build the message dict to append to history
        msg_dict: dict = {
            "role": "assistant",
            "content": assistant_msg.content or "",
        }
        if assistant_msg.tool_calls:
            msg_dict["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in assistant_msg.tool_calls
            ]
        messages.append(msg_dict)

        # ── No tool calls → final text response ─────────────────────
        if not assistant_msg.tool_calls:
            if assistant_msg.content:
                yield {"type": "text", "content": assistant_msg.content}
            return

        # ── Execute each tool call ───────────────────────────────────
        for tc in assistant_msg.tool_calls:
            tool_name = tc.function.name
            label = TOOL_LABELS.get(tool_name, f"🔧 Running {tool_name}")
            yield {"type": "status", "content": f"{label}..."}

            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                args = {}

            result = execute_tool(tool_name, args)

            # Append tool result to history
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result, default=str),
                }
            )

            # Yield completion status
            if "error" in result:
                yield {
                    "type": "status",
                    "content": f"⚠️ {tool_name}: {result['error']}",
                }
            else:
                summary = result.get("summary", "Done")
                yield {"type": "status", "content": f"✅ {summary}"}

    yield {
        "type": "error",
        "content": "Exceeded maximum tool-calling rounds.",
    }
