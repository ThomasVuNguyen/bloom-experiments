"""
Shared utility functions — refactored from challenge_3 pipeline scripts.

Includes: HGVSp parsing, protein sequence fetching, FASTA parsing,
codon translation, and sliding window peptide generation.
"""

from __future__ import annotations

import re
import time
from typing import Optional

import requests

from bloomone.config import (
    AA_3TO1,
    CODON_TABLE,
    ENSEMBL_SEQ_URL,
    KMER_LENGTHS,
    UNIPROT_API_URL,
)


# ── HGVSp Parsing ────────────────────────────────────────────────────────────


def parse_hgvsp_short(
    hgvsp: str,
) -> Optional[tuple[int, str, str]]:
    """
    Parse protein change notation into (position, ref_aa, alt_aa).

    Supports formats:
      - 3-letter with prefix: p.Val600Glu → (600, 'V', 'E')
      - 1-letter with prefix: p.V600E    → (600, 'V', 'E')
      - 1-letter without prefix: V600E   → (600, 'V', 'E')  (cBioPortal)
      - 3-letter without prefix: Val600Glu → (600, 'V', 'E')

    Returns None if the string is unparseable.
    """
    if not isinstance(hgvsp, str):
        return None

    hgvsp = hgvsp.strip()

    # Normalize: add p. prefix if missing
    if not hgvsp.startswith("p."):
        hgvsp = f"p.{hgvsp}"

    # 3-letter format: p.Val600Glu
    match3 = re.match(r"p\.([A-Z][a-z]{2})(\d+)([A-Z][a-z]{2})", hgvsp)
    if match3:
        ref = AA_3TO1.get(match3.group(1))
        pos = int(match3.group(2))
        alt = AA_3TO1.get(match3.group(3))
        if ref and alt:
            return (pos, ref, alt)

    # 1-letter format: p.V600E
    match1 = re.match(r"p\.([A-Z])(\d+)([A-Z])", hgvsp)
    if match1:
        return (int(match1.group(2)), match1.group(1), match1.group(3))

    return None


# ── Protein Sequence Fetching ─────────────────────────────────────────────────

# In-memory cache (per-container lifecycle — OK for Modal stateless functions
# because each tool call runs in a single container invocation)
_uniprot_cache: dict[str, Optional[str]] = {}
_ensembl_cache: dict[str, Optional[str]] = {}


def fetch_protein_from_uniprot(gene_name: str) -> Optional[str]:
    """
    Fetch the canonical human protein sequence by gene name from UniProt.
    Results are cached per-container to avoid redundant API calls.
    """
    if gene_name in _uniprot_cache:
        return _uniprot_cache[gene_name]

    url = UNIPROT_API_URL
    params = {
        "query": f"gene_exact:{gene_name} AND organism_id:9606 AND reviewed:true",
        "fields": "sequence",
        "format": "json",
        "size": "1",
    }

    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if data.get("results"):
            seq = data["results"][0]["sequence"]["value"]
            _uniprot_cache[gene_name] = seq
            return seq
    except Exception as e:
        print(f"  UniProt fetch failed for {gene_name}: {e}")

    _uniprot_cache[gene_name] = None
    return None


def fetch_protein_from_ensembl(transcript_id: str) -> Optional[str]:
    """
    Fetch protein sequence from Ensembl using transcript ID.
    Preferred when transcript_id is available (more precise than gene lookup).
    """
    if transcript_id in _ensembl_cache:
        return _ensembl_cache[transcript_id]

    url = f"{ENSEMBL_SEQ_URL}/{transcript_id}"
    params = {"type": "protein"}
    headers = {"Content-Type": "text/plain"}

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=15)
        if not resp.ok:
            _ensembl_cache[transcript_id] = None
            return None

        seq = "".join(resp.text.split())

        # Guard against HTML error responses
        if not seq or seq.startswith("{") or "<html" in seq.lower():
            _ensembl_cache[transcript_id] = None
            return None

        _ensembl_cache[transcript_id] = seq
        return seq
    except Exception as e:
        print(f"  Ensembl fetch failed for {transcript_id}: {e}")

    _ensembl_cache[transcript_id] = None
    return None


def fetch_protein_sequence(
    gene_name: str,
    transcript_id: Optional[str] = None,
    polite_delay: float = 0.02,
) -> Optional[str]:
    """
    Fetch protein sequence, trying Ensembl transcript first, then UniProt gene.
    Adds a polite delay between API calls.
    """
    seq = None

    # Prefer Ensembl transcript (more precise)
    if transcript_id:
        seq = fetch_protein_from_ensembl(transcript_id)
        time.sleep(polite_delay)

    # Fallback to UniProt gene lookup
    if seq is None:
        seq = fetch_protein_from_uniprot(gene_name)
        time.sleep(polite_delay)

    return seq


# ── FASTA Parsing ─────────────────────────────────────────────────────────────


def read_fasta(path: str) -> list[tuple[str, str]]:
    """
    Parse a FASTA file into a list of (header, sequence) tuples.
    """
    records = []
    header = None
    seq_parts: list[str] = []

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


def build_sequence_index(
    proteome: list[tuple[str, str]],
) -> str:
    """
    Concatenate all proteome sequences into a single string for fast
    substring searching. Returns the concatenated string with separator
    characters between proteins.
    """
    # Use a character that can't appear in protein sequences as separator
    return "\x00".join(seq for _, seq in proteome)


# ── Peptide Generation ────────────────────────────────────────────────────────


def generate_spanning_peptides(
    mutant_seq: str,
    mutation_index_0based: int,
    kmer_lengths: Optional[list[int]] = None,
) -> list[dict]:
    """
    Generate all k-mer peptides that span the mutation site.

    For each kmer length (default 8-11), slides a window across the mutant
    sequence such that the mutation is included in every output peptide.

    Returns list of dicts with:
      - peptide: the amino acid sequence
      - peptide_length: length of the peptide
      - peptide_start_in_protein: 1-indexed start position in protein
      - mutation_offset_in_peptide: 1-indexed position of mutation within peptide
    """
    if kmer_lengths is None:
        kmer_lengths = KMER_LENGTHS

    results = []

    for length in kmer_lengths:
        start_min = max(0, mutation_index_0based - length + 1)
        start_max = min(mutation_index_0based, len(mutant_seq) - length)

        for start in range(start_min, start_max + 1):
            peptide = mutant_seq[start : start + length]

            if len(peptide) != length:
                continue
            if "*" in peptide or "X" in peptide:
                continue

            results.append(
                {
                    "peptide": peptide,
                    "peptide_length": length,
                    "peptide_start_in_protein": start + 1,
                    "mutation_offset_in_peptide": mutation_index_0based - start + 1,
                }
            )

    return results


def apply_mutation_and_generate_peptides(
    protein_seq: str,
    pos_1based: int,
    ref_aa: str,
    alt_aa: str,
    kmer_lengths: Optional[list[int]] = None,
) -> list[dict]:
    """
    Apply an amino acid substitution and generate all spanning peptides.

    Returns empty list if:
      - Position is out of bounds
      - Reference amino acid doesn't match the protein sequence
    """
    idx = pos_1based - 1  # Convert to 0-indexed

    if idx < 0 or idx >= len(protein_seq):
        return []
    if protein_seq[idx] != ref_aa:
        return []

    # Apply the mutation
    mutant_seq = protein_seq[:idx] + alt_aa + protein_seq[idx + 1 :]

    return generate_spanning_peptides(mutant_seq, idx, kmer_lengths)


# ── Codon Translation ────────────────────────────────────────────────────────


def aa_to_dna(peptide_aa: str) -> str:
    """Convert amino acid sequence to codon-optimized DNA sequence."""
    codons = []
    for aa in peptide_aa:
        codon = CODON_TABLE.get(aa)
        if codon is None:
            raise ValueError(f"Unknown amino acid: {aa}")
        codons.append(codon)
    return "".join(codons)


def dna_to_mrna(dna: str) -> str:
    """Convert DNA sequence to mRNA (T → U)."""
    return dna.replace("T", "U")


def gc_content(seq: str) -> float:
    """Calculate GC content percentage of a nucleotide sequence."""
    seq = seq.upper().replace("U", "T")
    gc = sum(1 for c in seq if c in "GC")
    return round(gc / len(seq) * 100, 1) if seq else 0.0


def check_premature_stops(cds_dna: str) -> list[int]:
    """
    Check for premature stop codons in a CDS (excluding the final stop).
    Returns list of codon indices (0-based) that are premature stops.
    """
    stop_codons = {"TAA", "TAG", "TGA"}
    # Exclude the last codon (expected stop)
    codons = [cds_dna[i : i + 3] for i in range(0, len(cds_dna) - 3, 3)]
    return [i for i, c in enumerate(codons) if c in stop_codons]


# ── Self-Similarity Checking ─────────────────────────────────────────────────


def compute_peptide_identity(
    peptide: str, target: str
) -> float:
    """
    Compute identity between a peptide and a same-length substring.
    Returns fraction of matching residues (0.0 to 1.0).
    """
    if len(peptide) != len(target):
        return 0.0
    matches = sum(1 for a, b in zip(peptide, target) if a == b)
    return matches / len(peptide)


def find_proteome_matches(
    peptide: str,
    proteome_records: list[tuple[str, str]],
    identity_threshold: float = 0.80,
) -> list[dict]:
    """
    Find all proteins in the proteome where a window of the same length
    as the peptide has identity ≥ threshold.

    For 8-11mers, this effectively catches:
      - Exact matches (100% identity)
      - Near-matches (≥80% identity, e.g. 8/9 matching residues for 9-mers)

    Returns list of match dicts with protein_header, identity, matched_substring.
    """
    pep_len = len(peptide)
    matches = []

    for header, seq in proteome_records:
        # Slide a window of peptide length across the protein
        for i in range(len(seq) - pep_len + 1):
            window = seq[i : i + pep_len]
            identity = compute_peptide_identity(peptide, window)

            if identity >= identity_threshold:
                matches.append(
                    {
                        "protein_header": header,
                        "position_start": i + 1,
                        "position_end": i + pep_len,
                        "identity": round(identity, 3),
                        "matched_substring": window,
                    }
                )
                # One match per protein is enough to flag it
                break

    return matches
