"""
Stage 3: Peptide Generation (MCP-3)

Generates 8-11mer mutant peptides from somatic mutations using a sliding
window approach. Annotates variant consequences via the Ensembl VEP public
REST API.

Input:  MAF/VCF file with somatic mutations
Output: Candidate peptide table with mutation metadata
"""

from __future__ import annotations

import os
import time
from typing import Optional

import pandas as pd
import requests

from bloomone.config import (
    KMER_LENGTHS,
    PATHS,
    TPM_THRESHOLD,
    VEP_API_URL,
    VEP_BATCH_SIZE,
)
from bloomone.models import PeptideCandidate, PeptideResult
from bloomone.utils import (
    apply_mutation_and_generate_peptides,
    fetch_protein_sequence,
    parse_hgvsp_short,
)


def filter_missense_mutations(maf: pd.DataFrame) -> pd.DataFrame:
    """Filter MAF to only missense mutations with parseable HGVSp_Short."""
    missense = maf[
        (maf["Variant_Classification"] == "Missense_Mutation")
        & (maf["HGVSp_Short"].notna())
    ].copy()
    return missense


def filter_by_expression(
    maf: pd.DataFrame,
    tpm_path: Optional[str],
    threshold: float = TPM_THRESHOLD,
) -> tuple[pd.DataFrame, bool]:
    """
    Filter mutations by gene expression level (TPM).

    If tpm_path is provided, removes mutations in genes with TPM < threshold.
    Returns (filtered_maf, expression_validated).
    """
    if tpm_path is None or not os.path.exists(tpm_path):
        return maf, False

    try:
        tpm_df = pd.read_csv(tpm_path, sep="\t")
        # Expected columns: gene (or Hugo_Symbol) and TPM
        gene_col = "gene" if "gene" in tpm_df.columns else "Hugo_Symbol"
        tpm_col = "TPM" if "TPM" in tpm_df.columns else "tpm"

        if gene_col not in tpm_df.columns or tpm_col not in tpm_df.columns:
            print("  ⚠️ TPM file missing expected columns, skipping expression filter")
            return maf, False

        expressed_genes = set(
            tpm_df[tpm_df[tpm_col] >= threshold][gene_col].values
        )

        before = len(maf)
        filtered = maf[maf["Hugo_Symbol"].isin(expressed_genes)].copy()
        after = len(filtered)
        print(
            f"  Expression filter: {before} → {after} mutations "
            f"({before - after} removed, TPM < {threshold})"
        )
        return filtered, True

    except Exception as e:
        print(f"  ⚠️ Expression filter failed: {e}")
        return maf, False


def annotate_vep(
    mutations: list[dict],
    batch_size: int = VEP_BATCH_SIZE,
) -> dict[str, str]:
    """
    Annotate mutations with Ensembl VEP public REST API.

    Sends HGVS notation strings in batches of up to 200 (API limit).
    Returns dict mapping hgvs_string → most_severe_consequence.
    """
    results: dict[str, str] = {}

    # Build HGVS strings from mutations
    hgvs_strings = []
    for mut in mutations:
        chrom = mut.get("Chromosome")
        start = mut.get("Start_Position")
        ref = mut.get("Reference_Allele")
        alt = mut.get("Tumor_Seq_Allele2")

        if all([chrom, start, ref, alt]):
            hgvs = f"{chrom}:g.{start}{ref}>{alt}"
            hgvs_strings.append(hgvs)

    if not hgvs_strings:
        return results

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    for i in range(0, len(hgvs_strings), batch_size):
        batch = hgvs_strings[i : i + batch_size]
        payload = {"hgvs_notations": batch}

        try:
            resp = requests.post(
                VEP_API_URL,
                json=payload,
                headers=headers,
                timeout=60,
            )
            if resp.ok:
                for entry in resp.json():
                    hgvs_id = entry.get("id", "")
                    consequence = entry.get("most_severe_consequence", "unknown")
                    results[hgvs_id] = consequence
            else:
                print(f"  VEP API returned {resp.status_code} for batch {i}")

        except Exception as e:
            print(f"  VEP API error for batch {i}: {e}")

        # Rate limit: 15 requests/sec
        time.sleep(0.1)

    return results


def generate_peptides(
    maf_path: str,
    patient_id: Optional[str] = None,
    tpm_path: Optional[str] = None,
    kmer_lengths: Optional[list[int]] = None,
) -> PeptideResult:
    """
    Full Stage 3 pipeline: MAF → missense filter → peptide generation.

    Args:
        maf_path: Path to MAF file (tab-separated)
        patient_id: Specific patient to process (None = first patient)
        tpm_path: Optional RNA-seq TPM file for expression filtering
        kmer_lengths: Peptide lengths to generate (default [8,9,10,11])

    Returns:
        PeptideResult with all candidate peptides
    """
    if kmer_lengths is None:
        kmer_lengths = KMER_LENGTHS

    # Load MAF
    print(f"Loading MAF from {maf_path}...")
    maf = pd.read_csv(maf_path, sep="\t", comment="#", low_memory=False)

    # Select patient
    if patient_id is None:
        patient_id = str(maf["Tumor_Sample_Barcode"].unique()[0])
        print(f"Auto-selected patient: {patient_id}")
    else:
        maf = maf[maf["Tumor_Sample_Barcode"] == patient_id].copy()

    patient_maf = maf[maf["Tumor_Sample_Barcode"] == patient_id].copy()
    print(f"Total mutations for {patient_id}: {len(patient_maf)}")

    # Filter missense
    missense = filter_missense_mutations(patient_maf)
    print(f"Missense mutations: {len(missense)}")

    # Optional expression filter
    expression_validated = False
    if tpm_path:
        missense, expression_validated = filter_by_expression(
            missense, tpm_path
        )

    # Compute VAF if available
    if "t_alt_count" in missense.columns and "t_depth" in missense.columns:
        missense["tumor_vaf"] = missense["t_alt_count"] / missense["t_depth"]
    elif "tumor_vaf" not in missense.columns:
        missense["tumor_vaf"] = None

    # VEP annotation (best-effort, non-blocking)
    vep_annotations = {}
    try:
        mutation_dicts = missense.to_dict("records")
        vep_annotations = annotate_vep(mutation_dicts)
        print(f"VEP annotated {len(vep_annotations)} variants")
    except Exception as e:
        print(f"  VEP annotation skipped: {e}")

    # Generate peptides
    print(f"\nGenerating {kmer_lengths}-mer peptides...")
    candidates: list[PeptideCandidate] = []
    skipped = 0

    for _, row in missense.iterrows():
        gene = row["Hugo_Symbol"]
        hgvsp = row.get("HGVSp_Short", "")
        transcript_id = row.get("Transcript_ID")

        parsed = parse_hgvsp_short(hgvsp)
        if parsed is None:
            skipped += 1
            continue

        pos, ref_aa, alt_aa = parsed

        # Fetch protein sequence
        protein_seq = fetch_protein_sequence(
            gene, transcript_id=transcript_id
        )
        if protein_seq is None:
            skipped += 1
            continue

        # Generate peptides spanning the mutation
        peptides = apply_mutation_and_generate_peptides(
            protein_seq, pos, ref_aa, alt_aa, kmer_lengths
        )

        # Extract VAF
        tumor_vaf = row.get("tumor_vaf")
        if pd.isna(tumor_vaf):
            tumor_vaf = None
        else:
            tumor_vaf = float(tumor_vaf)

        for pep_dict in peptides:
            candidates.append(
                PeptideCandidate(
                    patient_id=patient_id,
                    gene=gene,
                    transcript_id=str(transcript_id) if transcript_id else None,
                    hgvsp_short=hgvsp,
                    protein_position=pos,
                    ref_aa=ref_aa,
                    alt_aa=alt_aa,
                    tumor_vaf=tumor_vaf,
                    t_depth=int(row["t_depth"]) if "t_depth" in row and pd.notna(row.get("t_depth")) else None,
                    t_alt_count=int(row["t_alt_count"]) if "t_alt_count" in row and pd.notna(row.get("t_alt_count")) else None,
                    vep_consequence=vep_annotations.get(
                        f"{row.get('Chromosome', '')}:g.{row.get('Start_Position', '')}"
                        f"{row.get('Reference_Allele', '')}>{row.get('Tumor_Seq_Allele2', '')}",
                    ),
                    **pep_dict,
                )
            )

    # Save to volume
    output_path = os.path.join(PATHS["stage3"], f"{patient_id}_peptides.tsv")
    os.makedirs(PATHS["stage3"], exist_ok=True)

    if candidates:
        df_out = pd.DataFrame([c.model_dump() for c in candidates])
        df_out.to_csv(output_path, sep="\t", index=False)

    unique_peptides = len(set(c.peptide for c in candidates))
    print(f"\nDone. Generated {len(candidates)} candidates ({unique_peptides} unique peptides)")
    print(f"Skipped {skipped} unparseable/unfetchable mutations")

    return PeptideResult(
        patient_id=patient_id,
        candidates=candidates,
        candidates_path=output_path,
        total_candidates=len(candidates),
        unique_peptides=unique_peptides,
        skipped_mutations=skipped,
    )
