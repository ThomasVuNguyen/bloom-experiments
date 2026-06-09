"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import type { PatientDetail, PatientNote } from "@/lib/patient-api";
import {
  fetchPatient,
  updatePatient,
  addPatientNote,
  uploadPatientFile,
} from "@/lib/patient-api";

interface PatientDetailPanelProps {
  patientId: string;
  onClose: () => void;
}

function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return "—";
  return new Date(dateStr).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function formatDateTime(dateStr: string): string {
  return new Date(dateStr).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes}B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)}MB`;
}

/** Icon for file type */
function FileTypeIcon({ type }: { type: string }) {
  const icons: Record<string, string> = {
    image: "🖼️",
    pdf: "📄",
    genomic: "🧬",
    document: "📝",
    dicom: "🏥",
  };
  return <span>{icons[type] || "📎"}</span>;
}

/** Expandable section */
function Section({
  title,
  count,
  defaultOpen,
  children,
}: {
  title: string;
  count?: number;
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen ?? true);

  return (
    <div className="border-b border-[var(--border)] last:border-0">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-4 py-2.5 hover:bg-[var(--secondary)]/30 transition-colors"
      >
        <span className="text-xs font-semibold uppercase tracking-wider text-[var(--muted-foreground)]">
          {title}
          {count !== undefined && (
            <span className="ml-1.5 text-[10px] font-normal">({count})</span>
          )}
        </span>
        <svg
          className={`w-3.5 h-3.5 text-[var(--muted-foreground)] transition-transform ${open ? "rotate-180" : ""}`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>
      {open && <div className="px-4 pb-3">{children}</div>}
    </div>
  );
}

export function PatientDetailPanel({
  patientId,
  onClose,
}: PatientDetailPanelProps) {
  const [patient, setPatient] = useState<PatientDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [noteText, setNoteText] = useState("");
  const [addingNote, setAddingNote] = useState(false);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    try {
      const data = await fetchPatient(patientId);
      setPatient(data);
    } catch (err) {
      console.error("Failed to load patient:", err);
    } finally {
      setLoading(false);
    }
  }, [patientId]);

  useEffect(() => {
    load();
  }, [load]);

  const handleAddNote = useCallback(async () => {
    if (!noteText.trim()) return;
    setAddingNote(true);
    try {
      await addPatientNote(patientId, noteText.trim(), "user");
      setNoteText("");
      load(); // Refresh
    } catch (err) {
      console.error("Failed to add note:", err);
    } finally {
      setAddingNote(false);
    }
  }, [patientId, noteText, load]);

  const handleFileUpload = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (!file) return;
      setUploading(true);
      try {
        await uploadPatientFile(patientId, file);
        load(); // Refresh
      } catch (err) {
        console.error("Failed to upload file:", err);
      } finally {
        setUploading(false);
        if (fileInputRef.current) fileInputRef.current.value = "";
      }
    },
    [patientId, load],
  );

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="w-6 h-6 border-2 border-[var(--primary)]/30 border-t-[var(--primary)] rounded-full animate-spin" />
      </div>
    );
  }

  if (!patient) {
    return (
      <div className="flex items-center justify-center h-full text-sm text-[var(--muted-foreground)]">
        Patient not found
      </div>
    );
  }

  const details = (patient.details || {}) as Record<string, unknown>;
  const detailEntries = Object.entries(details).filter(
    ([, v]) => v !== null && v !== undefined && v !== "",
  );

  return (
    <div className="flex flex-col h-full bg-[var(--card)] border-l border-[var(--border)]">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-[var(--border)]">
        <div>
          <h2 className="text-base font-semibold text-[var(--foreground)]">
            {patient.name}
          </h2>
          <p className="text-[11px] text-[var(--muted-foreground)]">
            {patient.dob ? `DOB: ${formatDate(patient.dob)}` : "No DOB"} · ID:{" "}
            <span className="font-mono">{patient.id.slice(0, 8)}</span>
          </p>
        </div>
        <button
          onClick={onClose}
          className="p-1.5 rounded-lg hover:bg-[var(--secondary)] transition-colors"
          title="Close"
        >
          <svg
            className="w-4 h-4 text-[var(--muted-foreground)]"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      {/* Scrollable content */}
      <div className="flex-1 overflow-y-auto">
        {/* HLA Alleles */}
        {patient.hlaAlleles.length > 0 && (
          <Section title="HLA Alleles">
            <div className="flex flex-wrap gap-1.5">
              {patient.hlaAlleles.map((a, i) => (
                <span
                  key={i}
                  className="text-[11px] px-2 py-0.5 rounded-full bg-[var(--primary)]/10 text-[var(--primary)] font-mono"
                >
                  {a}
                </span>
              ))}
            </div>
          </Section>
        )}

        {/* Details */}
        {detailEntries.length > 0 && (
          <Section title="Details">
            <div className="space-y-1.5">
              {detailEntries.map(([key, value]) => (
                <div key={key} className="flex justify-between text-xs">
                  <span className="text-[var(--muted-foreground)] capitalize">
                    {key.replace(/_/g, " ")}
                  </span>
                  <span className="text-[var(--foreground)] font-medium">
                    {String(value)}
                  </span>
                </div>
              ))}
            </div>
          </Section>
        )}

        {/* Files */}
        <Section title="Files" count={patient.files.length}>
          <div className="space-y-1.5">
            {patient.files.map((file) => (
              <div
                key={file.id}
                className="flex items-center gap-2 px-2.5 py-2 rounded-lg bg-[var(--secondary)]/40 text-xs"
              >
                <FileTypeIcon type={file.fileType} />
                <div className="flex-1 min-w-0">
                  <p className="text-[var(--foreground)] truncate font-medium">
                    {file.filename}
                  </p>
                  <p className="text-[var(--muted-foreground)] text-[10px]">
                    {formatBytes(file.sizeBytes)} · {file.fileType}
                    {file.notes && ` · ${file.notes}`}
                  </p>
                </div>
              </div>
            ))}
            {/* Upload button */}
            <input
              ref={fileInputRef}
              type="file"
              onChange={handleFileUpload}
              className="hidden"
              accept=".maf,.vcf,.tsv,.csv,.txt,.pdf,.png,.jpg,.jpeg,.gif,.bmp,.tiff,.dcm,.doc,.docx,.xlsx"
            />
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={uploading}
              className="w-full flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg
                border border-dashed border-[var(--border)] text-xs text-[var(--muted-foreground)]
                hover:border-[var(--primary)]/50 hover:text-[var(--foreground)] transition-colors
                disabled:opacity-40"
            >
              {uploading ? (
                <>
                  <div className="w-3 h-3 border border-current border-t-transparent rounded-full animate-spin" />
                  Uploading...
                </>
              ) : (
                <>📎 Attach file</>
              )}
            </button>
          </div>
        </Section>

        {/* Notes */}
        <Section title="Notes" count={patient.notes.length}>
          <div className="space-y-2">
            {/* Add note input */}
            <div className="flex gap-1.5">
              <input
                value={noteText}
                onChange={(e) => setNoteText(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    handleAddNote();
                  }
                }}
                placeholder="Add a note..."
                className="flex-1 px-2.5 py-1.5 text-xs rounded-lg bg-[var(--secondary)]/50 
                  border border-[var(--border)] text-[var(--foreground)]
                  placeholder:text-[var(--muted-foreground)] outline-none
                  focus:border-[var(--primary)]/50"
              />
              <button
                onClick={handleAddNote}
                disabled={!noteText.trim() || addingNote}
                className="px-2.5 py-1.5 text-xs rounded-lg bg-[var(--primary)] text-white
                  hover:opacity-90 transition-opacity disabled:opacity-40"
              >
                Add
              </button>
            </div>
            {/* Notes timeline */}
            {patient.notes.map((note: PatientNote) => (
              <div
                key={note.id}
                className="px-2.5 py-2 rounded-lg bg-[var(--secondary)]/30 text-xs"
              >
                <div className="flex items-center gap-1.5 mb-0.5">
                  <span className="text-[10px]">
                    {note.source === "agent" ? "🤖" : "👤"}
                  </span>
                  <span className="text-[10px] text-[var(--muted-foreground)]">
                    {formatDateTime(note.createdAt)}
                  </span>
                </div>
                <p className="text-[var(--foreground)] whitespace-pre-wrap leading-relaxed">
                  {note.content}
                </p>
              </div>
            ))}
          </div>
        </Section>

        {/* Pipeline Runs */}
        <Section title="Pipeline Runs" count={patient.runs.length}>
          {patient.runs.length === 0 ? (
            <p className="text-[10px] text-[var(--muted-foreground)]">
              No pipeline runs yet.
            </p>
          ) : (
            <div className="space-y-2">
              {patient.runs.map((run) => (
                <div
                  key={run.id}
                  className="px-2.5 py-2 rounded-lg bg-[var(--secondary)]/30 text-xs"
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-[var(--muted-foreground)] text-[10px]">
                      {formatDateTime(run.startedAt)}
                    </span>
                    <div className="flex gap-0.5">
                      {[1, 2, 3, 4, 5, 6, 7].map((stage) => (
                        <div
                          key={stage}
                          className={`w-2 h-2 rounded-full ${
                            run.stagesCompleted.includes(stage)
                              ? "bg-[var(--primary)]"
                              : "bg-[var(--muted)]/30"
                          }`}
                          title={`Stage ${stage}`}
                        />
                      ))}
                    </div>
                  </div>
                  {run.summary && (
                    <p className="text-[var(--foreground)] whitespace-pre-wrap leading-relaxed">
                      {run.summary}
                    </p>
                  )}
                </div>
              ))}
            </div>
          )}
        </Section>
      </div>
    </div>
  );
}
