#!/usr/bin/env python3
"""
BloomOne Dry Run — test Stages 3-7 against TCGA-BF-A3DL-01 data.

Uses the same patient case from challenge_3 to validate the refactored
pipeline produces equivalent results.
"""

import os
import sys
import time

# Override volume paths to local temp for dry run
os.environ["BLOOMONE_DRY_RUN"] = "1"

# Patch config paths to use /tmp for this dry run
import bloomone.config as config

DRY_RUN_DIR = "/tmp/bloomone_dry_run"
for key in config.PATHS:
    config.PATHS[key] = os.path.join(DRY_RUN_DIR, key)
os.makedirs(DRY_RUN_DIR, exist_ok=True)

from bloomone.stages.stage3_peptides import generate_peptides
from bloomone.stages.stage4_binding import predict_binding
from bloomone.stages.stage5_safety import filter_self_similarity
from bloomone.stages.stage6_ranking import rank_candidates
from bloomone.stages.stage7_mrna import design_mrna


def main():
    MAF_PATH = "/tmp/test_patient.maf"
    PATIENT_ID = "TCGA-BF-A3DL-01"
    HLA_ALLELES = ["HLA-A*02:01", "HLA-B*07:02"]  # Example alleles

    start_time = time.time()

    # ── Stage 3: Peptide Generation ──────────────────────────────────────
    print("=" * 60)
    print("STAGE 3: Peptide Generation")
    print("=" * 60)
    t0 = time.time()

    peptide_result = generate_peptides(
        maf_path=MAF_PATH,
        patient_id=PATIENT_ID,
    )

    print(f"\n📊 Stage 3 Results:")
    print(f"  Total candidates: {peptide_result.total_candidates}")
    print(f"  Unique peptides: {peptide_result.unique_peptides}")
    print(f"  Skipped mutations: {peptide_result.skipped_mutations}")
    print(f"  Output: {peptide_result.candidates_path}")
    print(f"  ⏱️  Time: {time.time() - t0:.1f}s")

    if peptide_result.total_candidates == 0:
        print("❌ No peptides generated — aborting dry run")
        sys.exit(1)

    # ── Stage 4: HLA Binding (IEDB API — MHCflurry not installed) ──────
    print("\n" + "=" * 60)
    print("STAGE 4: HLA Binding Prediction (IEDB API)")
    print("=" * 60)
    t0 = time.time()

    binding_result = predict_binding(
        peptides_path=peptide_result.candidates_path,
        hla_alleles=HLA_ALLELES,
        patient_id=PATIENT_ID,
        use_mhcflurry=False,  # Use IEDB API for dry run (no GPU)
    )

    print(f"\n📊 Stage 4 Results:")
    print(f"  Total scored: {binding_result.total_scored}")
    print(f"  Strong binders: {binding_result.strong_binders}")
    print(f"  Method: {binding_result.method}")
    print(f"  Output: {binding_result.predictions_path}")
    print(f"  ⏱️  Time: {time.time() - t0:.1f}s")

    if binding_result.strong_binders == 0:
        print("⚠️  No strong binders — pipeline cannot continue")
        print("    This may be due to IEDB API rate limiting.")
        print("    Skipping Stages 5-7 for this dry run.")
        _print_summary(start_time, peptide_result, binding_result, None, None, None)
        return

    # ── Stage 5: Safety Filter ───────────────────────────────────────────
    print("\n" + "=" * 60)
    print("STAGE 5: Safety Filter")
    print("=" * 60)
    t0 = time.time()

    safety_result = filter_self_similarity(
        binders_path=binding_result.predictions_path,
        patient_id=PATIENT_ID,
    )

    print(f"\n📊 Stage 5 Results:")
    print(f"  Total input: {safety_result.total_input}")
    print(f"  Removed (self-match): {safety_result.total_removed}")
    print(f"    Exact matches: {safety_result.exact_matches_removed}")
    print(f"    Partial matches: {safety_result.partial_matches_removed}")
    print(f"  Safe candidates: {safety_result.total_safe}")
    print(f"  Output: {safety_result.safe_path}")
    print(f"  ⏱️  Time: {time.time() - t0:.1f}s")

    if safety_result.total_safe == 0:
        print("⚠️  All candidates matched human proteome")
        _print_summary(start_time, peptide_result, binding_result, safety_result, None, None)
        return

    # ── Stage 6: Ranking ─────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("STAGE 6: Candidate Ranking")
    print("=" * 60)
    t0 = time.time()

    ranking_result = rank_candidates(
        safe_path=safety_result.safe_path,
        patient_id=PATIENT_ID,
        top_n=20,
    )

    print(f"\n📊 Stage 6 Results:")
    print(f"  Total input: {ranking_result.total_input}")
    print(f"  Total ranked: {ranking_result.total_ranked}")
    print(f"  Expression data: {ranking_result.expression_available}")
    print(f"  Weights: {ranking_result.weights_used}")
    print(f"  Output: {ranking_result.ranked_path}")
    print(f"  ⏱️  Time: {time.time() - t0:.1f}s")

    # ── Stage 7: mRNA Design ─────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("STAGE 7: mRNA Construct Design")
    print("=" * 60)
    t0 = time.time()

    mrna_result = design_mrna(
        ranked_path=ranking_result.ranked_path,
        patient_id=PATIENT_ID,
        top_n=20,
    )

    print(f"\n📊 Stage 7 Results:")
    print(f"  Constructs designed: {mrna_result.total_designed}")
    if mrna_result.polytope_length:
        print(f"  Polytope mRNA length: {mrna_result.polytope_length} nt")
    print(f"  Output: {mrna_result.constructs_path}")
    print(f"  ⏱️  Time: {time.time() - t0:.1f}s")

    _print_summary(
        start_time, peptide_result, binding_result,
        safety_result, ranking_result, mrna_result,
    )


def _print_summary(start_time, peptide_result, binding_result,
                    safety_result, ranking_result, mrna_result):
    total_time = time.time() - start_time

    print("\n" + "=" * 60)
    print("🧬 BLOOMONE DRY RUN COMPLETE")
    print("=" * 60)
    print(f"\n  Patient: TCGA-BF-A3DL-01")
    print(f"  Total time: {total_time:.1f}s")
    print()
    print("  Pipeline funnel:")
    print(f"    Stage 3 → {peptide_result.total_candidates} peptides "
          f"({peptide_result.unique_peptides} unique)")
    print(f"    Stage 4 → {binding_result.strong_binders} strong binders")

    if safety_result:
        print(f"    Stage 5 → {safety_result.total_safe} safe candidates "
              f"({safety_result.total_removed} removed)")
    if ranking_result:
        print(f"    Stage 6 → Top {ranking_result.total_ranked} ranked")
    if mrna_result:
        print(f"    Stage 7 → {mrna_result.total_designed} mRNA constructs")
        if mrna_result.polytope_length:
            print(f"    Polytope → {mrna_result.polytope_length} nt")

    # Compare with challenge_3 results
    print(f"\n  📊 Challenge 3 comparison:")
    print(f"    Challenge 3 produced 2,878 candidate peptides")
    print(f"    BloomOne produced {peptide_result.total_candidates} candidates "
          f"({peptide_result.unique_peptides} unique)")
    print(f"    Challenge 3 found 75 strong binders")
    print(f"    BloomOne found {binding_result.strong_binders} strong binders")
    print()

    if mrna_result and mrna_result.total_designed > 0:
        print("  ✅ DRY RUN PASSED — Pipeline produces valid mRNA constructs")
    elif binding_result.strong_binders > 0:
        print("  ⚠️  DRY RUN PARTIAL — Binding works, later stages need data")
    else:
        print("  ⚠️  DRY RUN LIMITED — IEDB API may be rate-limiting")


if __name__ == "__main__":
    main()
