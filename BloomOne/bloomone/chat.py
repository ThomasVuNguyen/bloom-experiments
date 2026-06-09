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

1. **When a user uploads a file**, ALWAYS call `inspect_artifact` FIRST \
to analyze the file before running any pipeline stage. This reveals:
   - Patient barcodes (Tumor_Sample_Barcode) — use these as `patient_id`
   - Mutation types and counts
   - Gene list and column structure
   Never guess the patient_id — inspect the file to find the real barcode.

2. **HLA alleles are REQUIRED** for Stage 4. If the user hasn't provided \
them, you MUST ask before proceeding. \
Format: HLA-A*02:01,HLA-B*07:02,HLA-C*07:01. \
cBioPortal does NOT provide HLA alleles — always ask.

3. **Data flow**: Each stage produces a file path used by the next stage. \
Read the `next_action` field in each tool response for exactly what to do next.

4. **Research use only**: Always remind users that ALL outputs are for \
RESEARCH USE ONLY and not validated for clinical use.

5. After the pipeline completes, present a clear summary:
   - Pipeline funnel: mutations → peptides → binders → safe → ranked → mRNA
   - Top candidates (gene, mutation, peptide, IC50)
   - Any warnings

6. **Respect the user's requested scope.** If the user asks to run a \
specific stage (e.g., "run stage 1", "just generate peptides", "only do \
binding prediction"), run ONLY that stage's tool and then STOP and report \
the results. Do NOT automatically chain into subsequent stages unless the \
user explicitly says "run the full pipeline", "run all stages", or \
"continue through all stages". The `run_full_pipeline` tool should ONLY \
be used when the user explicitly asks for the complete pipeline (stages 3→7) \
in one go.

## Quick Start

- For uploaded files: inspect_artifact FIRST, then run pipeline with real barcode
- For TCGA/cBioPortal: ask for case/sample ID + HLA alleles
- Demo: case TCGA-BF-A3DL-01, study skcm_tcga_pan_can_atlas_2018

Be concise and scientific. Show progress as you run each stage.
"""

# ── Tool Definitions (OpenAI function-calling format) ────────────────────────

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "inspect_artifact",
            "description": (
                "Inspect and analyze a pipeline file (MAF, TSV, CSV, FASTA). "
                "ALWAYS call this FIRST when a user uploads a file. Returns "
                "row count, columns, patient barcodes (Tumor_Sample_Barcode), "
                "mutation type breakdown, gene list, and sample rows. Use the "
                "patient barcodes from the result as patient_id when calling "
                "pipeline tools — never guess the patient_id."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Absolute path to the file to inspect",
                    },
                    "max_rows": {
                        "type": "integer",
                        "description": (
                            "Max sample rows to return (default 5)"
                        ),
                    },
                },
                "required": ["file_path"],
            },
        },
    },
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
    "inspect_artifact": "🔍 Analyzing uploaded file",
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
        if name == "inspect_artifact":
            return _inspect_artifact(arguments)

        elif name == "stage1_fetch_cbio":
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


def _inspect_artifact(arguments: dict) -> dict:
    """Inspect a MAF/TSV/FASTA file and return a summary for the LLM."""
    import os

    import pandas as pd

    file_path = arguments["file_path"]
    max_rows = arguments.get("max_rows", 5)

    if not os.path.exists(file_path):
        return {
            "error": f"File not found: {file_path}",
            "suggestion": "Check the file path — was it uploaded correctly?",
        }

    stat = os.stat(file_path)
    result: dict = {
        "file_path": file_path,
        "size_bytes": stat.st_size,
    }

    try:
        # Determine separator
        if file_path.endswith(".csv"):
            sep = ","
        else:
            sep = "\t"

        df = pd.read_csv(file_path, sep=sep, comment="#", low_memory=False)

        result["total_rows"] = len(df)
        result["columns"] = list(df.columns)

        # Patient barcodes — critical for pipeline
        if "Tumor_Sample_Barcode" in df.columns:
            barcodes = df["Tumor_Sample_Barcode"].unique().tolist()
            result["patient_barcodes"] = barcodes[:10]
            result["total_patients"] = len(barcodes)
            result["recommended_patient_id"] = str(barcodes[0])

        # Mutation breakdown
        if "Variant_Classification" in df.columns:
            result["variant_types"] = (
                df["Variant_Classification"].value_counts().to_dict()
            )
            missense_count = int(
                (df["Variant_Classification"] == "Missense_Mutation").sum()
            )
            result["missense_mutations"] = missense_count

        # Gene list
        if "Hugo_Symbol" in df.columns:
            genes = sorted(df["Hugo_Symbol"].dropna().unique().tolist())
            result["unique_genes"] = len(genes)
            result["top_genes"] = genes[:20]

        # HGVSp_Short availability
        if "HGVSp_Short" in df.columns:
            has_hgvsp = int(df["HGVSp_Short"].notna().sum())
            result["rows_with_protein_change"] = has_hgvsp

        # Sample rows (trimmed to avoid token overflow)
        keep_cols = [
            c for c in [
                "Hugo_Symbol", "Variant_Classification", "HGVSp_Short",
                "Tumor_Sample_Barcode", "Chromosome", "Start_Position",
            ] if c in df.columns
        ]
        if keep_cols:
            result["sample_rows"] = (
                df[keep_cols].head(max_rows).to_dict("records")
            )
        else:
            result["sample_rows"] = (
                df.head(max_rows).to_dict("records")
            )

        # Build summary
        parts = [f"MAF/TSV file with {len(df)} rows and {len(df.columns)} columns."]
        if "total_patients" in result:
            parts.append(f"{result['total_patients']} patient(s): {result.get('patient_barcodes', [])[:3]}.")
        if "missense_mutations" in result:
            parts.append(f"{result['missense_mutations']} missense mutations.")
        if "unique_genes" in result:
            parts.append(f"{result['unique_genes']} unique genes.")
        result["summary"] = " ".join(parts)

    except Exception as e:
        result["error"] = f"Failed to parse file: {e}"

    return result


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

    if pep.total_candidates == 0:
        return {
            "patient_id": patient_id,
            "summary": (
                "Pipeline stopped at Stage 3: no missense-derived peptides generated. "
                "This may mean the MAF file has no missense mutations for the selected "
                "patient, or protein sequences could not be fetched."
            ),
            "stages_completed": [3],
            "warnings": pep.warnings,
            "research_use_only": True,
        }

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


# Default model fallback chain — tried in order on rate-limit / 5xx errors
FALLBACK_MODELS = [
    "google/gemma-4-31b-it:free",
    "openai/gpt-oss-120b:free",
    "qwen/qwen3-coder:free",
    "nvidia/nemotron-3-super-120b-a12b:free",
]


def _is_retryable(exc: Exception) -> bool:
    """Check if an LLM error is retryable (rate limit or server error)."""
    msg = str(exc).lower()
    return any(code in msg for code in ["429", "rate limit", "502", "503"])


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

    If the primary model hits a rate limit (429), automatically falls back
    to the next model in the FALLBACK_MODELS chain.

    Modifies ``messages`` in place — after exhausting the generator,
    ``messages`` contains the full conversation including tool calls.

    Yields dicts of the form:
        {"type": "status", "content": "🧬 Stage 3: ..."}
        {"type": "text",   "content": "Here are the results..."}
        {"type": "error",  "content": "Something went wrong"}
    """
    # Build fallback chain: requested model first, then others
    models_to_try = [model] + [
        m for m in FALLBACK_MODELS if m != model
    ]
    active_model = model

    for _ in range(max_rounds):
        # ── Call the LLM with fallback ───────────────────────────────
        response = None
        last_error = None

        for candidate_model in models_to_try:
            try:
                response = client.chat.completions.create(
                    model=candidate_model,
                    messages=messages,
                    tools=TOOLS,
                    tool_choice="auto",
                    temperature=0.3,
                )
                if candidate_model != active_model:
                    yield {
                        "type": "status",
                        "content": (
                            f"⚡ Switched to {candidate_model.split('/')[1].split(':')[0]}"
                        ),
                    }
                    active_model = candidate_model
                    # Update models_to_try so subsequent rounds use this model first
                    models_to_try = [candidate_model] + [
                        m for m in FALLBACK_MODELS if m != candidate_model
                    ]
                break  # Success — stop trying
            except Exception as e:
                last_error = e
                if _is_retryable(e):
                    yield {
                        "type": "status",
                        "content": (
                            f"⏳ {candidate_model.split('/')[1].split(':')[0]} "
                            f"rate-limited, trying next model..."
                        ),
                    }
                    continue  # Try next model
                else:
                    yield {"type": "error", "content": f"LLM request failed: {e}"}
                    return

        if response is None:
            yield {
                "type": "error",
                "content": f"All models exhausted. Last error: {last_error}",
            }
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
