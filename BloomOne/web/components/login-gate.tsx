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
    <div className="min-h-screen bg-background flex items-center justify-center p-4">
      {/* Background gradient orbs — soft sage/cream */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none">
        <div
          className="absolute top-1/4 -left-32 w-96 h-96 rounded-full opacity-30"
          style={{
            background:
              "radial-gradient(circle, var(--primary) 0%, transparent 70%)",
          }}
        />
        <div
          className="absolute bottom-1/4 -right-32 w-96 h-96 rounded-full opacity-20"
          style={{
            background:
              "radial-gradient(circle, var(--muted) 0%, transparent 70%)",
          }}
        />
        <div
          className="absolute top-2/3 left-1/3 w-64 h-64 rounded-full opacity-15"
          style={{
            background:
              "radial-gradient(circle, var(--accent) 0%, transparent 70%)",
          }}
        />
      </div>

      <div className="glass rounded-2xl p-8 w-full max-w-sm animate-[fade-in_0.4s_ease-out] relative z-10">
        {/* Bloom Icon */}
        <div className="text-center mb-6">
          <h1 className="text-2xl font-serif font-semibold text-foreground">
            BloomOne
          </h1>
          <p className="text-sm font-serif text-muted-foreground mt-1">
            Personalized Neoantigen Vaccine Platform
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
              className="w-full px-4 py-3 rounded-xl bg-input border border-border 
                         text-foreground placeholder:text-muted-foreground
                         focus:outline-none focus:ring-2 focus:ring-ring focus:border-transparent
                         transition-all duration-200"
            />
          </div>

          {error && (
            <p className="text-sm text-destructive animate-[fade-in_0.2s_ease-out]">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={loading || !password}
            className="w-full py-3 px-4 rounded-xl font-medium transition-all duration-200
                       bg-accent text-accent-foreground
                       hover:bg-[#c4613f] active:scale-[0.98]
                       disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {loading ? "Verifying..." : "Enter"}
          </button>
        </form>

        <p className="text-xs text-muted-foreground text-center mt-4">
          Research use only · Not for clinical decisions
        </p>
      </div>
    </div>
  );
}
