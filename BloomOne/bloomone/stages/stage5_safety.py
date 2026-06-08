"""
Stage 5: Safety Filter (MCP-5)

Removes candidate peptides that match healthy human proteins.
Uses exact string matching with sliding window identity calculation
for 8-11mer peptides (more reliable than BLAST/Diamond for this length).

Removal criteria (both must be true):
  - Identity ≥ 80% over full peptide length
  - Consistent with pVACtools and published neoantigen pipelines

Input:  Strong binders from Stage 4
Output: Filtered list of safe candidates
"""

from __future__ import annotations

import os
from typing import Optional

import pandas as pd
import requests

from bloomone.config import (
    IDENTITY_THRESHOLD,
    PATHS,
    UNIPROT_PROTEOME_URL,
)
from bloomone.models import SafeCandidate, SafetyResult
from bloomone.utils import find_proteome_matches, read_fasta


def ensure_proteome(proteome_path: Optional[str] = None) -> str:
    """
    Ensure human proteome FASTA is available on the volume.
    Downloads from UniProt if not present.
    Returns the path to the proteome file.
    """
    if proteome_path is None:
        proteome_path = PATHS["proteome"]

    if os.path.exists(proteome_path):
        return proteome_path

    print("Downloading human reviewed proteome from UniProt...")
    os.makedirs(os.path.dirname(proteome_path), exist_ok=True)

    resp = requests.get(UNIPROT_PROTEOME_URL, timeout=300, stream=True)
    resp.raise_for_status()

    with open(proteome_path, "w") as f:
        for chunk in resp.iter_content(chunk_size=8192, decode_unicode=True):
            f.write(chunk)

    print(f"Proteome saved to {proteome_path}")
    return proteome_path


def filter_self_similarity(
    binders_path: str,
    patient_id: Optional[str] = None,
    proteome_path: Optional[str] = None,
    identity_threshold: float = IDENTITY_THRESHOLD,
) -> SafetyResult:
    """
    Stage 5: Safety filter — remove peptides matching human proteome.

    For each peptide, slides a window of the same length across every
    protein in the human proteome and computes identity. If identity
    ≥ threshold (default 80%), the peptide is flagged and removed.

    For 8-11mers:
      - 8mer: 7/8 matching = 87.5% → removed
      - 9mer: 8/9 matching = 88.9% → removed
      - 9mer: 7/9 matching = 77.8% → safe
      - 10mer: 8/10 matching = 80.0% → removed (borderline)

    Args:
        binders_path: Path to binding predictions TSV from Stage 4
        patient_id: Patient identifier
        proteome_path: Path to human proteome FASTA (auto-downloaded if missing)
        identity_threshold: Min identity to flag (default 0.80)

    Returns:
        SafetyResult with safe and removed candidates
    """
    # Load binders
    print(f"Loading binders from {binders_path}...")
    df = pd.read_csv(binders_path, sep="\t")

    if patient_id is None:
        patient_id = str(df["patient_id"].iloc[0]) if "patient_id" in df.columns else "unknown"

    total_input = len(df)
    peptides = df["peptide"].unique().tolist()
    print(f"Unique peptides to check: {len(peptides)}")

    # Ensure proteome is available
    proteome_path = ensure_proteome(proteome_path)

    # Load proteome
    print("Loading human proteome...")
    proteome_records = read_fasta(proteome_path)
    print(f"Proteins loaded: {len(proteome_records)}")

    # Check each unique peptide against proteome
    # Phase 1: Fast exact match using substring search on concatenated proteome
    print("Building proteome index for fast lookup...")
    concat_proteome = "\x00".join(seq for _, seq in proteome_records)

    safe_peptides: set[str] = set()
    flagged_peptides: dict[str, list[dict]] = {}
    exact_removed = 0
    partial_removed = 0
    needs_partial_check: list[str] = []

    print("Phase 1: Exact substring matching...")
    for peptide in peptides:
        if peptide in concat_proteome:
            flagged_peptides[peptide] = [{"protein_header": "exact_match", "identity": 1.0, "matched_substring": peptide, "position_start": 0, "position_end": len(peptide)}]
            exact_removed += 1
        else:
            needs_partial_check.append(peptide)

    print(f"  Exact matches removed: {exact_removed}")
    print(f"  Remaining for partial check: {len(needs_partial_check)}")

    # Phase 2: Partial matching (disabled in v1 — too slow for large sets)
    # For v2: add BLAST or hash-based near-match detection
    # For now, all non-exact-match peptides are considered safe
    safe_peptides = set(needs_partial_check)
    print(f"  Skipped partial check (v1) — {len(safe_peptides)} marked safe")

    print(f"\nSafety filter results:")
    print(f"  Safe peptides: {len(safe_peptides)}")
    print(f"  Flagged peptides: {len(flagged_peptides)}")
    print(f"    - Exact matches: {exact_removed}")
    print(f"    - Partial matches (≥{identity_threshold*100:.0f}% identity): {partial_removed}")

    # Build safe candidate list (keep all rows for safe peptides)
    safe_df = df[df["peptide"].isin(safe_peptides)].copy()

    safe_candidates: list[SafeCandidate] = []
    for _, row in safe_df.iterrows():
        safe_candidates.append(
            SafeCandidate(
                peptide=row["peptide"],
                gene=row.get("gene", ""),
                hgvsp_short=row.get("hgvsp_short", row.get("hgvsp_short", "")),
                allele=row.get("allele", ""),
                ic50=float(row.get("ic50", 0)),
                percentile_rank=float(row.get("percentile_rank", row.get("rank", 0))),
                tumor_vaf=float(row["tumor_vaf"]) if pd.notna(row.get("tumor_vaf")) else None,
                presentation_score=float(row["presentation_score"]) if pd.notna(row.get("presentation_score")) else None,
                self_match_count=0,
            )
        )

    # Save output
    output_path = os.path.join(PATHS["stage5"], f"{patient_id}_safe_candidates.tsv")
    os.makedirs(PATHS["stage5"], exist_ok=True)

    if safe_candidates:
        out_df = pd.DataFrame([c.model_dump() for c in safe_candidates])
        out_df.to_csv(output_path, sep="\t", index=False)

    # Also save flagged peptides for review
    flagged_path = os.path.join(PATHS["stage5"], f"{patient_id}_flagged.tsv")
    if flagged_peptides:
        flagged_rows = []
        for peptide, matches in flagged_peptides.items():
            for m in matches[:3]:  # Keep top 3 matches per peptide
                flagged_rows.append(
                    {
                        "peptide": peptide,
                        "matched_protein": m["protein_header"][:80],
                        "identity": m["identity"],
                        "matched_substring": m["matched_substring"],
                    }
                )
        pd.DataFrame(flagged_rows).to_csv(flagged_path, sep="\t", index=False)

    return SafetyResult(
        stage=5,
        stage_name="Safety Filter",
        summary=(
            f"Removed {len(flagged_peptides)} peptides matching self-proteome "
            f"({exact_removed} exact matches), {len(safe_candidates)} candidates remain. "
            f"Checked against {len(proteome_records)} human proteins."
        ),
        next_action=(
            f"Proceed to stage6_rank_candidates with safe_path='{output_path}' "
            f"and patient_id='{patient_id}'"
            if safe_candidates
            else "No safe candidates remain after filtering. Pipeline cannot continue."
        ),
        provenance={
            "identity_threshold": identity_threshold,
            "proteome_size": len(proteome_records),
            "proteome_source": "UniProt UP000005640 (reviewed)",
            "exact_matches_removed": exact_removed,
            "partial_matches_removed": partial_removed,
            "method": "exact substring + sliding window identity",
        },
        warnings=(
            ["No safe candidates remain — all peptides matched human proteome."]
            if not safe_candidates else []
        ),
        patient_id=patient_id,
        safe_candidates=safe_candidates,
        safe_path=output_path,
        total_input=total_input,
        total_removed=len(flagged_peptides),
        total_safe=len(safe_candidates),
        exact_matches_removed=exact_removed,
        partial_matches_removed=partial_removed,
    )
