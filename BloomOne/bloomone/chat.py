"""
BloomOne — Chat engine with tool calling.

This module provides:
- Tool definitions (TOOLS) for OpenAI-compatible function calling
- Tool executor (execute_tool) to dispatch tool calls to pipeline stages
- Chat turn runner (run_chat_turn) with model fallback + streaming
- Multimodal support: patient_read_files injects images into Gemini context

The chat UI (chat_ui.py) imports and uses these components.
"""

from __future__ import annotations

import base64
import io
import json
import os
from pathlib import Path
from typing import Generator

from bloomone.config import BLOOMONE_VERSION


# ── Coolify File Fetch (fallback when Modal volume doesn't have the file) ────

COOLIFY_FRONTEND_URL = os.environ.get("COOLIFY_FRONTEND_URL", "")


def fetch_from_coolify(file_id: str, dest_dir: str = "/data/uploads") -> str | None:
    """
    Fetch a file from the Coolify frontend's /api/files/:id/download endpoint.

    Used as a fallback when the upload mirror to Modal fails and the
    pipeline needs to access a file that only exists on the Coolify Mac Mini.

    Returns the local path where the file was saved, or None on failure.
    """
    if not COOLIFY_FRONTEND_URL:
        return None

    import pathlib
    import requests

    try:
        # First get metadata to know the filename
        meta_url = f"{COOLIFY_FRONTEND_URL}/api/files/{file_id}"
        meta_resp = requests.get(meta_url, timeout=10)
        if not meta_resp.ok:
            print(f"[coolify-fetch] Metadata request failed: {meta_resp.status_code}")
            return None

        metadata = meta_resp.json()
        filename = metadata.get("filename", f"{file_id}.dat")

        # Download the file
        dl_url = f"{COOLIFY_FRONTEND_URL}/api/files/{file_id}/download"
        dl_resp = requests.get(dl_url, timeout=60, stream=True)
        if not dl_resp.ok:
            print(f"[coolify-fetch] Download failed: {dl_resp.status_code}")
            return None

        # Save to Modal volume
        pathlib.Path(dest_dir).mkdir(parents=True, exist_ok=True)
        dest_path = f"{dest_dir}/{filename}"
        with open(dest_path, "wb") as f:
            for chunk in dl_resp.iter_content(chunk_size=8192):
                f.write(chunk)

        # Commit to volume so other containers see it
        try:
            from bloomone.config import volume
            volume.commit()
        except Exception:
            pass

        print(f"[coolify-fetch] Downloaded {filename} -> {dest_path}")
        return dest_path

    except Exception as e:
        print(f"[coolify-fetch] Error: {e}")
        return None


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

## Patient Records

You can create and manage patient records to track data across conversations.

- When a user mentions a new patient, call `patient_create` with their name \
and DOB if known. Use name + DOB as the deduplication key (standard lab practice).
- When files are uploaded, call `patient_attach_file` to link them to the patient.
- After running pipeline stages, call `patient_add_result` to save results.
- Before starting work, call `patient_list` or `patient_get` to check for \
existing records so you don't create duplicates.
- Use `patient_update` to add notes, update details, or set HLA alleles.

## Reading Patient Files

When a user asks you to "review files", "look at the images", "read the \
documents", "what's in the files", or says "yes" to your offer to review \
files, you MUST call `patient_read_files`. This tool downloads the actual \
file content (images, PDFs, text files) so you can see and analyze them.

**After calling patient_read_files, you MUST describe in detail what you \
see in EACH file:**
- For images: describe what the image shows (charts, screenshots, medical \
  reports, test results, etc.) — include specific text, numbers, and data \
  you can read from the image.
- For PDFs/text: summarize the key content, data points, and findings.
- For genomic files: note the format, key columns, and sample data.

**Do NOT just report metadata** (filename, file type, size). The user wants \
to know WHAT IS IN the files. Think of yourself as reading the files on \
behalf of the user and reporting back everything you see.

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
    # ── Patient Management Tools ──────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "patient_create",
            "description": (
                "Create a new patient record. Use when a user mentions a new "
                "patient. The system auto-generates a unique ID. Use name + DOB "
                "as the deduplication key (standard lab practice for duplicate names)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Patient's name (e.g. 'Nani', 'John Doe')",
                    },
                    "dob": {
                        "type": "string",
                        "description": "Date of birth in YYYY-MM-DD format (optional, for dedup)",
                    },
                    "details": {
                        "type": "object",
                        "description": (
                            "Free-form details: cancer_type, diagnosis, etc."
                        ),
                    },
                    "hla_alleles": {
                        "type": "string",
                        "description": (
                            "Comma-separated HLA alleles if known "
                            "(e.g. 'HLA-A*02:01,HLA-B*07:02')"
                        ),
                    },
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "patient_get",
            "description": (
                "Get a patient record by ID or name. Returns full details "
                "including files, notes, and pipeline results."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "patient_id": {
                        "type": "string",
                        "description": "Patient ID (cuid) or name to search for",
                    },
                },
                "required": ["patient_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "patient_list",
            "description": (
                "List all patient records. Returns summary with name, ID, "
                "file count, and pipeline run count for each patient."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "patient_update",
            "description": (
                "Update a patient's details, HLA alleles, or add a note. "
                "Use this to add observations, OCR'd text from documents, "
                "or update clinical details."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "patient_id": {
                        "type": "string",
                        "description": "Patient ID",
                    },
                    "details": {
                        "type": "object",
                        "description": "Updated details (merged with existing)",
                    },
                    "hla_alleles": {
                        "type": "string",
                        "description": "Comma-separated HLA alleles to set",
                    },
                    "note": {
                        "type": "string",
                        "description": "A note to add to the patient's record",
                    },
                },
                "required": ["patient_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "patient_attach_file",
            "description": (
                "Attach an uploaded file to a patient record. The file_id "
                "comes from the file upload response. Use this after a user "
                "uploads files to link them to the correct patient."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "patient_id": {
                        "type": "string",
                        "description": "Patient ID to attach the file to",
                    },
                    "file_id": {
                        "type": "string",
                        "description": "File ID from the upload response",
                    },
                    "notes": {
                        "type": "string",
                        "description": "Notes about the file (e.g. 'MAF from biopsy 2024-01')",
                    },
                },
                "required": ["patient_id", "file_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "patient_add_result",
            "description": (
                "Save pipeline stage results to a patient's record. Call this "
                "after running pipeline stages to link the output to the patient."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "patient_id": {
                        "type": "string",
                        "description": "Patient ID",
                    },
                    "stages_completed": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "List of completed stage numbers (e.g. [3, 4, 5])",
                    },
                    "summary": {
                        "type": "string",
                        "description": "Human-readable summary of the pipeline run",
                    },
                    "output_paths": {
                        "type": "object",
                        "description": "Map of stage name to output file path",
                    },
                },
                "required": ["patient_id", "stages_completed", "summary"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "patient_read_files",
            "description": (
                "Read and analyze a patient's attached files (images, PDFs, "
                "documents). Downloads file content so you can see and describe "
                "images, read PDF text, and review documents. "
                "IMPORTANT: Only works with Gemini for image analysis. "
                "Call this when the user asks you to look at, review, or "
                "analyze a patient's files, scans, or documents."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "patient_id": {
                        "type": "string",
                        "description": "Patient ID to read files from",
                    },
                    "file_types": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Filter by file type: 'image', 'pdf', 'genomic', "
                            "'document', 'dicom'. Omit to read all types."
                        ),
                    },
                    "file_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Specific file IDs to read (from patient_get response). "
                            "Omit to read all files."
                        ),
                    },
                },
                "required": ["patient_id"],
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
    "patient_create": "👤 Creating patient record",
    "patient_get": "📋 Fetching patient details",
    "patient_list": "📋 Listing patients",
    "patient_update": "✏️ Updating patient record",
    "patient_attach_file": "📎 Attaching file to patient",
    "patient_add_result": "📊 Saving pipeline results",
    "patient_read_files": "👁️ Reading patient files",
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

        # ── Patient Management Tools ─────────────────────────────────
        elif name == "patient_create":
            from bloomone.patient import get_patient_manager
            mgr = get_patient_manager()
            alleles = None
            if arguments.get("hla_alleles"):
                alleles = [a.strip() for a in arguments["hla_alleles"].split(",") if a.strip()]
            return mgr.create(
                name=arguments["name"],
                dob=arguments.get("dob"),
                details=arguments.get("details"),
                hla_alleles=alleles,
            )

        elif name == "patient_get":
            from bloomone.patient import get_patient_manager
            mgr = get_patient_manager()
            pid = arguments["patient_id"]
            # Try by ID first, then by name
            result = mgr.get(pid)
            if "error" in result:
                by_name = mgr.get_by_name(pid)
                if by_name:
                    return by_name
            return result

        elif name == "patient_list":
            from bloomone.patient import get_patient_manager
            return get_patient_manager().list_all()

        elif name == "patient_update":
            from bloomone.patient import get_patient_manager
            mgr = get_patient_manager()
            pid = arguments["patient_id"]
            # Handle note separately
            if arguments.get("note"):
                mgr.add_note(pid, arguments["note"], source="agent")
            alleles = None
            if arguments.get("hla_alleles"):
                alleles = [a.strip() for a in arguments["hla_alleles"].split(",") if a.strip()]
            return mgr.update(
                patient_id=pid,
                details=arguments.get("details"),
                hla_alleles=alleles,
            )

        elif name == "patient_attach_file":
            from bloomone.patient import get_patient_manager
            return get_patient_manager().attach_file(
                patient_id=arguments["patient_id"],
                file_id=arguments["file_id"],
                notes=arguments.get("notes", ""),
            )

        elif name == "patient_add_result":
            from bloomone.patient import get_patient_manager
            return get_patient_manager().add_result(
                patient_id=arguments["patient_id"],
                stages_completed=arguments["stages_completed"],
                summary=arguments["summary"],
                output_paths=arguments.get("output_paths", {}),
                warnings=arguments.get("warnings"),
            )

        elif name == "patient_read_files":
            return _read_patient_files(arguments)

        else:
            return {"error": f"Unknown tool: {name}"}

    except Exception as e:
        import traceback
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
        # Try fetching from Coolify if we have a file ID in the path
        # The file_id might be embedded in the path or passed separately
        file_id = arguments.get("file_id")
        if file_id:
            fetched_path = fetch_from_coolify(file_id)
            if fetched_path:
                file_path = fetched_path

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


# ── Max limits for patient_read_files ────────────────────────────────────────
_MAX_FILES_PER_READ = 5
_MAX_TOTAL_BYTES = 20 * 1024 * 1024  # 20 MB
_IMAGE_MAX_DIMENSION = 1024  # resize images to this max width/height


def _resize_image_to_base64(raw_bytes: bytes, mime_type: str) -> str:
    """Resize an image to max dimension and return base64 data URI."""
    from PIL import Image

    img = Image.open(io.BytesIO(raw_bytes))

    # Resize if larger than max dimension
    w, h = img.size
    if max(w, h) > _IMAGE_MAX_DIMENSION:
        scale = _IMAGE_MAX_DIMENSION / max(w, h)
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

    # Convert to RGB if needed (e.g., RGBA PNGs)
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
        mime_type = "image/jpeg"

    buf = io.BytesIO()
    fmt = "JPEG" if "jpeg" in mime_type or "jpg" in mime_type else "PNG"
    img.save(buf, format=fmt, quality=85)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")

    return f"data:{mime_type};base64,{b64}"


def _extract_pdf_text(raw_bytes: bytes, max_pages: int = 10) -> str:
    """Extract text from a PDF. Returns first N pages of text."""
    try:
        import pdfplumber

        pages_text = []
        with pdfplumber.open(io.BytesIO(raw_bytes)) as pdf:
            for i, page in enumerate(pdf.pages[:max_pages]):
                text = page.extract_text() or ""
                if text.strip():
                    pages_text.append(f"--- Page {i + 1} ---\n{text}")

        if not pages_text:
            return "(PDF contained no extractable text — may be scanned/image-based)"

        result = "\n\n".join(pages_text)
        if len(pdf.pages) > max_pages:
            result += f"\n\n... ({len(pdf.pages) - max_pages} more pages not shown)"
        return result
    except Exception as e:
        return f"(Failed to extract PDF text: {e})"


def _read_patient_files(arguments: dict) -> dict:
    """
    Read and process patient files for AI analysis.

    Returns a dict with:
    - files: metadata for each file processed
    - _multimodal_parts: list of OpenAI content parts (images as data URIs)
      → used by run_chat_turn to inject into Gemini messages
    - text_summary: plain text summary for non-vision models
    """
    import requests

    patient_id = arguments["patient_id"]
    type_filter = arguments.get("file_types")
    id_filter = arguments.get("file_ids")

    if not COOLIFY_FRONTEND_URL:
        return {"error": "COOLIFY_FRONTEND_URL not configured"}

    # 1. Fetch patient file list from Coolify
    try:
        list_url = f"{COOLIFY_FRONTEND_URL}/api/patients/{patient_id}/files"
        resp = requests.get(list_url, timeout=15)
        if not resp.ok:
            return {"error": f"Failed to list patient files: {resp.status_code}"}
        files_data = resp.json().get("files", [])
    except Exception as e:
        return {"error": f"Failed to fetch patient files: {e}"}

    if not files_data:
        return {
            "files": [],
            "summary": f"Patient {patient_id} has no attached files.",
        }

    # 2. Apply filters
    if type_filter:
        files_data = [f for f in files_data if f.get("fileType") in type_filter]
    if id_filter:
        files_data = [f for f in files_data if f.get("id") in id_filter]

    if not files_data:
        return {
            "files": [],
            "summary": f"No files matched the filter for patient {patient_id}.",
        }

    # 3. Limit to max files
    if len(files_data) > _MAX_FILES_PER_READ:
        files_data = files_data[:_MAX_FILES_PER_READ]

    # 4. Download and process each file
    processed_files = []
    multimodal_parts = []  # OpenAI content parts for Gemini
    text_summaries = []    # Fallback for non-vision models
    total_bytes = 0

    for f in files_data:
        file_id = f["id"]
        filename = f.get("filename", "unknown")
        file_type = f.get("fileType", "document")
        mime_type = f.get("mimeType", "application/octet-stream")
        size_bytes = f.get("sizeBytes", 0)

        # Check total size
        if total_bytes + size_bytes > _MAX_TOTAL_BYTES:
            processed_files.append({
                "id": file_id,
                "filename": filename,
                "fileType": file_type,
                "status": "skipped",
                "reason": "Would exceed 20MB total limit",
            })
            continue

        # Download file bytes — try patient-scoped endpoint first,
        # then fall back to the general /api/files/{id}/download
        try:
            dl_url = (
                f"{COOLIFY_FRONTEND_URL}/api/patients/{patient_id}"
                f"/files/{file_id}/download"
            )
            dl_resp = requests.get(dl_url, timeout=60)

            # Fallback: try the general file download endpoint
            if not dl_resp.ok:
                dl_url = f"{COOLIFY_FRONTEND_URL}/api/files/{file_id}/download"
                dl_resp = requests.get(dl_url, timeout=60)

            if not dl_resp.ok:
                processed_files.append({
                    "id": file_id,
                    "filename": filename,
                    "fileType": file_type,
                    "status": "error",
                    "reason": f"Download failed: {dl_resp.status_code}",
                })
                continue

            raw_bytes = dl_resp.content
            total_bytes += len(raw_bytes)
        except Exception as e:
            processed_files.append({
                "id": file_id,
                "filename": filename,
                "status": "error",
                "reason": str(e),
            })
            continue

        # Process by file type
        if file_type == "image":
            try:
                data_uri = _resize_image_to_base64(raw_bytes, mime_type)
                multimodal_parts.append({
                    "type": "image_url",
                    "image_url": {"url": data_uri},
                })
                multimodal_parts.append({
                    "type": "text",
                    "text": f"[Image: {filename}]",
                })
                text_summaries.append(
                    f"📷 {filename} — {len(raw_bytes)} bytes image "
                    f"(use Gemini 2.5 Pro to view)"
                )
                processed_files.append({
                    "id": file_id,
                    "filename": filename,
                    "fileType": file_type,
                    "status": "loaded",
                    "sizeBytes": len(raw_bytes),
                })
            except Exception as e:
                processed_files.append({
                    "id": file_id,
                    "filename": filename,
                    "status": "error",
                    "reason": f"Image processing failed: {e}",
                })

        elif file_type == "pdf":
            text_content = _extract_pdf_text(raw_bytes)
            # PDF text goes to both multimodal and text summary
            multimodal_parts.append({
                "type": "text",
                "text": f"[PDF: {filename}]\n{text_content}",
            })
            text_summaries.append(
                f"📄 {filename}:\n{text_content[:2000]}"
                + ("..." if len(text_content) > 2000 else "")
            )
            processed_files.append({
                "id": file_id,
                "filename": filename,
                "fileType": file_type,
                "status": "loaded",
                "textLength": len(text_content),
            })

        elif file_type in ("genomic", "document"):
            # Try to read as text
            try:
                text_content = raw_bytes.decode("utf-8", errors="replace")
                # Truncate large text files
                if len(text_content) > 5000:
                    text_content = text_content[:5000] + "\n... (truncated)"
                multimodal_parts.append({
                    "type": "text",
                    "text": f"[File: {filename}]\n{text_content}",
                })
                text_summaries.append(f"📋 {filename}:\n{text_content[:2000]}")
                processed_files.append({
                    "id": file_id,
                    "filename": filename,
                    "fileType": file_type,
                    "status": "loaded",
                    "textLength": len(text_content),
                })
            except Exception as e:
                processed_files.append({
                    "id": file_id,
                    "filename": filename,
                    "status": "error",
                    "reason": f"Could not read as text: {e}",
                })

        else:
            processed_files.append({
                "id": file_id,
                "filename": filename,
                "fileType": file_type,
                "status": "skipped",
                "reason": f"Unsupported file type: {file_type}",
            })

    loaded_count = sum(1 for f in processed_files if f.get("status") == "loaded")
    summary = (
        f"Loaded {loaded_count} of {len(files_data)} files for patient {patient_id}."
    )

    return {
        "files": processed_files,
        "summary": summary,
        # These special keys are consumed by run_chat_turn for multimodal injection
        "_multimodal_parts": multimodal_parts,
        "_text_summary": "\n\n".join(text_summaries) if text_summaries else summary,
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

    # If IEDB failed and local MHCflurry isn't available, try the remote GPU function
    if bind.strong_binders == 0 and "No binding predictions" in (bind.summary or ""):
        print("\n🔄 Local binding prediction failed — trying remote MHCflurry GPU...")
        try:
            import modal
            mhcflurry_fn = modal.Function.from_name("bloomone", "run_mhcflurry_remote")
            remote_result = mhcflurry_fn.remote(
                peptides_path=pep.candidates_path,
                hla_alleles=alleles,
                patient_id=patient_id,
            )
            # Re-hydrate BindingResult from the dict returned by the remote function
            from bloomone.models import BindingResult as BR
            bind = BR(**remote_result)
            print(f"✅ Remote MHCflurry GPU returned {bind.strong_binders} strong binders")
        except Exception as e:
            print(f"⚠️ Remote MHCflurry GPU fallback failed: {e}")
            # Keep the original failed bind result
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
# Each entry is (model_id, provider_key) — provider_key maps to a client
FALLBACK_MODELS = [
    ("google/gemma-4-31b-it:free", "openrouter"),
    ("openai/gpt-oss-120b:free", "openrouter"),
    ("qwen/qwen3-coder:free", "openrouter"),
    ("nvidia/nemotron-3-super-120b-a12b:free", "openrouter"),
    ("Qwen/Qwen3.6-35B-A3B-FP8", "cloudrift"),
]

# Premium models — opt-in only, never used as automatic fallback.
# These require explicit user selection from the model dropdown.
# "vertexai" provider uses OIDC + Workload Identity Federation (no keys).
PREMIUM_MODELS = [
    ("google/gemini-2.5-pro", "vertexai"),
]


def _is_retryable(exc: Exception) -> bool:
    """Check if an LLM error is retryable (rate limit or server error)."""
    msg = str(exc).lower()
    return any(code in msg for code in ["429", "rate limit", "502", "503"])


def run_chat_turn(
    clients: dict,
    messages: list[dict],
    model: str = "google/gemma-4-31b-it:free",
    provider: str = "openrouter",
    max_rounds: int = 10,
) -> Generator[dict, None, None]:
    """
    Run one chat turn with multi-round tool calling.

    Sends messages to the LLM, handles tool calls, feeds results back,
    and repeats until the LLM produces a text response.

    If the primary model hits a rate limit (429) or other error, automatically
    falls back to the next model in the FALLBACK_MODELS chain. Supports
    multiple providers (e.g. OpenRouter, CloudRift) via the clients dict.

    Modifies ``messages`` in place — after exhausting the generator,
    ``messages`` contains the full conversation including tool calls.

    Parameters
    ----------
    clients : dict[str, OpenAI]
        Mapping of provider keys to OpenAI client instances.
        E.g. {"openrouter": client, "cloudrift": client}

    Yields dicts of the form:
        {"type": "status", "content": "🧬 Stage 3: ..."}
        {"type": "text",   "content": "Here are the results..."}
        {"type": "error",  "content": "Something went wrong"}
    """
    import time as _time

    # Build fallback chain: requested model first, then others
    models_to_try = [(model, provider)] + [
        (m, p) for m, p in FALLBACK_MODELS if m != model
    ]
    active_model = model
    active_provider = provider

    # ── Response metadata tracking ───────────────────────────────
    turn_start = _time.time()
    total_prompt_tokens = 0
    total_completion_tokens = 0
    tool_calls_count = 0
    rounds_used = 0

    for _ in range(max_rounds):
        rounds_used += 1
        # ── Call the LLM with fallback ───────────────────────────────
        response = None
        last_error = None

        for candidate_model, candidate_provider in models_to_try:
            candidate_client = clients.get(candidate_provider)
            if candidate_client is None:
                continue  # Skip if provider client not available
            try:
                create_kwargs = dict(
                    model=candidate_model,
                    messages=messages,
                    temperature=0.3,
                    tools=TOOLS,
                    tool_choice="auto",
                )

                response = candidate_client.chat.completions.create(**create_kwargs)
                if candidate_model != active_model:
                    yield {
                        "type": "status",
                        "content": (
                            f"⚡ Switched to {candidate_model.split('/')[1].split(':')[0]}"
                        ),
                    }
                    active_model = candidate_model
                    active_provider = candidate_provider
                    # Update models_to_try so subsequent rounds use this model first
                    models_to_try = [(candidate_model, candidate_provider)] + [
                        (m, p) for m, p in FALLBACK_MODELS if m != candidate_model
                    ]

                # Accumulate usage stats
                if hasattr(response, 'usage') and response.usage:
                    total_prompt_tokens += getattr(
                        response.usage, 'prompt_tokens', 0
                    ) or 0
                    total_completion_tokens += getattr(
                        response.usage, 'completion_tokens', 0
                    ) or 0

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
                # Continue to next model regardless — provider-specific
                # errors shouldn't block other providers
                continue

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
                elapsed = round(_time.time() - turn_start, 2)
                metadata = {
                    "model": active_model,
                    "provider": active_provider,
                    "prompt_tokens": total_prompt_tokens,
                    "completion_tokens": total_completion_tokens,
                    "total_tokens": (
                        total_prompt_tokens + total_completion_tokens
                    ),
                    "tool_calls": tool_calls_count,
                    "rounds": rounds_used,
                    "latency_s": elapsed,
                }
                yield {
                    "type": "text",
                    "content": assistant_msg.content,
                    "metadata": metadata,
                }
            return

        # ── Execute each tool call ───────────────────────────────────
        for tc in assistant_msg.tool_calls:
            tool_calls_count += 1
            tool_name = tc.function.name
            label = TOOL_LABELS.get(tool_name, f"🔧 Running {tool_name}")
            yield {"type": "status", "content": f"{label}..."}

            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                args = {}

            result = execute_tool(tool_name, args)

            # ── Multimodal injection for patient_read_files ──────────
            multimodal_parts = result.pop("_multimodal_parts", [])
            text_summary = result.pop("_text_summary", "")

            # Append tool result to history (without heavy base64 data)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result, default=str),
                }
            )

            # If we have multimodal content, inject as a follow-up
            # user message so Gemini can "see" the images
            if multimodal_parts:
                # Determine if current model supports vision
                is_vision_model = (
                    active_model in [m for m, p in PREMIUM_MODELS]
                    or "gemini" in active_model.lower()
                )

                if is_vision_model:
                    # Inject multimodal user message with images
                    vision_content = [
                        {
                            "type": "text",
                            "text": (
                                "Here are the patient's files. "
                                "Please analyze them carefully:"
                            ),
                        },
                    ] + multimodal_parts
                    messages.append({
                        "role": "user",
                        "content": vision_content,
                    })
                else:
                    # Non-vision model: inject text-only summary
                    messages.append({
                        "role": "user",
                        "content": (
                            f"[File contents (text only — images require "
                            f"Gemini 2.5 Pro)]:\n\n{text_summary}"
                        ),
                    })

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
