"""
Stage 4: HLA Binding Prediction (MCP-4)

Predicts how strongly each candidate peptide binds to the patient's
HLA-I alleles using MHCflurry 2.0 (primary) or IEDB NetMHCpan 4.1
(fallback).

Scope: MHC Class I only. MHC-II is out of scope for v1.

Input:  Candidate peptides from Stage 3 + patient HLA alleles
Output: Ranked binding predictions with IC50 and %rank
"""

from __future__ import annotations

import os
import time
from typing import Optional

import pandas as pd
import requests

from bloomone.config import (
    IC50_THRESHOLD,
    IEDB_API_URL,
    IEDB_BATCH_SIZE,
    PATHS,
    RANK_THRESHOLD,
)
from bloomone.models import BindingPrediction, BindingResult


def predict_mhcflurry(
    peptides: list[str],
    alleles: list[str],
) -> list[dict]:
    """
    Predict HLA-I binding using MHCflurry 2.0 Class1PresentationPredictor.

    Returns list of dicts with peptide, allele, ic50, percentile_rank,
    presentation_score, processing_score.
    """
    try:
        from mhcflurry import Class1PresentationPredictor

        predictor = Class1PresentationPredictor.load()

        results = []
        # MHCflurry expects alleles in format HLA-A0201 (no asterisk/colon)
        normalized_alleles = [
            a.replace("*", "").replace(":", "") for a in alleles
        ]

        # Process one allele at a time using predict() with single-element
        # genotype list (which is valid — ≤6 elements)
        for allele_orig, allele_norm in zip(alleles, normalized_alleles):
            try:
                # Batch peptides in chunks to avoid memory issues
                BATCH = 5000
                for start in range(0, len(peptides), BATCH):
                    batch = peptides[start:start + BATCH]
                    predictions = predictor.predict(
                        peptides=batch,
                        alleles=[allele_norm],  # Single-allele genotype
                        verbose=0,
                    )

                    for _, row in predictions.iterrows():
                        results.append(
                            {
                                "peptide": row["peptide"],
                                "allele": allele_orig,
                                "ic50": float(row.get("mhcflurry_affinity", 0)),
                                "percentile_rank": float(
                                    row.get("mhcflurry_affinity_percentile", 0)
                                ),
                                "presentation_score": float(
                                    row.get("mhcflurry_presentation_score", 0)
                                ),
                                "processing_score": float(
                                    row.get("mhcflurry_processing_score", 0)
                                ),
                                "prediction_method": "mhcflurry",
                            }
                        )
                    print(f"    {allele_orig}: batch {start}-{start+len(batch)} done")
            except Exception as e:
                print(f"  MHCflurry failed for {allele_orig}: {e}")
                continue

        return results

    except ImportError:
        print("  MHCflurry not available — falling back to IEDB API")
        return []


def predict_iedb(
    peptides: list[str],
    alleles: list[str],
    batch_size: int = IEDB_BATCH_SIZE,
) -> list[dict]:
    """
    Predict HLA-I binding using IEDB NetMHCpan 4.1 API (fallback).

    Rate-limited: batches of 20 peptides with 1s sleep between.
    """
    results = []

    for allele in alleles:
        print(f"  Querying IEDB for {allele}...")

        for i in range(0, len(peptides), batch_size):
            batch = peptides[i : i + batch_size]

            # Group by peptide length (IEDB requires uniform length per request)
            by_length: dict[int, list[str]] = {}
            for pep in batch:
                by_length.setdefault(len(pep), []).append(pep)

            for length, peps in by_length.items():
                payload = {
                    "method": "netmhcpan_ba",
                    "sequence_text": "\n".join(peps),
                    "allele": allele,
                    "length": str(length),
                }

                try:
                    resp = requests.post(IEDB_API_URL, data=payload, timeout=120)
                    resp.raise_for_status()

                    for line in resp.text.strip().split("\n"):
                        if line.startswith("allele") or not line.strip():
                            continue
                        parts = line.split("\t")
                        if len(parts) >= 10:
                            results.append(
                                {
                                    "peptide": parts[5],
                                    "allele": allele,
                                    "ic50": float(parts[8])
                                    if parts[8] != "NA"
                                    else None,
                                    "percentile_rank": float(parts[9])
                                    if parts[9] != "NA"
                                    else None,
                                    "presentation_score": None,
                                    "processing_score": None,
                                    "prediction_method": "netmhcpan_iedb",
                                }
                            )

                except Exception as e:
                    print(f"    IEDB API error: {e}")

                time.sleep(1.0)  # Rate limit

    return results


def predict_binding(
    peptides_path: str,
    hla_alleles: list[str],
    patient_id: Optional[str] = None,
    use_mhcflurry: bool = True,
) -> BindingResult:
    """
    Stage 4: HLA-I binding prediction.

    Tries MHCflurry 2.0 first (GPU-accelerated presentation predictor).
    Falls back to IEDB NetMHCpan 4.1 API if MHCflurry is unavailable or
    fails for specific alleles.

    Filters to strong binders: IC50 < 500nM OR %rank < 0.5

    Args:
        peptides_path: Path to peptide candidates TSV from Stage 3
        hla_alleles: Patient HLA-I alleles (e.g. ['HLA-A*02:01', 'HLA-B*07:02'])
        patient_id: Patient identifier
        use_mhcflurry: Whether to try MHCflurry first (default True)

    Returns:
        BindingResult with strong binder predictions
    """
    # Load peptides
    print(f"Loading peptides from {peptides_path}...")
    df = pd.read_csv(peptides_path, sep="\t")

    if patient_id is None:
        patient_id = str(df["patient_id"].iloc[0]) if "patient_id" in df.columns else "unknown"

    unique_peptides = df["peptide"].unique().tolist()
    print(f"Unique peptides to score: {len(unique_peptides)}")
    print(f"HLA alleles: {hla_alleles}")

    # Run predictions
    method = "mhcflurry"
    raw_results = []

    if use_mhcflurry:
        print("\nTrying MHCflurry 2.0...")
        raw_results = predict_mhcflurry(unique_peptides, hla_alleles)

    if not raw_results:
        print("\nFalling back to IEDB NetMHCpan API...")
        method = "netmhcpan_iedb"
        raw_results = predict_iedb(unique_peptides, hla_alleles)

    if not raw_results:
        print("  ❌ No binding predictions obtained")
        output_path = os.path.join(PATHS["stage4"], f"{patient_id}_binding.tsv")
        os.makedirs(PATHS["stage4"], exist_ok=True)
        return BindingResult(
            patient_id=patient_id,
            predictions=[],
            predictions_path=output_path,
            total_scored=0,
            strong_binders=0,
            hla_alleles_used=hla_alleles,
            method=method,
        )

    print(f"\nTotal raw predictions: {len(raw_results)}")

    # Convert to DataFrame for filtering
    results_df = pd.DataFrame(raw_results)
    results_df = results_df.dropna(subset=["ic50", "percentile_rank"])

    # Merge back with peptide metadata (gene, mutation, VAF)
    peptide_meta = df[
        ["peptide", "gene", "hgvsp_short", "tumor_vaf"]
    ].drop_duplicates(subset=["peptide"])

    merged = results_df.merge(peptide_meta, on="peptide", how="left")

    # Filter strong binders: IC50 < 500nM OR %rank < 0.5
    strong = merged[
        (merged["ic50"] < IC50_THRESHOLD) | (merged["percentile_rank"] < RANK_THRESHOLD)
    ].copy()
    strong = strong.sort_values("percentile_rank", ascending=True)

    print(f"Strong binders (IC50 < {IC50_THRESHOLD}nM or rank < {RANK_THRESHOLD}%): {len(strong)}")
    print(f"Discarded: {len(merged) - len(strong)}")

    # Build output models
    predictions: list[BindingPrediction] = []
    for _, row in strong.iterrows():
        predictions.append(
            BindingPrediction(
                peptide=row["peptide"],
                allele=row["allele"],
                ic50=float(row["ic50"]),
                percentile_rank=float(row["percentile_rank"]),
                presentation_score=float(row["presentation_score"]) if pd.notna(row.get("presentation_score")) else None,
                processing_score=float(row["processing_score"]) if pd.notna(row.get("processing_score")) else None,
                prediction_method=row.get("prediction_method", method),
                gene=row.get("gene"),
                hgvsp_short=row.get("hgvsp_short"),
                tumor_vaf=float(row["tumor_vaf"]) if pd.notna(row.get("tumor_vaf")) else None,
            )
        )

    # Save output
    output_path = os.path.join(PATHS["stage4"], f"{patient_id}_binding.tsv")
    os.makedirs(PATHS["stage4"], exist_ok=True)

    if predictions:
        out_df = pd.DataFrame([p.model_dump() for p in predictions])
        out_df.to_csv(output_path, sep="\t", index=False)

    return BindingResult(
        patient_id=patient_id,
        predictions=predictions,
        predictions_path=output_path,
        total_scored=len(merged),
        strong_binders=len(predictions),
        hla_alleles_used=hla_alleles,
        method=method,
    )
