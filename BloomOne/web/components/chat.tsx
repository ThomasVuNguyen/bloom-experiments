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
import {
  streamChat,
  fetchModels,
  type ChatMessage,
  type ModelInfo,
  type ResponseMetadata,
} from "@/lib/api";

const EXAMPLES = [
  "Run the neoantigen vaccine pipeline for melanoma case TCGA-BF-A3DL-01 with HLA-A*02:01,HLA-B*07:02,HLA-C*07:01",
  "What data do you need to design a neoantigen vaccine?",
  "Explain the 7 pipeline stages",
];

/** Provider badge colors — CSS variable / hex values only */
const PROVIDER_COLORS: Record<string, string> = {
  openrouter: "var(--primary)",
  cloudrift: "#6a9bcc",
};



interface ChatProps {
  messages: ChatMessage[];
  onMessagesChange: (messages: ChatMessage[]) => void;
  /** Full LLM history including tool-call context */
  llmHistory: ChatMessage[];
  onLlmHistoryChange: (history: ChatMessage[]) => void;
  onSidebarToggle: () => void;
}

export function Chat({
  messages,
  onMessagesChange,
  llmHistory,
  onLlmHistoryChange,
  onSidebarToggle,
}: ChatProps) {
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [statusUpdates, setStatusUpdates] = useState<string[]>([]);
  const [uploadedFiles, setUploadedFiles] = useState<{id: string; path: string; filename: string}[]>([]);
  const [streamingContent, setStreamingContent] = useState("");
  const [streamingMetadata, setStreamingMetadata] = useState<ResponseMetadata | null>(null);

  // Model picker state
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [selectedModel, setSelectedModel] = useState<string>("");
  const [defaultModel, setDefaultModel] = useState<string>("");
  const [modelPickerOpen, setModelPickerOpen] = useState(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const modelPickerRef = useRef<HTMLDivElement>(null);

  // Fetch models on mount
  useEffect(() => {
    fetchModels()
      .then((data) => {
        setModels(data.models);
        setDefaultModel(data.default);
        if (!selectedModel) {
          setSelectedModel(data.default);
        }
      })
      .catch((err) => {
        console.error("Failed to fetch models:", err);
        // Hardcoded fallback if backend is unreachable
        setModels([
          {
            id: "google/gemma-4-31b-it:free",
            provider: "openrouter",
            display_name: "gemma-4-31b-it  (OpenRouter)",
          },
        ]);
        setSelectedModel("google/gemma-4-31b-it:free");
        setDefaultModel("google/gemma-4-31b-it:free");
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Close model picker on outside click
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (
        modelPickerRef.current &&
        !modelPickerRef.current.contains(event.target as Node)
      ) {
        setModelPickerOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

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
      if (uploadedFiles.length > 0) {
        const fileList = uploadedFiles
          .map((f) => `- ${f.filename} (file_id: ${f.id}, path: ${f.path})`)
          .join("\n");
        content = `[User uploaded ${uploadedFiles.length} file(s):\n${fileList}]\n\n${content}`;
        setUploadedFiles([]);
      }

      const userMessage: ChatMessage = { role: "user", content };
      const newMessages = [...messages, userMessage];
      const newHistory = [...llmHistory, userMessage];

      onMessagesChange(newMessages);
      setInput("");
      setIsLoading(true);
      setStatusUpdates([]);
      setStreamingContent("");
      setStreamingMetadata(null);

      let finalText = "";
      let updatedHistory = newHistory;
      const collectedStatus: string[] = [];

      let latestMetadata: ResponseMetadata | null = null;

      try {
        for await (const event of streamChat(newHistory, selectedModel || undefined)) {
          switch (event.type) {
            case "status":
              if (event.content) {
                collectedStatus.push(event.content);
                setStatusUpdates([...collectedStatus]);
              }
              break;
            case "text":
              finalText = event.content || "";
              setStreamingContent(finalText);
              if (event.metadata) {
                latestMetadata = event.metadata;
                setStreamingMetadata(event.metadata);
              }
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

      if (finalText) {
        const assistantMessage: ChatMessage = {
          role: "assistant",
          content: finalText,
          metadata: latestMetadata ?? undefined,
        };
        const finalMessages = [...newMessages, assistantMessage];
        onMessagesChange(finalMessages);
      }

      onLlmHistoryChange(updatedHistory);
      setStreamingContent("");
      setStreamingMetadata(null);
      setStatusUpdates([]);
      setIsLoading(false);
    },
    [input, isLoading, messages, llmHistory, uploadedFiles, selectedModel, onMessagesChange, onLlmHistoryChange],
  );

  const handleFileUploaded = useCallback(
    (fileInfo: { id: string; path: string; filename: string }) => {
      setUploadedFiles((prev) => [...prev, fileInfo]);
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

  const currentModel = models.find((m) => m.id === selectedModel);
  const shortModelName = currentModel
    ? currentModel.id.split("/")[1]?.split(":")[0] || currentModel.id
    : "Loading...";

  return (
    <div className="flex flex-col h-screen flex-1 min-w-0">
      {/* Header */}
      <header className="flex items-center justify-between px-4 py-3 bg-card/80 backdrop-blur-sm border-b border-border">
        <div className="flex items-center gap-3">
          {/* Mobile sidebar toggle */}
          <button
            onClick={onSidebarToggle}
            className="px-2 py-1 rounded-lg hover:bg-secondary transition-colors lg:hidden text-foreground text-sm font-medium"
          >
            Menu
          </button>
          <div>
            <h1 className="text-base font-semibold text-foreground font-serif">
              BloomOne
            </h1>
            <p className="text-xs text-muted-foreground">
              Neoantigen Vaccine Design
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {/* Model Picker */}
          <div className="relative" ref={modelPickerRef}>
            <button
              id="model-picker-trigger"
              onClick={() => setModelPickerOpen(!modelPickerOpen)}
              className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs
                       bg-secondary border border-border hover:bg-muted
                       transition-all duration-200
                       text-foreground"
              title="Select model"
            >
              <span
                className="w-1.5 h-1.5 rounded-full flex-shrink-0"
                style={{
                  background: currentModel
                    ? PROVIDER_COLORS[currentModel.provider] || "var(--muted-foreground)"
                    : "var(--muted-foreground)",
                }}
              />
              <span className="max-w-[120px] truncate hidden sm:inline">
                {shortModelName}
              </span>
              <span className={`text-[10px] transition-transform duration-200 inline-block ${
                  modelPickerOpen ? "rotate-180" : ""
                }`}>▾</span>
            </button>

            {/* Dropdown */}
            {modelPickerOpen && (
              <div
                className="absolute right-0 top-full mt-1 w-72 rounded-xl border border-border
                          bg-card shadow-lg z-50 overflow-hidden
                          animate-[fade-in_0.15s_ease-out]"
              >
                <div className="px-3 py-2 border-b border-border">
                  <p className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium">
                    Select Model
                  </p>
                </div>
                <div className="py-1 max-h-64 overflow-y-auto">
                  {models.map((model) => {
                    const isActive = model.id === selectedModel;
                    const isDefault = model.id === defaultModel;
                    const modelShort =
                      model.id.split("/")[1]?.split(":")[0] || model.id;

                    return (
                      <button
                        key={model.id}
                        id={`model-option-${model.provider}-${modelShort}`}
                        onClick={() => {
                          setSelectedModel(model.id);
                          setModelPickerOpen(false);
                        }}
                        className={`w-full flex items-center gap-3 px-3 py-2.5 text-left text-sm
                                  transition-colors duration-150
                                  ${
                                    isActive
                                      ? "bg-primary/10 text-foreground"
                                      : "text-foreground hover:bg-secondary"
                                  }`}
                      >
                        <span
                          className="w-2 h-2 rounded-full flex-shrink-0"
                          style={{
                            background:
                              PROVIDER_COLORS[model.provider] ||
                              "var(--muted-foreground)",
                          }}
                        />
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="font-medium truncate">
                              {modelShort}
                            </span>
                            {isDefault && (
                              <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-primary/10 text-primary font-medium uppercase">
                                default
                              </span>
                            )}
                          </div>
                          <span className="text-[10px] text-muted-foreground capitalize">
                            {model.provider}
                          </span>
                        </div>
                        {isActive && (
                          <span className="text-primary text-sm flex-shrink-0">✓</span>
                        )}
                      </button>
                    );
                  })}
                </div>
                <div className="px-3 py-2 border-t border-border">
                  <p className="text-[10px] text-muted-foreground leading-relaxed">
                    Auto-fallback is active — if the selected model fails,
                    others are tried automatically.
                  </p>
                </div>
              </div>
            )}
          </div>

          <span className="text-[10px] px-2 py-0.5 rounded-full text-muted-foreground font-medium uppercase tracking-wide border border-border">
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
              <div className="relative z-10 flex items-center justify-center">
                <span className="text-4xl font-serif font-bold text-primary">B1</span>
              </div>
            </div>

            <h2 className="text-xl font-semibold text-foreground mb-2 font-serif">
              Welcome to BloomOne
            </h2>
            <p className="text-sm text-muted-foreground max-w-md mb-8 leading-relaxed">
              Design personalized mRNA neoantigen vaccine constructs from tumor
              mutations. Upload a MAF file or start with a TCGA case.
            </p>

            <div className="grid gap-2 w-full max-w-md">
              {EXAMPLES.map((example, i) => (
                <button
                  key={i}
                  onClick={() => handleSubmit(undefined, example)}
                  className="text-left px-4 py-3 rounded-xl glass text-sm text-foreground
                           border border-transparent hover:border-primary/20 hover:shadow-sm
                           transition-all duration-200
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
                message={{ role: "assistant", content: streamingContent, metadata: streamingMetadata ?? undefined }}
                isStreaming={true}
              />
            ) : (
              statusUpdates.length === 0 && (
                <div className="flex gap-3 animate-[fade-in_0.3s_ease-out]">
                  <div className="w-8 h-8 rounded-full flex items-center justify-center bg-accent text-sm flex-shrink-0 font-serif font-bold text-accent-foreground">
                    B
                  </div>
                  <div className="glass rounded-2xl px-4 py-3 max-w-xs">
                    <div className="flex items-center gap-2.5">
                      <div className="flex gap-1">
                        <div
                          className="w-2 h-2 rounded-full bg-primary"
                          style={{
                            animation: "typing-bounce 1.4s ease-in-out infinite",
                          }}
                        />
                        <div
                          className="w-2 h-2 rounded-full bg-primary"
                          style={{
                            animation:
                              "typing-bounce 1.4s ease-in-out 0.2s infinite",
                          }}
                        />
                        <div
                          className="w-2 h-2 rounded-full bg-primary"
                          style={{
                            animation:
                              "typing-bounce 1.4s ease-in-out 0.4s infinite",
                          }}
                        />
                      </div>
                      <span className="text-xs text-muted-foreground">
                        Thinking...
                      </span>
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
      <div className="bg-card border-t border-border px-4 py-3">
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
              className="w-full px-4 py-3 rounded-xl bg-input border border-border
                       text-foreground placeholder:text-muted-foreground
                       focus:outline-none focus:ring-2 focus:ring-ring focus:border-transparent
                       resize-none transition-all duration-200 text-sm
                       disabled:opacity-50 disabled:cursor-not-allowed"
            />
          </div>

          <button
            type="submit"
            disabled={isLoading || (!input.trim() && uploadedFiles.length === 0)}
            className="flex-shrink-0 p-3 rounded-xl transition-all duration-200
                     bg-accent text-accent-foreground
                     hover:bg-[#c4613f] active:scale-95
                     disabled:opacity-30 disabled:cursor-not-allowed"
          >
            <span className="text-sm font-medium">Send</span>
          </button>
        </form>

        <p className="text-[10px] text-muted-foreground text-center mt-2">
          All outputs are for research use only · Not validated for clinical
          decisions
        </p>
      </div>
    </div>
  );
}
