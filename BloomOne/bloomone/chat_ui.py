"""
BloomOne Gradio Chat UI — Gemma 4 26B A4B powered chatbot.

Creates a Gradio chat interface that connects to OpenRouter's API
and orchestrates BloomOne pipeline tools via LLM function calling.

The UI maintains a full OpenAI message history (including tool calls
and results) in a Gradio State component for multi-turn context.

Compatible with Gradio 6.x (used by vLLM 0.22+).
"""

from __future__ import annotations

CUSTOM_CSS = """
.chatbot-container { min-height: 500px; }
.status-bar {
    padding: 8px 16px;
    border-radius: 8px;
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
    color: #e0e0e0;
    font-size: 0.85em;
    margin-bottom: 8px;
}
.header-section {
    text-align: center;
    padding: 16px 0;
}
.disclaimer {
    font-size: 0.75em;
    color: #888;
    text-align: center;
    padding: 4px 0;
}
"""


def create_app(
    llm_url: str = "https://openrouter.ai/api/v1",
    model_name: str = "google/gemma-4-31b-it:free",
):
    """
    Build and return the ASGI-compatible Gradio chatbot app.

    Parameters
    ----------
    llm_url : str
        Base URL of the OpenAI-compatible LLM endpoint (Gemini API or local).
    model_name : str
        Model name to use for chat completions.

    Returns
    -------
    FastAPI
        ASGI app ready for Modal ``@modal.asgi_app()`` deployment.
    """
    import os

    import gradio as gr
    from fastapi import FastAPI, Header as fastapi_Header
    from openai import OpenAI

    from bloomone.chat import SYSTEM_PROMPT, TOOL_LABELS, FALLBACK_MODELS, PREMIUM_MODELS, run_chat_turn

    # Build model choices for the dropdown from the fallback chain
    _provider_map = {m: p for m, p in FALLBACK_MODELS}
    _display_names = {
        "openrouter": "OpenRouter",
        "cloudrift": "CloudRift",
    }
    model_choices = [
        (
            f"{m.split('/')[1].split(':')[0]}  "
            f"({_display_names.get(p, p)})",
            m,
        )
        for m, p in FALLBACK_MODELS
    ]

    # ── OpenAI client (connects to Vertex AI / OpenRouter / Gemini) ────

    def _get_api_key():
        """Get auth token: Vertex AI uses OAuth2, others use API key."""
        # Check for explicit API keys first (OpenRouter, Gemini)
        for env_key in ("OPENROUTER_API_KEY", "GEMINI_API_KEY"):
            key = os.environ.get(env_key)
            if key:
                return key

        # Vertex AI: write SA JSON to file, then get OAuth2 token
        creds_json = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS_JSON")
        if creds_json:
            creds_path = "/tmp/gcp-credentials.json"
            with open(creds_path, "w") as f:
                f.write(creds_json)
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = creds_path

        try:
            import google.auth
            import google.auth.transport.requests

            creds, _ = google.auth.default(
                scopes=["https://www.googleapis.com/auth/cloud-platform"]
            )
            creds.refresh(google.auth.transport.requests.Request())
            print(f"[auth] Got GCP access token (expires: {creds.expiry})")
            return creds.token
        except Exception as e:
            print(f"[auth] Warning: Could not get GCP credentials: {e}")
            return "not-needed"

    api_key = _get_api_key()
    openrouter_client = OpenAI(base_url=llm_url, api_key=api_key)

    # CloudRift fallback client
    cloudrift_key = os.environ.get("CLOUDRIFT_API_KEY", "")
    cloudrift_client = (
        OpenAI(
            base_url="https://inference.cloudrift.ai/v1",
            api_key=cloudrift_key,
        )
        if cloudrift_key
        else None
    )

    clients = {"openrouter": openrouter_client}
    if cloudrift_client:
        clients["cloudrift"] = cloudrift_client

    # ── Vertex AI client (OIDC + Workload Identity Federation) ────
    # No API key or SA key — uses Modal's OIDC token exchanged for
    # a short-lived GCP access token at runtime. Nothing to leak.
    #
    # IMPORTANT: OIDC tokens expire after ~1 hour. Since Modal containers
    # can live longer (scaledown_window=120s, max 30min active), we use
    # a lazy-refresh pattern: the client is recreated with a fresh token
    # whenever the current one is near expiry.
    _vertexai_available = False
    _wif_project_id = os.environ.get("GCP_PROJECT_ID", "")
    _wif_project_number = os.environ.get("GCP_PROJECT_NUMBER", "")
    _wif_region = os.environ.get("GCP_REGION", "us-central1")
    _wif_sa_email = os.environ.get(
        "GCP_SA_EMAIL",
        f"bloomone-llm@{_wif_project_id}.iam.gserviceaccount.com"
        if _wif_project_id else "",
    )
    _vertexai_creds = None  # Cached credentials object (handles refresh)

    def _get_vertexai_client():
        """
        Create an OpenAI client authenticated via OIDC → WIF → Vertex AI.

        Flow:
        1. Read Modal's OIDC JWT from MODAL_IDENTITY_TOKEN env var
        2. Exchange it for a GCP access token via Security Token Service
        3. Use the short-lived token as api_key for OpenAI client

        The credentials object is cached and auto-refreshed when expired.
        Returns None if OIDC token is not available (running locally).
        """
        nonlocal _vertexai_creds

        oidc_token = os.environ.get("MODAL_IDENTITY_TOKEN")
        if not oidc_token or not _wif_project_id:
            return None

        try:
            from google.auth import identity_pool, exceptions as auth_exceptions
            import google.auth.transport.requests

            # SubjectTokenSupplier reads the OIDC JWT from Modal's env var.
            # This is called each time credentials need refresh.
            class ModalOIDCSupplier(identity_pool.SubjectTokenSupplier):
                def get_subject_token(self, context, request):
                    token = os.environ.get("MODAL_IDENTITY_TOKEN")
                    if not token:
                        raise auth_exceptions.RefreshError(
                            "MODAL_IDENTITY_TOKEN not available"
                        )
                    return token

            # Reuse credentials if still valid (auto-refresh handles expiry)
            if _vertexai_creds is None or not _vertexai_creds.valid:
                audience = (
                    f"//iam.googleapis.com/projects/{_wif_project_number}"
                    f"/locations/global/workloadIdentityPools/modal-pool"
                    f"/providers/modal-provider"
                )

                _vertexai_creds = identity_pool.Credentials(
                    audience=audience,
                    subject_token_type="urn:ietf:params:oauth:token-type:jwt",
                    token_url="https://sts.googleapis.com/v1/token",
                    service_account_impersonation_url=(
                        f"https://iamcredentials.googleapis.com/v1/projects/-"
                        f"/serviceAccounts/{_wif_sa_email}:generateAccessToken"
                    ),
                    subject_token_supplier=ModalOIDCSupplier(),
                    scopes=["https://www.googleapis.com/auth/cloud-platform"],
                )

            _vertexai_creds.refresh(google.auth.transport.requests.Request())

            vertex_base_url = (
                f"https://{_wif_region}-aiplatform.googleapis.com/v1"
                f"/projects/{_wif_project_id}/locations/{_wif_region}"
                f"/endpoints/openapi"
            )

            print(f"[auth] Vertex AI OIDC token acquired (expires: {_vertexai_creds.expiry})")
            return OpenAI(base_url=vertex_base_url, api_key=_vertexai_creds.token)

        except Exception as e:
            print(f"[auth] Vertex AI OIDC auth failed: {e}")
            return None

    if _wif_project_id and _wif_project_number:
        vertexai_client = _get_vertexai_client()
        if vertexai_client:
            clients["vertexai"] = vertexai_client
            _vertexai_available = True
            print("[auth] ✅ Vertex AI client ready (OIDC + WIF, no keys)")
        else:
            print("[auth] ⚠️ Vertex AI OIDC not available (running locally?)")

    # Add premium models to dropdown (only if provider client initialized)
    _premium_display = {"vertexai": "Google Vertex AI"}
    for m, p in PREMIUM_MODELS:
        if p in clients:
            model_choices.append((f"⭐ {m}  ({_premium_display.get(p, p)})", m))
            _provider_map[m] = p

    # ── Gradio Interface (Gradio 6 compatible) ────────────────────────
    # In Gradio 6, theme/css/title moved from Blocks() to launch().
    # Chatbot lost: type, show_copy_button, placeholder params.

    with gr.Blocks(
        title="BloomOne — AI Neoantigen Vaccine Design",
    ) as demo:

        # ── Header ───────────────────────────────────────────────────
        gr.Markdown(
            """
            <div class="header-section">

            # 🧬 BloomOne

            ### Personalized Neoantigen Vaccine Pipeline

            AI-powered personalized mRNA vaccine design
            from tumor mutations.

            </div>
            """,
        )

        # ── Chat Components ──────────────────────────────────────────

        chatbot = gr.Chatbot(
            height=520,
            show_label=False,
            avatar_images=(None, "🧬"),
            elem_classes=["chatbot-container"],
        )

        # Full OpenAI message history (includes tool calls + results)
        openai_history = gr.State([])

        # Track uploaded file path
        uploaded_file_path = gr.State(None)

        # Persist model selection across chat turns
        model_state = gr.State(model_name)

        with gr.Row():
            msg = gr.Textbox(
                placeholder="Describe your neoantigen analysis...",
                show_label=False,
                container=False,
                scale=6,
                autofocus=True,
            )
            file_upload = gr.File(
                label="Upload MAF/VCF",
                file_types=[".maf", ".vcf", ".tsv", ".csv", ".txt"],
                file_count="single",
                scale=2,
                min_width=120,
            )
            send_btn = gr.Button(
                "Send",
                variant="primary",
                scale=1,
                min_width=80,
            )

        with gr.Accordion("⚙️ Model Settings", open=False):
            model_dropdown = gr.Dropdown(
                choices=model_choices,
                value=model_name,
                label="Primary Model",
                info=(
                    "Select the LLM to use. If it hits a rate limit, "
                    "the system automatically falls back to the next model."
                ),
                interactive=True,
            )

        gr.Markdown(
            '<p class="disclaimer">'
            "⚠️ All outputs are for <strong>RESEARCH USE ONLY</strong>. "
            "Not validated for clinical use."
            "</p>"
        )

        # ── Examples ─────────────────────────────────────────────────

        gr.Examples(
            examples=[
                "Run the neoantigen vaccine pipeline for melanoma case "
                "TCGA-BF-A3DL-01 with HLA-A*02:01,HLA-B*07:02,HLA-C*07:01",
                "What data do you need to design a neoantigen vaccine?",
                "Explain the pipeline stages",
            ],
            inputs=msg,
        )

        # ── Event Handlers ───────────────────────────────────────────

        def handle_file_upload(file, current_path):
            """Save uploaded file to Modal volume and return path."""
            if file is None:
                return current_path, gr.update()
            import shutil
            import pathlib

            upload_dir = "/data/uploads"
            pathlib.Path(upload_dir).mkdir(parents=True, exist_ok=True)

            # Gradio 6 passes a filepath string
            src_path = str(file)
            filename = pathlib.Path(src_path).name
            dest = f"{upload_dir}/{filename}"

            try:
                shutil.copy2(src_path, dest)
            except FileNotFoundError:
                # Gradio may have cleaned up the temp file — try reading
                # from the original path components
                try:
                    # If it's a NamedString or similar, read content
                    if hasattr(file, 'read'):
                        with open(dest, 'wb') as f:
                            f.write(file.read())
                    else:
                        return current_path, gr.update(
                            label="❌ Upload failed — file not found",
                        )
                except Exception:
                    return current_path, gr.update(
                        label="❌ Upload failed — try again",
                    )

            # Commit to Modal volume so other containers can see it
            try:
                from bloomone.config import volume
                volume.commit()
            except Exception:
                pass  # Running locally or volume not available

            return dest, gr.update(
                value=None,
                label=f"✅ Uploaded: {filename}",
            )

        def user_submit(message, display_history, full_history, file_path):
            """Immediately show user message and clear input."""
            if not message.strip() and not file_path:
                return "", display_history, full_history, file_path

            # Build the user message, prepending file info if available
            content = message.strip()
            if file_path:
                file_notice = (
                    f"[User uploaded a MAF file to: {file_path}]"
                )
                if content:
                    content = f"{file_notice}\n\n{content}"
                else:
                    content = (
                        f"{file_notice}\n\n"
                        "I've uploaded my MAF file. "
                        "Please run the pipeline with it."
                    )

            display_history = list(display_history) + [
                {"role": "user", "content": content}
            ]
            full_history = list(full_history) + [
                {"role": "user", "content": content}
            ]
            # Clear the file path after injecting into message
            return "", display_history, full_history, None

        def bot_respond(display_history, full_history, selected_model):
            """Stream LLM response with tool-call status updates."""
            # Resolve provider for the selected model
            sel_provider = _provider_map.get(selected_model, "openrouter")

            # Refresh Vertex AI client if selected (OIDC tokens expire hourly)
            if sel_provider == "vertexai" and _vertexai_available:
                refreshed = _get_vertexai_client()
                if refreshed:
                    clients["vertexai"] = refreshed

            # Build messages for LLM (system prompt + full history)
            llm_messages = [
                {"role": "system", "content": SYSTEM_PROMPT}
            ] + list(full_history)

            status_parts: list[str] = []
            responded = False

            for update in run_chat_turn(
                clients, llm_messages,
                model=selected_model, provider=sel_provider,
            ):
                if update["type"] == "status":
                    status_parts.append(update["content"])
                    partial = "\n".join(status_parts) + "\n\n⏳ *Working...*"
                    responded = True
                    yield (
                        display_history
                        + [{"role": "assistant", "content": partial}],
                        # Strip system prompt from stored history
                        llm_messages[1:],
                    )

                elif update["type"] == "text":
                    final_content = ""
                    if status_parts:
                        final_content = (
                            "\n".join(status_parts) + "\n\n---\n\n"
                        )
                    final_content += update["content"]
                    responded = True
                    yield (
                        display_history
                        + [{"role": "assistant", "content": final_content}],
                        llm_messages[1:],
                    )

                elif update["type"] == "error":
                    error_content = ""
                    if status_parts:
                        error_content = "\n".join(status_parts) + "\n\n"
                    error_content += f"❌ {update['content']}"
                    responded = True
                    yield (
                        display_history
                        + [{"role": "assistant", "content": error_content}],
                        llm_messages[1:],
                    )

            # Fallback: only if the LLM produced no output at all
            if not responded:
                yield (
                    display_history
                    + [
                        {
                            "role": "assistant",
                            "content": (
                                "I'm ready to help with neoantigen vaccine "
                                "design. What data do you have?"
                            ),
                        }
                    ],
                    llm_messages[1:],
                )

        def clear_chat():
            """Reset all chat state."""
            return [], []

        # ── Wire Events ──────────────────────────────────────────────

        # File upload handler
        file_upload.change(
            handle_file_upload,
            inputs=[file_upload, uploaded_file_path],
            outputs=[uploaded_file_path, file_upload],
        )

        # Sync dropdown → model state
        model_dropdown.change(
            lambda m: m,
            inputs=[model_dropdown],
            outputs=[model_state],
        )

        submit_event = msg.submit(
            user_submit,
            inputs=[msg, chatbot, openai_history, uploaded_file_path],
            outputs=[msg, chatbot, openai_history, uploaded_file_path],
        ).then(
            bot_respond,
            inputs=[chatbot, openai_history, model_state],
            outputs=[chatbot, openai_history],
        )

        send_btn.click(
            user_submit,
            inputs=[msg, chatbot, openai_history, uploaded_file_path],
            outputs=[msg, chatbot, openai_history, uploaded_file_path],
        ).then(
            bot_respond,
            inputs=[chatbot, openai_history, model_state],
            outputs=[chatbot, openai_history],
        )

    demo.queue(default_concurrency_limit=5)

    # Mount Gradio on a FastAPI app for ASGI compatibility
    fastapi_app = FastAPI(title="BloomOne Chatbot")

    # ── CORS (allow HF Spaces to call /api/chat) ─────────────────────
    from fastapi.middleware.cors import CORSMiddleware

    fastapi_app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # API key for REST endpoint auth (set via Modal secret)
    _api_key = os.environ.get("BLOOMONE_API_KEY", "")

    from starlette.responses import RedirectResponse, JSONResponse
    from starlette.routing import Route

    async def _health(request):
        return JSONResponse({"status": "ok", "model": model_name})

    async def _models(request):
        """Return available models for the frontend model picker."""
        models_list = [
            {
                "id": m,
                "provider": p,
                "display_name": (
                    f"{m.split('/')[1].split(':')[0]}  "
                    f"({_display_names.get(p, p)})"
                ),
            }
            for m, p in FALLBACK_MODELS
        ]
        # Include premium models if available
        if _vertexai_available:
            for m, p in PREMIUM_MODELS:
                if p in clients:
                    models_list.append({
                        "id": m,
                        "provider": p,
                        "display_name": f"⭐ {m}  ({_premium_display.get(p, p)})",
                        "premium": True,
                    })
        return JSONResponse({"models": models_list, "default": model_name})

    async def _chat(request):
        # Auth check
        if _api_key:
            auth = request.headers.get("authorization", "")
            if not auth.startswith("Bearer ") or auth[7:] != _api_key:
                return JSONResponse(
                    {"error": "Unauthorized"}, status_code=401
                )

        body = await request.json()
        messages = body.get("messages", [])
        selected_model = body.get("model", model_name)
        sel_provider = _provider_map.get(selected_model, "openrouter")

        # Refresh Vertex AI client if selected (OIDC tokens expire hourly)
        if sel_provider == "vertexai" and _vertexai_available:
            refreshed = _get_vertexai_client()
            if refreshed:
                clients["vertexai"] = refreshed

        llm_messages = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ] + list(messages)

        status_updates = []
        final_text = ""

        for update in run_chat_turn(
            clients, llm_messages,
            model=selected_model, provider=sel_provider,
        ):
            if update["type"] == "status":
                status_updates.append(update["content"])
            elif update["type"] == "text":
                final_text = update["content"]
            elif update["type"] == "error":
                final_text = f"❌ {update['content']}"

        return JSONResponse({
            "response": final_text,
            "status_updates": status_updates,
            "updated_messages": llm_messages[1:],
        })

    async def _upload(request):
        """Accept a file upload and save to Modal volume."""
        # Auth check
        if _api_key:
            auth = request.headers.get("authorization", "")
            if not auth.startswith("Bearer ") or auth[7:] != _api_key:
                return JSONResponse(
                    {"error": "Unauthorized"}, status_code=401
                )

        import pathlib

        # Parse multipart form data
        form = await request.form()
        upload_file = form.get("file")
        if not upload_file:
            return JSONResponse(
                {"error": "No file provided"}, status_code=400
            )

        upload_dir = "/data/uploads"
        pathlib.Path(upload_dir).mkdir(parents=True, exist_ok=True)

        filename = upload_file.filename or "upload.maf"
        dest = f"{upload_dir}/{filename}"

        contents = await upload_file.read()
        with open(dest, "wb") as f:
            f.write(contents)

        # Commit to Modal volume
        try:
            from bloomone.config import volume
            volume.commit()
        except Exception:
            pass

        return JSONResponse({
            "path": dest,
            "filename": filename,
            "size_bytes": len(contents),
        })

    async def _chat_stream(request):
        """SSE streaming endpoint for the Next.js frontend."""
        import json as _json
        import asyncio
        import threading
        import queue as _queue

        # Auth check
        if _api_key:
            auth = request.headers.get("authorization", "")
            if not auth.startswith("Bearer ") or auth[7:] != _api_key:
                return JSONResponse(
                    {"error": "Unauthorized"}, status_code=401
                )

        body = await request.json()
        messages = body.get("messages", [])
        selected_model = body.get("model", model_name)
        sel_provider = _provider_map.get(selected_model, "openrouter")

        # Refresh Vertex AI client if selected (OIDC tokens expire hourly)
        if sel_provider == "vertexai" and _vertexai_available:
            refreshed = _get_vertexai_client()
            if refreshed:
                clients["vertexai"] = refreshed

        llm_messages = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ] + list(messages)

        async def event_generator():
            q: _queue.Queue = _queue.Queue()
            done_event = threading.Event()

            def _run_pipeline():
                try:
                    for update in run_chat_turn(
                        clients, llm_messages,
                        model=selected_model, provider=sel_provider,
                    ):
                        q.put(update)
                except Exception as exc:
                    q.put({"type": "error", "content": str(exc)})
                finally:
                    done_event.set()

            # Run the blocking pipeline in a background thread
            thread = threading.Thread(
                target=_run_pipeline, daemon=True
            )
            thread.start()

            # Yield events as they arrive, with heartbeat pings
            while not done_event.is_set() or not q.empty():
                try:
                    update = q.get(timeout=0.1)
                    payload = _json.dumps(update, default=str)
                    yield f"data: {payload}\n\n"
                except _queue.Empty:
                    if not done_event.is_set():
                        # Send SSE comment as keepalive ping
                        yield ": heartbeat\n\n"
                        await asyncio.sleep(10)

            # Drain any remaining items
            while not q.empty():
                update = q.get_nowait()
                payload = _json.dumps(update, default=str)
                yield f"data: {payload}\n\n"

            # Send final event with updated message history
            final = _json.dumps({
                "type": "done",
                "updated_messages": llm_messages[1:],
            }, default=str)
            yield f"data: {final}\n\n"

        from starlette.responses import StreamingResponse

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    async def _chat_title(request):
        """Generate a short chat title using Gemini 2.5 Flash Lite."""
        if _api_key:
            auth = request.headers.get("authorization", "")
            if not auth.startswith("Bearer ") or auth[7:] != _api_key:
                return JSONResponse(
                    {"error": "Unauthorized"}, status_code=401
                )

        body = await request.json()
        messages = body.get("messages", [])

        if not messages:
            return JSONResponse({"title": "New Chat"})

        # Build a compact conversation summary for title generation
        convo_lines = []
        for m in messages[:10]:  # Max 10 messages for context
            role = m.get("role", "user")
            content = m.get("content", "")
            # Truncate long messages
            if len(content) > 300:
                content = content[:300] + "..."
            convo_lines.append(f"{role}: {content}")

        convo_text = "\n".join(convo_lines)

        title_prompt = [
            {
                "role": "user",
                "content": (
                    "Generate a SHORT title (3-6 words max) for this chat "
                    "conversation. The title should capture the main topic. "
                    "Return ONLY the title text, nothing else.\n\n"
                    f"Conversation:\n{convo_text}"
                ),
            }
        ]

        # Try Vertex AI (Flash Lite) first, fall back to OpenRouter
        title = "New Chat"
        title_model = "google/gemini-2.5-flash-lite"

        try:
            if _vertexai_available and "vertexai" in clients:
                # Refresh token if needed
                print(f"[title] Trying Vertex AI ({title_model})...")
                refreshed = _get_vertexai_client()
                if refreshed:
                    clients["vertexai"] = refreshed

                resp = clients["vertexai"].chat.completions.create(
                    model=title_model,
                    messages=title_prompt,
                    max_tokens=30,
                    temperature=0.3,
                )
                title = resp.choices[0].message.content.strip().strip('"\'')
                print(f"[title] Vertex AI success: {title!r}")
            else:
                # Fallback to OpenRouter with a free model
                print(f"[title] Vertex AI not available, trying OpenRouter ({model_name})...")
                resp = clients["openrouter"].chat.completions.create(
                    model=model_name,
                    messages=title_prompt,
                    max_tokens=30,
                    temperature=0.3,
                )
                title = resp.choices[0].message.content.strip().strip('"\'')
                print(f"[title] OpenRouter success: {title!r}")
        except Exception as e:
            print(f"[title] LLM title generation failed: {e}")
            # Fall back to first user message truncation
            first_user = next(
                (m["content"] for m in messages if m.get("role") == "user"),
                "New Chat",
            )
            # Strip file upload context
            import re as _re
            first_user = _re.sub(r'\[.*?\]\s*', '', first_user).strip()
            title = (
                first_user[:57] + "..."
                if len(first_user) > 60
                else first_user
            )
            print(f"[title] Fallback to truncation: {title!r}")

        # Ensure title isn't too long
        if len(title) > 80:
            title = title[:77] + "..."

        return JSONResponse({"title": title})

    async def _root(request):
        return RedirectResponse(url="/chat")

    # Mount Gradio first
    app = gr.mount_gradio_app(fastapi_app, demo, path="/chat")

    # Add REST routes AFTER Gradio mount (prepend so they take priority)
    app.routes.insert(0, Route("/v1/health", _health, methods=["GET"]))
    app.routes.insert(0, Route("/v1/models", _models, methods=["GET"]))
    app.routes.insert(0, Route("/v1/chat/stream", _chat_stream, methods=["POST"]))
    app.routes.insert(0, Route("/v1/chat/title", _chat_title, methods=["POST"]))
    app.routes.insert(0, Route("/v1/chat", _chat, methods=["POST"]))
    app.routes.insert(0, Route("/v1/upload", _upload, methods=["POST"]))
    app.routes.insert(0, Route("/", _root, methods=["GET"]))

    return app
