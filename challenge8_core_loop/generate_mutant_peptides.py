import re
import time
import requests
import pandas as pd
from tqdm import tqdm

MAF_PATH = "5b913527-2907-4006-b096-c460e6054c10.wxs.aliquot_ensemble_masked.maf"

# For first run, keep this small.
# Set to None later to process all missense mutations.
MAX_MUTATIONS = 25


def parse_hgvsp_short(value):
    """
    Parses simple missense protein changes like:
    p.G13R, p.V600E, p.R334K
    """
    if pd.isna(value):
        return None

    value = str(value).strip()
    match = re.fullmatch(r"p\.([A-Z])(\d+)([A-Z])", value)

    if not match:
        return None

    ref_aa = match.group(1)
    position = int(match.group(2))
    alt_aa = match.group(3)

    return ref_aa, position, alt_aa


def fetch_protein_sequence(transcript_id):
    """
    Fetch protein sequence from Ensembl using transcript ID.
    Example transcript ID: ENST00000256078
    """
    url = f"https://rest.ensembl.org/sequence/id/{transcript_id}"
    params = {"type": "protein"}
    headers = {"Content-Type": "text/plain"}

    try:
        response = requests.get(url, params=params, headers=headers, timeout=30)
    except requests.RequestException:
        return None

    if not response.ok:
        return None

    seq = "".join(response.text.split())

    if not seq:
        return None

    if seq.startswith("{") or "<html" in seq.lower():
        return None

    return seq


def generate_spanning_peptides(mutant_seq, mutation_index_0based):
    """
    Generate all 8-mer, 9-mer, 10-mer, and 11-mer peptides that contain the mutated amino acid.
    """
    rows = []

    for length in [8, 9, 10, 11]:
        start_min = max(0, mutation_index_0based - length + 1)
        start_max = min(mutation_index_0based, len(mutant_seq) - length)

        for start in range(start_min, start_max + 1):
            peptide = mutant_seq[start:start + length]

            if len(peptide) != length:
                continue

            if "*" in peptide or "X" in peptide:
                continue

            rows.append({
                "peptide": peptide,
                "peptide_length": length,
                "peptide_start_in_protein": start + 1,
                "mutation_offset_in_peptide": mutation_index_0based - start + 1,
            })

    return rows


maf = pd.read_csv(MAF_PATH, sep="\t", comment="#", low_memory=False)

missense = maf[
    (maf["Variant_Classification"] == "Missense_Mutation") &
    (maf["HGVSp_Short"].notna()) &
    (maf["Transcript_ID"].notna())
].copy()

missense["parsed"] = missense["HGVSp_Short"].apply(parse_hgvsp_short)
missense = missense[missense["parsed"].notna()].copy()

missense["tumor_vaf"] = missense["t_alt_count"] / missense["t_depth"]

if "callers" in missense.columns:
    missense["caller_count"] = missense["callers"].fillna("").apply(
        lambda x: len(str(x).split(";")) if x else 0
    )
else:
    missense["caller_count"] = 0

if "hotspot" not in missense.columns:
    missense["hotspot"] = ""

# Prioritize interesting-looking mutations first for the dry run.
missense = missense.sort_values(
    by=["hotspot", "caller_count", "tumor_vaf"],
    ascending=[False, False, False]
)

if MAX_MUTATIONS:
    missense = missense.head(MAX_MUTATIONS)

protein_cache = {}
candidate_rows = []
skipped_rows = []

for _, row in tqdm(missense.iterrows(), total=len(missense)):
    gene = row["Hugo_Symbol"]
    transcript_id = row["Transcript_ID"]
    hgvsp = row["HGVSp_Short"]
    ref_aa, pos_1based, alt_aa = row["parsed"]
    mutation_index = pos_1based - 1

    if transcript_id not in protein_cache:
        protein_cache[transcript_id] = fetch_protein_sequence(transcript_id)
        time.sleep(0.15)

    ref_seq = protein_cache[transcript_id]

    if not ref_seq:
        skipped_rows.append({
            "gene": gene,
            "hgvsp_short": hgvsp,
            "transcript_id": transcript_id,
            "reason": "could_not_fetch_protein_sequence"
        })
        continue

    if mutation_index < 0 or mutation_index >= len(ref_seq):
        skipped_rows.append({
            "gene": gene,
            "hgvsp_short": hgvsp,
            "transcript_id": transcript_id,
            "reason": "mutation_position_outside_sequence"
        })
        continue

    observed_ref_aa = ref_seq[mutation_index]

    if observed_ref_aa != ref_aa:
        skipped_rows.append({
            "gene": gene,
            "hgvsp_short": hgvsp,
            "transcript_id": transcript_id,
            "expected_ref_aa": ref_aa,
            "observed_ref_aa": observed_ref_aa,
            "reason": "reference_amino_acid_mismatch"
        })
        continue

    mutant_seq = ref_seq[:mutation_index] + alt_aa + ref_seq[mutation_index + 1:]
    peptides = generate_spanning_peptides(mutant_seq, mutation_index)

    for peptide_row in peptides:
        candidate_rows.append({
            "sample": row["Tumor_Sample_Barcode"],
            "gene": gene,
            "transcript_id": transcript_id,
            "hgvsp_short": hgvsp,
            "protein_position": pos_1based,
            "ref_aa": ref_aa,
            "alt_aa": alt_aa,
            "tumor_vaf": row["tumor_vaf"],
            "t_depth": row["t_depth"],
            "t_alt_count": row["t_alt_count"],
            "caller_count": row["caller_count"],
            "hotspot": row["hotspot"],
            **peptide_row
        })

candidates = pd.DataFrame(candidate_rows)
skipped = pd.DataFrame(skipped_rows)

candidates.to_csv("candidate_mutant_peptides.tsv", sep="\t", index=False)
skipped.to_csv("skipped_mutations.tsv", sep="\t", index=False)

if len(candidates) > 0:
    unique_peptides = candidates["peptide"].drop_duplicates()
    unique_peptides.to_csv("netmhcpan_peptides.txt", index=False, header=False)
else:
    pd.Series([], dtype=str).to_csv("netmhcpan_peptides.txt", index=False, header=False)

print("Mutations processed:", len(missense))
print("Candidate peptide rows:", len(candidates))
print("Unique peptides:", len(candidates["peptide"].drop_duplicates()) if len(candidates) else 0)
print("Skipped mutations:", len(skipped))
print("Wrote:")
print("- candidate_mutant_peptides.tsv")
print("- netmhcpan_peptides.txt")
print("- skipped_mutations.tsv")