"use client";

import {
  useState,
  useRef,
  useEffect,
  useCallback,
  type FormEvent,
} from "react";
import { Message } from "./message";
import { PipelineStatus } from "./pipeline-status";
import { FileUpload } from "./file-upload";
import { streamChat, type ChatMessage } from "@/lib/api";

const EXAMPLES = [
  "Run the neoantigen vaccine pipeline for melanoma case TCGA-BF-A3DL-01 with HLA-A*02:01,HLA-B*07:02,HLA-C*07:01",
  "What data do you need to design a neoantigen vaccine?",
  "Explain the 7 pipeline stages",
];

export function Chat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [statusUpdates, setStatusUpdates] = useState<string[]>([]);
  const [uploadedFilePath, setUploadedFilePath] = useState<string | null>(null);
  const [streamingContent, setStreamingContent] = useState("");

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Full message history for LLM context (includes tool calls)
  const [llmHistory, setLlmHistory] = useState<ChatMessage[]>([]);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, streamingContent, statusUpdates, scrollToBottom]);

  // Auto-resize textarea
  useEffect(() => {
    if (inputRef.current) {
      inputRef.current.style.height = "auto";
      inputRef.current.style.height = `${Math.min(inputRef.current.scrollHeight, 160)}px`;
    }
  }, [input]);

  const handleSubmit = useCallback(
    async (e?: FormEvent, overrideInput?: string) => {
      e?.preventDefault();
      const text = overrideInput ?? input.trim();
      if (!text || isLoading) return;

      // Build user content with file context
      let content = text;
      if (uploadedFilePath) {
        content = `[User uploaded a MAF file to: ${uploadedFilePath}]\n\n${content}`;
        setUploadedFilePath(null);
      }

      const userMessage: ChatMessage = { role: "user", content };
      const newMessages = [...messages, userMessage];
      const newHistory = [...llmHistory, userMessage];

      setMessages(newMessages);
      setInput("");
      setIsLoading(true);
      setStatusUpdates([]);
      setStreamingContent("");

      let finalText = "";
      let updatedHistory = newHistory;

      try {
        for await (const event of streamChat(newHistory)) {
          switch (event.type) {
            case "status":
              if (event.content) {
                setStatusUpdates((prev) => [...prev, event.content!]);
              }
              break;
            case "text":
              finalText = event.content || "";
              setStreamingContent(finalText);
              break;
            case "error":
              finalText = `❌ ${event.content || "Unknown error"}`;
              setStreamingContent(finalText);
              break;
            case "done":
              if (event.updated_messages) {
                updatedHistory = event.updated_messages;
              }
              break;
          }
        }
      } catch (err) {
        finalText = `❌ Connection error: ${err instanceof Error ? err.message : "Unknown error"}`;
      }

      // Build the final response content
      let responseContent = "";
      if (statusUpdates.length > 0 || finalText) {
        responseContent = finalText;
      }

      if (responseContent) {
        const assistantMessage: ChatMessage = {
          role: "assistant",
          content: responseContent,
        };
        setMessages((prev) => [...prev, assistantMessage]);
      }

      setLlmHistory(updatedHistory);
      setStreamingContent("");
      setStatusUpdates([]);
      setIsLoading(false);
    },
    [input, isLoading, messages, llmHistory, uploadedFilePath, statusUpdates],
  );

  const handleFileUploaded = useCallback(
    (path: string, _filename: string) => {
      setUploadedFilePath(path);
    },
    [],
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSubmit();
      }
    },
    [handleSubmit],
  );

  return (
    <div className="flex flex-col h-screen max-w-3xl mx-auto">
      {/* Header */}
      <header className="flex items-center justify-between px-4 py-3 border-b border-[var(--border)]">
        <div className="flex items-center gap-3">
          <span className="text-2xl">🧬</span>
          <div>
            <h1 className="text-base font-semibold text-[var(--foreground)]">
              BloomOne
            </h1>
            <p className="text-xs text-[var(--muted-foreground)]">
              Neoantigen Vaccine Design
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[10px] px-2 py-0.5 rounded-full bg-[var(--primary)]/15 text-[var(--primary)] font-medium uppercase tracking-wide">
            Research Only
          </span>
        </div>
      </header>

      {/* Messages area */}
      <div className="flex-1 overflow-y-auto px-4 py-6 space-y-6">
        {messages.length === 0 && !isLoading && (
          <div className="flex flex-col items-center justify-center h-full text-center animate-[fade-in_0.5s_ease-out]">
            {/* Ambient glow */}
            <div className="relative mb-8">
              <div
                className="absolute inset-0 w-24 h-24 rounded-full mx-auto opacity-30"
                style={{
                  background:
                    "radial-gradient(circle, oklch(0.72 0.18 160) 0%, transparent 70%)",
                  animation: "pulse-glow 3s ease-in-out infinite",
                }}
              />
              <div className="text-6xl relative z-10">🧬</div>
            </div>

            <h2 className="text-xl font-semibold text-[var(--foreground)] mb-2">
              Welcome to BloomOne
            </h2>
            <p className="text-sm text-[var(--muted-foreground)] max-w-md mb-8 leading-relaxed">
              Design personalized mRNA neoantigen vaccine constructs from tumor
              mutations. Upload a MAF file or start with a TCGA case.
            </p>

            <div className="grid gap-2 w-full max-w-md">
              {EXAMPLES.map((example, i) => (
                <button
                  key={i}
                  onClick={() => handleSubmit(undefined, example)}
                  className="text-left px-4 py-3 rounded-xl glass text-sm text-[var(--foreground)]
                           hover:border-[var(--primary)]/50 transition-all duration-200
                           hover:translate-y-[-1px] active:translate-y-0"
                >
                  {example}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg, i) => (
          <Message key={i} message={msg} />
        ))}

        {/* Live streaming state */}
        {isLoading && (
          <>
            {statusUpdates.length > 0 && (
              <PipelineStatus updates={statusUpdates} isActive={true} />
            )}
            {streamingContent ? (
              <Message
                message={{ role: "assistant", content: streamingContent }}
                isStreaming={true}
              />
            ) : (
              statusUpdates.length === 0 && (
                <div className="flex gap-3 animate-[fade-in_0.3s_ease-out]">
                  <div className="w-8 h-8 rounded-full flex items-center justify-center bg-[var(--primary)] text-sm">
                    🧬
                  </div>
                  <div className="glass rounded-2xl px-4 py-3">
                    <div className="flex gap-1.5">
                      <div
                        className="w-2 h-2 rounded-full bg-[var(--muted-foreground)]"
                        style={{
                          animation: "pulse-glow 1.2s ease-in-out infinite",
                        }}
                      />
                      <div
                        className="w-2 h-2 rounded-full bg-[var(--muted-foreground)]"
                        style={{
                          animation:
                            "pulse-glow 1.2s ease-in-out 0.2s infinite",
                        }}
                      />
                      <div
                        className="w-2 h-2 rounded-full bg-[var(--muted-foreground)]"
                        style={{
                          animation:
                            "pulse-glow 1.2s ease-in-out 0.4s infinite",
                        }}
                      />
                    </div>
                  </div>
                </div>
              )
            )}
          </>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input area */}
      <div className="border-t border-[var(--border)] px-4 py-3">
        <form
          onSubmit={handleSubmit}
          className="flex items-end gap-2 max-w-3xl mx-auto"
        >
          <FileUpload
            onFileUploaded={handleFileUploaded}
            disabled={isLoading}
          />

          <div className="flex-1 relative">
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Describe your neoantigen analysis..."
              disabled={isLoading}
              rows={1}
              className="w-full px-4 py-3 rounded-xl bg-[var(--input)] border border-[var(--border)]
                       text-[var(--foreground)] placeholder:text-[var(--muted-foreground)]
                       focus:outline-none focus:ring-2 focus:ring-[var(--ring)] focus:border-transparent
                       resize-none transition-all duration-200 text-sm
                       disabled:opacity-50 disabled:cursor-not-allowed"
            />
          </div>

          <button
            type="submit"
            disabled={isLoading || (!input.trim() && !uploadedFilePath)}
            className="flex-shrink-0 p-3 rounded-xl transition-all duration-200
                     bg-[var(--primary)] text-[var(--primary-foreground)]
                     hover:opacity-90 active:scale-95
                     disabled:opacity-30 disabled:cursor-not-allowed"
          >
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
                d="M6 12L3.269 3.126A59.768 59.768 0 0121.485 12 59.77 59.77 0 013.27 20.876L5.999 12zm0 0h7.5"
              />
            </svg>
          </button>
        </form>

        <p className="text-[10px] text-[var(--muted-foreground)] text-center mt-2">
          ⚠️ All outputs are for research use only · Not validated for clinical
          decisions
        </p>
      </div>
    </div>
  );
}
