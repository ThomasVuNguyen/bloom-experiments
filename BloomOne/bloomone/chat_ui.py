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

    from bloomone.chat import SYSTEM_PROMPT, TOOL_LABELS, FALLBACK_MODELS, run_chat_turn

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

        submit_event = msg.submit(
            user_submit,
            inputs=[msg, chatbot, openai_history, uploaded_file_path],
            outputs=[msg, chatbot, openai_history, uploaded_file_path],
        ).then(
            bot_respond,
            inputs=[chatbot, openai_history, model_dropdown],
            outputs=[chatbot, openai_history],
        )

        send_btn.click(
            user_submit,
            inputs=[msg, chatbot, openai_history, uploaded_file_path],
            outputs=[msg, chatbot, openai_history, uploaded_file_path],
        ).then(
            bot_respond,
            inputs=[chatbot, openai_history, model_dropdown],
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

    async def _root(request):
        return RedirectResponse(url="/chat")

    # Mount Gradio first
    app = gr.mount_gradio_app(fastapi_app, demo, path="/chat")

    # Add REST routes AFTER Gradio mount (prepend so they take priority)
    app.routes.insert(0, Route("/v1/health", _health, methods=["GET"]))
    app.routes.insert(0, Route("/v1/models", _models, methods=["GET"]))
    app.routes.insert(0, Route("/v1/chat/stream", _chat_stream, methods=["POST"]))
    app.routes.insert(0, Route("/v1/chat", _chat, methods=["POST"]))
    app.routes.insert(0, Route("/v1/upload", _upload, methods=["POST"]))
    app.routes.insert(0, Route("/", _root, methods=["GET"]))

    return app
