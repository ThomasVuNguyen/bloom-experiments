"""
Stage 1: Data Ingestion (MCP-1)

Handles all data input pathways:
  - Local file upload (BAM/FASTQ/MAF)
  - TCGA via GDC API
  - cBioPortal API
  - HLA-I typing via OptiType (if alleles not provided)
  - Optional RNA-seq expression filtering

Input:  Raw sequencing files or pre-called mutations
Output: PatientData with validated paths and HLA alleles
"""

from __future__ import annotations

import json
import os
import shutil
from typing import Optional

import requests

from bloomone.config import (
    CBIO_API_URL,
    GDC_DATA_ENDPOINT,
    GDC_FILES_ENDPOINT,
    PATHS,
)
from bloomone.models import DataSource, PatientData


def ingest_local_files(
    tumor_path: str,
    normal_path: Optional[str] = None,
    hla_alleles: Optional[list[str]] = None,
    rna_seq_path: Optional[str] = None,
    patient_id: str = "local_patient",
) -> PatientData:
    """
    Ingest locally uploaded files.

    Copies files to the Modal Volume under /data/input/{patient_id}/
    and validates that they exist.

    Args:
        tumor_path: Path to tumor BAM/FASTQ or MAF file
        normal_path: Path to normal BAM/FASTQ (None if MAF input)
        hla_alleles: HLA-I alleles (None to auto-detect via OptiType)
        rna_seq_path: Optional RNA-seq TPM file
        patient_id: Identifier for this patient run

    Returns:
        PatientData with volume paths
    """
    input_dir = os.path.join(PATHS["input"], patient_id)
    os.makedirs(input_dir, exist_ok=True)

    # Determine if input is MAF (pre-called mutations)
    is_maf = tumor_path.endswith((".maf", ".maf.gz", ".txt"))

    # Copy tumor file
    tumor_dest = os.path.join(input_dir, os.path.basename(tumor_path))
    if not os.path.exists(tumor_dest):
        shutil.copy2(tumor_path, tumor_dest)
    print(f"Tumor file: {tumor_dest}")

    # Copy normal file (if provided and not MAF)
    normal_dest = None
    if normal_path and not is_maf:
        normal_dest = os.path.join(input_dir, os.path.basename(normal_path))
        if not os.path.exists(normal_dest):
            shutil.copy2(normal_path, normal_dest)
        print(f"Normal file: {normal_dest}")

    # Copy RNA-seq file
    tpm_dest = None
    if rna_seq_path:
        tpm_dest = os.path.join(input_dir, os.path.basename(rna_seq_path))
        if not os.path.exists(tpm_dest):
            shutil.copy2(rna_seq_path, tpm_dest)
        print(f"RNA-seq file: {tpm_dest}")

    # HLA alleles
    hla_source = "provided"
    if hla_alleles is None:
        hla_alleles = []
        hla_source = "pending_optitype"
        print("HLA alleles not provided — will need OptiType typing")

    maf_path = tumor_dest if is_maf else None
    requires_optitype = hla_alleles == []
    skip_stage2 = maf_path is not None

    warnings = []
    if requires_optitype:
        warnings.append(
            "HLA alleles not provided. Run stage1_run_optitype with a BAM/FASTQ "
            "file, or provide HLA alleles manually (e.g. HLA-A*02:01,HLA-B*07:02). "
            "Pipeline CANNOT proceed past Stage 3 without HLA alleles."
        )
    if skip_stage2:
        next_action = (
            f"Proceed to stage3_generate_peptides with maf_path='{maf_path}'"
            if not requires_optitype
            else f"First run stage1_run_optitype, then stage3_generate_peptides with maf_path='{maf_path}'"
        )
    else:
        next_action = (
            f"Run stage2_call_mutations with the patient data JSON"
        )

    return PatientData(
        stage=1,
        stage_name="Data Ingestion",
        summary=(
            f"Ingested local files for patient {patient_id}. "
            f"{'MAF provided (skip Stage 2). ' if skip_stage2 else 'BAM input (Stage 2 required). '}"
            f"{'HLA alleles provided. ' if not requires_optitype else 'HLA alleles MISSING. '}"
            f"{'RNA-seq available.' if tpm_dest else 'No RNA-seq data.'}"
        ),
        next_action=next_action,
        provenance={"input_type": "maf" if is_maf else "bam", "data_source": "local"},
        warnings=warnings,
        patient_id=patient_id,
        tumor_path=tumor_dest,
        normal_path=normal_dest,
        hla_alleles=hla_alleles,
        hla_source=hla_source,
        maf_path=maf_path,
        tpm_path=tpm_dest,
        data_source=DataSource.LOCAL,
        expression_validated=tpm_dest is not None,
        requires_optitype=requires_optitype,
        skip_stage2=skip_stage2,
    )


def fetch_tcga_data(
    case_id: str,
    data_type: str = "Masked Somatic Mutation",
) -> PatientData:
    """
    Fetch data from TCGA via the GDC API.

    For mutation data, downloads MAF files (skips Stage 2).
    For raw sequencing, downloads BAM files (requires Stage 2).

    Args:
        case_id: TCGA case ID (e.g., 'TCGA-BF-A3DL-01')
        data_type: Type of data to fetch

    Returns:
        PatientData with volume paths
    """
    input_dir = os.path.join(PATHS["input"], case_id)
    os.makedirs(input_dir, exist_ok=True)

    print(f"Querying GDC for case: {case_id}...")

    # Search for MAF files for this case
    filters = {
        "op": "and",
        "content": [
            {
                "op": "in",
                "content": {
                    "field": "cases.case_id",
                    "value": [case_id],
                },
            },
            {
                "op": "in",
                "content": {
                    "field": "data_type",
                    "value": [data_type],
                },
            },
        ],
    }

    params = {
        "filters": json.dumps(filters),
        "fields": "file_id,file_name,data_type,file_size",
        "format": "JSON",
        "size": "10",
    }

    resp = requests.get(GDC_FILES_ENDPOINT, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    hits = data.get("data", {}).get("hits", [])
    if not hits:
        raise ValueError(f"No {data_type} files found for case {case_id}")

    # Download the first matching file
    file_info = hits[0]
    file_id = file_info["file_id"]
    file_name = file_info["file_name"]

    print(f"Downloading: {file_name} ({file_info.get('file_size', '?')} bytes)")

    download_resp = requests.get(
        f"{GDC_DATA_ENDPOINT}/{file_id}",
        timeout=600,
        stream=True,
    )
    download_resp.raise_for_status()

    file_path = os.path.join(input_dir, file_name)
    with open(file_path, "wb") as f:
        for chunk in download_resp.iter_content(chunk_size=8192):
            f.write(chunk)

    print(f"Downloaded to: {file_path}")

    is_maf = file_name.endswith((".maf", ".maf.gz"))

    warnings = [
        "HLA alleles not available from TCGA download. Run stage1_run_optitype "
        "with a BAM file, or provide HLA alleles manually."
    ]

    return PatientData(
        stage=1,
        stage_name="Data Ingestion",
        summary=(
            f"Fetched {data_type} from TCGA/GDC for case {case_id}. "
            f"Downloaded: {file_name}. "
            f"{'MAF format — skip Stage 2. ' if is_maf else 'BAM format — Stage 2 required. '}"
            f"HLA alleles MISSING."
        ),
        next_action=(
            f"Provide HLA alleles, then proceed to stage3_generate_peptides with maf_path='{file_path}'"
            if is_maf
            else f"Run stage2_call_mutations, then provide HLA alleles for Stage 4"
        ),
        provenance={"data_source": "tcga", "gdc_file_id": file_id, "file_name": file_name},
        warnings=warnings,
        patient_id=case_id,
        tumor_path=file_path,
        normal_path=None,
        hla_alleles=[],
        hla_source="pending_optitype",
        maf_path=file_path if is_maf else None,
        tpm_path=None,
        data_source=DataSource.TCGA,
        expression_validated=False,
        requires_optitype=True,
        skip_stage2=is_maf,
    )


def fetch_cbio_data(
    study_id: str,
    sample_id: str,
) -> PatientData:
    """
    Fetch pre-called mutations from cBioPortal API.

    Downloads mutation data as MAF-like format. Always skips Stage 2.

    Args:
        study_id: cBioPortal study ID (e.g., 'skcm_tcga_pan_can_atlas_2018')
        sample_id: Sample barcode (e.g., 'TCGA-BF-A3DL-01')

    Returns:
        PatientData with volume paths
    """
    import pandas as pd

    input_dir = os.path.join(PATHS["input"], sample_id)
    os.makedirs(input_dir, exist_ok=True)

    print(f"Fetching mutations from cBioPortal: {study_id} / {sample_id}")

    # Use the /fetch endpoint with POST — sampleIds filter returns only this patient's mutations
    url = f"{CBIO_API_URL}/molecular-profiles/{study_id}_mutations/mutations/fetch"
    params = {
        "projection": "DETAILED",
    }
    body = {
        "sampleIds": [sample_id],
    }

    resp = requests.post(url, json=body, params=params, timeout=60)
    resp.raise_for_status()
    sample_mutations = resp.json()

    if not sample_mutations:
        raise ValueError(f"No mutations found for sample {sample_id}")

    print(f"Found {len(sample_mutations)} mutations")

    # Convert to MAF-like format
    maf_rows = []
    for m in sample_mutations:
        maf_rows.append(
            {
                "Hugo_Symbol": m.get("gene", {}).get("hugoGeneSymbol", ""),
                "Variant_Classification": m.get("mutationType", ""),
                "HGVSp_Short": m.get("proteinChange", ""),
                "Chromosome": m.get("chr", ""),
                "Start_Position": m.get("startPosition", ""),
                "Reference_Allele": m.get("referenceAllele", ""),
                "Tumor_Seq_Allele2": m.get("variantAllele", ""),
                "Tumor_Sample_Barcode": sample_id,
                "Transcript_ID": "",  # cBioPortal keyword doesn't contain Ensembl IDs
                "t_depth": m.get("tumorRefCount", 0)
                + m.get("tumorAltCount", 0),
                "t_alt_count": m.get("tumorAltCount", 0),
            }
        )

    maf_df = pd.DataFrame(maf_rows)
    maf_path = os.path.join(input_dir, f"{sample_id}_cbio_mutations.maf")
    maf_df.to_csv(maf_path, sep="\t", index=False)

    print(f"MAF saved to: {maf_path}")

    # Count mutation types for summary
    missense_count = sum(1 for m in sample_mutations if m.get("mutationType") == "Missense_Mutation")

    warnings = [
        "HLA alleles not available from cBioPortal. You MUST provide HLA alleles "
        "manually (e.g. HLA-A*02:01,HLA-B*07:02) or they cannot be determined "
        "from MAF data. Pipeline cannot proceed past Stage 3 without HLA alleles."
    ]

    return PatientData(
        stage=1,
        stage_name="Data Ingestion",
        summary=(
            f"Fetched {len(sample_mutations)} mutations ({missense_count} missense) "
            f"from cBioPortal study '{study_id}' for sample {sample_id}. "
            f"MAF format — skip Stage 2. HLA alleles MISSING."
        ),
        next_action=(
            f"Provide HLA alleles, then call stage3_generate_peptides "
            f"with maf_path='{maf_path}' and patient_id='{sample_id}'"
        ),
        provenance={
            "data_source": "cbio",
            "study_id": study_id,
            "sample_id": sample_id,
            "total_mutations": len(sample_mutations),
            "missense_mutations": missense_count,
        },
        warnings=warnings,
        patient_id=sample_id,
        tumor_path=maf_path,
        normal_path=None,
        hla_alleles=[],
        hla_source="pending_optitype",
        maf_path=maf_path,
        tpm_path=None,
        data_source=DataSource.CBIO,
        expression_validated=False,
        requires_optitype=True,
        skip_stage2=True,
    )


def run_optitype(
    bam_path: str,
    patient_id: str,
) -> list[str]:
    """
    Run OptiType for HLA-I genotyping from BAM/FASTQ.

    Note: This function is designed to run inside the OptiType Modal
    container image. When called outside that image, it will raise
    an appropriate error.

    Args:
        bam_path: Path to BAM or FASTQ file
        patient_id: Patient identifier

    Returns:
        List of HLA-I alleles (e.g., ['HLA-A*02:01', 'HLA-A*01:01', ...])
    """
    import subprocess

    output_dir = os.path.join(PATHS["stage1"], patient_id, "optitype")
    os.makedirs(output_dir, exist_ok=True)

    # Determine input type
    is_bam = bam_path.endswith((".bam", ".BAM"))
    input_flag = "--dna" if not bam_path.endswith((".rna", ".RNA")) else "--rna"

    cmd = [
        "OptiTypePipeline.py",
        "-i", bam_path,
        input_flag,
        "-o", output_dir,
        "-v",
    ]

    print(f"Running OptiType: {' '.join(cmd)}")
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=3600,
    )

    if result.returncode != 0:
        raise RuntimeError(f"OptiType failed: {result.stderr}")

    # Parse OptiType result TSV
    import pandas as pd

    result_files = [
        f for f in os.listdir(output_dir) if f.endswith("_result.tsv")
    ]
    if not result_files:
        raise RuntimeError("OptiType produced no result file")

    result_df = pd.read_csv(
        os.path.join(output_dir, result_files[0]), sep="\t"
    )

    # Extract alleles from columns A1, A2, B1, B2, C1, C2
    alleles = []
    for col in ["A1", "A2", "B1", "B2", "C1", "C2"]:
        if col in result_df.columns:
            allele = result_df.iloc[0][col]
            if isinstance(allele, str) and allele:
                # Normalize format: A*02:01 → HLA-A*02:01
                if not allele.startswith("HLA-"):
                    allele = f"HLA-{allele}"
                alleles.append(allele)

    print(f"OptiType HLA alleles: {alleles}")
    return alleles
