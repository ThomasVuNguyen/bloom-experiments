"""
Stage 7: mRNA Construct Design (MCP-7)

Builds complete mRNA vaccine constructs from ranked neoantigen candidates.
Includes codon optimization, signal peptide, linker, UTRs, poly-A tail,
and optional ViennaRNA MFE structure prediction.

Input:  Top 20 ranked candidates from Stage 6
Output: Complete mRNA sequences ready for synthesis
"""

from __future__ import annotations

import os
from typing import Optional

import pandas as pd

from bloomone.config import PATHS, POLY_A_LENGTH, TOP_N_CANDIDATES
from bloomone.models import MRNAConstruct, MRNAResult
from bloomone.utils import aa_to_dna, check_premature_stops, dna_to_mrna, gc_content


# ── mRNA Construct Components ─────────────────────────────────────────────────
# Real, validated sequences used in mRNA vaccine design

# 5' UTR — from human beta-globin gene, promotes strong translation
UTR_5 = "GGGAAATAAGAGAGAAAAGAAGAGTAAGAAGAAATATAAGAGCCACC"

# Signal peptide — routes peptide into MHC-I presentation pathway
# Human tissue plasminogen activator (tPA) signal peptide
# Ensures the peptide gets processed and loaded onto HLA
SIGNAL_PEPTIDE_AA = "MDAMKRGLCCVLLLCGAVFVSPS"

# Linker — connects signal peptide to neoantigen peptide
# AAY linker is commonly used in polytope vaccines — helps proteasomal cleavage
LINKER_AA = "AAY"

# 3' UTR — from human alpha-globin gene (open, non-patented)
UTR_3 = (
    "GCUCCUGGAGACCCCAGUGCUGAGCUUCAGCUGGAGAAGCCCAGGGCCUGGGCGGGAGCU"
    "GGGAGUGGGUGCUGAGGCCCAGUGCACCCUGGAGUGCUGGGCAGCCCUGGGCCUGGGCGG"
    "GAGCUGGGAGUGGGUGCUGAGGCCCAGUGCACCCUGGAGUGCUGGGCAGCCCUGG"
)

# Poly-A tail — standard 120 A's for mRNA stability
POLY_A = "A" * POLY_A_LENGTH


def build_single_construct(neoantigen_aa: str) -> dict:
    """
    Build a complete mRNA vaccine construct for a single neoantigen peptide.

    Structure:
    5'UTR | START | Signal Peptide | Linker | Neoantigen | STOP | 3'UTR | Poly-A
    """
    # Build the full protein coding sequence (CDS)
    full_aa = SIGNAL_PEPTIDE_AA + LINKER_AA + neoantigen_aa

    # Translate to codon-optimized DNA
    # ATG start codon + remaining CDS + stop codon
    cds_dna = "ATG" + aa_to_dna(full_aa[1:]) + aa_to_dna("*")

    # Convert to mRNA
    cds_mrna = dna_to_mrna(cds_dna)

    # Assemble full construct
    full_mrna = UTR_5 + cds_mrna + UTR_3 + POLY_A

    # Check for premature stop codons
    premature_stops = check_premature_stops(cds_dna)

    # Attempt ViennaRNA MFE prediction
    mfe = None
    try:
        import RNA  # ViennaRNA Python bindings

        # Predict MFE for the CDS region (most relevant for stability)
        structure, mfe_value = RNA.fold(cds_mrna)
        mfe = round(mfe_value, 2)
    except ImportError:
        pass  # ViennaRNA not available in this environment
    except Exception as e:
        print(f"  ViennaRNA MFE prediction failed: {e}")

    return {
        "cds_dna": cds_dna,
        "cds_mrna": cds_mrna,
        "full_mrna": full_mrna,
        "cds_length": len(cds_dna),
        "full_length": len(full_mrna),
        "gc_content": gc_content(cds_dna),
        "has_premature_stop": len(premature_stops) > 0,
        "mfe": mfe,
    }


def build_polytope_construct(peptides: list[str]) -> dict:
    """
    Build a single concatenated polytope mRNA construct from multiple
    neoantigen peptides, each separated by AAY linkers.

    Structure:
    5'UTR | START | Signal | Linker | Pep1 | Linker | Pep2 | ... | STOP | 3'UTR | Poly-A
    """
    # Concatenate peptides with linkers
    polytope_aa = SIGNAL_PEPTIDE_AA
    for i, pep in enumerate(peptides):
        polytope_aa += LINKER_AA + pep

    # Build construct
    cds_dna = "ATG" + aa_to_dna(polytope_aa[1:]) + aa_to_dna("*")
    cds_mrna = dna_to_mrna(cds_dna)
    full_mrna = UTR_5 + cds_mrna + UTR_3 + POLY_A

    return {
        "cds_dna": cds_dna,
        "cds_mrna": cds_mrna,
        "full_mrna": full_mrna,
        "cds_length": len(cds_dna),
        "full_length": len(full_mrna),
        "gc_content": gc_content(cds_dna),
        "num_epitopes": len(peptides),
    }


def design_mrna(
    ranked_path: str,
    patient_id: Optional[str] = None,
    top_n: int = TOP_N_CANDIDATES,
) -> MRNAResult:
    """
    Stage 7: Design mRNA vaccine constructs.

    Builds individual mRNA constructs for each top-N candidate, plus
    a single concatenated polytope construct containing all epitopes.

    Args:
        ranked_path: Path to ranked candidates TSV from Stage 6
        patient_id: Patient identifier
        top_n: Number of top candidates to design constructs for

    Returns:
        MRNAResult with individual + polytope constructs
    """
    # Load ranked candidates
    print(f"Loading ranked candidates from {ranked_path}...")
    df = pd.read_csv(ranked_path, sep="\t")
    top = df.head(top_n)

    if patient_id is None:
        patient_id = str(df["patient_id"].iloc[0]) if "patient_id" in df.columns else "unknown"

    print(f"Designing mRNA constructs for top {len(top)} candidates\n")

    constructs: list[MRNAConstruct] = []

    for _, row in top.iterrows():
        peptide = row["peptide"]
        gene = row.get("gene", "")
        hgvsp = row.get("hgvsp_short", "")
        ic50 = float(row.get("ic50", 0))
        rank_val = float(row.get("percentile_rank", row.get("rank", 0)))
        rank_pos = int(row.get("rank", len(constructs) + 1)) if "rank" in row.index else len(constructs) + 1

        print(f"  {gene} {hgvsp} → {peptide}")

        try:
            construct_data = build_single_construct(peptide)

            if construct_data["has_premature_stop"]:
                print(f"    ⚠️  WARNING: premature stop codon detected")
            else:
                print(f"    ✅ No premature stop codons")

            print(f"    CDS: {construct_data['cds_length']} nt | "
                  f"Full: {construct_data['full_length']} nt | "
                  f"GC: {construct_data['gc_content']}%")

            if construct_data["mfe"] is not None:
                print(f"    MFE: {construct_data['mfe']} kcal/mol")

            constructs.append(
                MRNAConstruct(
                    rank=rank_pos,
                    peptide=peptide,
                    gene=gene,
                    hgvsp_short=hgvsp,
                    ic50=ic50,
                    percentile_rank=rank_val,
                    **construct_data,
                )
            )

        except Exception as e:
            print(f"    ❌ Error: {e}")

    # Build polytope construct
    polytope_mrna = None
    polytope_length = None
    if constructs:
        print(f"\nBuilding polytope construct ({len(constructs)} epitopes)...")
        polytope_data = build_polytope_construct(
            [c.peptide for c in constructs]
        )
        polytope_mrna = polytope_data["full_mrna"]
        polytope_length = polytope_data["full_length"]
        print(f"  Polytope mRNA: {polytope_length} nt | "
              f"GC: {polytope_data['gc_content']}%")

    # Save output
    output_path = os.path.join(PATHS["stage7"], f"{patient_id}_mrna_constructs.tsv")
    os.makedirs(PATHS["stage7"], exist_ok=True)

    if constructs:
        out_df = pd.DataFrame([c.model_dump() for c in constructs])
        out_df.to_csv(output_path, sep="\t", index=False)

    # Also save polytope FASTA
    if polytope_mrna:
        polytope_path = os.path.join(PATHS["stage7"], f"{patient_id}_polytope.fasta")
        with open(polytope_path, "w") as f:
            f.write(f">BloomOne_polytope_{patient_id}_{len(constructs)}_epitopes\n")
            # Write in 80-char lines
            for i in range(0, len(polytope_mrna), 80):
                f.write(polytope_mrna[i : i + 80] + "\n")

    print(f"\n✅ Designed {len(constructs)} mRNA constructs")
    print(f"Saved to {output_path}")

    return MRNAResult(
        patient_id=patient_id,
        constructs=constructs,
        constructs_path=output_path,
        total_designed=len(constructs),
        polytope_mrna=polytope_mrna,
        polytope_length=polytope_length,
    )
