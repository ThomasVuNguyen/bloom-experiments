"""
MCP Resources & Prompts — expose documentation and guided workflows.

Resources let agents read pipeline docs, input format specs, and safety info.
Prompts provide step-by-step guided workflows for common use cases.
"""

from __future__ import annotations

from bloomone.config import BLOOMONE_VERSION


# ── Pipeline Documentation ──────────────────────────────────────────────────

PIPELINE_DOCS = f"""\
# BloomOne Neoantigen Vaccine Pipeline v{BLOOMONE_VERSION}

BloomOne is a 7-stage pipeline that turns tumor DNA into a personalized
mRNA neoantigen vaccine construct.

## Pipeline Overview

| Stage | Name | Input | Output | Est. Time |
|-------|------|-------|--------|-----------|
| 1 | Data Ingestion | BAM/FASTQ/MAF | PatientData | 1-5 min |
| 2 | Mutation Calling | Tumor+Normal BAM | VCF/MAF | 30-60 min |
| 3 | Peptide Generation | MAF | 8-11mer peptides | 1-3 min |
| 4 | HLA Binding | Peptides + HLA | Binding predictions | 5-15 min |
| 5 | Safety Filter | Strong binders | Safe candidates | 1-2 min |
| 6 | Ranking | Safe candidates | Top 20 ranked | <1 min |
| 7 | mRNA Design | Top 20 | mRNA constructs | <1 min |

## When to Use Each Data Source

- **cBioPortal** (`stage1_fetch_cbio`): Best for TCGA samples when you
  want pre-called mutations (MAF format). Skips Stage 2 entirely.
  Example: `study_id="skcm_tcga_pan_can_atlas_2018"`.

- **TCGA/GDC** (`stage1_fetch_tcga`): Use when you need raw BAM files
  for custom mutation calling, or specific data types beyond MAF.

- **Local files** (`stage1_ingest_local`): Use when the user provides
  their own sequencing data or MAF files.

## HLA Alleles — Critical Decision Point

HLA alleles are REQUIRED for Stage 4 (binding prediction). Three paths:

1. **User provides them**: Pass directly as `hla_alleles` parameter
2. **OptiType typing**: Run `stage1_run_optitype` with a BAM/FASTQ file
3. **Neither available**: Pipeline CANNOT proceed past Stage 3.
   cBioPortal data does NOT include HLA alleles.

⚠️ If you fetch from cBioPortal and have no HLA alleles, you MUST ask
the user to provide them before running Stage 4.

## Common Failure Modes

1. **Empty peptide list**: MAF has mutations but no missense variants,
   or protein sequences couldn't be fetched from UniProt/Ensembl.
2. **No strong binders**: All peptides have IC50 > 500nM. May indicate
   unfavorable HLA alleles or too few mutations.
3. **Stage 2 timeout**: Strelka2 on large WES can take 2+ hours.
   Use `start_stage` for async execution.
4. **API rate limits**: Ensembl VEP is limited to 15 req/sec.
   The pipeline handles this automatically.

## Minimum Viable Inputs

- **Fastest path**: MAF file + HLA alleles → `run_full_pipeline`
- **From public data**: cBioPortal study_id + sample_id + HLA alleles
- **Full pipeline**: Tumor BAM + Normal BAM (HLA auto-detected)
"""

MAF_FORMAT_DOCS = """\
# MAF File Format

MAF (Mutation Annotation Format) is a tab-separated file containing
somatic mutation calls. BloomOne requires these columns:

## Required Columns

| Column | Description | Example |
|--------|-------------|---------|
| Hugo_Symbol | Gene name | BRAF |
| Variant_Classification | Mutation type | Missense_Mutation |
| HGVSp_Short | Protein change | p.V600E |
| Tumor_Sample_Barcode | Patient/sample ID | TCGA-BF-A3DL-01 |

## Optional (Recommended) Columns

| Column | Description | Used In |
|--------|-------------|---------|
| Chromosome | e.g. chr7 | VEP annotation |
| Start_Position | Genomic position | VEP annotation |
| Reference_Allele | Reference base | VEP annotation |
| Tumor_Seq_Allele2 | Variant base | VEP annotation |
| Transcript_ID | Ensembl transcript | Protein lookup |
| t_depth | Total read depth | VAF calculation |
| t_alt_count | Variant read count | VAF calculation |

## Notes

- Only `Missense_Mutation` variants are used for peptide generation
- Protein changes must be parseable: `p.V600E`, `p.Val600Glu`, or `V600E`
- VAF is calculated as `t_alt_count / t_depth` when both are present
- Tab-separated, lines starting with `#` are ignored
"""

HLA_FORMAT_DOCS = """\
# HLA Allele Format

BloomOne uses standard WHO HLA nomenclature for MHC Class I alleles.

## Required Format

```
HLA-A*02:01
HLA-B*07:02
HLA-C*04:01
```

## Format Rules

- Prefix: `HLA-` (required)
- Gene: `A`, `B`, or `C` (Class I only in v1)
- Separator: `*`
- Allele group: 2 digits
- Specific protein: 2-3 digits
- Full pattern: `HLA-[ABC]*XX:XX` or `HLA-[ABC]*XX:XXX`

## Common Examples

| Allele | Frequency | Common Cancers |
|--------|-----------|----------------|
| HLA-A*02:01 | ~28% Caucasian | Melanoma, Lung |
| HLA-A*01:01 | ~16% Caucasian | Various |
| HLA-B*07:02 | ~12% Caucasian | Various |
| HLA-A*24:02 | ~20% Asian | Various |

## How to Provide

Pass as comma-separated string:
```
"HLA-A*02:01,HLA-A*01:01,HLA-B*07:02,HLA-B*08:01,HLA-C*07:01,HLA-C*07:02"
```

Typically 6 alleles (2 per gene: A, B, C) but fewer is acceptable.

## When HLA is Unknown

1. If you have BAM/FASTQ data: use `stage1_run_optitype`
2. If you only have MAF data: ask the user for their HLA type
3. For research/demo: HLA-A*02:01 is the most common and a good default
"""

SAFETY_DOCS = f"""\
# BloomOne Safety & Compliance

## Research Use Only

⚠️ ALL BloomOne outputs are strictly for RESEARCH USE ONLY.

BloomOne is a computational research tool. Its outputs:
- Are NOT validated for clinical use
- Have NOT been reviewed by regulatory authorities (FDA, EMA)
- Should NOT be used to make treatment decisions
- Are NOT a substitute for clinical genomic analysis

## Data Handling

- **No PHI storage**: BloomOne does not persistently store Protected
  Health Information. Patient data on the Modal volume is ephemeral.
- **De-identification**: Users should de-identify data before upload.
  Use anonymized patient IDs (not real names/MRNs).
- **Data retention**: Modal volume data persists until explicitly deleted.
  Use responsible data practices.

## Scientific Limitations

- Binding prediction (IC50) is not the same as immunogenicity
- Self-similarity filter catches exact/near-exact matches only
- Codon optimization is computational — wet lab validation is essential
- Population-level HLA frequencies don't predict individual response

## Tool Versions (v{BLOOMONE_VERSION})

- MHCflurry 2.0 (Class I presentation predictor)
- Strelka2 (somatic variant caller)
- Ensembl VEP (variant effect prediction)
- UniProt human reviewed proteome (UP000005640)
- Human-optimized codon table
- ViennaRNA (mRNA structure prediction, optional)
"""


# ── Tool Registration ───────────────────────────────────────────────────────


def register_resources_and_prompts(mcp):
    """Register MCP resources and prompts on the server."""

    # ── Resources ──

    @mcp.resource("bloomone://docs/pipeline")
    async def pipeline_docs() -> str:
        """Complete BloomOne pipeline documentation — stages, data sources, decision points."""
        return PIPELINE_DOCS

    @mcp.resource("bloomone://docs/input-formats/maf")
    async def maf_format_docs() -> str:
        """MAF file format specification — required and optional columns."""
        return MAF_FORMAT_DOCS

    @mcp.resource("bloomone://docs/hla-format")
    async def hla_format_docs() -> str:
        """HLA allele naming conventions and format requirements."""
        return HLA_FORMAT_DOCS

    @mcp.resource("bloomone://docs/safety")
    async def safety_docs() -> str:
        """Research-use-only disclaimers, data handling, and scientific limitations."""
        return SAFETY_DOCS

    # ── Prompts ──

    @mcp.prompt()
    async def neoantigen_from_tcga(case_id: str, hla_alleles: str = "") -> str:
        """
        Guided workflow: fetch TCGA/cBioPortal data and run the full
        neoantigen vaccine pipeline. Walks through each decision point.
        """
        return f"""\
# Neoantigen Vaccine Pipeline — TCGA Case {case_id}

Follow these steps to generate a personalized neoantigen mRNA vaccine
design for TCGA case {case_id}.

## Step 1: Validate Environment
Call `check_environment` to verify server health.

## Step 2: Fetch Data
Call `stage1_fetch_cbio` with:
- study_id: determine the appropriate TCGA study (e.g. "skcm_tcga_pan_can_atlas_2018" for melanoma)
- sample_id: "{case_id}"

Check the response for `skip_stage2` (should be true for cBioPortal data)
and `requires_optitype` (will be true — cBioPortal doesn't include HLA).

## Step 3: HLA Alleles
{"You provided HLA alleles: " + hla_alleles + ". Validate them with validate_inputs." if hla_alleles else "⚠️ No HLA alleles provided. You MUST ask the user for their HLA type. cBioPortal data does not include HLA information. Common default for research: HLA-A*02:01,HLA-B*07:02,HLA-C*07:01"}

## Step 4: Run Pipeline
Once you have the MAF path (from Step 2) and HLA alleles (from Step 3),
call `run_full_pipeline` with:
- maf_path: (from stage1 response)
- hla_alleles: (comma-separated)
- patient_id: "{case_id}"

## Step 5: Review Results
- Use `inspect_artifact` to examine intermediate files
- Use `pipeline_status` to verify all stages completed
- Present the summary from Stage 7 to the user

## Important Notes
- All results are for RESEARCH USE ONLY
- Binding prediction ≠ immunogenicity
- Wet lab validation is required before any clinical application
"""

    @mcp.prompt()
    async def neoantigen_from_maf(maf_path: str, hla_alleles: str) -> str:
        """
        Quick path: run the pipeline from an existing MAF file with known
        HLA alleles. Skips data fetching and mutation calling.
        """
        return f"""\
# Quick Neoantigen Pipeline — MAF + HLA

## Step 1: Validate
Call `validate_inputs` with:
- maf_path: "{maf_path}"
- hla_alleles: "{hla_alleles}"

## Step 2: Run
If validation passes, call `run_full_pipeline` with:
- maf_path: "{maf_path}"
- hla_alleles: "{hla_alleles}"

## Step 3: Review
The pipeline runs Stages 3-7 and returns a complete result with:
- Peptide counts and gene list
- Binding predictions and strong binder counts
- Safety-filtered candidates
- Ranked top 20 candidates
- mRNA construct sequences ready for synthesis

Present the `summary` from each stage to the user.
All results are for RESEARCH USE ONLY.
"""
