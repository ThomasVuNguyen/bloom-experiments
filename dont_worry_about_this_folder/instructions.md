Challenge 8 — Core Loop Dry Run
Goal
Build the first working version of the ComfyBloom core loop:
TCGA melanoma MAF
→ missense mutations
→ mutant 8–11mer peptides
→ NetMHCpan binding predictions
→ ranked candidate neoantigen table
Because Challenge 7 is blocked by TCGA controlled-access BAM files, this run uses:
Real TCGA-SKCM tumor mutations
+ placeholder HLA alleles
= pipeline dry run
This is structurally correct, but not biologically patient-matched yet.

Step 0 — Current file path
Your MAF file is here:
/Users/thomasthemaker/Downloads/gdc_download_20260524_040257.758182/34745fc1-1ae6-4311-a7a3-fd43eeb40e4e/5b913527-2907-4006-b096-c460e6054c10.wxs.aliquot_ensemble_masked.maf
Use quotes around it because long paths are easy to mess up.

Step 1 — Create the Challenge 8 folder
mkdir -p ~/comfybench/challenge8_core_loop
cd ~/comfybench/challenge8_core_loop

Step 2 — Copy the MAF file correctly
Run this exact command:
cp "/Users/thomasthemaker/Downloads/gdc_download_20260524_040257.758182/34745fc1-1ae6-4311-a7a3-fd43eeb40e4e/5b913527-2907-4006-b096-c460e6054c10.wxs.aliquot_ensemble_masked.maf" .
Then confirm it copied:
ls -lh
You should see:
5b913527-2907-4006-b096-c460e6054c10.wxs.aliquot_ensemble_masked.maf

Step 3 — Create placeholder HLA panel
Create a file called hla_panel.txt:
cat > hla_panel.txt <<'EOF'
HLA-A02:01,HLA-A01:01,HLA-B07:02,HLA-B08:01,HLA-C07:01,HLA-C07:02
EOF
This is temporary. Later, replace this with the real OptiType HLA output from Challenge 7.

Step 4 — Set up Python environment
python3 -m venv venv
source venv/bin/activate
pip install pandas requests tqdm

Step 5 — Create the peptide generation script
Create the script:
nano generate_mutant_peptides.py
Paste this code:
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
Save in nano:
Ctrl + O
Enter
Ctrl + X

Step 6 — Run peptide generation
python generate_mutant_peptides.py
Check files:
ls -lh
head candidate_mutant_peptides.tsv
head netmhcpan_peptides.txt
head skipped_mutations.tsv
Expected output files:
candidate_mutant_peptides.tsv
netmhcpan_peptides.txt
skipped_mutations.tsv

Step 7 — Understand what the generated files mean
candidate_mutant_peptides.tsv
This is the main peptide metadata table.
Each row says:
This mutation generated this mutant peptide, at this length, with this mutation position inside the peptide.
Important columns:
gene
hgvsp_short
peptide
peptide_length
protein_position
tumor_vaf
t_depth
t_alt_count
caller_count
hotspot
netmhcpan_peptides.txt
This is the peptide-only input file for NetMHCpan / IEDB.
It should look like:
AAAAAAAA
AAAAAAAAB
AAAAAAAABC
...
skipped_mutations.tsv
This records mutations we could not safely convert into peptides.
Common reasons:
could_not_fetch_protein_sequence
reference_amino_acid_mismatch
mutation_position_outside_sequence
This is normal. Real variant data is messy.

Step 8 — Run NetMHCpan using IEDB web tool
Go to:
https://tools.iedb.org/mhci/
Use these settings:
Prediction method: NetMHCpan
Input peptides: paste contents of netmhcpan_peptides.txt
Alleles: HLA-A02:01,HLA-A01:01,HLA-B07:02,HLA-B08:01,HLA-C07:01,HLA-C07:02
Peptide lengths: 8, 9, 10, 11
Download the result table and save it in this folder as:
netmhcpan_results.tsv
If the web tool gives you CSV instead, name it:
netmhcpan_results.csv

Step 9 — What the final ranked table should contain
The final Challenge 8 output should look like:
gene | mutation | peptide | length | allele | IC50 | percentile_rank | tumor_vaf
Rank by:
1. Percentile rank ascending
2. IC50 ascending
3. Tumor VAF descending
4. Caller count descending
Strong candidates usually have:
low percentile rank
low IC50
mutation-containing peptide
reasonable tumor VAF
good read support

Step 10 — Completion definition
Challenge 8 dry run is complete when you have:
candidate_mutant_peptides.tsv
netmhcpan_peptides.txt
netmhcpan_results.tsv or netmhcpan_results.csv
final ranked neoantigen candidate table

Important note for your lab log
Use this wording:
Challenge 8 dry run used real TCGA-SKCM tumor mutations from Challenge 6 and a placeholder HLA panel because same-patient HLA typing was blocked by controlled-access TCGA BAM files. The pipeline is structurally complete but not biologically patient-matched yet.

Current command you need next
From inside:
~/comfybench/challenge8_core_loop
Run:
cp "/Users/thomasthemaker/Downloads/gdc_download_20260524_040257.758182/34745fc1-1ae6-4311-a7a3-fd43eeb40e4e/5b913527-2907-4006-b096-c460e6054c10.wxs.aliquot_ensemble_masked.maf" .
Then continue from Step 3.

Yep. Step 4 = **self/safety filter**.

We will remove candidates that:

1. are not cleanly linked to a mutation
2. do not contain the mutated amino acid
3. already appear exactly in normal human proteins

Run this inside:

```bash
cd ~/comfybench/challenge8_core_loop
source venv/bin/activate
```

## 1. Download normal human proteome

```bash
curl -L "https://rest.uniprot.org/uniprotkb/stream?compressed=false&format=fasta&includeIsoform=true&query=%28proteome%3AUP000005640%29%20AND%20%28reviewed%3Atrue%29" \
  -o human_reviewed_proteome.fasta
```

Check it:

```bash
grep -c "^>" human_reviewed_proteome.fasta
head human_reviewed_proteome.fasta
```

## 2. Create safety filter script

```bash
nano step4_safety_filter.py
```

Paste:

```python
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
```

Save:

```text
Ctrl + O
Enter
Ctrl + X
```

## 3. Run Step 4

```bash
python step4_safety_filter.py
```

## 4. View final candidates

```bash
column -t -s $'\t' step4_final_candidates.tsv | less -S
```

Press `q` to exit.

## What Step 4 means

You are now doing:

```text
ranked candidates
→ remove bad/NaN rows
→ require peptide contains the mutation
→ remove exact matches to normal human proteome
→ final safer candidate list
```

The main output is:

```text
step4_final_candidates.tsv
```

That is your **best current dry-run neoantigen candidate table**.
