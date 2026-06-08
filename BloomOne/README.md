# Building BloomOne

BloomOne is a set of MCP tools available for AI agents to complete the full pipeline of turning a tumor DNA and a patient's healthy DNA into a personalized neoantigen vaccine.

## Stack
- **MCP & backend:** Modal (compute — GPU/CPU burst workloads)
- **GCP:** Gemini API (2.5 Pro), use ADC for authentication — zero leakable secrets/API keys
- **HF:** Gradio (UI requirement)

---

## Stage 1: Data Ingestion (MCP-1)

**Input:**
- Tumor genomic DNA file (BAM/FASTQ)
- Patient healthy cell genomic DNA file (BAM/FASTQ)
- HLA alleles (if known)
- RNA-seq expression data (optional — TPM values per gene)

**HLA Typing (if alleles not provided):**
- Tool: [OptiType](https://github.com/FRED-2/OptiType) — state-of-the-art HLA-I genotyping from sequencing data
- Hosted on Modal CPU
- Predicts HLA-A, HLA-B, HLA-C alleles from BAM/FASTQ input

**Data Sources (if not user-provided):**
- TCGA via GDC API
- cBioPortal API
- ICGC (International Cancer Genome Consortium)

**Optional Expression Filter:**
If RNA-seq TPM data is available, mutations in genes with TPM < 1 are filtered out before peptide generation (Stage 3). If RNA-seq is not available, the pipeline runs without it and flags output as "expression not validated." Graceful degradation — not a hard requirement.

---

## Stage 2: Mutation Calling (MCP-2)

**Input:**
- Tumor BAM file (sequencing reads from tumor tissue)
- Normal BAM file (sequencing reads from healthy tissue)
- Reference genome (hg38) — pre-baked into Modal image to avoid re-downloading ~3GB per run

> If coming from cBioPortal MAF — skip this stage entirely, mutations are pre-called.

**Output:**
- VCF file (list of somatic mutations — positions in the genome where tumor DNA differs from normal)

**Algorithm:**
- **Strelka2** — fast, accurate somatic variant caller optimized for high-throughput use
- Deployed on Modal with 96 vCPUs for maximum parallelism
- Compares tumor vs normal, filters germline variants, outputs only tumor-specific somatic mutations

---

## Stage 3: Peptide Generation (MCP-3)

**Input:**
- Somatic mutations (VCF or MAF file)
- Reference proteome (human protein sequences)

**Output:**
- List of mutant peptides, 8–11 amino acids long (8mers, 9mers, 10mers, 11mers)
- Each peptide contains the mutation at various positions within the window

**Algorithm:**
- **Sliding window** — for each mutation, extract the surrounding protein sequence and slide a window of length 8, 9, 10, 11 across it, generating all possible peptide fragments that contain the mutation. Hosted on Modal CPU.
- **VEP (Variant Effect Predictor)** by Ensembl — called via the public REST API to annotate variant consequences (missense, frameshift, etc.)

---

## Stage 4: HLA Binding Prediction (MCP-4)

> Scope: **MHC Class I only.** MHC-II (CD4+ T-helper responses, 15-24mers) is out of scope for v1.

**Input:**
- Peptide candidates (8–11mers from Stage 3)
- Patient HLA-I type (e.g., HLA-A*02:01)

**Output:**
- Ranked list of strong binders
- Binding score per peptide (IC50 in nM, lower = stronger binding)
- Filter: IC50 < 500nM or %rank < 0.5

**Algorithm:**
- Neural network trained on experimental binding data. Predicts how strongly each peptide binds to the patient's specific HLA-I allele.
- **Primary:** MHCflurry 2.0 (OpenVax), hosted on Modal GPU
- **Fallback:** NetMHCpan 4.1 (DTU Denmark)

---

## Stage 5: Safety Filter (MCP-5)

**Input:**
- Strong binders from Stage 4 (IC50 < 500nM)
- Human proteome reference

**Output:**
- Filtered list of safe candidates that do NOT match healthy human proteins
- Anything that matches human proteins gets removed — prevents T cells from attacking healthy tissue

**Algorithm:**
- **Diamond** (BLAST-compatible, ~100x faster) — compares each peptide sequence against the human proteome database. Self-hosted on Modal.

**Removal Criteria (both must be true):**
- Sequence identity ≥ 80% over full peptide length
- E-value ≤ 1

> Consistent with pVACtools and published neoantigen pipelines.

**Key parameters for short peptides (8–11mers):**
- Word size: 2 (critical — default is too large for short peptides)
- E-value threshold: 1
- Matrix: BLOSUM62
- Database: UniProt human proteome (~20,000 proteins)

---

## Stage 6: Candidate Ranking (MCP-6)

**Input:**
- Safe neoantigen candidates from Stage 5
- VCF data (for variant allele frequency)
- RNA-seq expression data (optional — TPM values)

**Output:**
- Top 20 ranked neoantigen candidates, passed to Stage 7

**Scoring Model:**

| Weight | Feature | Source |
|--------|---------|--------|
| 50% | IC50 %rank | Stage 4 (MHCflurry / NetMHCpan) |
| 30% | Variant Allele Frequency (VAF) | VCF from Stage 2 |
| 20% | Tumor expression (TPM) | RNA-seq (optional) |

**Graceful degradation:** If RNA-seq is not available, expression weight is redistributed (IC50 %rank 60%, VAF 40%) and output is flagged as "expression not validated."

---

## Stage 7: mRNA Construct Design (MCP-7)

**Input:**
- Top 20 neoantigen candidates from Stage 6

**Output:**
- Complete mRNA sequence ready for synthesis, including:
  - Signal peptide
  - Neoantigen peptide sequences (concatenated)
  - UTRs (5' and 3' untranslated regions)
  - Poly-A tail
  - Codon optimized sequence

**Algorithm / Tools:**

**Codon Optimization:**
- Tool: Python Codon Optimization Library (`python-codon-tables`) or GenScript's free API
- Replaces codons with human-preferred synonymous codons for better expression
- Complexity: low, pure computation

**UTR Design:**
- Use known high-expression open UTR sequences (e.g., alpha-globin 3'UTR, beta-globin 5'UTR)
- Static templates, no computation needed

**Poly-A Tail:**
- Standard 120 adenine tail
- Static, no computation needed

**Tools:**
- Codon Optimizer: `python-codon-tables` (open source, pip install)
- mRNA structure prediction: ViennaRNA package (open source, predicts mRNA secondary structure for stability)
- Combined optimization: LinearDesign (Meta, open source) — optimizes both codon usage and mRNA structure simultaneously. Most advanced option. Non-commercial license — acceptable for internal use.

---

## v2 Roadmap

- **Immunogenicity scoring:** HLA binding ≠ immunogenicity. Deliberately excluded from v1 — current computational tools (e.g., IEDB) are insufficiently validated to meaningfully rerank candidates. Wet lab validation (future Stage 8) is the ground truth we're building toward. Immunogenicity scoring will be added in v2 once we have our own wet lab feedback data to calibrate against.
- **MHC-II binding prediction:** CD4+ T-helper responses for durable vaccine efficacy.
- **Delivery vehicle design:** LNP formulation optimization.
