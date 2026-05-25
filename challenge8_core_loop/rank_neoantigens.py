import pandas as pd

# Load candidate peptide metadata from our mutation → peptide script
candidates = pd.read_csv("candidate_mutant_peptides.tsv", sep="\t")

# Parse IEDB plain-text result
rows = []
with open("netmhcpan_results.txt", "r") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        if line.startswith("MHC-I") or line.startswith("-----") or line.startswith("Method"):
            continue
        if line.startswith("allele"):
            continue

        parts = line.split()
        if len(parts) < 8:
            continue

        rows.append({
            "allele": parts[0],
            "seq_num": int(parts[1]),
            "start": int(parts[2]),
            "end": int(parts[3]),
            "length": int(parts[4]),
            "peptide": parts[5],
            "ic50": float(parts[6]),
            "rank": float(parts[7]),
        })

predictions = pd.DataFrame(rows)

# Merge NetMHCpan predictions back to mutation metadata
merged = predictions.merge(
    candidates,
    on="peptide",
    how="left",
    suffixes=("_netmhc", "_candidate")
)

# Rank: strongest binders first, then higher tumor VAF
ranked = merged.sort_values(
    by=["rank", "ic50", "tumor_vaf"],
    ascending=[True, True, False]
)

cols = [
    "gene",
    "hgvsp_short",
    "peptide",
    "peptide_length",
    "allele",
    "ic50",
    "rank",
    "tumor_vaf",
    "t_depth",
    "t_alt_count",
    "caller_count",
    "hotspot",
    "transcript_id",
    "protein_position",
    "mutation_offset_in_peptide",
]

cols = [c for c in cols if c in ranked.columns]

ranked[cols].to_csv("ranked_neoantigen_candidates.tsv", sep="\t", index=False)

print("Predictions:", len(predictions))
print("Merged rows:", len(merged))
print("Wrote ranked_neoantigen_candidates.tsv")
print()
print(ranked[cols].head(25).to_string(index=False))