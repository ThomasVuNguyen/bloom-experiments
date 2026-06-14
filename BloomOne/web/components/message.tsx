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
      {/* Assistant avatar */}
      {!isUser && (
        <div
          className="flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center
                     bg-accent text-accent-foreground text-sm font-serif font-bold"
        >
          B
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

      {/* User avatar */}
      {isUser && (
        <div
          className="flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center
                     bg-primary text-primary-foreground text-sm font-bold"
        >
          U
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
