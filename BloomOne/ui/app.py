"""
BloomOne Gradio UI — Simple pipeline runner.

Upload files → configure → run pipeline → view results.
"""

from __future__ import annotations

import json
import os
import tempfile

import gradio as gr


def run_pipeline(
    tumor_file,
    hla_alleles: str,
    patient_id: str,
    rna_seq_file,
    data_source: str,
    tcga_case_id: str,
    cbio_study_id: str,
    cbio_sample_id: str,
    top_n: int,
    progress=gr.Progress(),
):
    """Execute the BloomOne pipeline."""
    try:
        from bloomone.stages.stage3_peptides import generate_peptides
        from bloomone.stages.stage4_binding import predict_binding
        from bloomone.stages.stage5_safety import filter_self_similarity
        from bloomone.stages.stage6_ranking import rank_candidates
        from bloomone.stages.stage7_mrna import design_mrna

        logs = []

        # Parse HLA alleles
        alleles = [a.strip() for a in hla_alleles.split(",") if a.strip()]
        if not alleles:
            return "❌ Please provide at least one HLA allele", "", ""

        # Determine input path
        if data_source == "Local Upload":
            if tumor_file is None:
                return "❌ Please upload a tumor MAF/BAM file", "", ""
            maf_path = tumor_file.name
        elif data_source == "TCGA (GDC)":
            from bloomone.stages.stage1_ingest import fetch_tcga_data

            progress(0.05, desc="Fetching from TCGA...")
            result = fetch_tcga_data(tcga_case_id)
            maf_path = result.maf_path
            patient_id = result.patient_id
        elif data_source == "cBioPortal":
            from bloomone.stages.stage1_ingest import fetch_cbio_data

            progress(0.05, desc="Fetching from cBioPortal...")
            result = fetch_cbio_data(cbio_study_id, cbio_sample_id)
            maf_path = result.maf_path
            patient_id = result.patient_id
        else:
            return "❌ Unknown data source", "", ""

        tpm_path = rna_seq_file.name if rna_seq_file else None

        # Stage 3
        progress(0.15, desc="Stage 3: Generating peptides...")
        logs.append("═" * 50)
        logs.append("STAGE 3: Peptide Generation")
        peptide_result = generate_peptides(
            maf_path=maf_path, patient_id=patient_id, tpm_path=tpm_path
        )
        logs.append(
            f"  ✅ {peptide_result.total_candidates} candidates "
            f"({peptide_result.unique_peptides} unique)"
        )

        # Stage 4
        progress(0.35, desc="Stage 4: Predicting HLA binding...")
        logs.append("═" * 50)
        logs.append("STAGE 4: HLA Binding Prediction")
        binding_result = predict_binding(
            peptides_path=peptide_result.candidates_path,
            hla_alleles=alleles,
            patient_id=patient_id,
        )
        logs.append(f"  ✅ {binding_result.strong_binders} strong binders")

        if binding_result.strong_binders == 0:
            return (
                "⚠️ No strong binders found. Try different HLA alleles.",
                "\n".join(logs),
                "",
            )

        # Stage 5
        progress(0.55, desc="Stage 5: Safety filtering...")
        logs.append("═" * 50)
        logs.append("STAGE 5: Safety Filter")
        safety_result = filter_self_similarity(
            binders_path=binding_result.predictions_path,
            patient_id=patient_id,
        )
        logs.append(
            f"  ✅ {safety_result.total_safe} safe "
            f"({safety_result.total_removed} removed)"
        )

        if safety_result.total_safe == 0:
            return (
                "⚠️ All candidates matched human proteome. No safe candidates.",
                "\n".join(logs),
                "",
            )

        # Stage 6
        progress(0.75, desc="Stage 6: Ranking candidates...")
        logs.append("═" * 50)
        logs.append("STAGE 6: Candidate Ranking")
        ranking_result = rank_candidates(
            safe_path=safety_result.safe_path,
            tpm_path=tpm_path,
            patient_id=patient_id,
            top_n=top_n,
        )
        logs.append(f"  ✅ Top {ranking_result.total_ranked} ranked")

        # Stage 7
        progress(0.90, desc="Stage 7: Designing mRNA constructs...")
        logs.append("═" * 50)
        logs.append("STAGE 7: mRNA Construct Design")
        mrna_result = design_mrna(
            ranked_path=ranking_result.ranked_path,
            patient_id=patient_id,
            top_n=top_n,
        )
        logs.append(f"  ✅ {mrna_result.total_designed} mRNA constructs designed")

        progress(1.0, desc="Pipeline complete!")

        # Build summary
        summary = f"""# 🧬 BloomOne Pipeline Complete

**Patient:** {patient_id}
**HLA Alleles:** {', '.join(alleles)}
**Expression Data:** {'✅ Available' if tpm_path else '❌ Not provided'}

## Results Summary

| Stage | Metric | Count |
|-------|--------|-------|
| 3 | Candidate Peptides | {peptide_result.total_candidates} |
| 3 | Unique Peptides | {peptide_result.unique_peptides} |
| 4 | Strong Binders | {binding_result.strong_binders} |
| 5 | Self-matches Removed | {safety_result.total_removed} |
| 5 | Safe Candidates | {safety_result.total_safe} |
| 6 | Top Ranked | {ranking_result.total_ranked} |
| 7 | mRNA Constructs | {mrna_result.total_designed} |

## Output Files
- Peptides: `{peptide_result.candidates_path}`
- Binding: `{binding_result.predictions_path}`
- Safe: `{safety_result.safe_path}`
- Ranked: `{ranking_result.ranked_path}`
- mRNA: `{mrna_result.constructs_path}`

## Top 5 Candidates
"""
        for c in mrna_result.constructs[:5]:
            summary += (
                f"\n**#{c.rank}** {c.gene} {c.hgvsp_short} → `{c.peptide}` | "
                f"IC50: {c.ic50:.1f}nM | GC: {c.gc_content}% | "
                f"mRNA: {c.full_length}nt"
            )

        if mrna_result.polytope_length:
            summary += f"\n\n**Polytope mRNA:** {mrna_result.polytope_length} nt"

        summary += "\n\n✅ **Ready for wet lab synthesis!**"

        # mRNA preview
        mrna_preview = ""
        if mrna_result.constructs:
            top = mrna_result.constructs[0]
            mrna_preview = f"""Top candidate mRNA construct:

Peptide:  {top.peptide}
Gene:     {top.gene} {top.hgvsp_short}
IC50:     {top.ic50:.1f} nM
GC:       {top.gc_content}%

CDS DNA (first 120nt):
{top.cds_dna[:120]}...

Full mRNA (first 120nt):
{top.full_mrna[:120]}...

Full mRNA length: {top.full_length} nt
"""

        return summary, "\n".join(logs), mrna_preview

    except Exception as e:
        import traceback

        return f"❌ Pipeline error: {str(e)}", traceback.format_exc(), ""


# ── Gradio Interface ─────────────────────────────────────────────────────────

with gr.Blocks(
    title="BloomOne — Neoantigen Vaccine Pipeline",
    theme=gr.themes.Soft(),
) as demo:
    gr.Markdown(
        """
        # 🧬 BloomOne
        ### Personalized Neoantigen Vaccine Pipeline

        Transform tumor DNA into personalized mRNA vaccine constructs in 7 stages.
        """
    )

    with gr.Row():
        with gr.Column(scale=1):
            gr.Markdown("### Input Configuration")

            data_source = gr.Radio(
                choices=["Local Upload", "TCGA (GDC)", "cBioPortal"],
                value="Local Upload",
                label="Data Source",
            )

            # Local upload inputs
            with gr.Group(visible=True) as local_group:
                tumor_file = gr.File(
                    label="Tumor MAF/BAM File",
                    file_types=[".maf", ".bam", ".fastq", ".txt", ".gz"],
                )
                rna_seq_file = gr.File(
                    label="RNA-seq TPM File (Optional)",
                    file_types=[".tsv", ".csv", ".txt"],
                )

            # TCGA inputs
            with gr.Group(visible=False) as tcga_group:
                tcga_case_id = gr.Textbox(
                    label="TCGA Case ID",
                    placeholder="TCGA-BF-A3DL-01",
                )

            # cBioPortal inputs
            with gr.Group(visible=False) as cbio_group:
                cbio_study_id = gr.Textbox(
                    label="Study ID",
                    placeholder="skcm_tcga_pan_can_atlas_2018",
                )
                cbio_sample_id = gr.Textbox(
                    label="Sample ID",
                    placeholder="TCGA-BF-A3DL-01",
                )

            hla_alleles = gr.Textbox(
                label="HLA-I Alleles (comma-separated)",
                placeholder="HLA-A*02:01, HLA-A*01:01, HLA-B*07:02",
                value="HLA-A*02:01, HLA-B*07:02",
            )

            patient_id = gr.Textbox(
                label="Patient ID",
                value="patient_001",
            )

            top_n = gr.Slider(
                minimum=5,
                maximum=50,
                value=20,
                step=1,
                label="Top N Candidates",
            )

            run_btn = gr.Button("🚀 Run Pipeline", variant="primary", size="lg")

        with gr.Column(scale=2):
            gr.Markdown("### Results")
            summary_output = gr.Markdown(label="Pipeline Summary")

            with gr.Accordion("Pipeline Logs", open=False):
                log_output = gr.Textbox(
                    label="Stage Logs",
                    lines=20,
                    interactive=False,
                )

            with gr.Accordion("mRNA Construct Preview", open=False):
                mrna_output = gr.Textbox(
                    label="Top Candidate mRNA",
                    lines=15,
                    interactive=False,
                )

    # Toggle visibility based on data source
    def toggle_source(source):
        return (
            gr.update(visible=source == "Local Upload"),
            gr.update(visible=source == "TCGA (GDC)"),
            gr.update(visible=source == "cBioPortal"),
        )

    data_source.change(
        toggle_source,
        inputs=[data_source],
        outputs=[local_group, tcga_group, cbio_group],
    )

    # Run pipeline
    run_btn.click(
        run_pipeline,
        inputs=[
            tumor_file,
            hla_alleles,
            patient_id,
            rna_seq_file,
            data_source,
            tcga_case_id,
            cbio_study_id,
            cbio_sample_id,
            top_n,
        ],
        outputs=[summary_output, log_output, mrna_output],
    )


if __name__ == "__main__":
    demo.launch()
