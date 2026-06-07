import pandas as pd
import requests
import re
from time import sleep

# ── CONFIG ──────────────────────────────────────────────────────────────────
INPUT_FILE  = "output/missense_mutations.csv"
OUTPUT_FILE = "output/candidate_peptides.csv"
KMER_SIZE   = 9          # NetMHCpan sweet spot; change to 10 or 11 if needed
# ────────────────────────────────────────────────────────────────────────────


# ── STEP 1: Load & pick one patient ─────────────────────────────────────────
print("Loading missense mutations...")
maf = pd.read_csv(INPUT_FILE, low_memory=False)

# Show available patients so you can pick
print(f"\nTotal mutations: {len(maf)}")
print(f"Total patients:  {maf['Tumor_Sample_Barcode'].nunique()}")
print("\nFirst 5 patient IDs:")
print(maf['Tumor_Sample_Barcode'].unique()[:5])

# Pick the first patient automatically (swap this ID to choose a different one)
patient_id = maf['Tumor_Sample_Barcode'].unique()[0]
print(f"\nUsing patient: {patient_id}")

patient_maf = maf[maf['Tumor_Sample_Barcode'] == patient_id].copy()
print(f"Mutations for this patient: {len(patient_maf)}")
# ────────────────────────────────────────────────────────────────────────────


# ── STEP 2: Parse HGVSp_Short → position + amino acid swap ──────────────────
def parse_hgvsp(hgvsp):
    """
    Parse strings like 'p.Val600Glu' or 'p.V600E'
    Returns (position, ref_aa_1letter, alt_aa_1letter) or None if unparseable
    """
    if not isinstance(hgvsp, str):
        return None

    # 3-letter format: p.Val600Glu
    match3 = re.match(r'p\.([A-Z][a-z]{2})(\d+)([A-Z][a-z]{2})', hgvsp)
    # 1-letter format: p.V600E
    match1 = re.match(r'p\.([A-Z])(\d+)([A-Z])', hgvsp)

    aa3to1 = {
        'Ala':'A','Arg':'R','Asn':'N','Asp':'D','Cys':'C',
        'Gln':'Q','Glu':'E','Gly':'G','His':'H','Ile':'I',
        'Leu':'L','Lys':'K','Met':'M','Phe':'F','Pro':'P',
        'Ser':'S','Thr':'T','Trp':'W','Tyr':'Y','Val':'V',
        'Ter':'*'
    }

    if match3:
        ref = aa3to1.get(match3.group(1))
        pos = int(match3.group(2))
        alt = aa3to1.get(match3.group(3))
        if ref and alt:
            return (pos, ref, alt)
    elif match1:
        return (int(match1.group(2)), match1.group(1), match1.group(3))

    return None
# ────────────────────────────────────────────────────────────────────────────


# ── STEP 3: Fetch full protein sequence from UniProt ────────────────────────
_uniprot_cache = {}  # cache so we don't re-fetch the same gene twice

def fetch_protein_sequence(gene_name):
    """
    Query UniProt for the canonical human protein sequence by gene name.
    Returns amino acid string or None.
    """
    if gene_name in _uniprot_cache:
        return _uniprot_cache[gene_name]

    url = (
        f"https://rest.uniprot.org/uniprotkb/search"
        f"?query=gene_exact:{gene_name}+AND+organism_id:9606+AND+reviewed:true"
        f"&fields=sequence"
        f"&format=json"
        f"&size=1"
    )

    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data['results']:
            seq = data['results'][0]['sequence']['value']
            _uniprot_cache[gene_name] = seq
            return seq
    except Exception as e:
        print(f"  UniProt fetch failed for {gene_name}: {e}")

    _uniprot_cache[gene_name] = None
    return None
# ────────────────────────────────────────────────────────────────────────────


# ── STEP 4: Apply mutation + cut 9-mer window ────────────────────────────────
def get_mutant_peptides(protein_seq, pos, ref_aa, alt_aa, k=9):
    """
    Apply the amino acid swap at `pos` (1-indexed) and return all
    k-mer windows that span the mutation site.
    """
    idx = pos - 1  # convert to 0-indexed

    # Sanity check: does the reference AA match the protein sequence?
    if idx >= len(protein_seq):
        return []
    if protein_seq[idx] != ref_aa:
        # Mismatch — protein version in DB may differ; skip
        return []

    # Apply the mutation
    mutant_seq = protein_seq[:idx] + alt_aa + protein_seq[idx+1:]

    # Slide a k-mer window over all positions that include the mutation site
    peptides = []
    for start in range(max(0, idx - k + 1), min(len(mutant_seq) - k + 1, idx + 1)):
        peptide = mutant_seq[start:start + k]
        if len(peptide) == k:
            peptides.append(peptide)

    return peptides
# ────────────────────────────────────────────────────────────────────────────


# ── STEP 5: Run the pipeline ─────────────────────────────────────────────────
print("\nGenerating mutant peptides...")
records = []
skipped = 0

for _, row in patient_maf.iterrows():
    gene     = row['Hugo_Symbol']
    hgvsp    = row.get('HGVSp_Short', '')
    mutation = parse_hgvsp(hgvsp)

    if mutation is None:
        skipped += 1
        continue

    pos, ref_aa, alt_aa = mutation

    # Fetch protein sequence (cached after first call per gene)
    protein_seq = fetch_protein_sequence(gene)
    sleep(0.1)  # be polite to UniProt API

    if protein_seq is None:
        skipped += 1
        continue

    # Generate peptides
    peptides = get_mutant_peptides(protein_seq, pos, ref_aa, alt_aa, k=KMER_SIZE)

    for pep in peptides:
        records.append({
            'patient':   patient_id,
            'gene':      gene,
            'mutation':  hgvsp,
            'position':  pos,
            'peptide':   pep,
        })

print(f"\nDone. Skipped {skipped} unparseable rows.")
print(f"Generated {len(records)} candidate peptides from {len(patient_maf) - skipped} mutations.")

# ── STEP 6: Save output ──────────────────────────────────────────────────────
df_out = pd.DataFrame(records)
df_out.to_csv(OUTPUT_FILE, index=False)
print(f"\nSaved to {OUTPUT_FILE}")
print(df_out.head(10).to_string())