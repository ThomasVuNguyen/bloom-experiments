"use client";

import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ChatMessage } from "@/lib/api";

interface MessageProps {
  message: ChatMessage;
  isStreaming?: boolean;
}

export function Message({ message, isStreaming }: MessageProps) {
  const isUser = message.role === "user";
  const meta = message.metadata;
  const [showInfo, setShowInfo] = useState(false);

  return (
    <div
      className={`flex gap-3 animate-[slide-up_0.3s_ease-out] ${
        isUser ? "justify-end" : "justify-start"
      }`}
    >
      {/* Avatar */}
      {!isUser && (
        <div
          className="flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center text-sm
                     bg-[var(--primary)] text-[var(--primary-foreground)]"
        >
          🧬
        </div>
      )}

      {/* Bubble */}
      <div className="relative group max-w-[80%]">
        <div
          className={`rounded-2xl px-4 py-3 ${
            isUser
              ? "bg-[var(--primary)] text-[var(--primary-foreground)]"
              : "glass"
          }`}
        >
          {isUser ? (
            <p className="text-sm leading-relaxed whitespace-pre-wrap">
              {message.content}
            </p>
          ) : (
            <div className="markdown-body text-sm leading-relaxed">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {message.content}
              </ReactMarkdown>
              {isStreaming && (
                <span className="inline-block w-2 h-4 bg-[var(--primary)] rounded-sm animate-pulse ml-0.5 align-middle" />
              )}
            </div>
          )}
        </div>

        {/* Info button — assistant messages only, with metadata */}
        {!isUser && meta && !isStreaming && (
          <div className="relative inline-block">
            <button
              id="message-info-toggle"
              onClick={() => setShowInfo(!showInfo)}
              className="absolute -bottom-1 right-1 w-5 h-5 rounded-full
                       flex items-center justify-center text-[10px]
                       bg-[var(--secondary)] text-[var(--muted-foreground)]
                       border border-[var(--border)]
                       opacity-0 group-hover:opacity-100
                       transition-opacity duration-200
                       hover:bg-[var(--primary)]/20 hover:text-[var(--foreground)]
                       cursor-pointer z-10"
              title="Response info"
            >
              i
            </button>

            {/* Info tooltip */}
            {showInfo && (
              <div
                className="absolute bottom-7 right-0 w-64 rounded-xl
                         bg-[var(--card)] border border-[var(--border)]
                         shadow-2xl z-50 overflow-hidden
                         animate-[fade-in_0.15s_ease-out]"
              >
                <div className="px-3 py-2 border-b border-[var(--border)]">
                  <p className="text-[10px] uppercase tracking-wider text-[var(--muted-foreground)] font-medium">
                    Response Info
                  </p>
                </div>
                <div className="px-3 py-2 space-y-1.5">
                  <InfoRow
                    label="Model"
                    value={
                      meta.model.split("/")[1]?.split(":")[0] || meta.model
                    }
                  />
                  <InfoRow label="Provider" value={meta.provider} />
                  <InfoRow
                    label="Tokens"
                    value={`${meta.total_tokens.toLocaleString()} (${meta.prompt_tokens.toLocaleString()}↑ ${meta.completion_tokens.toLocaleString()}↓)`}
                  />
                  {meta.tool_calls > 0 && (
                    <InfoRow
                      label="Tool calls"
                      value={`${meta.tool_calls} (${meta.rounds} round${meta.rounds > 1 ? "s" : ""})`}
                    />
                  )}
                  <InfoRow
                    label="Latency"
                    value={`${meta.latency_s}s`}
                  />
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* User avatar */}
      {isUser && (
        <div
          className="flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center text-sm
                     bg-[var(--secondary)] text-[var(--secondary-foreground)]"
        >
          👤
        </div>
      )}
    </div>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-2">
      <span className="text-[10px] text-[var(--muted-foreground)] uppercase tracking-wide flex-shrink-0">
        {label}
      </span>
      <span className="text-[11px] text-[var(--foreground)] text-right font-medium leading-tight">
        {value}
      </span>
    </div>
  );
}
