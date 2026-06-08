"""
Shared configuration — Modal volumes, paths, API endpoints, constants.
"""

import modal

# ── Version ──────────────────────────────────────────────────────────────────

BLOOMONE_VERSION = "4.0.0"

# ── Modal Resources ──────────────────────────────────────────────────────────

APP_NAME = "bloomone"

# Single shared volume for all pipeline data
volume = modal.Volume.from_name("bloomone-data", create_if_missing=True)

# Distributed KV store for job state and pipeline tracking
state_store = modal.Dict.from_name("bloomone-state", create_if_missing=True)

# Mount point inside containers
VOLUME_MOUNT = "/data"

# ── Volume Directory Layout ──────────────────────────────────────────────────

# /data/
# ├── input/           # Raw input files (BAM, FASTQ, MAF)
# ├── reference/       # Reference genome (hg38), proteome
# ├── stage1/          # HLA typing results
# ├── stage2/          # VCF output from Strelka2
# ├── stage3/          # Candidate peptides
# ├── stage4/          # Binding predictions
# ├── stage5/          # Safety-filtered candidates
# ├── stage6/          # Ranked candidates
# └── stage7/          # mRNA constructs

PATHS = {
    "input": f"{VOLUME_MOUNT}/input",
    "reference": f"{VOLUME_MOUNT}/reference",
    "proteome": f"{VOLUME_MOUNT}/reference/human_reviewed_proteome.fasta",
    "hg38": f"{VOLUME_MOUNT}/reference/hg38.fa",
    "stage1": f"{VOLUME_MOUNT}/stage1",
    "stage2": f"{VOLUME_MOUNT}/stage2",
    "stage3": f"{VOLUME_MOUNT}/stage3",
    "stage4": f"{VOLUME_MOUNT}/stage4",
    "stage5": f"{VOLUME_MOUNT}/stage5",
    "stage6": f"{VOLUME_MOUNT}/stage6",
    "stage7": f"{VOLUME_MOUNT}/stage7",
}

# ── API Endpoints ────────────────────────────────────────────────────────────

# Ensembl VEP REST API (public, rate-limited: 15 req/sec, 200 variants/req)
VEP_API_URL = "https://rest.ensembl.org/vep/human/hgvs"
VEP_BATCH_SIZE = 200

# Ensembl sequence API
ENSEMBL_SEQ_URL = "https://rest.ensembl.org/sequence/id"

# UniProt REST API
UNIPROT_API_URL = "https://rest.uniprot.org/uniprotkb/search"

# UniProt proteome download
UNIPROT_PROTEOME_URL = (
    "https://rest.uniprot.org/uniprotkb/stream"
    "?compressed=false&format=fasta"
    "&includeIsoform=true"
    "&query=%28proteome%3AUP000005640%29%20AND%20%28reviewed%3Atrue%29"
)

# IEDB NetMHCpan API (fallback for MHCflurry)
IEDB_API_URL = "https://tools-cluster-interface.iedb.org/tools_api/mhci/"

# GDC (TCGA) API
GDC_API_URL = "https://api.gdc.cancer.gov"
GDC_FILES_ENDPOINT = f"{GDC_API_URL}/files"
GDC_DATA_ENDPOINT = f"{GDC_API_URL}/data"

# cBioPortal API
CBIO_API_URL = "https://www.cbioportal.org/api"

# ── Pipeline Constants ───────────────────────────────────────────────────────

# Peptide generation
KMER_LENGTHS = [8, 9, 10, 11]  # MHC-I standard

# HLA binding thresholds
IC50_THRESHOLD = 500       # nM — strong binder cutoff
RANK_THRESHOLD = 0.5       # percentile rank cutoff
IEDB_BATCH_SIZE = 20       # IEDB API max peptides per request

# Safety filter
IDENTITY_THRESHOLD = 0.80  # ≥80% identity over full peptide → remove
EVALUE_THRESHOLD = 1.0     # E-value ≤ 1 (used with identity check)

# Ranking weights
RANKING_WEIGHTS = {
    "ic50_rank": 0.50,     # IC50 %rank weight
    "vaf": 0.30,           # Variant Allele Frequency weight
    "tpm": 0.20,           # Tumor expression weight (optional)
}

# Ranking weights without RNA-seq (graceful degradation)
RANKING_WEIGHTS_NO_EXPRESSION = {
    "ic50_rank": 0.60,
    "vaf": 0.40,
}

# Ranking
TOP_N_CANDIDATES = 20      # Pass top 20 to mRNA design

# Expression filter
TPM_THRESHOLD = 1.0        # Genes with TPM < 1 are filtered out

# mRNA design
POLY_A_LENGTH = 120        # Standard poly-A tail

# ── Amino Acid Mappings ──────────────────────────────────────────────────────

AA_3TO1 = {
    "Ala": "A", "Arg": "R", "Asn": "N", "Asp": "D", "Cys": "C",
    "Gln": "Q", "Glu": "E", "Gly": "G", "His": "H", "Ile": "I",
    "Leu": "L", "Lys": "K", "Met": "M", "Phe": "F", "Pro": "P",
    "Ser": "S", "Thr": "T", "Trp": "W", "Tyr": "Y", "Val": "V",
    "Ter": "*",
}

# Human-optimized codon table (most frequent codon per amino acid)
CODON_TABLE = {
    "A": "GCC",  "R": "AGG",  "N": "AAC",  "D": "GAC",  "C": "TGC",
    "Q": "CAG",  "E": "GAG",  "G": "GGC",  "H": "CAC",  "I": "ATC",
    "L": "CTG",  "K": "AAG",  "M": "ATG",  "F": "TTC",  "P": "CCC",
    "S": "AGC",  "T": "ACC",  "W": "TGG",  "Y": "TAC",  "V": "GTG",
    "*": "TGA",
}
