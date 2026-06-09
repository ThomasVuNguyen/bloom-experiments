"use client";

import { useRef, useState, useCallback } from "react";
import { uploadFile } from "@/lib/api";

interface FileUploadProps {
  onFileUploaded: (path: string, filename: string) => void;
  disabled?: boolean;
}

export function FileUpload({ onFileUploaded, disabled }: FileUploadProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadedFile, setUploadedFile] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFile = useCallback(
    async (file: File) => {
      setUploading(true);
      try {
        const result = await uploadFile(file);
        setUploadedFile(result.filename);
        onFileUploaded(result.path, result.filename);
      } catch (err) {
        console.error("Upload failed:", err);
      } finally {
        setUploading(false);
      }
    },
    [onFileUploaded],
  );

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragging(false);
      const file = e.dataTransfer.files[0];
      if (file) handleFile(file);
    },
    [handleFile],
  );

  const handleInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) handleFile(file);
    },
    [handleFile],
  );

  if (uploadedFile) {
    return (
      <div className="flex items-center gap-2 px-3 py-2 rounded-xl bg-[var(--primary)]/10 border border-[var(--primary)]/30 text-sm">
        <span>📎</span>
        <span className="text-[var(--primary)] truncate max-w-[200px]">
          {uploadedFile}
        </span>
        <button
          onClick={() => setUploadedFile(null)}
          className="text-[var(--muted-foreground)] hover:text-[var(--foreground)] ml-auto"
        >
          ✕
        </button>
      </div>
    );
  }

  return (
    <>
      <input
        ref={inputRef}
        type="file"
        accept=".maf,.vcf,.tsv,.csv,.txt,.pdf,.png,.jpg,.jpeg,.gif,.bmp,.tiff,.dcm,.doc,.docx,.xlsx"
        onChange={handleInputChange}
        className="hidden"
      />
      <button
        type="button"
        disabled={disabled || uploading}
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setIsDragging(true);
        }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={handleDrop}
        className={`flex items-center gap-2 px-3 py-2 rounded-xl text-sm transition-all duration-200
          border border-dashed
          ${
            isDragging
              ? "border-[var(--primary)] bg-[var(--primary)]/10 text-[var(--primary)]"
              : "border-[var(--border)] text-[var(--muted-foreground)] hover:border-[var(--primary)]/50 hover:text-[var(--foreground)]"
          }
          disabled:opacity-40 disabled:cursor-not-allowed`}
        title="Upload MAF/VCF file"
      >
        {uploading ? (
          <svg
            className="w-4 h-4"
            style={{ animation: "spin-slow 1s linear infinite" }}
            viewBox="0 0 24 24"
            fill="none"
          >
            <circle
              cx="12"
              cy="12"
              r="10"
              stroke="currentColor"
              strokeWidth="3"
              strokeDasharray="60"
              strokeLinecap="round"
            />
          </svg>
        ) : (
          <svg
            className="w-4 h-4"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13"
            />
          </svg>
        )}
        <span className="hidden sm:inline">
          {uploading ? "Uploading..." : "Attach file"}
        </span>
      </button>
    </>
  );
}
