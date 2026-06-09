"""
Patient management proxy — calls Coolify frontend API for patient CRUD.

The Modal backend doesn't directly access the PostgreSQL database.
Instead, it proxies patient operations through the Coolify Next.js
frontend's REST API endpoints, which use Prisma to talk to PostgreSQL.

This is the same pattern used by `fetch_from_coolify` in chat.py.
"""

from __future__ import annotations

import json
import os
from typing import Any

import requests

COOLIFY_FRONTEND_URL = os.environ.get("COOLIFY_FRONTEND_URL", "")


class PatientManager:
    """Proxy patient operations through the Coolify frontend API."""

    def __init__(self, coolify_url: str | None = None):
        self.base_url = (coolify_url or COOLIFY_FRONTEND_URL).rstrip("/")
        if not self.base_url:
            raise RuntimeError(
                "COOLIFY_FRONTEND_URL is not set — cannot manage patients"
            )

    def _url(self, path: str) -> str:
        return f"{self.base_url}/api/patients{path}"

    def _get(self, path: str) -> dict | list | None:
        try:
            resp = requests.get(self._url(path), timeout=15)
            if resp.ok:
                return resp.json()
            print(f"[patient-mgr] GET {path} failed: {resp.status_code}")
            return None
        except Exception as e:
            print(f"[patient-mgr] GET {path} error: {e}")
            return None

    def _post(self, path: str, data: dict) -> dict | None:
        try:
            resp = requests.post(
                self._url(path),
                json=data,
                timeout=15,
            )
            if resp.ok:
                return resp.json()
            print(f"[patient-mgr] POST {path} failed: {resp.status_code} {resp.text}")
            return None
        except Exception as e:
            print(f"[patient-mgr] POST {path} error: {e}")
            return None

    def _patch(self, path: str, data: dict) -> dict | None:
        try:
            resp = requests.patch(
                self._url(path),
                json=data,
                timeout=15,
            )
            if resp.ok:
                return resp.json()
            print(f"[patient-mgr] PATCH {path} failed: {resp.status_code}")
            return None
        except Exception as e:
            print(f"[patient-mgr] PATCH {path} error: {e}")
            return None

    # ── CRUD ─────────────────────────────────────────────────────────────

    def create(
        self,
        name: str,
        dob: str | None = None,
        details: dict | None = None,
        hla_alleles: list[str] | None = None,
    ) -> dict:
        """Create a new patient record."""
        payload: dict[str, Any] = {"name": name}
        if dob:
            payload["dob"] = dob
        if details:
            payload["details"] = details
        if hla_alleles:
            payload["hlaAlleles"] = hla_alleles

        result = self._post("", payload)
        if not result:
            return {"error": "Failed to create patient"}
        return {
            "patient_id": result["id"],
            "name": result["name"],
            "summary": f"Created patient record for {result['name']} (ID: {result['id']})",
        }

    def get(self, patient_id: str) -> dict:
        """Get patient by ID."""
        result = self._get(f"/{patient_id}")
        if not result:
            return {"error": f"Patient {patient_id} not found"}
        return result

    def get_by_name(self, name: str) -> dict | None:
        """Search for patient by name (returns first match)."""
        result = self._get(f"?search={name}")
        if isinstance(result, dict) and "patients" in result:
            patients = result["patients"]
            if patients:
                return patients[0]
        return None

    def list_all(self) -> dict:
        """List all patients."""
        result = self._get("")
        if not result:
            return {"patients": [], "total": 0}
        if isinstance(result, dict):
            return result
        return {"patients": result, "total": len(result)}

    def update(
        self,
        patient_id: str,
        details: dict | None = None,
        hla_alleles: list[str] | None = None,
    ) -> dict:
        """Update patient metadata."""
        payload: dict[str, Any] = {}
        if details:
            payload["details"] = details
        if hla_alleles is not None:
            payload["hlaAlleles"] = hla_alleles

        result = self._patch(f"/{patient_id}", payload)
        if not result:
            return {"error": f"Failed to update patient {patient_id}"}
        return {
            "patient_id": patient_id,
            "summary": f"Updated patient {result.get('name', patient_id)}",
        }

    def add_note(
        self, patient_id: str, content: str, source: str = "agent"
    ) -> dict:
        """Add a note to a patient's record."""
        result = self._post(f"/{patient_id}/notes", {
            "content": content,
            "source": source,
        })
        if not result:
            return {"error": f"Failed to add note to patient {patient_id}"}
        return {
            "patient_id": patient_id,
            "summary": f"Added note to patient record",
        }

    def attach_file(
        self, patient_id: str, file_id: str, notes: str = ""
    ) -> dict:
        """Attach an uploaded file to a patient."""
        result = self._post(f"/{patient_id}/files", {
            "fileId": file_id,
            "notes": notes,
        })
        if not result:
            return {"error": f"Failed to attach file to patient {patient_id}"}
        return {
            "patient_id": patient_id,
            "file_id": file_id,
            "summary": f"Attached file {result.get('filename', file_id)} to patient",
        }

    def add_result(
        self,
        patient_id: str,
        stages_completed: list[int],
        summary: str,
        output_paths: dict[str, str],
        warnings: list[str] | None = None,
    ) -> dict:
        """Save pipeline run results to a patient."""
        result = self._post(f"/{patient_id}/results", {
            "stagesCompleted": stages_completed,
            "summary": summary,
            "outputPaths": output_paths,
            "warnings": warnings or [],
        })
        if not result:
            return {"error": f"Failed to save results for patient {patient_id}"}
        return {
            "patient_id": patient_id,
            "run_id": result.get("id"),
            "summary": f"Saved pipeline results to patient record",
        }


# ── Module-level singleton ───────────────────────────────────────────────────

_manager: PatientManager | None = None


def get_patient_manager() -> PatientManager:
    """Get or create the PatientManager singleton."""
    global _manager
    if _manager is None:
        _manager = PatientManager()
    return _manager
