"""
Async job management — non-blocking execution for long-running stages.

Uses modal.Dict as a distributed state store and modal.Function.spawn()
for background execution. Agents get a job_id back immediately and can
poll for status.

Tools:
  - start_stage: Submit a stage as a background job
  - get_job_status: Check job progress
  - cancel_job: Cancel a running job
  - list_jobs: List all jobs for a patient
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Optional


def _get_state_store():
    """Lazy import of modal.Dict state store."""
    try:
        from bloomone.config import state_store
        return state_store
    except Exception:
        return None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _job_key(job_id: str) -> str:
    return f"job:{job_id}"


def _patient_jobs_key(patient_id: str) -> str:
    return f"patient_jobs:{patient_id}"


# ── Tool Registration ───────────────────────────────────────────────────────


def register_job_tools(mcp):
    """Register async job management tools on the MCP server."""

    @mcp.tool()
    async def start_stage(
        stage: int,
        patient_id: str,
        maf_path: str = "",
        hla_alleles: str = "",
        peptides_path: str = "",
        binders_path: str = "",
        safe_path: str = "",
        ranked_path: str = "",
        tpm_path: str = "",
        patient_data_json: str = "",
        top_n: int = 20,
    ) -> dict:
        """
        Submit a long-running stage as a background job.

        Returns a job_id immediately. Use get_job_status to poll for
        completion. This is especially useful for Stage 2 (Strelka2, ~45min)
        and Stage 4 (MHCflurry, ~5-15min).

        For fast stages (3, 5, 6, 7), prefer calling the stage tool directly.

        Args:
            stage: Stage number (2 or 4 recommended for async)
            patient_id: Patient identifier
            maf_path: MAF file path (Stage 3)
            hla_alleles: Comma-separated HLA alleles (Stage 4)
            peptides_path: Peptides TSV path (Stage 4)
            binders_path: Binders TSV path (Stage 5)
            safe_path: Safe candidates TSV path (Stage 6)
            ranked_path: Ranked candidates TSV path (Stage 7)
            tpm_path: Optional TPM file path
            patient_data_json: JSON string of PatientData (Stage 2)
            top_n: Number of top candidates (Stages 6, 7)
        """
        store = _get_state_store()
        job_id = f"bloom-{uuid.uuid4().hex[:12]}"

        job_record = {
            "job_id": job_id,
            "stage": stage,
            "patient_id": patient_id,
            "status": "submitted",
            "submitted_at": _now_iso(),
            "started_at": None,
            "completed_at": None,
            "progress_pct": 0,
            "progress_message": "Job submitted, waiting to start...",
            "result": None,
            "error": None,
            "modal_call_id": None,
        }

        # Try to spawn the appropriate Modal function
        try:
            import modal

            if stage == 2:
                if not patient_data_json:
                    return {
                        "error": "patient_data_json is required for Stage 2",
                        "suggestion": "Pass the JSON output from Stage 1.",
                    }
                fn = modal.Function.from_name("bloomone", "run_strelka2")
                patient_data = json.loads(patient_data_json)
                call = fn.spawn(
                    tumor_bam=patient_data.get("tumor_path", ""),
                    normal_bam=patient_data.get("normal_path", ""),
                    patient_id=patient_id,
                )
                job_record["modal_call_id"] = call.object_id
                job_record["status"] = "running"
                job_record["started_at"] = _now_iso()
                job_record["progress_message"] = "Strelka2 somatic calling started (est. 45 min)"

            elif stage == 4:
                if not peptides_path or not hla_alleles:
                    return {
                        "error": "peptides_path and hla_alleles required for Stage 4",
                        "suggestion": "Pass the peptides TSV from Stage 3 and HLA alleles.",
                    }
                fn = modal.Function.from_name("bloomone", "run_mhcflurry_remote")
                alleles_list = [a.strip() for a in hla_alleles.split(",") if a.strip()]
                call = fn.spawn(
                    peptides_path=peptides_path,
                    hla_alleles=alleles_list,
                    patient_id=patient_id,
                )
                job_record["modal_call_id"] = call.object_id
                job_record["status"] = "running"
                job_record["started_at"] = _now_iso()
                job_record["progress_message"] = "MHCflurry GPU prediction started (est. 5-15 min)"

            else:
                return {
                    "job_id": job_id,
                    "status": "not_recommended",
                    "message": (
                        f"Stage {stage} typically completes in under 2 minutes. "
                        "Call the stage tool directly instead of using start_stage."
                    ),
                    "suggestion": f"Call stage{stage}_* tool directly for faster results.",
                }

        except Exception as e:
            job_record["status"] = "failed"
            job_record["error"] = str(e)
            job_record["progress_message"] = f"Failed to spawn job: {e}"

        # Store job record
        if store is not None:
            try:
                store[_job_key(job_id)] = json.dumps(job_record)
                # Also track by patient
                patient_key = _patient_jobs_key(patient_id)
                existing = json.loads(store.get(patient_key, "[]"))
                existing.append(job_id)
                store[patient_key] = json.dumps(existing)
            except Exception:
                pass  # State store unavailable — job still runs

        return job_record

    @mcp.tool()
    async def get_job_status(job_id: str) -> dict:
        """
        Check the status of a background job.

        Returns current status, progress percentage, elapsed time, and
        result (if completed). Poll this periodically for long-running stages.

        Args:
            job_id: Job identifier from start_stage
        """
        store = _get_state_store()

        if store is None:
            return {"error": "State store unavailable", "suggestion": "The job may still be running on Modal."}

        try:
            raw = store.get(_job_key(job_id))
            if raw is None:
                return {
                    "error": f"Job not found: {job_id}",
                    "suggestion": "Use list_jobs to see all jobs for a patient.",
                }
            job_record = json.loads(raw)
        except Exception as e:
            return {"error": f"Failed to read job state: {e}"}

        # If the job has a Modal call ID and is still running, check if it finished
        if job_record.get("status") == "running" and job_record.get("modal_call_id"):
            try:
                import modal
                call = modal.functions.FunctionCall.from_id(job_record["modal_call_id"])
                try:
                    # Try to get result with short timeout
                    result = call.get(timeout=0.5)
                    job_record["status"] = "completed"
                    job_record["completed_at"] = _now_iso()
                    job_record["progress_pct"] = 100
                    job_record["progress_message"] = "Job completed successfully"
                    job_record["result"] = result
                    # Update store
                    store[_job_key(job_id)] = json.dumps(job_record)
                except TimeoutError:
                    pass  # Still running
                except Exception as e:
                    job_record["status"] = "failed"
                    job_record["error"] = str(e)
                    job_record["progress_message"] = f"Job failed: {e}"
                    store[_job_key(job_id)] = json.dumps(job_record)
            except Exception:
                pass  # Can't check Modal — return cached state

        # Calculate elapsed time
        elapsed = None
        if job_record.get("submitted_at"):
            submitted = datetime.fromisoformat(job_record["submitted_at"])
            elapsed = (datetime.now(timezone.utc) - submitted).total_seconds()
            job_record["elapsed_seconds"] = int(elapsed)

        return job_record

    @mcp.tool()
    async def cancel_job(job_id: str) -> dict:
        """
        Cancel a running background job.

        Args:
            job_id: Job identifier from start_stage
        """
        store = _get_state_store()
        if store is None:
            return {"error": "State store unavailable"}

        try:
            raw = store.get(_job_key(job_id))
            if raw is None:
                return {"error": f"Job not found: {job_id}"}
            job_record = json.loads(raw)
        except Exception as e:
            return {"error": f"Failed to read job state: {e}"}

        if job_record["status"] not in ("submitted", "running"):
            return {
                "job_id": job_id,
                "status": job_record["status"],
                "message": f"Job is already {job_record['status']}, cannot cancel.",
            }

        # Try to cancel the Modal function call
        if job_record.get("modal_call_id"):
            try:
                import modal
                call = modal.functions.FunctionCall.from_id(job_record["modal_call_id"])
                call.cancel()
            except Exception:
                pass  # Best effort

        job_record["status"] = "cancelled"
        job_record["completed_at"] = _now_iso()
        job_record["progress_message"] = "Job cancelled by user"
        store[_job_key(job_id)] = json.dumps(job_record)

        return {
            "job_id": job_id,
            "status": "cancelled",
            "message": "Job has been cancelled.",
        }

    @mcp.tool()
    async def list_jobs(patient_id: str = "") -> dict:
        """
        List all background jobs, optionally filtered by patient.

        Args:
            patient_id: Optional patient ID to filter by
        """
        store = _get_state_store()
        if store is None:
            return {"error": "State store unavailable", "jobs": []}

        jobs = []

        if patient_id:
            try:
                patient_key = _patient_jobs_key(patient_id)
                raw = store.get(patient_key, "[]")
                job_ids = json.loads(raw)
                for jid in job_ids:
                    try:
                        raw_job = store.get(_job_key(jid))
                        if raw_job:
                            jobs.append(json.loads(raw_job))
                    except Exception:
                        pass
            except Exception:
                pass
        else:
            # Without patient filter, we can't enumerate all keys easily
            # with modal.Dict — return guidance
            return {
                "message": "Provide a patient_id to list jobs for that patient.",
                "suggestion": "Call list_jobs(patient_id='your-patient-id')",
                "jobs": [],
            }

        return {
            "patient_id": patient_id,
            "total_jobs": len(jobs),
            "jobs": jobs,
        }
