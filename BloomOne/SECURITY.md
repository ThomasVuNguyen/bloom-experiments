# BloomOne Security Model

BloomOne uses a layered architecture where no single secret compromise gives full access. LLM API keys never touch the browser or user-facing frontend. Vertex AI access uses keyless OIDC authentication — no credential is ever created or stored.

## Architecture

```
User (browser) → Coolify frontend (no secrets) → Modal backend (secrets here) → LLM APIs
                                                                                ├── OpenRouter (API key)
                                                                                ├── CloudRift (API key)
                                                                                └── Vertex AI (OIDC → WIF, no key)
```

- **Coolify frontend:** Next.js app. Holds only a shared `BLOOMONE_API_KEY` for authenticating to Modal. Cannot call any LLM directly.
- **Modal backend:** Private compute layer. Holds API keys for OpenRouter/CloudRift. For Vertex AI, uses OIDC token exchange — no key stored.
- **Vertex AI (Gemini 2.5 Pro):** Authenticated via Workload Identity Federation. Modal's OIDC JWT is exchanged at runtime for a 1-hour GCP access token. No service account key ever created.

---

## Secrets Inventory

| Secret | Location | Purpose | Blast radius if leaked |
|--------|----------|---------|------------------------|
| `OPENROUTER_API_KEY` | Modal secret | Authenticates to OpenRouter LLM API | Attacker can generate text on your bill (free tier, capped by quota) |
| `CLOUDRIFT_API_KEY` | Modal secret | Authenticates to CloudRift LLM API | Attacker can generate text on CloudRift (capped) |
| `BLOOMONE_API_KEY` | Modal secret + Coolify | Authenticates frontend→Modal link | Attacker can call Modal `/v1/chat` endpoint |
| `vertex-ai-wif-config` | Modal secret | GCP project ID, number, region, SA email | **No blast radius** — contains only public project metadata, not credentials |

---

## API Key Restrictions (OpenRouter / CloudRift)

- **Scope:** Keys are specific to each LLM provider (OpenRouter, CloudRift) — cannot access GCP resources
- **Quota:** Rate-limited by provider (OpenRouter free tier, CloudRift caps)
- **Budget alert:** Monitor via provider dashboards

## Vertex AI — OIDC + Workload Identity Federation

Gemini 2.5 Pro uses **keyless authentication** via Modal OIDC → GCP Workload Identity Federation.

```
Modal container → MODAL_IDENTITY_TOKEN (JWT) → GCP STS → 1-hour access token → Vertex AI
```

### What exists in GCP

| Resource | What it is | If leaked |
|----------|-----------|----------|
| Service account `bloomone-llm@starmind-72daa` | Impersonation target (no key) | Not a credential — useless without valid OIDC token |
| Workload Identity Pool `modal-pool` | Trust config for Modal OIDC | Public metadata — no secret value |
| OIDC Provider `modal-provider` | Maps `oidc.modal.com` tokens | Public knowledge |
| IAM binding: `roles/aiplatform.user` | SA can call Vertex AI | Cannot create/delete resources, access Storage/BigQuery/IAM |

### Threat Analysis

**To call Vertex AI, an attacker must:**
1. Be running code on YOUR Modal workspace (to get a valid OIDC JWT)
2. The JWT is signed by Modal and verified by GCP STS
3. Even then, the token only grants `aiplatform.user` — text generation only

**If the Modal account is compromised:** Attacker gets OIDC token access but tokens expire in 1 hour. Disable the WIF pool to instantly revoke all access:
```bash
gcloud iam workload-identity-pools update modal-pool --location=global --disabled --project=starmind-72daa
```

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

1. **No secrets in browser** — Frontend never sees any LLM API key
2. **Endpoint authentication** — Modal validates `Authorization: Bearer` header on every request
3. **Keyless Vertex AI** — OIDC + WIF, no credential file ever created
4. **Short-lived tokens** — Vertex AI access tokens expire in 1 hour, auto-refreshed
5. **Minimal IAM** — SA has only `aiplatform.user`, cannot access other GCP resources
6. **Shared project isolation** — WIF pool scoped to Modal identity only
7. **Quota caps** — Hard limits on requests/min and tokens/min per provider
8. **Budget alerts** — Dollar threshold notifications
9. **Kill switch** — Disable WIF pool with one command to revoke all Vertex AI access

---

## Incident Response

| Scenario | Action |
|----------|--------|
| OpenRouter/CloudRift key leaked | Revoke on provider dashboard → Create new → Update Modal secret |
| BloomOne API key leaked | Generate new random key → Update Modal + Coolify secrets → Redeploy |
| Suspicious Vertex AI usage | `gcloud iam workload-identity-pools update modal-pool --location=global --disabled --project=starmind-72daa` |
| Modal account compromised | Disable WIF pool (above) + rotate all Modal secrets + enable 2FA |
| Budget alert triggered | Review usage → Disable WIF pool if unauthorized → Check provider dashboards |
