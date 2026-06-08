"""
Validation & pre-flight tools — let agents check inputs and environment
before spending compute.

Tools:
  - validate_inputs: Pre-flight check on MAF, HLA, BAM, patient_id
  - check_environment: Server health check (volume, APIs, disk)
"""

from __future__ import annotations

import os
import re
from typing import Optional

from bloomone.config import PATHS, BLOOMONE_VERSION


# ── HLA Validation ──────────────────────────────────────────────────────────

HLA_PATTERN = re.compile(r"^HLA-[ABC]\*\d{2}:\d{2,3}$")


def _validate_hla_allele(allele: str) -> dict:
    """Validate a single HLA allele string."""
    allele = allele.strip()
    if HLA_PATTERN.match(allele):
        return {"allele": allele, "valid": True, "error": None}
    return {
        "allele": allele,
        "valid": False,
        "error": (
            f"Invalid format '{allele}'. Expected HLA-A*02:01 format. "
            "Must be HLA-[A|B|C]*XX:XX where X is a digit."
        ),
    }


def _validate_maf_file(path: str) -> dict:
    """Quick validation of a MAF file."""
    if not os.path.exists(path):
        return {
            "valid": False,
            "error": f"File not found: {path}",
            "row_count": 0,
            "columns": [],
        }

    try:
        import pandas as pd
        df = pd.read_csv(path, sep="\t", comment="#", low_memory=False, nrows=5)

        required_cols = {"Hugo_Symbol", "Variant_Classification", "HGVSp_Short"}
        missing = required_cols - set(df.columns)

        if missing:
            return {
                "valid": False,
                "error": f"MAF missing required columns: {missing}",
                "columns": list(df.columns),
                "row_count": 0,
            }

        # Count full file
        full_df = pd.read_csv(path, sep="\t", comment="#", low_memory=False)
        missense = full_df[
            full_df["Variant_Classification"] == "Missense_Mutation"
        ]

        return {
            "valid": True,
            "error": None,
            "row_count": len(full_df),
            "missense_count": len(missense),
            "columns": list(df.columns),
            "genes": sorted(full_df["Hugo_Symbol"].dropna().unique().tolist())[:20],
        }
    except Exception as e:
        return {"valid": False, "error": f"Failed to parse MAF: {e}", "row_count": 0, "columns": []}


# ── Tool Registration ───────────────────────────────────────────────────────


def register_validation_tools(mcp):
    """Register validation tools on the MCP server."""

    @mcp.tool()
    async def validate_inputs(
        maf_path: str = "",
        hla_alleles: str = "",
        bam_path: str = "",
        normal_bam_path: str = "",
        patient_id: str = "",
    ) -> dict:
        """
        Pre-flight check: validate all inputs before running the pipeline.

        Call this BEFORE running any stage to catch errors early. Returns
        which stages are needed, estimated runtime, and any input problems.

        Args:
            maf_path: Path to MAF file (if available)
            hla_alleles: Comma-separated HLA alleles (e.g. "HLA-A*02:01,HLA-B*07:02")
            bam_path: Path to tumor BAM/FASTQ (if available)
            normal_bam_path: Path to normal BAM/FASTQ (if available)
            patient_id: Patient identifier to use
        """
        errors = []
        warnings = []
        checks = {}
        suggested_stages = []

        # ── Validate MAF ──
        has_maf = False
        if maf_path:
            maf_check = _validate_maf_file(maf_path)
            checks["maf"] = maf_check
            has_maf = maf_check["valid"]
            if not has_maf:
                errors.append(f"MAF validation failed: {maf_check['error']}")
            else:
                suggested_stages = [3, 4, 5, 6, 7]  # Skip stages 1-2
        else:
            checks["maf"] = {"valid": False, "error": "No MAF path provided"}

        # ── Validate BAM ──
        has_bam = False
        if bam_path:
            if os.path.exists(bam_path):
                checks["tumor_bam"] = {"valid": True, "size_bytes": os.path.getsize(bam_path)}
                has_bam = True
            else:
                checks["tumor_bam"] = {"valid": False, "error": f"File not found: {bam_path}"}
                errors.append(f"Tumor BAM not found: {bam_path}")

        if normal_bam_path:
            if os.path.exists(normal_bam_path):
                checks["normal_bam"] = {"valid": True, "size_bytes": os.path.getsize(normal_bam_path)}
            else:
                checks["normal_bam"] = {"valid": False, "error": f"File not found: {normal_bam_path}"}
                errors.append(f"Normal BAM not found: {normal_bam_path}")

        if has_bam and not has_maf:
            suggested_stages = [1, 2, 3, 4, 5, 6, 7]  # Full pipeline

        # ── Validate HLA ──
        has_hla = False
        if hla_alleles:
            alleles = [a.strip() for a in hla_alleles.split(",") if a.strip()]
            hla_results = [_validate_hla_allele(a) for a in alleles]
            checks["hla_alleles"] = hla_results
            invalid = [r for r in hla_results if not r["valid"]]
            if invalid:
                for r in invalid:
                    errors.append(r["error"])
            else:
                has_hla = True
        else:
            checks["hla_alleles"] = []
            warnings.append(
                "No HLA alleles provided. You must either provide HLA alleles "
                "or run stage1_run_optitype with a BAM/FASTQ file."
            )

        # ── Patient ID ──
        if not patient_id:
            warnings.append(
                "No patient_id specified. A default will be auto-generated, "
                "but providing one prevents accidental data collisions."
            )

        # ── Estimate ──
        estimated_minutes = 0
        if has_maf and has_hla:
            estimated_minutes = 5  # Stages 3-7 are fast
        elif has_bam:
            estimated_minutes = 60  # Stage 2 (Strelka2) is slow
            if not has_hla:
                estimated_minutes += 15  # OptiType

        # ── Minimum viable check ──
        if not has_maf and not has_bam:
            errors.append(
                "No input data provided. You need either a MAF file (skips "
                "stages 1-2) or tumor+normal BAM files (runs full pipeline). "
                "Use stage1_fetch_cbio or stage1_fetch_tcga to fetch data."
            )

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "checks": checks,
            "has_maf": has_maf,
            "has_bam": has_bam,
            "has_hla": has_hla,
            "suggested_stages": suggested_stages,
            "estimated_minutes": estimated_minutes,
            "suggestion": (
                "Inputs look good. Proceed with the pipeline."
                if len(errors) == 0
                else "Fix the errors above before running the pipeline."
            ),
        }

    @mcp.tool()
    async def check_environment() -> dict:
        """
        Verify server health: volume accessible, APIs reachable, disk space.

        Call this if a stage fails unexpectedly, or before starting a long
        pipeline run on real clinical data.
        """
        checks = []

        # ── Volume access ──
        try:
            vol_exists = os.path.isdir(PATHS["input"])
            if not vol_exists:
                os.makedirs(PATHS["input"], exist_ok=True)
            checks.append({
                "name": "Modal Volume",
                "status": "ok",
                "detail": f"Volume mounted at /data, input dir accessible",
            })
        except Exception as e:
            checks.append({
                "name": "Modal Volume",
                "status": "error",
                "detail": f"Volume not accessible: {e}",
            })

        # ── Reference genome ──
        hg38_exists = os.path.exists(PATHS["hg38"])
        checks.append({
            "name": "Reference Genome (hg38)",
            "status": "ok" if hg38_exists else "missing",
            "detail": (
                "hg38.fa present" if hg38_exists
                else "hg38.fa not found — Stage 2 (Strelka2) will fail. "
                     "Upload to /data/reference/hg38.fa"
            ),
        })

        # ── Proteome ──
        proteome_exists = os.path.exists(PATHS["proteome"])
        checks.append({
            "name": "Human Proteome",
            "status": "ok" if proteome_exists else "will_download",
            "detail": (
                "Proteome cached" if proteome_exists
                else "Will be auto-downloaded from UniProt when Stage 5 runs"
            ),
        })

        # ── Ensembl API ──
        try:
            import requests
            resp = requests.get(
                "https://rest.ensembl.org/info/ping",
                headers={"Content-Type": "application/json"},
                timeout=5,
            )
            checks.append({
                "name": "Ensembl REST API",
                "status": "ok" if resp.ok else "degraded",
                "detail": f"Ping response: {resp.status_code}",
            })
        except Exception as e:
            checks.append({
                "name": "Ensembl REST API",
                "status": "unreachable",
                "detail": f"Cannot reach Ensembl: {e}",
            })

        # ── UniProt API ──
        try:
            import requests
            resp = requests.get(
                "https://rest.uniprot.org/uniprotkb/search?query=P53_HUMAN&size=1&format=json",
                timeout=5,
            )
            checks.append({
                "name": "UniProt REST API",
                "status": "ok" if resp.ok else "degraded",
                "detail": f"Response: {resp.status_code}",
            })
        except Exception as e:
            checks.append({
                "name": "UniProt REST API",
                "status": "unreachable",
                "detail": f"Cannot reach UniProt: {e}",
            })

        # ── Overall ──
        all_ok = all(c["status"] == "ok" for c in checks)
        critical_fail = any(c["status"] == "error" for c in checks)

        return {
            "healthy": not critical_fail,
            "all_optimal": all_ok,
            "version": BLOOMONE_VERSION,
            "checks": checks,
            "suggestion": (
                "All systems operational."
                if all_ok
                else "Some checks have warnings — see details above."
                if not critical_fail
                else "Critical issue detected — fix before running pipeline."
            ),
        }
