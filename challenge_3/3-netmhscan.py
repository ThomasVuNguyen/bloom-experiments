import pandas as pd
import requests
import time

# ── CONFIG ───────────────────────────────────────────────────────────────────
INPUT_FILE   = "output/candidate_peptides.csv"
OUTPUT_FILE  = "output/binding_predictions.csv"
HLA_ALLELE   = "HLA-A*02:01"
RANK_CUTOFF  = 2.0      # percentile rank threshold — standard strong binder cutoff
BATCH_SIZE   = 20       # IEDB API max peptides per request
SLEEP_SEC    = 1.0      # be polite to IEDB server
# ─────────────────────────────────────────────────────────────────────────────


# ── STEP 1: Load peptides ─────────────────────────────────────────────────────
print("Loading candidate peptides...")
df = pd.read_csv(INPUT_FILE)
peptides = df['peptide'].tolist()
print(f"Total peptides to score: {len(peptides)}")
# ─────────────────────────────────────────────────────────────────────────────


# ── STEP 2: Query IEDB API in batches ────────────────────────────────────────
def query_iedb(peptide_batch, allele):
    """
    Submit a batch of peptides to IEDB NetMHCpan API.
    Returns a list of dicts with peptide, ic50, rank.
    """
    url = "https://tools-cluster-interface.iedb.org/tools_api/mhci/"
    
    payload = {
        "method":        "netmhcpan_ba",
        "sequence_text": "\n".join(peptide_batch),
        "allele":        allele,
        "length":        str(len(peptide_batch[0])),  # all same length
    }

    try:
        resp = requests.post(url, data=payload, timeout=60)
        resp.raise_for_status()
        
        results = []
        lines = resp.text.strip().split("\n")
        
        for line in lines:
            if line.startswith("allele") or not line.strip():
                continue  # skip header
            parts = line.split("\t")
            if len(parts) >= 10:
                results.append({
                    "allele":  parts[0],
                    "peptide": parts[5],   # peptide sequence
                    "ic50":    float(parts[8]) if parts[8] != "NA" else None,
                    "rank":    float(parts[9]) if parts[9] != "NA" else None,
                })
        return results

    except Exception as e:
        print(f"  API error: {e}")
        return []


print(f"\nRunning NetMHCpan via IEDB API ({HLA_ALLELE})...")
print(f"Batching {len(peptides)} peptides in groups of {BATCH_SIZE}...\n")

all_results = []
total_batches = (len(peptides) + BATCH_SIZE - 1) // BATCH_SIZE

for i in range(0, len(peptides), BATCH_SIZE):
    batch = peptides[i:i + BATCH_SIZE]
    batch_num = (i // BATCH_SIZE) + 1
    print(f"  Batch {batch_num}/{total_batches}...", end=" ", flush=True)
    
    results = query_iedb(batch, HLA_ALLELE)
    all_results.extend(results)
    print(f"got {len(results)} results")
    
    time.sleep(SLEEP_SEC)

print(f"\nTotal raw results: {len(all_results)}")
# ─────────────────────────────────────────────────────────────────────────────


# ── STEP 3: Filter to strong binders ─────────────────────────────────────────
results_df = pd.DataFrame(all_results)

# Drop rows with missing scores
results_df = results_df.dropna(subset=['rank', 'ic50'])

# Merge back with original metadata (gene, mutation, patient)
# Match on peptide sequence
merged = results_df.merge(
    df[['patient', 'gene', 'mutation', 'position', 'peptide']],
    on='peptide',
    how='left'
)

# Filter strong binders
strong = merged[merged['rank'] <= RANK_CUTOFF].copy()
strong = strong.sort_values('rank')

print(f"Strong binders (rank ≤ {RANK_CUTOFF}%): {len(strong)}")
print(f"Weak/non-binders discarded: {len(merged) - len(strong)}")
# ─────────────────────────────────────────────────────────────────────────────


# ── STEP 4: Save output ───────────────────────────────────────────────────────
strong.to_csv(OUTPUT_FILE, index=False)
print(f"\nSaved to {OUTPUT_FILE}")
print("\nTop 10 strongest binders:")
print(strong[['gene', 'mutation', 'peptide', 'ic50', 'rank']].head(10).to_string())