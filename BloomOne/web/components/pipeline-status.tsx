"use client";

const STAGE_LABELS = ["Ingest", "Mutate", "Peptide", "Bind", "Safety", "Rank", "Construct"];

/** Simple dot representing a growth stage */
function StageDot({ status }: { status: "completed" | "active" | "pending" | "error" }) {
  const bgClass: Record<string, string> = {
    completed: "bg-primary",
    active: "bg-pop",
    pending: "bg-muted opacity-50",
    error: "bg-destructive",
  };
  return (
    <div className={`w-3 h-3 rounded-full flex-shrink-0 ${bgClass[status]}`} />
  );
}

function getStageStatus(update: string): "completed" | "active" | "error" {
  if (update.startsWith("✅")) return "completed";
  if (update.startsWith("⚠️")) return "error";
  return "active";
}

function getStageIndex(update: string): number {
  for (let i = 1; i <= 7; i++) {
    if (update.includes(`Stage ${i}`)) return i - 1;
  }
  return -1;
}

interface PipelineStatusProps {
  updates: string[];
  isActive: boolean;
}

export function PipelineStatus({ updates, isActive }: PipelineStatusProps) {
  if (updates.length === 0) return null;

  // Determine which stages are completed / active / error
  const stageStatuses: Record<number, "completed" | "active" | "error"> = {};
  updates.forEach((u) => {
    const idx = getStageIndex(u);
    if (idx >= 0) {
      stageStatuses[idx] = getStageStatus(u);
    }
  });

  return (
    <div className="glass rounded-xl p-4 mb-4 animate-[fade-in_0.3s_ease-out]">
      {/* Header */}
      <div className="flex items-center gap-2 mb-3">
        {isActive ? (
          <div className="w-2 h-2 rounded-full bg-pop animate-[pulse-glow_2.5s_ease-in-out_infinite]" />
        ) : (
          <div className="w-2 h-2 rounded-full bg-muted-foreground" />
        )}
        <span className="text-xs font-medium text-primary uppercase tracking-wider">
          Pipeline {isActive ? "Running" : "Complete"}
        </span>
      </div>

      {/* Stage indicators */}
      <div className="flex items-center gap-1 mb-3">
        {STAGE_LABELS.map((label, i) => {
          const status = stageStatuses[i] || "pending";
          return (
            <div key={i} className="flex flex-col items-center gap-0.5 flex-1 min-w-0">
              <div className={status === "active" ? "animate-[pulse-glow_2.5s_ease-in-out_infinite]" : ""}>
                <StageDot status={status} />
              </div>
              <span
                className={`text-[8px] leading-tight truncate w-full text-center ${
                  status === "completed"
                    ? "text-primary"
                    : status === "active"
                      ? "text-foreground font-medium"
                      : status === "error"
                        ? "text-destructive"
                        : "text-muted-foreground"
                }`}
              >
                {label}
              </span>
            </div>
          );
        })}
      </div>

      {/* Update log */}
      <div className="space-y-1.5">
        {updates.map((update, i) => {
          const status = getStageStatus(update);

          return (
            <div
              key={i}
              className={`flex items-start gap-2 text-sm animate-[slide-up_0.2s_ease-out] ${
                status === "completed"
                  ? "text-primary"
                  : status === "error"
                    ? "text-destructive"
                    : "text-foreground"
              }`}
              style={{ animationDelay: `${i * 50}ms` }}
            >
              <span className="leading-relaxed">{update}</span>
            </div>
          );
        })}

        {isActive && (
          <div className="flex items-center gap-2 text-sm text-muted-foreground mt-2">
            <div className="w-3.5 h-3.5 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
            <span>Working...</span>
          </div>
        )}
      </div>
    </div>
  );
}
