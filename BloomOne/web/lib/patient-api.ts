/**
 * Patient API client — client-side functions for the patient management system.
 */

export interface PatientSummary {
  id: string;
  name: string;
  dob: string | null;
  details: Record<string, unknown>;
  hlaAlleles: string[];
  createdAt: string;
  updatedAt: string;
  fileCount: number;
  runCount: number;
  noteCount: number;
}

export interface PatientNote {
  id: string;
  content: string;
  source: "agent" | "user";
  createdAt: string;
}

export interface PatientFile {
  id: string;
  filename: string;
  fileType: string;
  mimeType: string;
  sizeBytes: number;
  blobPath: string;
  notes: string;
  createdAt: string;
}

export interface PipelineRun {
  id: string;
  stagesCompleted: number[];
  summary: string;
  outputPaths: Record<string, string>;
  warnings: string[];
  startedAt: string;
  completedAt: string | null;
}

export interface PatientDetail {
  id: string;
  name: string;
  dob: string | null;
  details: Record<string, unknown>;
  hlaAlleles: string[];
  createdAt: string;
  updatedAt: string;
  files: PatientFile[];
  notes: PatientNote[];
  runs: PipelineRun[];
}

export interface PatientsListResponse {
  patients: PatientSummary[];
  total: number;
}

// ── Fetch all patients ──────────────────────────────────────────────────────

export async function fetchPatients(
  search?: string,
): Promise<PatientsListResponse> {
  const params = new URLSearchParams();
  if (search) params.set("search", search);
  const qs = params.toString();

  const response = await fetch(`/api/patients${qs ? `?${qs}` : ""}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch patients: ${response.status}`);
  }
  return response.json();
}

// ── Fetch single patient ────────────────────────────────────────────────────

export async function fetchPatient(id: string): Promise<PatientDetail> {
  const response = await fetch(`/api/patients/${id}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch patient: ${response.status}`);
  }
  return response.json();
}

// ── Create patient ──────────────────────────────────────────────────────────

export async function createPatient(data: {
  name: string;
  dob?: string;
  details?: Record<string, unknown>;
}): Promise<PatientDetail> {
  const response = await fetch("/api/patients", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    throw new Error(`Failed to create patient: ${response.status}`);
  }
  return response.json();
}

// ── Update patient ──────────────────────────────────────────────────────────

export async function updatePatient(
  id: string,
  data: {
    name?: string;
    dob?: string | null;
    details?: Record<string, unknown>;
    hlaAlleles?: string[];
  },
): Promise<PatientDetail> {
  const response = await fetch(`/api/patients/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    throw new Error(`Failed to update patient: ${response.status}`);
  }
  return response.json();
}

// ── Delete patient ──────────────────────────────────────────────────────────

export async function deletePatient(id: string): Promise<void> {
  const response = await fetch(`/api/patients/${id}`, {
    method: "DELETE",
  });
  if (!response.ok) {
    throw new Error(`Failed to delete patient: ${response.status}`);
  }
}

// ── Add note ────────────────────────────────────────────────────────────────

export async function addPatientNote(
  patientId: string,
  content: string,
  source: "agent" | "user" = "user",
): Promise<PatientNote> {
  const response = await fetch(`/api/patients/${patientId}/notes`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content, source }),
  });
  if (!response.ok) {
    throw new Error(`Failed to add note: ${response.status}`);
  }
  return response.json();
}

// ── Upload file to patient ──────────────────────────────────────────────────

export async function uploadPatientFile(
  patientId: string,
  file: File,
  notes?: string,
): Promise<PatientFile> {
  const formData = new FormData();
  formData.append("file", file);
  if (notes) formData.append("notes", notes);

  const response = await fetch(`/api/patients/${patientId}/files`, {
    method: "POST",
    body: formData,
  });
  if (!response.ok) {
    throw new Error(`Failed to upload file: ${response.status}`);
  }
  return response.json();
}
