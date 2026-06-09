"use client";

const STAGE_ICONS: Record<string, string> = {
  "Stage 1": "📥",
  "Stage 2": "🔬",
  "Stage 3": "🧬",
  "Stage 4": "🔬",
  "Stage 5": "🛡️",
  "Stage 6": "📊",
  "Stage 7": "💉",
  "Analyzing": "🔍",
  "Running": "🚀",
};

function getIcon(status: string): string {
  for (const [key, icon] of Object.entries(STAGE_ICONS)) {
    if (status.includes(key)) return icon;
  }
  if (status.startsWith("✅")) return "";
  if (status.startsWith("⚠️")) return "";
  return "⏳";
}

interface PipelineStatusProps {
  updates: string[];
  isActive: boolean;
}

export function PipelineStatus({ updates, isActive }: PipelineStatusProps) {
  if (updates.length === 0) return null;

  return (
    <div className="glass rounded-xl p-4 mb-4 animate-[fade-in_0.3s_ease-out]">
      <div className="flex items-center gap-2 mb-3">
        {isActive ? (
          <div
            className="w-2 h-2 rounded-full bg-[var(--primary)]"
            style={{ animation: "pulse-glow 1.5s ease-in-out infinite" }}
          />
        ) : (
          <div className="w-2 h-2 rounded-full bg-[var(--muted-foreground)]" />
        )}
        <span className="text-xs font-medium text-[var(--muted-foreground)] uppercase tracking-wider">
          Pipeline {isActive ? "Running" : "Complete"}
        </span>
      </div>

      <div className="space-y-1.5">
        {updates.map((update, i) => {
          const icon = getIcon(update);
          const isComplete = update.startsWith("✅");
          const isError = update.startsWith("⚠️");

          return (
            <div
              key={i}
              className={`flex items-start gap-2 text-sm animate-[slide-up_0.2s_ease-out] ${
                isComplete
                  ? "text-[var(--primary)]"
                  : isError
                    ? "text-[var(--destructive)]"
                    : "text-[var(--foreground)]"
              }`}
              style={{ animationDelay: `${i * 50}ms` }}
            >
              {icon && <span className="flex-shrink-0">{icon}</span>}
              <span className="leading-relaxed">{update}</span>
            </div>
          );
        })}

        {isActive && (
          <div className="flex items-center gap-2 text-sm text-[var(--muted-foreground)] mt-2">
            <svg
              className="w-3.5 h-3.5"
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
            <span>Working...</span>
          </div>
        )}
      </div>
    </div>
  );
}
