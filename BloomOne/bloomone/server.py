"""
BloomOne MCP Server — FastMCP server exposing all 7 pipeline stages as tools,
plus validation, status, inspection, and async job management tools.

Each tool maps to one pipeline stage, with clear inputs/outputs that
an AI agent can orchestrate sequentially. All tool responses include:
- summary: human-readable description of what happened
- next_action: what tool to call next with which arguments
- provenance: scientific parameters, thresholds, tool versions
- warnings: issues the agent should surface to the user
- research_use_only: always True — results are not for clinical use
"""

from __future__ import annotations

from fastmcp import FastMCP

from bloomone.config import BLOOMONE_VERSION
from bloomone.errors import wrap_stage_error
from bloomone.stages.stage1_ingest import (
    fetch_cbio_data,
    fetch_tcga_data,
    ingest_local_files,
    run_optitype,
)
from bloomone.stages.stage2_mutations import call_mutations
from bloomone.stages.stage3_peptides import generate_peptides
from bloomone.stages.stage4_binding import predict_binding
from bloomone.stages.stage5_safety import filter_self_similarity
from bloomone.stages.stage6_ranking import rank_candidates
from bloomone.stages.stage7_mrna import design_mrna


# ── Volume Sync Helpers ─────────────────────────────────────────────────────
# Modal Volume requires explicit commit/reload for cross-request persistence.
# These are no-ops when running locally (volume won't be available).

def _sync_before():
    """Reload volume to see latest data from other requests."""
    try:
        from bloomone.config import volume
        volume.reload()
    except Exception:
        pass  # Running locally without Modal


def _sync_after():
    """Commit volume changes so other requests can see them."""
    try:
        from bloomone.config import volume
        volume.commit()
    except Exception:
        pass  # Running locally without Modal

# ── MCP Server Definition ───────────────────────────────────────────────────

mcp = FastMCP(
    "BloomOne — Personalized Neoantigen Vaccine Pipeline",
    instructions=(
        f"BloomOne v{BLOOMONE_VERSION} is a 7-stage pipeline that turns tumor DNA "
        "into a personalized mRNA neoantigen vaccine construct.\n\n"
        "## Pipeline Stages\n"
        "1→2→3→4→5→6→7 (sequential). Stage 2 is skipped with MAF input.\n\n"
        "## Quick Start\n"
        "- Use `validate_inputs` FIRST to check inputs before running.\n"
        "- Use `pipeline_status` to see what has already been run.\n"
        "- Use `get_dependency_graph` to understand stage requirements.\n"
        "- Use `inspect_artifact` to examine intermediate files.\n\n"
        "## Data Source Selection\n"
        "- **cBioPortal** (`stage1_fetch_cbio`): Pre-called MAF, skips Stage 2. "
        "Best for TCGA samples with known study IDs.\n"
        "- **TCGA/GDC** (`stage1_fetch_tcga`): Raw data download. May need Stage 2.\n"
        "- **Local** (`stage1_ingest_local`): User-provided BAM/FASTQ/MAF files.\n\n"
        "## HLA Alleles — CRITICAL\n"
        "HLA alleles are REQUIRED for Stage 4. cBioPortal does NOT provide them.\n"
        "If missing: ask the user, or run `stage1_run_optitype` with BAM data.\n"
        "Format: HLA-A*02:01,HLA-B*07:02,HLA-C*04:01\n\n"
        "## Every Response Contains\n"
        "- `summary`: human-readable narration\n"
        "- `next_action`: exactly what tool to call next\n"
        "- `provenance`: scientific parameters used\n"
        "- `warnings`: issues to surface to the user\n"
        "- `research_use_only`: always True\n\n"
        "## Safety\n"
        "ALL outputs are for RESEARCH USE ONLY. Not validated for clinical use."
    ),
)


# ── Register Additional Tools ───────────────────────────────────────────────

# Phase 2: Validation tools
from bloomone.tools.validate import register_validation_tools
register_validation_tools(mcp)

# Phase 3: Status & inspection tools
from bloomone.tools.status import register_status_tools
register_status_tools(mcp)

from bloomone.tools.inspect import register_inspect_tools
register_inspect_tools(mcp)

# Phase 4: Async job tools
from bloomone.tools.jobs import register_job_tools
register_job_tools(mcp)

# Phase 6: Resources & prompts
from bloomone.resources import register_resources_and_prompts
register_resources_and_prompts(mcp)


# ── Stage 1: Data Ingestion ─────────────────────────────────────────────────


@mcp.tool()
async def stage1_ingest_local(
    tumor_path: str,
    patient_id: str = "patient_001",
    normal_path: str = "",
    hla_alleles: str = "",
    rna_seq_path: str = "",
) -> dict:
    """
    Stage 1: Ingest local patient files (BAM, FASTQ, or MAF).

    Upload tumor/normal sequencing files and optionally provide HLA alleles
    and RNA-seq expression data. If HLA alleles are not provided, run
    stage1_run_optitype to predict them.

    Check the response for:
    - requires_optitype: True if HLA alleles need to be determined
    - skip_stage2: True if MAF input was provided (skip mutation calling)
    - next_action: exactly what to do next

    Args:
        tumor_path: Path to tumor BAM/FASTQ or pre-called MAF file
        patient_id: Unique identifier for this patient run
        normal_path: Path to normal BAM/FASTQ (empty if MAF input)
        hla_alleles: Comma-separated HLA alleles (e.g. "HLA-A*02:01,HLA-B*07:02")
        rna_seq_path: Path to RNA-seq TPM file (optional, for expression filtering)
    """
    try:
        alleles_list = [a.strip() for a in hla_alleles.split(",") if a.strip()] if hla_alleles else None
        _sync_before()
        result = ingest_local_files(
            tumor_path=tumor_path,
            normal_path=normal_path if normal_path else None,
            hla_alleles=alleles_list,
            rna_seq_path=rna_seq_path if rna_seq_path else None,
            patient_id=patient_id,
        )
        _sync_after()
        return result.model_dump()
    except Exception as e:
        return wrap_stage_error(e, stage=1)


@mcp.tool()
async def stage1_fetch_tcga(
    case_id: str,
    data_type: str = "Masked Somatic Mutation",
) -> dict:
    """
    Stage 1: Fetch patient data from TCGA via GDC API.

    Downloads mutation data (MAF) or raw sequencing (BAM) from TCGA.
    MAF downloads skip Stage 2. BAM downloads require Stage 2.

    Note: TCGA does NOT provide HLA alleles. You will need to either
    ask the user for HLA alleles or run OptiType on BAM data.

    Args:
        case_id: TCGA case ID (e.g. "TCGA-BF-A3DL-01")
        data_type: GDC data type to fetch (default: "Masked Somatic Mutation")
    """
    try:
        _sync_before()
        result = fetch_tcga_data(case_id=case_id, data_type=data_type)
        _sync_after()
        return result.model_dump()
    except Exception as e:
        return wrap_stage_error(e, stage=1)


@mcp.tool()
async def stage1_fetch_cbio(
    study_id: str,
    sample_id: str,
) -> dict:
    """
    Stage 1: Fetch pre-called mutations from cBioPortal.

    Downloads mutation data in MAF format. Always skips Stage 2.

    ⚠️ IMPORTANT: cBioPortal does NOT provide HLA alleles. The response
    will include requires_optitype=True and a warning. You MUST obtain
    HLA alleles from the user before proceeding to Stage 4.

    Args:
        study_id: cBioPortal study ID (e.g. "skcm_tcga_pan_can_atlas_2018")
        sample_id: Sample barcode (e.g. "TCGA-BF-A3DL-01")
    """
    try:
        _sync_before()
        result = fetch_cbio_data(study_id=study_id, sample_id=sample_id)
        _sync_after()
        return result.model_dump()
    except Exception as e:
        return wrap_stage_error(e, stage=1)


@mcp.tool()
async def stage1_run_optitype(
    bam_path: str,
    patient_id: str,
) -> dict:
    """
    Stage 1 (sub-tool): Run OptiType HLA-I genotyping.

    Predicts HLA-A, HLA-B, HLA-C alleles from BAM/FASTQ input.
    Only needed if HLA alleles were not provided in stage1_ingest_local.

    This is a long-running operation (~15 min). Consider using start_stage
    for async execution on large files.

    Args:
        bam_path: Path to BAM or FASTQ file
        patient_id: Patient identifier
    """
    try:
        _sync_before()
        alleles = run_optitype(bam_path=bam_path, patient_id=patient_id)
        _sync_after()
        return {
            "patient_id": patient_id,
            "hla_alleles": alleles,
            "source": "optitype",
            "summary": f"OptiType predicted {len(alleles)} HLA-I alleles: {', '.join(alleles)}",
            "next_action": "HLA alleles are now available. Proceed to the next stage.",
            "research_use_only": True,
        }
    except Exception as e:
        return wrap_stage_error(e, stage=1)


# ── Stage 2: Mutation Calling ────────────────────────────────────────────────


@mcp.tool()
async def stage2_call_mutations(
    patient_data_json: str,
) -> dict:
    """
    Stage 2: Somatic variant calling with Strelka2.

    Takes the JSON output from Stage 1 and runs Strelka2 to identify
    somatic mutations. If the input contains pre-called MAF data
    (e.g. from cBioPortal), this stage is automatically skipped.

    ⚠️ This is a LONG-RUNNING operation (~45 min for WES data).
    For async execution, use start_stage(stage=2, ...) instead.

    Args:
        patient_data_json: JSON string of PatientData from Stage 1
    """
    try:
        import json as _json
        from bloomone.models import PatientData

        _sync_before()
        patient_data = PatientData(**_json.loads(patient_data_json))
        result = call_mutations(patient_data)
        _sync_after()
        return result.model_dump()
    except Exception as e:
        return wrap_stage_error(e, stage=2)


# ── Stage 3: Peptide Generation ──────────────────────────────────────────────


@mcp.tool()
async def stage3_generate_peptides(
    maf_path: str,
    patient_id: str = "",
    tpm_path: str = "",
) -> dict:
    """
    Stage 3: Generate 8-11mer mutant peptides from somatic mutations.

    Parses missense mutations, fetches protein sequences, and generates
    all possible peptide fragments containing each mutation using a
    sliding window approach. Optionally annotates via Ensembl VEP.

    Response includes summary with peptide count, gene count, and
    skipped mutation count for transparency.

    Args:
        maf_path: Path to MAF file from Stage 2 (or Stage 1 if skipped)
        patient_id: Patient ID (auto-detected from MAF if empty)
        tpm_path: Optional RNA-seq TPM file for expression filtering
    """
    try:
        _sync_before()
        result = generate_peptides(
            maf_path=maf_path,
            patient_id=patient_id if patient_id else None,
            tpm_path=tpm_path if tpm_path else None,
        )
        _sync_after()
        return result.model_dump()
    except Exception as e:
        return wrap_stage_error(e, stage=3)


# ── Stage 4: HLA Binding Prediction ─────────────────────────────────────────


@mcp.tool()
async def stage4_predict_binding(
    peptides_path: str,
    hla_alleles: str,
    patient_id: str = "",
) -> dict:
    """
    Stage 4: Predict HLA-I binding affinity for candidate peptides.

    Uses MHCflurry 2.0 (GPU, primary) or IEDB NetMHCpan 4.1 (fallback).
    Filters to strong binders: IC50 < 500nM or percentile rank < 0.5%.
    MHC Class I only.

    ⚠️ This can take 5-15 minutes on GPU. For async execution, use
    start_stage(stage=4, ...) instead.

    Args:
        peptides_path: Path to peptide candidates TSV from Stage 3
        hla_alleles: Comma-separated HLA-I alleles (e.g. "HLA-A*02:01,HLA-B*07:02")
        patient_id: Patient identifier
    """
    try:
        alleles_list = [a.strip() for a in hla_alleles.split(",") if a.strip()]
        pid = patient_id if patient_id else None

        _sync_before()

        # Try to dispatch to MHCflurry GPU container (preferred)
        try:
            import modal
            mhcflurry_fn = modal.Function.from_name("bloomone", "run_mhcflurry_remote")
            print("Dispatching to MHCflurry GPU container...")
            result_dict = mhcflurry_fn.remote(
                peptides_path=peptides_path,
                hla_alleles=alleles_list,
                patient_id=pid or "unknown",
            )
            _sync_after()
            return result_dict
        except Exception as e:
            print(f"MHCflurry GPU dispatch failed: {e}")
            print("Falling back to local prediction (IEDB API)...")

        # Fallback: run locally
        result = predict_binding(
            peptides_path=peptides_path,
            hla_alleles=alleles_list,
            patient_id=pid,
        )
        _sync_after()
        return result.model_dump()
    except Exception as e:
        return wrap_stage_error(e, stage=4)


# ── Stage 5: Safety Filter ──────────────────────────────────────────────────


@mcp.tool()
async def stage5_safety_filter(
    binders_path: str,
    patient_id: str = "",
) -> dict:
    """
    Stage 5: Remove peptides matching healthy human proteins.

    Checks each peptide against the entire human proteome (~20,000 proteins)
    using sliding window identity calculation. Removes candidates with
    ≥80% identity over full peptide length. Downloads proteome from
    UniProt if not cached.

    Args:
        binders_path: Path to binding predictions TSV from Stage 4
        patient_id: Patient identifier
    """
    try:
        _sync_before()
        result = filter_self_similarity(
            binders_path=binders_path,
            patient_id=patient_id if patient_id else None,
        )
        _sync_after()
        return result.model_dump()
    except Exception as e:
        return wrap_stage_error(e, stage=5)


# ── Stage 6: Candidate Ranking ───────────────────────────────────────────────


@mcp.tool()
async def stage6_rank_candidates(
    safe_path: str,
    patient_id: str = "",
    tpm_path: str = "",
    top_n: int = 20,
) -> dict:
    """
    Stage 6: Score and rank safe neoantigen candidates.

    Composite score: IC50 %rank (50%) + VAF (30%) + TPM (20%, optional).
    Without RNA-seq: IC50 (60%) + VAF (40%), flagged "expression not validated".
    Selects top N candidates for mRNA design.

    Args:
        safe_path: Path to safe candidates TSV from Stage 5
        patient_id: Patient identifier
        tpm_path: Optional RNA-seq TPM file for expression weighting
        top_n: Number of top candidates to select (default 20)
    """
    try:
        _sync_before()
        result = rank_candidates(
            safe_path=safe_path,
            tpm_path=tpm_path if tpm_path else None,
            patient_id=patient_id if patient_id else None,
            top_n=top_n,
        )
        _sync_after()
        return result.model_dump()
    except Exception as e:
        return wrap_stage_error(e, stage=6)


# ── Stage 7: mRNA Construct Design ──────────────────────────────────────────


@mcp.tool()
async def stage7_design_mrna(
    ranked_path: str,
    patient_id: str = "",
    top_n: int = 20,
) -> dict:
    """
    Stage 7: Design mRNA vaccine constructs.

    Builds individual mRNA constructs for each top candidate, plus
    a concatenated polytope construct. Includes:
    - Codon optimization (human-preferred codons)
    - Signal peptide (tPA) for MHC-I presentation
    - AAY linker for proteasomal cleavage
    - 5'UTR (beta-globin) and 3'UTR (alpha-globin)
    - 120nt poly-A tail
    - ViennaRNA MFE prediction (if available)

    Output is ready for wet lab synthesis review.
    ⚠️ All outputs are for RESEARCH USE ONLY.

    Args:
        ranked_path: Path to ranked candidates TSV from Stage 6
        patient_id: Patient identifier
        top_n: Number of constructs to design (default 20)
    """
    try:
        _sync_before()
        result = design_mrna(
            ranked_path=ranked_path,
            patient_id=patient_id if patient_id else None,
            top_n=top_n,
        )
        _sync_after()
        return result.model_dump()
    except Exception as e:
        return wrap_stage_error(e, stage=7)


# ── Pipeline Orchestrator ────────────────────────────────────────────────────


@mcp.tool()
async def run_full_pipeline(
    maf_path: str,
    hla_alleles: str,
    patient_id: str = "patient_001",
    tpm_path: str = "",
    top_n: int = 20,
) -> dict:
    """
    Run the complete BloomOne pipeline from MAF to mRNA construct.

    This is a convenience tool that runs Stages 3-7 sequentially.
    Use this when you have a pre-called MAF file and known HLA alleles
    (skips Stages 1-2).

    For raw BAM input or data fetching, use the individual stage tools.

    ⚠️ Use validate_inputs FIRST to check your inputs.
    ⚠️ All outputs are for RESEARCH USE ONLY.

    Args:
        maf_path: Path to MAF file with somatic mutations
        hla_alleles: Comma-separated HLA-I alleles
        patient_id: Patient identifier
        tpm_path: Optional RNA-seq TPM file
        top_n: Number of top candidates for mRNA design
    """
    try:
        from bloomone.models import PipelineResult, DataSource, BindingResult

        alleles_list = [a.strip() for a in hla_alleles.split(",") if a.strip()]
        tpm = tpm_path if tpm_path else None
        stages_completed = []
        all_warnings = []

        _sync_before()

        # Stage 3: Peptide Generation
        print("=" * 60)
        print("STAGE 3: Peptide Generation")
        print("=" * 60)
        peptide_result = generate_peptides(
            maf_path=maf_path, patient_id=patient_id, tpm_path=tpm
        )
        stages_completed.append(3)
        all_warnings.extend(peptide_result.warnings)

        if peptide_result.total_candidates == 0:
            _sync_after()
            return {
                "patient_id": patient_id,
                "summary": (
                    "Pipeline stopped at Stage 3: no missense-derived peptides generated. "
                    "This may mean the MAF has no missense mutations for the selected "
                    "patient, or protein sequences could not be fetched."
                ),
                "stages_completed": stages_completed,
                "warnings": all_warnings,
                "research_use_only": True,
            }

        # Commit so GPU container can see the peptides file
        _sync_after()

        # Stage 4: HLA Binding Prediction (GPU dispatch preferred)
        print("\n" + "=" * 60)
        print("STAGE 4: HLA Binding Prediction")
        print("=" * 60)

        binding_result = None
        try:
            import modal as _modal
            mhcflurry_fn = _modal.Function.from_name("bloomone", "run_mhcflurry_remote")
            print("Dispatching to MHCflurry GPU container...")
            binding_dict = mhcflurry_fn.remote(
                peptides_path=peptide_result.candidates_path,
                hla_alleles=alleles_list,
                patient_id=patient_id,
            )
            binding_result = BindingResult(**binding_dict)
        except Exception as e:
            print(f"GPU dispatch failed: {e}")
            print("Falling back to local prediction...")
            binding_result = predict_binding(
                peptides_path=peptide_result.candidates_path,
                hla_alleles=alleles_list,
                patient_id=patient_id,
            )
        stages_completed.append(4)
        all_warnings.extend(binding_result.warnings)

        # Reload volume to see GPU-written binding results
        _sync_before()

        # Stage 5: Safety Filter
        print("\n" + "=" * 60)
        print("STAGE 5: Safety Filter")
        print("=" * 60)
        safety_result = filter_self_similarity(
            binders_path=binding_result.predictions_path,
            patient_id=patient_id,
        )
        stages_completed.append(5)
        all_warnings.extend(safety_result.warnings)

        # Stage 6: Candidate Ranking
        print("\n" + "=" * 60)
        print("STAGE 6: Candidate Ranking")
        print("=" * 60)
        ranking_result = rank_candidates(
            safe_path=safety_result.safe_path,
            tpm_path=tpm,
            patient_id=patient_id,
            top_n=top_n,
        )
        stages_completed.append(6)
        all_warnings.extend(ranking_result.warnings)

        # Stage 7: mRNA Design
        print("\n" + "=" * 60)
        print("STAGE 7: mRNA Construct Design")
        print("=" * 60)
        mrna_result = design_mrna(
            ranked_path=ranking_result.ranked_path,
            patient_id=patient_id,
            top_n=top_n,
        )
        stages_completed.append(7)
        all_warnings.extend(mrna_result.warnings)

        # Final commit
        _sync_after()

        # Build summary
        summary = (
            f"Pipeline complete for {patient_id}. "
            f"{peptide_result.total_candidates} peptides generated from "
            f"{peptide_result.genes_affected} genes → "
            f"{binding_result.strong_binders} strong binders → "
            f"{safety_result.total_safe} safe candidates → "
            f"top {ranking_result.total_ranked} ranked → "
            f"{mrna_result.total_designed} mRNA constructs designed."
        )

        # Build final result
        pipeline_result = PipelineResult(
            patient_id=patient_id,
            data_source=DataSource.LOCAL,
            hla_alleles=alleles_list,
            total_mutations=peptide_result.total_candidates,
            total_peptides=peptide_result.unique_peptides,
            strong_binders=binding_result.strong_binders,
            safe_candidates=safety_result.total_safe,
            top_n_ranked=ranking_result.total_ranked,
            mrna_constructs=mrna_result.total_designed,
            expression_validated=tpm is not None,
            stages_completed=stages_completed,
            stages_skipped=[1, 2],
            output_paths={
                "peptides": peptide_result.candidates_path,
                "binding": binding_result.predictions_path,
                "safety": safety_result.safe_path,
                "ranked": ranking_result.ranked_path,
                "mrna": mrna_result.constructs_path,
            },
            summary=summary,
            warnings=all_warnings,
        )

        print("\n" + "=" * 60)
        print("PIPELINE COMPLETE")
        print("=" * 60)
        print(summary)

        return pipeline_result.model_dump()
    except Exception as e:
        return wrap_stage_error(e, stage=0)
