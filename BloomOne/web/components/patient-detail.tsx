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

/** SVG icons for file types */
function FileTypeIcon({ type }: { type: string }) {
  const iconClass = "w-4 h-4 flex-shrink-0";

  if (type === "image") {
    return (
      <svg className={iconClass} fill="none" viewBox="0 0 24 24" stroke="var(--primary)" strokeWidth={1.5}>
        <rect x="3" y="3" width="18" height="18" rx="2" />
        <circle cx="8.5" cy="8.5" r="1.5" fill="var(--accent)" stroke="none" />
        <path d="M21 15l-5-5L5 21" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    );
  }

  if (type === "pdf") {
    return (
      <svg className={iconClass} fill="none" viewBox="0 0 24 24" stroke="var(--primary)" strokeWidth={1.5}>
        <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" strokeLinecap="round" strokeLinejoin="round" />
        <polyline points="14 2 14 8 20 8" strokeLinecap="round" strokeLinejoin="round" />
        <line x1="9" y1="13" x2="15" y2="13" strokeLinecap="round" />
        <line x1="9" y1="17" x2="13" y2="17" strokeLinecap="round" />
      </svg>
    );
  }

  if (type === "genomic") {
    return (
      <svg className={iconClass} viewBox="0 0 24 24" fill="none" stroke="var(--primary)" strokeWidth={1.5}>
        <path d="M12 3c-3 2.5-3 6.5 0 9s3 6.5 0 9" strokeLinecap="round" />
        <path d="M12 3c3 2.5 3 6.5 0 9s-3 6.5 0 9" strokeLinecap="round" />
        <line x1="8" y1="7" x2="16" y2="7" strokeLinecap="round" />
        <line x1="7" y1="12" x2="17" y2="12" strokeLinecap="round" />
        <line x1="8" y1="17" x2="16" y2="17" strokeLinecap="round" />
      </svg>
    );
  }

  if (type === "dicom") {
    return (
      <svg className={iconClass} fill="none" viewBox="0 0 24 24" stroke="var(--primary)" strokeWidth={1.5}>
        <rect x="3" y="3" width="18" height="18" rx="2" />
        <path d="M12 8v8M8 12h8" strokeLinecap="round" />
      </svg>
    );
  }

  // document / default
  return (
    <svg className={iconClass} fill="none" viewBox="0 0 24 24" stroke="var(--primary)" strokeWidth={1.5}>
      <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" strokeLinecap="round" strokeLinejoin="round" />
      <polyline points="14 2 14 8 20 8" strokeLinecap="round" strokeLinejoin="round" />
      <line x1="9" y1="13" x2="15" y2="13" strokeLinecap="round" />
      <line x1="9" y1="17" x2="15" y2="17" strokeLinecap="round" />
    </svg>
  );
}

/** SVG paperclip icon */
function PaperclipIcon({ className = "w-4 h-4" }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13"
      />
    </svg>
  );
}

/** SVG icon for agent notes (circuit/bot) */
function AgentIcon() {
  return (
    <svg className="w-3.5 h-3.5" viewBox="0 0 16 16" fill="none">
      <rect x="2" y="3" width="12" height="10" rx="2" fill="var(--primary)" opacity="0.15" stroke="var(--primary)" strokeWidth="1" />
      <circle cx="6" cy="8" r="1.2" fill="var(--primary)" />
      <circle cx="10" cy="8" r="1.2" fill="var(--primary)" />
      <line x1="5" y1="11" x2="11" y2="11" stroke="var(--primary)" strokeWidth="0.8" strokeLinecap="round" />
    </svg>
  );
}

/** SVG icon for user notes */
function UserIcon() {
  return (
    <svg className="w-3.5 h-3.5" viewBox="0 0 16 16" fill="none">
      <circle cx="8" cy="5.5" r="2.5" fill="var(--primary)" opacity="0.2" stroke="var(--primary)" strokeWidth="1" />
      <path d="M3 14c0-2.76 2.24-5 5-5s5 2.24 5 5" fill="var(--primary)" opacity="0.15" stroke="var(--primary)" strokeWidth="1" strokeLinecap="round" />
    </svg>
  );
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
    <div className="border-b border-border last:border-0">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-4 py-2.5 hover:bg-secondary/30 transition-colors"
      >
        <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground font-serif">
          {title}
          {count !== undefined && (
            <span className="ml-1.5 text-[10px] font-normal font-sans">({count})</span>
          )}
        </span>
        <svg
          className={`w-3.5 h-3.5 text-muted-foreground transition-transform ${open ? "rotate-180" : ""}`}
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
        <div className="w-6 h-6 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
      </div>
    );
  }

  if (!patient) {
    return (
      <div className="flex items-center justify-center h-full text-sm text-muted-foreground">
        Patient not found
      </div>
    );
  }

  const details = (patient.details || {}) as Record<string, unknown>;
  const detailEntries = Object.entries(details).filter(
    ([, v]) => v !== null && v !== undefined && v !== "",
  );

  return (
    <div className="flex flex-col h-full bg-card border-l border-border">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border">
        <div>
          <h2 className="text-base font-semibold font-serif text-foreground">
            {patient.name}
          </h2>
          <p className="text-[11px] text-muted-foreground">
            {patient.dob ? `DOB: ${formatDate(patient.dob)}` : "No DOB"} · ID:{" "}
            <span className="font-mono">{patient.id.slice(0, 8)}</span>
          </p>
        </div>
        <button
          onClick={onClose}
          className="p-1.5 rounded-lg hover:bg-secondary transition-colors text-muted-foreground hover:text-foreground"
          title="Close"
        >
          <svg
            className="w-4 h-4"
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
                  className="text-[11px] px-2 py-0.5 rounded-full bg-primary/10 text-primary border border-primary/20 font-mono"
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
                  <span className="text-muted-foreground capitalize">
                    {key.replace(/_/g, " ")}
                  </span>
                  <span className="text-foreground font-medium">
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
                className="flex items-center gap-2 px-2.5 py-2 rounded-lg bg-secondary/40 text-xs"
              >
                <FileTypeIcon type={file.fileType} />
                <div className="flex-1 min-w-0">
                  <p className="text-foreground truncate font-medium">
                    {file.filename}
                  </p>
                  <p className="text-muted-foreground text-[10px]">
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
                border border-dashed border-muted-foreground/40 text-xs text-muted-foreground
                hover:border-primary/60 hover:text-primary transition-colors
                disabled:opacity-40"
            >
              {uploading ? (
                <>
                  <div className="w-3 h-3 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
                  Uploading...
                </>
              ) : (
                <>
                  <PaperclipIcon className="w-3.5 h-3.5" /> Attach file
                </>
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
                className="flex-1 px-2.5 py-1.5 text-xs rounded-lg bg-secondary/50 
                  border border-border text-foreground
                  placeholder:text-muted-foreground outline-none
                  focus:border-primary/50"
              />
              <button
                onClick={handleAddNote}
                disabled={!noteText.trim() || addingNote}
                className="px-2.5 py-1.5 text-xs rounded-lg bg-primary text-primary-foreground
                  hover:bg-primary/90 transition-opacity disabled:opacity-40"
              >
                Add
              </button>
            </div>
            {/* Notes timeline */}
            {patient.notes.map((note: PatientNote) => (
              <div
                key={note.id}
                className="px-2.5 py-2 rounded-lg bg-secondary/30 text-xs"
              >
                <div className="flex items-center gap-1.5 mb-0.5">
                  {note.source === "agent" ? <AgentIcon /> : <UserIcon />}
                  <span className="text-[10px] text-muted-foreground">
                    {formatDateTime(note.createdAt)}
                  </span>
                </div>
                <p className="text-foreground whitespace-pre-wrap leading-relaxed">
                  {note.content}
                </p>
              </div>
            ))}
          </div>
        </Section>

        {/* Pipeline Runs */}
        <Section title="Pipeline Runs" count={patient.runs.length}>
          {patient.runs.length === 0 ? (
            <p className="text-[10px] text-muted-foreground">
              No pipeline runs yet.
            </p>
          ) : (
            <div className="space-y-2">
              {patient.runs.map((run) => (
                <div
                  key={run.id}
                  className="px-2.5 py-2 rounded-lg bg-secondary/30 text-xs"
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-muted-foreground text-[10px]">
                      {formatDateTime(run.startedAt)}
                    </span>
                    <div className="flex gap-0.5">
                      {[1, 2, 3, 4, 5, 6, 7].map((stage) => (
                        <div
                          key={stage}
                          className={`w-2 h-2 rounded-full ${
                            run.stagesCompleted.includes(stage)
                              ? "bg-primary"
                              : "bg-muted"
                          }`}
                          title={`Stage ${stage}`}
                        />
                      ))}
                    </div>
                  </div>
                  {run.summary && (
                    <p className="text-foreground whitespace-pre-wrap leading-relaxed">
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
