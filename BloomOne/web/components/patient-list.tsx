"use client";

import { useState, useEffect, useCallback } from "react";
import type { PatientSummary } from "@/lib/patient-api";
import { fetchPatients, deletePatient } from "@/lib/patient-api";

interface PatientListProps {
  onSelectPatient: (id: string) => void;
  selectedPatientId: string | null;
}

function formatDate(dateStr: string | null): string {
  if (!dateStr) return "";
  return new Date(dateStr).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

/** Small bloom icon for pipeline dots */
function SmallBloomIcon() {
  return (
    <svg viewBox="0 0 16 16" fill="none" className="w-3 h-3 inline-block">
      <circle cx="8" cy="7" r="2.5" fill="var(--primary)" opacity="0.9" />
      <circle cx="8" cy="8" r="1.2" fill="var(--accent)" />
      <ellipse cx="5.5" cy="8.5" rx="2" ry="2.5" transform="rotate(-30 5.5 8.5)" fill="var(--primary)" opacity="0.5" />
      <ellipse cx="10.5" cy="8.5" rx="2" ry="2.5" transform="rotate(30 10.5 8.5)" fill="var(--primary)" opacity="0.5" />
    </svg>
  );
}

/** Small paperclip icon for file count */
function SmallPaperclipIcon() {
  return (
    <svg className="w-2.5 h-2.5 inline-block" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13"
      />
    </svg>
  );
}

/** Compact pipeline progress dots (stages 1-7) */
function PipelineDots({ runCount }: { runCount: number }) {
  if (runCount === 0) return null;
  return (
    <span
      className="inline-flex items-center gap-0.5 text-[10px] px-1.5 py-0.5 rounded-full bg-primary/10 text-primary"
      title={`${runCount} pipeline run${runCount > 1 ? "s" : ""}`}
    >
      <SmallBloomIcon /> {runCount}
    </span>
  );
}

function PatientCard({
  patient,
  isActive,
  onSelect,
  onDelete,
}: {
  patient: PatientSummary;
  isActive: boolean;
  onSelect: () => void;
  onDelete: () => void;
}) {
  return (
    <button
      onClick={onSelect}
      className={`w-full text-left px-3 py-2.5 rounded-lg text-sm transition-all duration-150 group
        bg-card border
        ${
          isActive
            ? "bg-secondary border-l-2 border-primary"
            : "border-border hover:bg-secondary/50"
        }`}
    >
      <div className="flex items-start justify-between gap-1">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5">
            <span className="text-foreground font-medium truncate">
              {patient.name}
            </span>
            {patient.fileCount > 0 && (
              <span
                className="inline-flex items-center gap-0.5 text-[10px] px-1.5 py-0.5 rounded-full bg-muted/50 text-muted-foreground"
                title={`${patient.fileCount} file${patient.fileCount > 1 ? "s" : ""}`}
              >
                <SmallPaperclipIcon /> {patient.fileCount}
              </span>
            )}
            <PipelineDots runCount={patient.runCount} />
          </div>
          {patient.dob && (
            <span className="text-[10px] text-muted-foreground mt-0.5 block">
              DOB: {formatDate(patient.dob)}
            </span>
          )}
        </div>
        <button
          onClick={(e) => {
            e.stopPropagation();
            if (confirm(`Delete patient "${patient.name}"?`)) {
              onDelete();
            }
          }}
          className="flex-shrink-0 opacity-0 group-hover:opacity-60 hover:!opacity-100 transition-opacity p-0.5 rounded text-muted-foreground hover:text-destructive hover:bg-destructive/10"
          title="Delete patient"
        >
          <svg
            className="w-3.5 h-3.5"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M6 18L18 6M6 6l12 12"
            />
          </svg>
        </button>
      </div>
      <span className="text-[10px] text-muted-foreground mt-0.5 block">
        Added {formatDate(patient.createdAt)}
      </span>
    </button>
  );
}

export function PatientList({
  onSelectPatient,
  selectedPatientId,
}: PatientListProps) {
  const [patients, setPatients] = useState<PatientSummary[]>([]);
  const [loading, setLoading] = useState(true);

  const loadPatients = useCallback(async () => {
    try {
      const result = await fetchPatients();
      setPatients(result.patients);
    } catch (err) {
      console.error("Failed to load patients:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadPatients();
    // Refresh every 10 seconds to pick up agent-created patients
    const interval = setInterval(loadPatients, 10000);
    return () => clearInterval(interval);
  }, [loadPatients]);

  const handleDelete = useCallback(
    async (id: string) => {
      try {
        await deletePatient(id);
        setPatients((prev) => prev.filter((p) => p.id !== id));
      } catch (err) {
        console.error("Failed to delete patient:", err);
      }
    },
    [],
  );

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="w-5 h-5 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
      </div>
    );
  }

  if (patients.length === 0) {
    return (
      <p className="text-xs text-muted-foreground text-center py-8 px-4">
        No patients yet. The agent will create records during chat, or add one manually.
      </p>
    );
  }

  return (
    <div className="space-y-0.5">
      {patients.map((patient) => (
        <PatientCard
          key={patient.id}
          patient={patient}
          isActive={patient.id === selectedPatientId}
          onSelect={() => onSelectPatient(patient.id)}
          onDelete={() => handleDelete(patient.id)}
        />
      ))}
    </div>
  );
}
