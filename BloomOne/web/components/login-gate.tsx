"use client";

import { useState, FormEvent } from "react";

interface LoginGateProps {
  children: React.ReactNode;
}

export function LoginGate({ children }: LoginGateProps) {
  const [authenticated, setAuthenticated] = useState(() => {
    if (typeof window !== "undefined") {
      return document.cookie.includes("bloom_auth=1");
    }
    return false;
  });
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");

    try {
      const res = await fetch("/api/auth", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password }),
      });

      if (res.ok) {
        document.cookie = "bloom_auth=1; path=/; max-age=604800; SameSite=Lax";
        setAuthenticated(true);
      } else {
        setError("Incorrect password");
      }
    } catch {
      setError("Connection error — try again");
    }
    setLoading(false);
  };

  if (authenticated) {
    return <>{children}</>;
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      {/* Background gradient orbs */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none">
        <div
          className="absolute top-1/4 -left-32 w-96 h-96 rounded-full opacity-20"
          style={{
            background:
              "radial-gradient(circle, oklch(0.72 0.18 160) 0%, transparent 70%)",
          }}
        />
        <div
          className="absolute bottom-1/4 -right-32 w-96 h-96 rounded-full opacity-15"
          style={{
            background:
              "radial-gradient(circle, oklch(0.65 0.2 170) 0%, transparent 70%)",
          }}
        />
      </div>

      <div className="glass rounded-2xl p-8 w-full max-w-sm animate-[fade-in_0.4s_ease-out] relative z-10">
        {/* DNA Helix Icon */}
        <div className="text-center mb-6">
          <div className="text-5xl mb-3">🧬</div>
          <h1 className="text-2xl font-semibold text-[var(--foreground)]">
            BloomOne
          </h1>
          <p className="text-sm text-[var(--muted-foreground)] mt-1">
            Neoantigen Vaccine Pipeline
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <input
              type="password"
              placeholder="Enter access password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoFocus
              className="w-full px-4 py-3 rounded-xl bg-[var(--input)] border border-[var(--border)] 
                         text-[var(--foreground)] placeholder:text-[var(--muted-foreground)]
                         focus:outline-none focus:ring-2 focus:ring-[var(--ring)] focus:border-transparent
                         transition-all duration-200"
            />
          </div>

          {error && (
            <p className="text-sm text-[var(--destructive)] animate-[fade-in_0.2s_ease-out]">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={loading || !password}
            className="w-full py-3 px-4 rounded-xl font-medium transition-all duration-200
                       bg-[var(--primary)] text-[var(--primary-foreground)]
                       hover:opacity-90 active:scale-[0.98]
                       disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {loading ? "Verifying..." : "Enter"}
          </button>
        </form>

        <p className="text-xs text-[var(--muted-foreground)] text-center mt-4">
          Research use only · Not for clinical decisions
        </p>
      </div>
    </div>
  );
}
