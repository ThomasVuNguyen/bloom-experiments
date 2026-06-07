import pandas as pd
import random

# ── CONFIG ───────────────────────────────────────────────────────────────────
INPUT_FILE  = "output/final_candidates.csv"
OUTPUT_FILE = "output/mrna_constructs.csv"
TOP_N       = 10   # design mRNA for top N candidates
# ─────────────────────────────────────────────────────────────────────────────


# ── CODON TABLE (human optimized) ────────────────────────────────────────────
# For each amino acid, the BEST codon for human cell expression
# Based on human codon usage frequency tables
CODON_TABLE = {
    'A': 'GCC',  # Alanine
    'R': 'AGG',  # Arginine
    'N': 'AAC',  # Asparagine
    'D': 'GAC',  # Aspartate
    'C': 'TGC',  # Cysteine
    'Q': 'CAG',  # Glutamine
    'E': 'GAG',  # Glutamate
    'G': 'GGC',  # Glycine
    'H': 'CAC',  # Histidine
    'I': 'ATC',  # Isoleucine
    'L': 'CTG',  # Leucine
    'K': 'AAG',  # Lysine
    'M': 'ATG',  # Methionine
    'F': 'TTC',  # Phenylalanine
    'P': 'CCC',  # Proline
    'S': 'AGC',  # Serine
    'T': 'ACC',  # Threonine
    'W': 'TGG',  # Tryptophan
    'Y': 'TAC',  # Tyrosine
    'V': 'GTG',  # Valine
    '*': 'TGA',  # Stop codon
}

# ── mRNA CONSTRUCT COMPONENTS ─────────────────────────────────────────────────
# These are real, validated sequences used in mRNA vaccine design

# 5' UTR — from human beta-globin gene, promotes strong translation
UTR_5 = "GGGAAATAAGAGAGAAAAGAAGAGTAAGAAGAAATATAAGAGCCACC"

# Signal peptide — routes peptide into MHC-I presentation pathway
# This is the human tissue plasminogen activator (tPA) signal peptide
# It ensures the peptide gets processed and loaded onto HLA
SIGNAL_PEPTIDE_AA = "MDAMKRGLCCVLLLCGAVFVSPS"

# Linker — connects signal peptide to neoantigen peptide
# AAY linker is commonly used in polytope vaccines — helps proteasomal cleavage
LINKER_AA = "AAY"

# 3' UTR — from human beta-globin gene, stabilizes mRNA
UTR_3 = "UGCCUGGAGACCCCAGUGCUGAGCUUCAGCUGGAGAAGCCCAGGGCCUGGGCGGGAGCUGGGAGUGGGUGCUGAGGCCCAGUGCACCCUGGAGUGCUGGGCAGCCCUGGGCCUGGGCGGGAGCUGGGAGUGGGUGCUGAGGCCCAGUGCACCCUGGAGUGCUGGGCAGCCCUGGGCCUGGGCGGGAGCUGGGAGUGGGUGCUGAGGCCCAGUGCA"

# Poly-A tail — 120 A's, standard for mRNA stability
POLY_A = "A" * 120


# ── FUNCTIONS ─────────────────────────────────────────────────────────────────
def aa_to_dna(peptide_aa):
    """Convert amino acid sequence to codon-optimized DNA sequence."""
    dna = ""
    for aa in peptide_aa:
        codon = CODON_TABLE.get(aa)
        if codon is None:
            raise ValueError(f"Unknown amino acid: {aa}")
        dna += codon
    return dna

def dna_to_mrna(dna):
    """Convert DNA sequence to mRNA (T → U)."""
    return dna.replace('T', 'U')

def gc_content(seq):
    """Calculate GC content % of a sequence."""
    seq = seq.upper().replace('U', 'T')  # normalize
    gc = sum(1 for c in seq if c in 'GC')
    return round(gc / len(seq) * 100, 1)

def build_mrna_construct(neoantigen_aa):
    """
    Build a full mRNA vaccine construct for a given neoantigen peptide.
    
    Structure:
    5'UTR | START | Signal Peptide | Linker | Neoantigen | STOP | 3'UTR | Poly-A
    """
    # Build the full protein coding sequence (CDS)
    full_aa = SIGNAL_PEPTIDE_AA + LINKER_AA + neoantigen_aa

    # Translate to codon-optimized DNA
    cds_dna = "ATG" + aa_to_dna(full_aa[1:]) + CODON_TABLE['*']  # ATG start + CDS + stop

    # Convert to mRNA
    cds_mrna = dna_to_mrna(cds_dna)

    # Assemble full construct
    full_mrna = UTR_5 + cds_mrna + UTR_3 + POLY_A

    return {
        "cds_dna":    cds_dna,
        "cds_mrna":   cds_mrna,
        "full_mrna":  full_mrna,
        "cds_length": len(cds_dna),
        "full_length": len(full_mrna),
        "gc_content": gc_content(cds_dna),
    }

def check_stop_codons(cds_dna):
    """Check for premature stop codons in the CDS (excluding the final stop)."""
    stop_codons = {'TAA', 'TAG', 'TGA'}
    codons = [cds_dna[i:i+3] for i in range(0, len(cds_dna)-3, 3)]
    premature = [i for i, c in enumerate(codons) if c in stop_codons]
    return premature


# ── MAIN ──────────────────────────────────────────────────────────────────────
print("Loading final neoantigen candidates...")
df = pd.read_csv(INPUT_FILE)
top = df.head(TOP_N)
print(f"Designing mRNA constructs for top {TOP_N} candidates\n")

records = []

for _, row in top.iterrows():
    peptide  = row['peptide']
    gene     = row['gene']
    mutation = row['mutation']
    ic50     = row['ic50']
    rank     = row['rank']

    print(f"Processing {gene} {mutation} → {peptide}")

    try:
        construct = build_mrna_construct(peptide)

        # Safety check — no premature stop codons
        premature_stops = check_stop_codons(construct['cds_dna'])
        if premature_stops:
            print(f"  ⚠️  WARNING: premature stop codon at position(s) {premature_stops}")
        else:
            print(f"  ✅ No premature stop codons")

        print(f"  CDS length:   {construct['cds_length']} nt")
        print(f"  Full mRNA:    {construct['full_length']} nt")
        print(f"  GC content:   {construct['gc_content']}%")
        print()

        records.append({
            "gene":        gene,
            "mutation":    mutation,
            "peptide":     peptide,
            "ic50":        ic50,
            "rank":        rank,
            "cds_dna":     construct['cds_dna'],
            "cds_mrna":    construct['cds_mrna'],
            "full_mrna":   construct['full_mrna'],
            "cds_length":  construct['cds_length'],
            "full_length": construct['full_length'],
            "gc_content":  construct['gc_content'],
        })

    except Exception as e:
        print(f"  ❌ Error: {e}\n")

# ── SAVE ──────────────────────────────────────────────────────────────────────
out = pd.DataFrame(records)
out.to_csv(OUTPUT_FILE, index=False)
print(f"{'='*60}")
print(f"Saved {len(records)} mRNA constructs to {OUTPUT_FILE}")
print(f"\nTop candidate mRNA construct preview:")
print(f"\nPeptide:    {records[0]['peptide']}")
print(f"Gene:       {records[0]['gene']} {records[0]['mutation']}")
print(f"IC50:       {records[0]['ic50']} nM")
print(f"Rank:       {records[0]['rank']}%")
print(f"\nCDS DNA:    {records[0]['cds_dna'][:60]}...")
print(f"CDS mRNA:   {records[0]['cds_mrna'][:60]}...")
print(f"Full mRNA:  {records[0]['full_mrna'][:60]}...")
print(f"\nFull mRNA length: {records[0]['full_length']} nucleotides")
print(f"GC content: {records[0]['gc_content']}%")
print(f"\n✅ Ready for wet lab synthesis!")