"""
Pipeline status & dependency graph tools — let agents inspect state
and make intelligent decisions about what to run next.

Tools:
  - pipeline_status: Full pipeline state for a patient
  - get_dependency_graph: Structured stage dependency information
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Optional

from bloomone.config import PATHS, BLOOMONE_VERSION


# ── Stage Dependency Graph ──────────────────────────────────────────────────

DEPENDENCY_GRAPH = [
    {
        "stage": 1,
        "name": "Data Ingestion",
        "tools": ["stage1_ingest_local", "stage1_fetch_tcga", "stage1_fetch_cbio"],
        "requires": [],
        "produces": ["maf_path", "hla_alleles", "tumor_path", "normal_path"],
        "skip_if": None,
        "estimated_minutes": 2,
        "description": "Load patient data from local files, TCGA, or cBioPortal.",
    },
    {
        "stage": 2,
        "name": "Mutation Calling",
        "tools": ["stage2_call_mutations"],
        "requires": ["tumor_bam", "normal_bam", "hg38_reference"],
        "produces": ["vcf_path", "maf_path"],
        "skip_if": "MAF file already provided (pre-called mutations)",
        "estimated_minutes": 45,
        "description": "Run Strelka2 somatic variant calling on tumor/normal BAMs.",
    },
    {
        "stage": 3,
        "name": "Peptide Generation",
        "tools": ["stage3_generate_peptides"],
        "requires": ["maf_path"],
        "produces": ["peptides_tsv"],
        "skip_if": None,
        "estimated_minutes": 2,
        "description": "Generate 8-11mer mutant peptides from missense mutations.",
    },
    {
        "stage": 4,
        "name": "HLA Binding Prediction",
        "tools": ["stage4_predict_binding"],
        "requires": ["peptides_tsv", "hla_alleles"],
        "produces": ["binding_predictions_tsv"],
        "skip_if": None,
        "estimated_minutes": 10,
        "description": "Predict HLA-I binding affinity using MHCflurry 2.0 or NetMHCpan.",
    },
    {
        "stage": 5,
        "name": "Safety Filter",
        "tools": ["stage5_safety_filter"],
        "requires": ["binding_predictions_tsv"],
        "produces": ["safe_candidates_tsv"],
        "skip_if": None,
        "estimated_minutes": 2,
        "description": "Remove peptides matching healthy human proteins.",
    },
    {
        "stage": 6,
        "name": "Candidate Ranking",
        "tools": ["stage6_rank_candidates"],
        "requires": ["safe_candidates_tsv"],
        "produces": ["ranked_candidates_tsv"],
        "skip_if": None,
        "estimated_minutes": 1,
        "description": "Score and rank candidates using IC50, VAF, and expression.",
    },
    {
        "stage": 7,
        "name": "mRNA Construct Design",
        "tools": ["stage7_design_mrna"],
        "requires": ["ranked_candidates_tsv"],
        "produces": ["mrna_constructs_tsv", "polytope_fasta"],
        "skip_if": None,
        "estimated_minutes": 1,
        "description": "Design codon-optimized mRNA vaccine constructs.",
    },
]


# ── File Pattern Detection ──────────────────────────────────────────────────

STAGE_OUTPUT_PATTERNS = {
    1: {"dir": "input", "pattern": "{patient_id}"},
    2: {"dir": "stage2", "pattern": "{patient_id}"},
    3: {"dir": "stage3", "pattern": "{patient_id}_peptides.tsv"},
    4: {"dir": "stage4", "pattern": "{patient_id}_binding.tsv"},
    5: {"dir": "stage5", "pattern": "{patient_id}_safe_candidates.tsv"},
    6: {"dir": "stage6", "pattern": "{patient_id}_ranked.tsv"},
    7: {"dir": "stage7", "pattern": "{patient_id}_mrna_constructs.tsv"},
}


def _check_stage_output(stage: int, patient_id: str) -> dict:
    """Check if a stage's output exists for a patient."""
    info = STAGE_OUTPUT_PATTERNS.get(stage, {})
    if not info:
        return {"status": "unknown"}

    dir_key = info["dir"]
    pattern = info["pattern"].format(patient_id=patient_id)
    dir_path = PATHS.get(dir_key, "")

    if stage == 1:
        # Stage 1 creates a directory
        full_path = os.path.join(dir_path, patient_id)
        if os.path.isdir(full_path):
            files = os.listdir(full_path)
            return {
                "status": "completed",
                "output_path": full_path,
                "files": files,
            }
        return {"status": "not_started"}

    if stage == 2:
        # Stage 2 creates a directory with VCF
        full_path = os.path.join(dir_path, patient_id)
        if os.path.isdir(full_path):
            return {"status": "completed", "output_path": full_path}
        return {"status": "not_started"}

    # Stages 3-7 create specific TSV files
    full_path = os.path.join(dir_path, pattern)
    if os.path.exists(full_path):
        stat = os.stat(full_path)
        return {
            "status": "completed",
            "output_path": full_path,
            "size_bytes": stat.st_size,
            "modified": datetime.fromtimestamp(
                stat.st_mtime, tz=timezone.utc
            ).isoformat(),
        }
    return {"status": "not_started"}


# ── Tool Registration ───────────────────────────────────────────────────────


def register_status_tools(mcp):
    """Register pipeline status tools on the MCP server."""

    @mcp.tool()
    async def pipeline_status(patient_id: str) -> dict:
        """
        Return full pipeline state for a patient.

        Checks the volume for output files from each stage and reports what
        has completed, what's next, and what inputs are missing. Use this to
        make intelligent decisions about which tool to call next.

        Args:
            patient_id: Patient identifier to check status for
        """
        stages = {}
        last_completed = 0
        missing_inputs = []

        for stage_num in range(1, 8):
            result = _check_stage_output(stage_num, patient_id)
            stages[stage_num] = {
                "stage": stage_num,
                "name": DEPENDENCY_GRAPH[stage_num - 1]["name"],
                **result,
            }
            if result["status"] == "completed":
                last_completed = stage_num

        # Determine next runnable stage
        next_stage = last_completed + 1 if last_completed < 7 else None

        # Check if Stage 2 was skipped (MAF exists but no Stage 2 output)
        if stages[1]["status"] == "completed" and stages[2]["status"] == "not_started":
            # Check if input dir has a MAF file
            input_dir = os.path.join(PATHS["input"], patient_id)
            if os.path.isdir(input_dir):
                maf_files = [f for f in os.listdir(input_dir) if f.endswith(".maf")]
                if maf_files:
                    stages[2]["status"] = "skipped"
                    stages[2]["reason"] = "MAF input provided — mutations pre-called"
                    if last_completed == 1:
                        next_stage = 3

        # Check for HLA alleles
        has_hla = False
        # We can't easily check without loading state — flag as potential issue
        if next_stage and next_stage >= 4:
            missing_inputs.append(
                "Ensure hla_alleles are available for Stage 4. "
                "If not provided, run stage1_run_optitype first."
            )

        # Pipeline completion
        all_done = all(
            s.get("status") in ("completed", "skipped")
            for s in stages.values()
        )

        return {
            "patient_id": patient_id,
            "stages": stages,
            "next_runnable_stage": next_stage,
            "pipeline_complete": all_done,
            "missing_inputs": missing_inputs,
            "suggestion": (
                f"Pipeline complete for {patient_id}. Review outputs in Stage 7."
                if all_done
                else f"Next: run Stage {next_stage} ({DEPENDENCY_GRAPH[next_stage - 1]['name']})"
                if next_stage
                else f"No stages completed yet. Start with Stage 1."
            ),
            "version": BLOOMONE_VERSION,
        }

    @mcp.tool()
    async def get_dependency_graph() -> dict:
        """
        Return the full stage dependency graph as structured data.

        Use this to understand: which stages exist, what each requires,
        what each produces, and which stages can be skipped. This enables
        deterministic pipeline orchestration without reading documentation.
        """
        return {
            "pipeline_name": "BloomOne Neoantigen Vaccine Pipeline",
            "version": BLOOMONE_VERSION,
            "total_stages": 7,
            "stages": DEPENDENCY_GRAPH,
            "quick_paths": {
                "maf_with_hla": {
                    "description": "Pre-called MAF + known HLA alleles (fastest)",
                    "stages": [3, 4, 5, 6, 7],
                    "estimated_minutes": 15,
                    "tool": "run_full_pipeline",
                },
                "cbio_with_hla": {
                    "description": "Fetch from cBioPortal + provide HLA alleles",
                    "stages": [1, 3, 4, 5, 6, 7],
                    "estimated_minutes": 20,
                },
                "bam_full_pipeline": {
                    "description": "Raw BAM files — full pipeline including mutation calling",
                    "stages": [1, 2, 3, 4, 5, 6, 7],
                    "estimated_minutes": 75,
                },
            },
        }
