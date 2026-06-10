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
      {/* Assistant avatar — Bloom icon on terra cotta */}
      {!isUser && (
        <div
          className="flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center
                     bg-accent p-1.5"
        >
          <svg
            viewBox="0 0 32 32"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
            className="w-full h-full"
          >
            <circle cx="16" cy="13" r="4" fill="#FFFDF8" opacity="0.9" />
            <ellipse
              cx="10.5"
              cy="15.5"
              rx="3.5"
              ry="4.5"
              transform="rotate(-30 10.5 15.5)"
              fill="#FFFDF8"
              opacity="0.6"
            />
            <ellipse
              cx="21.5"
              cy="15.5"
              rx="3.5"
              ry="4.5"
              transform="rotate(30 21.5 15.5)"
              fill="#FFFDF8"
              opacity="0.6"
            />
            <ellipse
              cx="12"
              cy="20"
              rx="3.5"
              ry="4.5"
              transform="rotate(-60 12 20)"
              fill="#FFFDF8"
              opacity="0.45"
            />
            <ellipse
              cx="20"
              cy="20"
              rx="3.5"
              ry="4.5"
              transform="rotate(60 20 20)"
              fill="#FFFDF8"
              opacity="0.45"
            />
            <circle cx="16" cy="16" r="2.5" fill="#FFFDF8" />
            <rect
              x="15.25"
              y="20"
              width="1.5"
              height="8"
              rx="0.75"
              fill="#FFFDF8"
              opacity="0.7"
            />
          </svg>
        </div>
      )}

      {/* Bubble */}
      <div className="relative group max-w-[80%]">
        <div
          className={`rounded-2xl px-4 py-3 ${
            isUser
              ? "bg-primary text-primary-foreground"
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
                <span className="inline-block w-2 h-4 bg-primary rounded-sm animate-pulse ml-0.5 align-middle" />
              )}
            </div>
          )}
        </div>

        {/* Info button — assistant messages only, with metadata */}
        {!isUser && meta && !isStreaming && (
          <>
            <button
              id="message-info-toggle"
              onClick={() => setShowInfo(!showInfo)}
              className="absolute -bottom-2 left-2 w-5 h-5 rounded-full
                       flex items-center justify-center text-[10px]
                       bg-secondary text-muted-foreground
                       border border-border
                       opacity-0 group-hover:opacity-100
                       transition-opacity duration-200
                       hover:bg-primary/20 hover:text-foreground
                       cursor-pointer z-10"
              title="Response info"
            >
              i
            </button>

            {/* Info tooltip */}
            {showInfo && (
              <div
                className="absolute top-full left-0 mt-2 w-64 rounded-xl
                         bg-card border border-border
                         shadow-lg z-50 overflow-hidden
                         animate-[fade-in_0.15s_ease-out]"
              >
                <div className="px-3 py-2 border-b border-border">
                  <p className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium">
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
          </>
        )}
      </div>

      {/* User avatar — person silhouette on olive green */}
      {isUser && (
        <div
          className="flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center
                     bg-primary p-1.5"
        >
          <svg
            viewBox="0 0 24 24"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
            className="w-full h-full"
          >
            <circle cx="12" cy="8" r="4" fill="#FFFDF8" />
            <path
              d="M4 20c0-3.314 3.582-6 8-6s8 2.686 8 6"
              stroke="#FFFDF8"
              strokeWidth="2"
              strokeLinecap="round"
            />
          </svg>
        </div>
      )}
    </div>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-2">
      <span className="text-[10px] text-muted-foreground uppercase tracking-wide flex-shrink-0">
        {label}
      </span>
      <span className="text-[11px] text-foreground text-right font-medium leading-tight">
        {value}
      </span>
    </div>
  );
}
