"""
BloomOne structured error handling.

Replaces raw Python tracebacks with agent-friendly, actionable error
responses.  Every error includes: error_code, stage info, human-readable
message, technical detail, a concrete suggestion for what to do next,
and a recoverable flag.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


# ── Structured Error Model ──────────────────────────────────────────────────

class BloomOneError(BaseModel):
    """Agent-friendly error response."""
    error_code: str
    stage: Optional[int] = None
    stage_name: Optional[str] = None
    message: str
    detail: str
    suggestion: str
    recoverable: bool = False
    research_use_only: bool = True


# ── Error Code Catalog ──────────────────────────────────────────────────────

FILE_NOT_FOUND = "FILE_NOT_FOUND"
INVALID_HLA_FORMAT = "INVALID_HLA_FORMAT"
EMPTY_MAF = "EMPTY_MAF"
NO_MISSENSE_MUTATIONS = "NO_MISSENSE_MUTATIONS"
NO_PEPTIDES_GENERATED = "NO_PEPTIDES_GENERATED"
NO_BINDERS_FOUND = "NO_BINDERS_FOUND"
API_TIMEOUT = "API_TIMEOUT"
API_ERROR = "API_ERROR"
MISSING_DEPENDENCY = "MISSING_DEPENDENCY"
INVALID_INPUT = "INVALID_INPUT"
STAGE_PREREQUISITE_MISSING = "STAGE_PREREQUISITE_MISSING"
PATIENT_NOT_FOUND = "PATIENT_NOT_FOUND"
JOB_NOT_FOUND = "JOB_NOT_FOUND"
JOB_ALREADY_RUNNING = "JOB_ALREADY_RUNNING"
INTERNAL_ERROR = "INTERNAL_ERROR"

# Stage name lookup
STAGE_NAMES = {
    1: "Data Ingestion",
    2: "Mutation Calling",
    3: "Peptide Generation",
    4: "HLA Binding Prediction",
    5: "Safety Filter",
    6: "Candidate Ranking",
    7: "mRNA Construct Design",
}


# ── Error Factory ───────────────────────────────────────────────────────────

def make_error(
    code: str,
    message: str,
    detail: str,
    suggestion: str,
    stage: Optional[int] = None,
    recoverable: bool = False,
) -> dict:
    """Build a structured error dict from components."""
    return BloomOneError(
        error_code=code,
        stage=stage,
        stage_name=STAGE_NAMES.get(stage) if stage else None,
        message=message,
        detail=detail,
        suggestion=suggestion,
        recoverable=recoverable,
    ).model_dump()


def wrap_stage_error(
    exc: Exception,
    stage: int,
) -> dict:
    """
    Convert any exception raised during a stage into a structured error.

    Inspects the exception type to provide the most helpful response.
    """
    stage_name = STAGE_NAMES.get(stage, f"Stage {stage}")
    exc_type = type(exc).__name__
    detail = str(exc)

    # ── FileNotFoundError ──
    if isinstance(exc, FileNotFoundError):
        return make_error(
            code=FILE_NOT_FOUND,
            message=f"{stage_name} failed: a required file was not found.",
            detail=detail,
            suggestion=(
                "Check that the file path from the previous stage exists. "
                "Use the inspect_artifact tool to verify, or re-run the "
                "previous stage. Use pipeline_status to see completed stages."
            ),
            stage=stage,
            recoverable=True,
        )

    # ── ValueError (bad input) ──
    if isinstance(exc, ValueError):
        return make_error(
            code=INVALID_INPUT,
            message=f"{stage_name} received invalid input.",
            detail=detail,
            suggestion=(
                "Verify your input parameters. Use validate_inputs for "
                "pre-flight checks before running stages. Common issues: "
                "wrong patient_id, empty HLA alleles, corrupt MAF file."
            ),
            stage=stage,
            recoverable=True,
        )

    # ── RuntimeError (tool failure) ──
    if isinstance(exc, RuntimeError):
        return make_error(
            code=MISSING_DEPENDENCY,
            message=f"{stage_name} encountered a runtime error.",
            detail=detail,
            suggestion=(
                "This may indicate a missing tool (Strelka2, OptiType, etc.) "
                "or a container configuration issue. Use check_environment "
                "to verify server health."
            ),
            stage=stage,
            recoverable=False,
        )

    # ── TimeoutError / requests exceptions ──
    if "timeout" in detail.lower() or "Timeout" in exc_type:
        return make_error(
            code=API_TIMEOUT,
            message=f"{stage_name} timed out.",
            detail=detail,
            suggestion=(
                "An external API call timed out. Retry the stage — this is "
                "usually transient. If it persists, check if the API "
                "(Ensembl VEP, IEDB, UniProt) is experiencing downtime."
            ),
            stage=stage,
            recoverable=True,
        )

    # ── Generic fallback ──
    return make_error(
        code=INTERNAL_ERROR,
        message=f"{stage_name} failed with an unexpected error.",
        detail=f"{exc_type}: {detail}",
        suggestion=(
            "This is an unexpected error. Check the detail field for clues. "
            "Use pipeline_status to see what completed before the failure. "
            "Re-running the stage may resolve transient issues."
        ),
        stage=stage,
        recoverable=False,
    )
