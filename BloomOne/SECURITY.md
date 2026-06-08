# BloomOne Security Model

BloomOne uses a layered architecture where no single secret compromise gives full access. The Gemini API key never touches the browser or user-facing frontend.

## Architecture

```
User (browser) → HF Space (Gradio, no secrets) → Modal backend (secrets here) → Gemini API
```

- **HF Space:** Public Gradio UI. Holds only a shared `BLOOMONE_API_KEY` for authenticating to Modal. Cannot call Gemini directly.
- **Modal backend:** Private compute layer. Holds `GEMINI_API_KEY` and `BLOOMONE_API_KEY`. Validates incoming requests, proxies to Gemini.
- **Gemini API:** Google-managed. Restricted API key with quota caps.

---

## Secrets Inventory

| Secret | Location | Purpose | Blast radius if leaked |
|--------|----------|---------|------------------------|
| `GEMINI_API_KEY` | Modal secret | Authenticates to Gemini API | Attacker can generate text on your bill (capped by quota) |
| `BLOOMONE_API_KEY` | Modal secret + HF Space secret | Authenticates HF→Modal link | Attacker can call Modal `/v1/chat` endpoint |
| `HF_TOKEN` | Modal secret | Pulls gated models from HF Hub | Attacker can access private HF repos on your account |

---

## API Key Restrictions (Gemini)

Applied in Google Cloud Console → API & Services → Credentials:

- **API restriction:** "Generative Language API" only — key cannot access Cloud Storage, Compute, BigQuery, etc.
- **Quota:** 10 RPM, 100K tokens/min — caps runaway abuse
- **Budget alert:** $10/day — triggers email notification
- **Referrer restriction (optional):** Lock to Modal's egress IPs

---

## Threat Model

### If `GEMINI_API_KEY` leaks

| Can do | Cannot do |
|--------|-----------|
| Call Gemini API on your bill | Access GCP project resources |
| Generate text/images | Read Cloud Storage, BigQuery |
| Consume quota (capped) | Access Modal, HF, or infrastructure |

**Worst case:** ~$5–20/day before quota blocks them. Revoke in Cloud Console in 30 seconds.

### If `BLOOMONE_API_KEY` leaks

| Can do | Cannot do |
|--------|-----------|
| Call Modal `/v1/chat` | Get the Gemini key |
| Proxy through your infra | Access Modal dashboard |
| Consume Modal compute + Gemini tokens | Modify deployments |

**Mitigation:** Rate limiting on Modal. Rotate the key and redeploy.

### If Modal account is compromised

This is the worst case — attacker gets all secrets. **Mitigation:** 2FA on Modal, audit logs, minimal secrets.

---

## Defense Layers

1. **No secrets in browser** — HF Space frontend never sees the Gemini key
2. **Endpoint authentication** — Modal validates `X-API-Key` header on every request
3. **API restriction** — Gemini key locked to one API, cannot pivot
4. **Quota caps** — Hard limits on requests/min and tokens/min
5. **Budget alerts** — Dollar threshold notifications
6. **Key rotation** — All secrets stored as env vars, rotatable without code changes
7. **Minimal permissions** — Each secret has the narrowest possible scope

---

## Incident Response

| Scenario | Action |
|----------|--------|
| Gemini key leaked | Revoke in Cloud Console → Credentials → Delete key → Create new → Update Modal secret |
| BloomOne key leaked | Generate new random key → Update Modal + HF Space secrets → Redeploy |
| Suspicious usage spike | Check Cloud Console → APIs & Services → Dashboard for anomalous traffic |
| Budget alert triggered | Review usage → Revoke key if unauthorized → Rotate |
