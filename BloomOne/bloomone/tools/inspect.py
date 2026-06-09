"""
Artifact inspection tool — let agents read and summarize intermediate
pipeline files (MAF, TSV, FASTA) without downloading them.

Tools:
  - inspect_artifact: Read and summarize a pipeline file
"""

from __future__ import annotations

import os


def register_inspect_tools(mcp):
    """Register artifact inspection tools on the MCP server."""

    @mcp.tool()
    async def inspect_artifact(
        file_path: str,
        max_rows: int = 10,
    ) -> dict:
        """
        Read and summarize a pipeline artifact (MAF, TSV, or FASTA file).

        Use this to inspect intermediate results between stages without
        downloading files. Returns: row count, columns, sample rows,
        mutation breakdown, gene list, and other relevant summaries.

        Args:
            file_path: Absolute path to the file on the server volume
            max_rows: Maximum sample rows to include (default 10)
        """
        if not os.path.exists(file_path):
            return {
                "error": f"File not found: {file_path}",
                "suggestion": "Use pipeline_status to find valid output paths.",
            }

        stat = os.stat(file_path)
        result = {
            "file_path": file_path,
            "size_bytes": stat.st_size,
            "file_type": "unknown",
        }

        # ── FASTA files ──
        if file_path.endswith((".fasta", ".fa", ".faa")):
            result["file_type"] = "fasta"
            try:
                sequences = []
                header = None
                seq_parts = []
                with open(file_path) as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith(">"):
                            if header is not None:
                                sequences.append({
                                    "header": header,
                                    "length": len("".join(seq_parts)),
                                })
                            header = line[1:]
                            seq_parts = []
                        elif line:
                            seq_parts.append(line)
                    if header is not None:
                        sequences.append({
                            "header": header,
                            "length": len("".join(seq_parts)),
                        })

                result["total_sequences"] = len(sequences)
                result["sequences"] = sequences[:max_rows]
                result["summary"] = (
                    f"FASTA file with {len(sequences)} sequences. "
                    f"Lengths: {min(s['length'] for s in sequences)}-"
                    f"{max(s['length'] for s in sequences)} residues."
                    if sequences else "Empty FASTA file."
                )
            except Exception as e:
                result["error"] = f"Failed to parse FASTA: {e}"
            return result

        # ── TSV/MAF/CSV files ──
        if file_path.endswith((".tsv", ".maf", ".csv", ".txt")):
            # For .txt files, check if it's actually tabular or free-text
            if file_path.endswith(".txt"):
                try:
                    with open(file_path, encoding="utf-8", errors="replace") as f:
                        first_lines = [f.readline() for _ in range(5)]
                    first_line = first_lines[0].strip()
                    # Heuristic: if the first line has fewer than 3 tab-separated
                    # fields and fewer than 3 comma-separated fields, treat as text
                    tab_cols = len(first_line.split("\t"))
                    csv_cols = len(first_line.split(","))
                    if tab_cols < 3 and csv_cols < 3:
                        # It's a free-text file — return raw content
                        result["file_type"] = "text"
                        with open(file_path, encoding="utf-8", errors="replace") as f:
                            content = f.read(50_000)  # Cap at 50KB
                        result["content"] = content
                        result["total_lines"] = content.count("\n") + 1
                        result["summary"] = (
                            f"Free-text file ({result['total_lines']} lines, "
                            f"{stat.st_size} bytes). Full content included."
                        )
                        return result
                except Exception:
                    pass  # Fall through to tabular parsing

            result["file_type"] = "tabular"
            try:
                import pandas as pd
                sep = "\t" if file_path.endswith((".tsv", ".maf")) else ","
                df = pd.read_csv(file_path, sep=sep, comment="#", low_memory=False)

                result["total_rows"] = len(df)
                result["columns"] = list(df.columns)
                result["sample_rows"] = df.head(max_rows).to_dict("records")

                # MAF-specific summaries
                if "Hugo_Symbol" in df.columns:
                    genes = sorted(df["Hugo_Symbol"].dropna().unique().tolist())
                    result["unique_genes"] = len(genes)
                    result["top_genes"] = genes[:20]

                if "Variant_Classification" in df.columns:
                    result["variant_types"] = (
                        df["Variant_Classification"]
                        .value_counts()
                        .to_dict()
                    )

                if "Tumor_Sample_Barcode" in df.columns:
                    barcodes = df["Tumor_Sample_Barcode"].unique().tolist()
                    result["patient_barcodes"] = barcodes[:10]
                    result["total_patients"] = len(barcodes)
                    result["recommended_patient_id"] = str(barcodes[0])

                # Peptide file summaries
                if "peptide" in df.columns:
                    result["unique_peptides"] = df["peptide"].nunique()
                    if "peptide_length" in df.columns:
                        result["length_distribution"] = (
                            df["peptide_length"].value_counts().sort_index().to_dict()
                        )

                # Binding prediction summaries
                if "ic50" in df.columns:
                    result["ic50_stats"] = {
                        "min": round(float(df["ic50"].min()), 1),
                        "max": round(float(df["ic50"].max()), 1),
                        "median": round(float(df["ic50"].median()), 1),
                        "strong_binders_lt500": int((df["ic50"] < 500).sum()),
                    }

                if "allele" in df.columns:
                    result["alleles_present"] = sorted(df["allele"].unique().tolist())

                # Ranking summaries
                if "composite_score" in df.columns:
                    result["score_range"] = {
                        "best": round(float(df["composite_score"].min()), 4),
                        "worst": round(float(df["composite_score"].max()), 4),
                    }

                # mRNA construct summaries
                if "full_length" in df.columns:
                    result["construct_lengths"] = {
                        "min": int(df["full_length"].min()),
                        "max": int(df["full_length"].max()),
                    }
                if "gc_content" in df.columns:
                    result["gc_content_range"] = {
                        "min": round(float(df["gc_content"].min()), 1),
                        "max": round(float(df["gc_content"].max()), 1),
                    }

                # Build summary string
                summaries = [f"Tabular file with {len(df)} rows and {len(df.columns)} columns."]
                if "unique_genes" in result:
                    summaries.append(f"{result['unique_genes']} unique genes.")
                if "unique_peptides" in result:
                    summaries.append(f"{result['unique_peptides']} unique peptides.")
                if "ic50_stats" in result:
                    stats = result["ic50_stats"]
                    summaries.append(
                        f"{stats['strong_binders_lt500']} strong binders (IC50 < 500nM), "
                        f"median IC50: {stats['median']}nM."
                    )
                result["summary"] = " ".join(summaries)

            except Exception as e:
                result["error"] = f"Failed to parse tabular file: {e}"
            return result

        # ── Image files ──
        if file_path.endswith((".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".webp")):
            result["file_type"] = "image"
            result["summary"] = (
                f"Image file ({stat.st_size} bytes). "
                "Use a vision-capable model to analyze this image."
            )
            return result

        # ── PDF files ──
        if file_path.endswith(".pdf"):
            result["file_type"] = "pdf"
            result["summary"] = (
                f"PDF document ({stat.st_size} bytes). "
                "PDF text extraction is not yet supported. "
                "Ask the user to extract text or provide a text version."
            )
            return result

        # ── Unknown file type ──
        result["summary"] = f"Unknown file type. Size: {stat.st_size} bytes."
        return result
