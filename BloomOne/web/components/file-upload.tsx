"use client";

import { useRef, useState, useCallback } from "react";
import { uploadFile } from "@/lib/api";

/** Inline SVG paperclip icon */
function PaperclipIcon({ className = "w-4 h-4" }: { className?: string }) {
  return (
    <svg
      className={className}
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
  );
}

interface FileUploadProps {
  onFileUploaded: (fileInfo: { id: string; path: string; filename: string }) => void;
  disabled?: boolean;
}

export function FileUpload({ onFileUploaded, disabled }: FileUploadProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState("");
  const [uploadedFiles, setUploadedFiles] = useState<string[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFiles = useCallback(
    async (files: File[]) => {
      if (files.length === 0) return;
      setUploading(true);
      const uploaded: string[] = [];
      try {
        for (let i = 0; i < files.length; i++) {
          setUploadProgress(`Uploading ${i + 1}/${files.length}: ${files[i].name}`);
          const result = await uploadFile(files[i]);
          uploaded.push(result.filename);
          onFileUploaded({ id: result.id, path: result.path, filename: result.filename });
        }
        setUploadedFiles(uploaded);
      } catch (err) {
        console.error("Upload failed:", err);
      } finally {
        setUploading(false);
        setUploadProgress("");
      }
    },
    [onFileUploaded],
  );

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragging(false);
      const files = Array.from(e.dataTransfer.files);
      if (files.length) handleFiles(files);
    },
    [handleFiles],
  );

  const handleInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const files = Array.from(e.target.files || []);
      if (files.length) handleFiles(files);
    },
    [handleFiles],
  );

  if (uploadedFiles.length > 0) {
    return (
      <div className="flex items-center gap-2 px-3 py-2 rounded-xl bg-primary/5 border border-primary/20 text-sm">
        <PaperclipIcon className="w-4 h-4 text-primary flex-shrink-0" />
        <span className="text-primary truncate max-w-[200px]">
          {uploadedFiles.length === 1
            ? uploadedFiles[0]
            : `${uploadedFiles.length} files uploaded`}
        </span>
        <button
          onClick={() => setUploadedFiles([])}
          className="text-muted-foreground hover:text-destructive ml-auto transition-colors"
        >
          <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
          </svg>
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
        multiple
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
              ? "border-primary bg-primary/5 text-primary"
              : "border-muted-foreground/40 text-muted-foreground hover:border-primary/60 hover:text-primary"
          }
          disabled:opacity-40 disabled:cursor-not-allowed`}
        title="Upload MAF/VCF file"
      >
        {uploading ? (
          <div className="w-4 h-4 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
        ) : (
          <PaperclipIcon />
        )}
        <span className="hidden sm:inline">
          {uploading ? (uploadProgress || "Uploading...") : "Attach file"}
        </span>
      </button>
    </>
  );
}
