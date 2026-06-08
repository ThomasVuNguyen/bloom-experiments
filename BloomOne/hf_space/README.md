---
title: BloomOne
emoji: 🧬
colorFrom: blue
colorTo: purple
sdk: gradio
sdk_version: "5.31.0"
python_version: "3.12"
app_file: app.py
pinned: true
license: apache-2.0
short_description: AI-powered personalized neoantigen mRNA vaccine design
---

# 🧬 BloomOne

**Personalized Neoantigen Vaccine Pipeline** — powered by Gemma 4 12B

Transform tumor DNA into personalized mRNA neoantigen vaccine constructs through a 7-stage computational pipeline, orchestrated by an AI assistant.

## Pipeline Stages

1. **Data Ingestion** — Fetch mutations from TCGA/cBioPortal
2. **Mutation Calling** — Strelka2 somatic variant calling
3. **Peptide Generation** — 8-11mer mutant peptide candidates
4. **HLA Binding Prediction** — MHCflurry/NetMHCpan
5. **Safety Filter** — Remove self-matching peptides
6. **Candidate Ranking** — Score by binding + VAF + expression
7. **mRNA Design** — Codon-optimized vaccine constructs

⚠️ **All outputs are for RESEARCH USE ONLY.** Not validated for clinical use.
