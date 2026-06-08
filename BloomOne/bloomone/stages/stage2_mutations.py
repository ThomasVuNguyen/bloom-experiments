"""
Stage 2: Mutation Calling (MCP-2)

Runs Strelka2 somatic variant calling on tumor/normal BAM pairs.
If input is already MAF (from cBioPortal), this stage is skipped entirely.

Input:  Tumor BAM + Normal BAM + hg38 reference genome
Output: VCF file with somatic mutations

Note: This stage requires the Strelka2 Modal container image and
96 vCPUs for maximum parallelism.
"""

from __future__ import annotations

import os
import subprocess
from typing import Optional

import pandas as pd

from bloomone.config import PATHS
from bloomone.models import MutationResult, PatientData, SomaticMutation


def call_mutations(
    patient_data: PatientData,
) -> MutationResult:
    """
    Stage 2: Somatic variant calling with Strelka2.

    If patient_data.maf_path is set (pre-called mutations), this stage
    is skipped and the existing MAF is returned directly.

    Args:
        patient_data: PatientData from Stage 1

    Returns:
        MutationResult with somatic mutations
    """
    patient_id = patient_data.patient_id

    # Skip if MAF already provided
    if patient_data.maf_path:
        print(f"MAF already provided — skipping Stage 2 (mutation calling)")
        return _load_existing_maf(patient_data)

    # Validate inputs
    if not patient_data.normal_path:
        raise ValueError(
            "Normal BAM is required for mutation calling. "
            "Provide a MAF file to skip this stage."
        )

    tumor_bam = patient_data.tumor_path
    normal_bam = patient_data.normal_path
    reference = PATHS["hg38"]

    if not os.path.exists(reference):
        raise FileNotFoundError(
            f"Reference genome not found at {reference}. "
            "Upload hg38.fa to the Modal volume under /data/reference/"
        )

    # Create output directory
    output_dir = os.path.join(PATHS["stage2"], patient_id)
    os.makedirs(output_dir, exist_ok=True)

    # ── Step 1: Configure Strelka2 workflow ──────────────────────────────
    config_cmd = [
        "configureStrelkaSomaticWorkflow.py",
        "--normalBam", normal_bam,
        "--tumorBam", tumor_bam,
        "--referenceFasta", reference,
        "--runDir", output_dir,
        "--callMemMb", "4096",
    ]

    print(f"Configuring Strelka2 workflow...")
    result = subprocess.run(
        config_cmd,
        capture_output=True,
        text=True,
        timeout=300,
    )

    if result.returncode != 0:
        raise RuntimeError(f"Strelka2 configuration failed: {result.stderr}")

    # ── Step 2: Run the workflow ─────────────────────────────────────────
    run_script = os.path.join(output_dir, "runWorkflow.py")

    run_cmd = [
        "python2", run_script,
        "-m", "local",
        "-j", "96",  # 96 vCPUs
    ]

    print(f"Running Strelka2 with 96 vCPUs...")
    result = subprocess.run(
        run_cmd,
        capture_output=True,
        text=True,
        timeout=7200,  # 2 hour timeout
    )

    if result.returncode != 0:
        raise RuntimeError(f"Strelka2 execution failed: {result.stderr}")

    # ── Step 3: Parse VCF output ─────────────────────────────────────────
    vcf_path = os.path.join(
        output_dir, "results", "variants", "somatic.snvs.vcf.gz"
    )

    if not os.path.exists(vcf_path):
        raise FileNotFoundError(f"Strelka2 VCF not found at {vcf_path}")

    print(f"Strelka2 complete. VCF: {vcf_path}")

    # Convert VCF to mutations list
    mutations = _parse_strelka_vcf(vcf_path, patient_id)

    return MutationResult(
        patient_id=patient_id,
        mutations=mutations,
        mutations_path=vcf_path,
        skipped_stage2=False,
        total_mutations=len(mutations),
        missense_count=sum(
            1 for m in mutations if m.variant_classification == "Missense_Mutation"
        ),
    )


def _load_existing_maf(patient_data: PatientData) -> MutationResult:
    """Load pre-called mutations from an existing MAF file."""
    maf_path = patient_data.maf_path
    patient_id = patient_data.patient_id

    print(f"Loading existing MAF from {maf_path}...")
    maf = pd.read_csv(maf_path, sep="\t", comment="#", low_memory=False)

    # Filter to this patient if multiple patients in MAF
    if "Tumor_Sample_Barcode" in maf.columns:
        patient_maf = maf[
            maf["Tumor_Sample_Barcode"].str.contains(patient_id, na=False)
        ]
        if len(patient_maf) == 0:
            patient_maf = maf  # Use all if patient not found
    else:
        patient_maf = maf

    mutations: list[SomaticMutation] = []

    for _, row in patient_maf.iterrows():
        hgvsp = row.get("HGVSp_Short", "")
        if pd.isna(hgvsp) or not isinstance(hgvsp, str):
            continue

        # Compute VAF if possible
        tumor_vaf = None
        t_depth = None
        t_alt_count = None

        if "t_alt_count" in row and "t_depth" in row:
            try:
                t_alt_count = int(row["t_alt_count"]) if pd.notna(row["t_alt_count"]) else None
                t_depth = int(row["t_depth"]) if pd.notna(row["t_depth"]) else None
                if t_alt_count is not None and t_depth is not None and t_depth > 0:
                    tumor_vaf = t_alt_count / t_depth
            except (ValueError, TypeError):
                pass

        mutations.append(
            SomaticMutation(
                gene=str(row.get("Hugo_Symbol", "")),
                transcript_id=str(row.get("Transcript_ID", "")) if pd.notna(row.get("Transcript_ID")) else None,
                hgvsp_short=hgvsp,
                chromosome=str(row.get("Chromosome", "")) if pd.notna(row.get("Chromosome")) else None,
                position=int(row.get("Start_Position")) if pd.notna(row.get("Start_Position")) else None,
                ref_allele=str(row.get("Reference_Allele", "")) if pd.notna(row.get("Reference_Allele")) else None,
                alt_allele=str(row.get("Tumor_Seq_Allele2", "")) if pd.notna(row.get("Tumor_Seq_Allele2")) else None,
                variant_classification=str(row.get("Variant_Classification", "")),
                tumor_vaf=tumor_vaf,
                t_depth=t_depth,
                t_alt_count=t_alt_count,
            )
        )

    missense_count = sum(
        1 for m in mutations if m.variant_classification == "Missense_Mutation"
    )

    print(f"Loaded {len(mutations)} mutations ({missense_count} missense)")

    return MutationResult(
        patient_id=patient_id,
        mutations=mutations,
        mutations_path=maf_path,
        skipped_stage2=True,
        total_mutations=len(mutations),
        missense_count=missense_count,
    )


def _parse_strelka_vcf(
    vcf_path: str,
    patient_id: str,
) -> list[SomaticMutation]:
    """
    Parse Strelka2 VCF output into SomaticMutation objects.
    """
    import gzip

    mutations = []

    opener = gzip.open if vcf_path.endswith(".gz") else open
    with opener(vcf_path, "rt") as f:
        for line in f:
            if line.startswith("#"):
                continue

            fields = line.strip().split("\t")
            if len(fields) < 10:
                continue

            chrom, pos, _, ref, alt, _, filt, info, fmt, *samples = fields

            # Only keep PASS variants
            if filt != "PASS":
                continue

            # Parse tumor sample data (last column in Strelka2 output)
            tumor_data = samples[-1] if samples else ""
            fmt_fields = fmt.split(":")
            tumor_values = tumor_data.split(":")

            # Extract allele depths from Strelka2 format
            tumor_vaf = None
            t_depth = None
            t_alt_count = None

            try:
                # Strelka2 uses refCounts and altCounts in tier1
                data_dict = dict(zip(fmt_fields, tumor_values))
                ref_counts = int(data_dict.get("DP", 0))
                alt_counts_key = f"{alt}U"  # e.g., AU, CU, GU, TU
                if alt_counts_key in data_dict:
                    alt_tier1 = int(data_dict[alt_counts_key].split(",")[0])
                    t_alt_count = alt_tier1
                    t_depth = ref_counts
                    if t_depth > 0:
                        tumor_vaf = t_alt_count / t_depth
            except (ValueError, KeyError, IndexError):
                pass

            mutations.append(
                SomaticMutation(
                    gene="",  # VCF doesn't have gene annotation
                    hgvsp_short="",
                    chromosome=chrom,
                    position=int(pos),
                    ref_allele=ref,
                    alt_allele=alt,
                    variant_classification="SNV",
                    tumor_vaf=tumor_vaf,
                    t_depth=t_depth,
                    t_alt_count=t_alt_count,
                )
            )

    return mutations
