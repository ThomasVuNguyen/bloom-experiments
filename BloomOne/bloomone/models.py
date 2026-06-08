"""
Pydantic models for type-safe stage input/output across the pipeline.

Every stage result inherits from StageResponse, ensuring all tool outputs
include: summary, next_action, provenance, warnings, and research_use_only.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ── Agent-Friendly Base ─────────────────────────────────────────────────────


class StageResponse(BaseModel):
    """Base model for all stage outputs — ensures agent-friendly metadata."""
    stage: int = Field(description="Stage number (1-7)")
    stage_name: str = Field(description="Human-readable stage name")
    summary: str = Field(
        default="",
        description="Human-readable summary of what happened in this stage",
    )
    next_action: str = Field(
        default="",
        description="What the agent should do next (tool name + key args)",
    )
    research_use_only: bool = Field(
        default=True,
        description="Always true — results are for research use only, not clinical advice",
    )
    provenance: dict = Field(
        default_factory=dict,
        description="Scientific provenance: tool versions, thresholds, counts, filters",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Warnings or issues the agent should surface to the user",
    )


class DataSource(str, Enum):
    """Where the input data comes from."""
    LOCAL = "local"
    TCGA = "tcga"
    CBIO = "cbio"


class PatientData(StageResponse):
    """Stage 1 output — ingested patient data."""
    patient_id: str
    tumor_path: str = Field(description="Path to tumor BAM/FASTQ on volume")
    normal_path: Optional[str] = Field(
        None, description="Path to normal BAM/FASTQ (None if MAF input)"
    )
    hla_alleles: list[str] = Field(
        description="HLA-I alleles, e.g. ['HLA-A*02:01', 'HLA-B*07:02']"
    )
    hla_source: str = Field(
        default="provided",
        description="'provided' or 'optitype' — how alleles were determined",
    )
    maf_path: Optional[str] = Field(
        None, description="Pre-called MAF path (skip Stage 2 if present)"
    )
    tpm_path: Optional[str] = Field(
        None, description="RNA-seq TPM file path (optional)"
    )
    data_source: DataSource = DataSource.LOCAL
    expression_validated: bool = Field(
        default=False,
        description="True if RNA-seq TPM was available and used",
    )
    # ── Agent branching flags ──
    requires_optitype: bool = Field(
        default=False,
        description="True if HLA alleles are missing and OptiType is needed",
    )
    skip_stage2: bool = Field(
        default=False,
        description="True if MAF is pre-called — skip Stage 2 entirely",
    )


class SomaticMutation(BaseModel):
    """A single somatic mutation from Stage 2."""
    gene: str
    transcript_id: Optional[str] = None
    hgvsp_short: str = Field(description="e.g. p.V600E")
    chromosome: Optional[str] = None
    position: Optional[int] = None
    ref_allele: Optional[str] = None
    alt_allele: Optional[str] = None
    variant_classification: str = "Missense_Mutation"
    tumor_vaf: Optional[float] = Field(
        None, description="Variant allele frequency from VCF"
    )
    t_depth: Optional[int] = None
    t_alt_count: Optional[int] = None


class MutationResult(StageResponse):
    """Stage 2 output — somatic mutations."""
    patient_id: str
    mutations: list[SomaticMutation]
    mutations_path: str = Field(description="Path to VCF/MAF on volume")
    skipped_stage2: bool = Field(
        default=False, description="True if MAF was pre-called"
    )
    total_mutations: int = 0
    missense_count: int = 0


class PeptideCandidate(BaseModel):
    """A single candidate peptide from Stage 3."""
    patient_id: str
    gene: str
    transcript_id: Optional[str] = None
    hgvsp_short: str
    protein_position: int
    ref_aa: str
    alt_aa: str
    peptide: str
    peptide_length: int
    peptide_start_in_protein: int
    mutation_offset_in_peptide: int
    tumor_vaf: Optional[float] = None
    t_depth: Optional[int] = None
    t_alt_count: Optional[int] = None
    vep_consequence: Optional[str] = None


class PeptideResult(StageResponse):
    """Stage 3 output — candidate peptides."""
    patient_id: str
    candidates: list[PeptideCandidate]
    candidates_path: str
    total_candidates: int = 0
    unique_peptides: int = 0
    genes_affected: int = 0
    skipped_mutations: int = 0


class BindingPrediction(BaseModel):
    """A single HLA binding prediction from Stage 4."""
    peptide: str
    allele: str
    ic50: float = Field(description="Binding affinity in nM (lower = stronger)")
    percentile_rank: float = Field(description="Percentile rank (lower = stronger)")
    presentation_score: Optional[float] = Field(
        None, description="MHCflurry presentation score"
    )
    processing_score: Optional[float] = Field(
        None, description="MHCflurry antigen processing score"
    )
    prediction_method: str = "mhcflurry"
    # Carried forward from Stage 3
    gene: Optional[str] = None
    hgvsp_short: Optional[str] = None
    tumor_vaf: Optional[float] = None


class BindingResult(StageResponse):
    """Stage 4 output — binding predictions."""
    patient_id: str
    predictions: list[BindingPrediction]
    predictions_path: str
    total_scored: int = 0
    strong_binders: int = 0
    hla_alleles_used: list[str] = []
    method: str = "mhcflurry"


class SafeCandidate(BaseModel):
    """A candidate that passed the safety filter (Stage 5)."""
    peptide: str
    gene: str
    hgvsp_short: str
    allele: str
    ic50: float
    percentile_rank: float
    tumor_vaf: Optional[float] = None
    presentation_score: Optional[float] = None
    self_match_count: int = Field(
        0, description="Number of near-matches found in human proteome"
    )


class SafetyResult(StageResponse):
    """Stage 5 output — safety-filtered candidates."""
    patient_id: str
    safe_candidates: list[SafeCandidate]
    safe_path: str
    total_input: int = 0
    total_removed: int = 0
    total_safe: int = 0
    exact_matches_removed: int = 0
    partial_matches_removed: int = 0


class RankedCandidate(BaseModel):
    """A ranked candidate from Stage 6."""
    rank: int
    peptide: str
    gene: str
    hgvsp_short: str
    allele: str
    ic50: float
    percentile_rank: float
    tumor_vaf: Optional[float] = None
    tpm: Optional[float] = None
    composite_score: float = Field(
        description="Weighted composite score (lower = better)"
    )
    expression_validated: bool = False


class RankingResult(StageResponse):
    """Stage 6 output — ranked candidates."""
    patient_id: str
    ranked_candidates: list[RankedCandidate]
    ranked_path: str
    total_input: int = 0
    total_ranked: int = 0
    expression_available: bool = False
    weights_used: dict[str, float] = {}


class MRNAConstruct(BaseModel):
    """A single mRNA construct from Stage 7."""
    rank: int
    peptide: str
    gene: str
    hgvsp_short: str
    ic50: float
    percentile_rank: float
    cds_dna: str
    cds_mrna: str
    full_mrna: str
    cds_length: int
    full_length: int
    gc_content: float
    has_premature_stop: bool = False
    mfe: Optional[float] = Field(
        None, description="Minimum free energy from ViennaRNA (kcal/mol)"
    )


class MRNAResult(StageResponse):
    """Stage 7 output — mRNA constructs."""
    patient_id: str
    constructs: list[MRNAConstruct]
    constructs_path: str
    total_designed: int = 0
    polytope_mrna: Optional[str] = Field(
        None, description="Single concatenated polytope mRNA construct"
    )
    polytope_length: Optional[int] = None


class PipelineResult(BaseModel):
    """Complete pipeline output."""
    patient_id: str
    data_source: DataSource
    hla_alleles: list[str]
    total_mutations: int
    total_peptides: int
    strong_binders: int
    safe_candidates: int
    top_n_ranked: int
    mrna_constructs: int
    expression_validated: bool
    stages_completed: list[int] = []
    stages_skipped: list[int] = []
    output_paths: dict[str, str] = {}
    summary: str = ""
    research_use_only: bool = True
    warnings: list[str] = []
