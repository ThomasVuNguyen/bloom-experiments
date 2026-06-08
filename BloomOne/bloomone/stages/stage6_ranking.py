"""
Stage 6: Candidate Ranking (MCP-6)

Scores and ranks safe neoantigen candidates using a weighted composite
score combining binding affinity, variant allele frequency, and
optionally tumor expression.

Scoring model:
  - IC50 %rank:  50% weight (or 60% without expression data)
  - VAF:         30% weight (or 40% without expression data)
  - TPM:         20% weight (optional)

Top 20 candidates are passed to Stage 7 (mRNA design).

Input:  Safe candidates from Stage 5 + VCF + optional TPM
Output: Ranked candidate table
"""

from __future__ import annotations

import os
from typing import Optional

import pandas as pd

from bloomone.config import (
    PATHS,
    RANKING_WEIGHTS,
    RANKING_WEIGHTS_NO_EXPRESSION,
    TOP_N_CANDIDATES,
)
from bloomone.models import RankedCandidate, RankingResult


def normalize_series(s: pd.Series, invert: bool = False) -> pd.Series:
    """
    Min-max normalize a series to [0, 1].
    If invert=True, lower raw values get higher normalized scores (closer to 1).
    This is used for IC50 %rank where lower is better.
    """
    if s.max() == s.min():
        return pd.Series(0.5, index=s.index)

    normalized = (s - s.min()) / (s.max() - s.min())

    if invert:
        normalized = 1 - normalized

    return normalized


def rank_candidates(
    safe_path: str,
    vcf_path: Optional[str] = None,
    tpm_path: Optional[str] = None,
    patient_id: Optional[str] = None,
    top_n: int = TOP_N_CANDIDATES,
) -> RankingResult:
    """
    Stage 6: Multi-score candidate ranking.

    Computes a weighted composite score for each candidate and selects
    the top N. Score is designed so that lower = better candidate.

    The composite score combines:
      1. IC50 percentile rank (lower = stronger binder = better)
      2. VAF (higher = more clonal = better)
      3. TPM expression (higher = more expressed = better, optional)

    All features are normalized to [0, 1] before weighting.

    Args:
        safe_path: Path to safe candidates TSV from Stage 5
        vcf_path: Optional path to VCF for VAF data (if not in candidates)
        tpm_path: Optional path to RNA-seq TPM file
        patient_id: Patient identifier
        top_n: Number of top candidates to select

    Returns:
        RankingResult with ranked candidates
    """
    # Load safe candidates
    print(f"Loading safe candidates from {safe_path}...")
    df = pd.read_csv(safe_path, sep="\t")
    total_input = len(df)

    if patient_id is None:
        patient_id = str(df["patient_id"].iloc[0]) if "patient_id" in df.columns else "unknown"

    print(f"Total candidates to rank: {total_input}")

    # Determine if expression data is available
    expression_available = False
    tpm_data = None

    if tpm_path and os.path.exists(tpm_path):
        try:
            tpm_df = pd.read_csv(tpm_path, sep="\t")
            gene_col = "gene" if "gene" in tpm_df.columns else "Hugo_Symbol"
            tpm_col = "TPM" if "TPM" in tpm_df.columns else "tpm"

            if gene_col in tpm_df.columns and tpm_col in tpm_df.columns:
                tpm_data = dict(zip(tpm_df[gene_col], tpm_df[tpm_col]))
                expression_available = True
                print(f"Expression data loaded: {len(tpm_data)} genes")
        except Exception as e:
            print(f"  ⚠️ TPM loading failed: {e}")

    # Select weights
    if expression_available:
        weights = RANKING_WEIGHTS
    else:
        weights = RANKING_WEIGHTS_NO_EXPRESSION
        print("  No expression data — using degraded weights (IC50 60%, VAF 40%)")

    print(f"  Weights: {weights}")

    # Ensure required columns exist
    rank_col = "percentile_rank" if "percentile_rank" in df.columns else "rank"

    # ── Component 1: IC50 %rank (lower = better → invert) ───────────────
    if rank_col in df.columns:
        df["score_ic50"] = normalize_series(df[rank_col].astype(float), invert=False)
        # Lower rank → lower score → better (no inversion needed — rank is already "lower = better")
    else:
        df["score_ic50"] = 0.5  # Default middle score if missing

    # ── Component 2: VAF (higher = better → invert so lower score = better) ──
    if "tumor_vaf" in df.columns and df["tumor_vaf"].notna().any():
        vaf = df["tumor_vaf"].fillna(0).astype(float)
        df["score_vaf"] = normalize_series(vaf, invert=True)
    else:
        df["score_vaf"] = 0.5

    # ── Component 3: TPM (higher = better → invert) ─────────────────────
    if expression_available and tpm_data:
        df["tpm"] = df["gene"].map(tpm_data).fillna(0).astype(float)
        df["score_tpm"] = normalize_series(df["tpm"], invert=True)
    else:
        df["tpm"] = None
        df["score_tpm"] = 0.5

    # ── Compute composite score ──────────────────────────────────────────
    df["composite_score"] = (
        df["score_ic50"] * weights["ic50_rank"]
        + df["score_vaf"] * weights["vaf"]
    )

    if expression_available and "tpm" in weights:
        df["composite_score"] += df["score_tpm"] * weights["tpm"]

    # Sort by composite score (lower = better)
    df = df.sort_values("composite_score", ascending=True).reset_index(drop=True)

    # Select top N
    top = df.head(top_n).copy()
    top["rank"] = range(1, len(top) + 1)

    print(f"\nTop {len(top)} candidates selected:")
    for _, row in top.head(5).iterrows():
        print(
            f"  #{int(row['rank'])} {row.get('gene', '?')} {row.get('hgvsp_short', '?')} "
            f"→ {row['peptide']} | score={row['composite_score']:.3f} | "
            f"rank={row.get(rank_col, '?')} | VAF={row.get('tumor_vaf', 'N/A')}"
        )

    # Build output models
    ranked_candidates: list[RankedCandidate] = []
    for _, row in top.iterrows():
        ranked_candidates.append(
            RankedCandidate(
                rank=int(row["rank"]),
                peptide=row["peptide"],
                gene=row.get("gene", ""),
                hgvsp_short=row.get("hgvsp_short", ""),
                allele=row.get("allele", ""),
                ic50=float(row.get("ic50", 0)),
                percentile_rank=float(row.get(rank_col, 0)),
                tumor_vaf=float(row["tumor_vaf"]) if pd.notna(row.get("tumor_vaf")) else None,
                tpm=float(row["tpm"]) if pd.notna(row.get("tpm")) else None,
                composite_score=float(row["composite_score"]),
                expression_validated=expression_available,
            )
        )

    # Save output
    output_path = os.path.join(PATHS["stage6"], f"{patient_id}_ranked.tsv")
    os.makedirs(PATHS["stage6"], exist_ok=True)

    if ranked_candidates:
        out_df = pd.DataFrame([c.model_dump() for c in ranked_candidates])
        out_df.to_csv(output_path, sep="\t", index=False)

    return RankingResult(
        patient_id=patient_id,
        ranked_candidates=ranked_candidates,
        ranked_path=output_path,
        total_input=total_input,
        total_ranked=len(ranked_candidates),
        expression_available=expression_available,
        weights_used=weights,
    )
