import re
import pandas as pd

RANKED_PATH = "ranked_neoantigen_candidates.tsv"
PROTEOME_FASTA = "human_reviewed_proteome.fasta"

def parse_hgvsp_short(value):
    """
    Parse p.S166L into ref=S, position=166, alt=L
    """
    if pd.isna(value):
        return None

    m = re.fullmatch(r"p\.([A-Z])(\d+)([A-Z])", str(value).strip())
    if not m:
        return None

    return {
        "ref_aa": m.group(1),
        "position": int(m.group(2)),
        "alt_aa": m.group(3),
    }

def read_fasta(path):
    records = []
    header = None
    seq_parts = []

    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            if line.startswith(">"):
                if header is not None:
                    records.append((header, "".join(seq_parts)))
                header = line[1:]
                seq_parts = []
            else:
                seq_parts.append(line)

    if header is not None:
        records.append((header, "".join(seq_parts)))

    return records

def find_exact_proteome_matches(peptide, proteome_records):
    matches = []

    for header, seq in proteome_records:
        idx = seq.find(peptide)
        if idx != -1:
            matches.append({
                "protein_header": header,
                "position_start": idx + 1,
                "position_end": idx + len(peptide),
            })

    return matches

df = pd.read_csv(RANKED_PATH, sep="\t")

original_count = len(df)

# 1. Remove rows that did not merge cleanly back to mutation metadata.
required = ["gene", "hgvsp_short", "peptide", "allele", "ic50", "rank", "tumor_vaf"]
clean = df.dropna(subset=[c for c in required if c in df.columns]).copy()

# 2. Parse mutation notation.
parsed = clean["hgvsp_short"].apply(parse_hgvsp_short)
clean = clean[parsed.notna()].copy()
parsed = clean["hgvsp_short"].apply(parse_hgvsp_short)

clean["ref_aa"] = parsed.apply(lambda x: x["ref_aa"])
clean["alt_aa"] = parsed.apply(lambda x: x["alt_aa"])

# 3. Keep only peptides where the mutation offset is valid and peptide contains the mutated amino acid.
clean["mutation_offset_in_peptide"] = pd.to_numeric(
    clean["mutation_offset_in_peptide"],
    errors="coerce"
)

def peptide_contains_mutation(row):
    if pd.isna(row["mutation_offset_in_peptide"]):
        return False

    offset = int(row["mutation_offset_in_peptide"])

    if offset < 1 or offset > len(row["peptide"]):
        return False

    return row["peptide"][offset - 1] == row["alt_aa"]

clean["contains_mutated_aa"] = clean.apply(peptide_contains_mutation, axis=1)

mutation_linked = clean[clean["contains_mutated_aa"]].copy()
discarded_not_mutation_linked = clean[~clean["contains_mutated_aa"]].copy()

# 4. Deduplicate exact same candidate.
mutation_linked = mutation_linked.sort_values(
    by=["rank", "ic50", "tumor_vaf"],
    ascending=[True, True, False]
)

mutation_linked = mutation_linked.drop_duplicates(
    subset=["gene", "hgvsp_short", "peptide", "allele"],
    keep="first"
).copy()

# 5. Exact self-match filter against normal human proteome.
print("Loading human proteome...")
proteome = read_fasta(PROTEOME_FASTA)
print(f"Proteins loaded: {len(proteome)}")

kept_rows = []
self_match_rows = []

for _, row in mutation_linked.iterrows():
    peptide = row["peptide"]
    matches = find_exact_proteome_matches(peptide, proteome)

    if matches:
        for m in matches[:5]:
            out = row.to_dict()
            out.update(m)
            out["num_self_matches"] = len(matches)
            self_match_rows.append(out)
    else:
        kept_rows.append(row.to_dict())

final_candidates = pd.DataFrame(kept_rows)
discarded_self_matches = pd.DataFrame(self_match_rows)

# 6. Sort final result.
if len(final_candidates) > 0:
    final_candidates = final_candidates.sort_values(
        by=["rank", "ic50", "tumor_vaf"],
        ascending=[True, True, False]
    )

# 7. Save outputs.
clean.to_csv("step4_clean_ranked_valid.tsv", sep="\t", index=False)
discarded_not_mutation_linked.to_csv("step4_discarded_not_mutation_linked.tsv", sep="\t", index=False)
discarded_self_matches.to_csv("step4_discarded_self_matches.tsv", sep="\t", index=False)
final_candidates.to_csv("step4_final_candidates.tsv", sep="\t", index=False)

print()
print("Original ranked rows:", original_count)
print("Clean mutation-linked candidates:", len(mutation_linked))
print("Discarded because peptide did not contain mutated AA:", len(discarded_not_mutation_linked))
print("Discarded exact self/proteome matches:", len(discarded_self_matches))
print("Final candidates:", len(final_candidates))
print()
print("Wrote:")
print("- step4_clean_ranked_valid.tsv")
print("- step4_discarded_not_mutation_linked.tsv")
print("- step4_discarded_self_matches.tsv")
print("- step4_final_candidates.tsv")
print()

if len(final_candidates) > 0:
    show_cols = [
        "gene", "hgvsp_short", "peptide", "peptide_length",
        "allele", "ic50", "rank", "tumor_vaf",
        "t_depth", "t_alt_count", "caller_count", "hotspot"
    ]
    show_cols = [c for c in show_cols if c in final_candidates.columns]
    print(final_candidates[show_cols].head(25).to_string(index=False))