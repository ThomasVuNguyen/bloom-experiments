"""
BloomOne — HuggingFace Space Frontend.

A Gradio chatbot UI that connects to the Modal-hosted BloomOne backend
(Gemini 2.5 Flash + pipeline tools) via REST API.

The backend handles LLM inference and pipeline tool execution.
This frontend is a lightweight chat interface.
"""

import os
import json

import gradio as gr
import httpx

# ── Configuration ────────────────────────────────────────────────────────────

BACKEND_URL = os.environ.get(
    "BLOOMONE_BACKEND_URL",
    "https://thomas-15--bloomone-chatbot.modal.run",
)
API_CHAT_URL = f"{BACKEND_URL}/v1/chat"
API_HEALTH_URL = f"{BACKEND_URL}/v1/health"
API_UPLOAD_URL = f"{BACKEND_URL}/v1/upload"
BLOOMONE_API_KEY = os.environ.get("BLOOMONE_API_KEY", "")

# Timeout: pipeline stages can take minutes (especially binding prediction)
API_TIMEOUT = httpx.Timeout(300.0, connect=30.0)


# ── API Client ───────────────────────────────────────────────────────────────


def call_backend(messages: list[dict]) -> dict:
    """
    Call the Modal-hosted BloomOne chat API.

    Returns dict with: response, status_updates, updated_messages
    """
    headers = {}
    if BLOOMONE_API_KEY:
        headers["Authorization"] = f"Bearer {BLOOMONE_API_KEY}"

    try:
        resp = httpx.post(
            API_CHAT_URL,
            json={"messages": messages},
            headers=headers,
            timeout=API_TIMEOUT,
            follow_redirects=True,
        )
        resp.raise_for_status()
        return resp.json()
    except httpx.ConnectError:
        return {
            "response": (
                "🔄 **Backend is warming up** (cold start ~30-60s).\n\n"
                "The GPU container is loading Gemma 4 27B. "
                "Please try again in about a minute."
            ),
            "status_updates": [],
            "updated_messages": messages,
        }
    except httpx.TimeoutException:
        return {
            "response": (
                "⏰ **Request timed out.**\n\n"
                "The pipeline stage may still be running. "
                "Try again or ask for a simpler query first."
            ),
            "status_updates": [],
            "updated_messages": messages,
        }
    except Exception as e:
        return {
            "response": f"❌ **Backend error:** {str(e)}",
            "status_updates": [],
            "updated_messages": messages,
        }


def upload_to_backend(file_path: str) -> dict:
    """
    Upload a file to the Modal backend's /v1/upload endpoint.

    Returns dict with: path (on Modal volume), filename, size_bytes
    """
    headers = {}
    if BLOOMONE_API_KEY:
        headers["Authorization"] = f"Bearer {BLOOMONE_API_KEY}"

    try:
        import pathlib
        filename = pathlib.Path(file_path).name
        with open(file_path, "rb") as f:
            resp = httpx.post(
                API_UPLOAD_URL,
                files={"file": (filename, f)},
                headers=headers,
                timeout=API_TIMEOUT,
                follow_redirects=True,
            )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": str(e)}


# ── Gradio Interface ─────────────────────────────────────────────────────────

CUSTOM_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

* { font-family: 'Inter', sans-serif !important; }

.gradio-container {
    max-width: 900px !important;
    margin: 0 auto !important;
}

.header-section {
    text-align: center;
    padding: 24px 16px 8px;
    background: linear-gradient(135deg, #0f0c29 0%, #302b63 50%, #24243e 100%);
    border-radius: 16px;
    margin-bottom: 16px;
    color: white;
}
.header-section h1 { color: white !important; font-size: 2.2em !important; }
.header-section h3 { color: #b8b8d0 !important; font-weight: 400 !important; }
.header-section p { color: #9090b0 !important; }

.disclaimer-bar {
    font-size: 0.78em;
    color: #888;
    text-align: center;
    padding: 6px 0;
    border-top: 1px solid rgba(255,255,255,0.05);
}

.status-chip {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 12px;
    font-size: 0.8em;
    margin: 2px 4px;
}

/* Upload progress bar */
#upload-progress-container {
    display: none;
    margin: 8px 0;
    padding: 10px 16px;
    background: rgba(100, 100, 255, 0.08);
    border: 1px solid rgba(100, 100, 255, 0.2);
    border-radius: 12px;
}
#upload-progress-container.active { display: block; }
#upload-progress-label {
    font-size: 0.85em;
    color: #a0a0d0;
    margin-bottom: 6px;
}
#upload-progress-bar-bg {
    width: 100%;
    height: 8px;
    background: rgba(255,255,255,0.08);
    border-radius: 4px;
    overflow: hidden;
}
#upload-progress-bar {
    height: 100%;
    width: 0%;
    background: linear-gradient(90deg, #6366f1, #8b5cf6, #a78bfa);
    border-radius: 4px;
    transition: width 0.2s ease;
}
#upload-progress-pct {
    font-size: 0.8em;
    color: #b8b8d0;
    text-align: right;
    margin-top: 4px;
}

.upload-status p {
    font-size: 0.85em;
    padding: 6px 12px;
    background: rgba(34, 197, 94, 0.08);
    border: 1px solid rgba(34, 197, 94, 0.2);
    border-radius: 8px;
    margin: 4px 0;
}

footer { display: none !important; }
"""

CUSTOM_JS = """
() => {
    // Create the progress overlay
    const container = document.createElement('div');
    container.id = 'upload-progress-container';
    container.innerHTML = `
        <div id="upload-progress-label">📤 Uploading file...</div>
        <div id="upload-progress-bar-bg">
            <div id="upload-progress-bar"></div>
        </div>
        <div id="upload-progress-pct">Starting upload...</div>
    `;

    let inserted = false;
    let uploadStartTime = null;
    let animFrame = null;
    let isUploading = false;

    function insertContainer() {
        if (inserted) return;
        // Find the gradio container area
        const target = document.querySelector('.disclaimer-bar')
                    || document.querySelector('.upload-status')
                    || document.querySelector('.examples');
        if (target && target.parentNode) {
            target.parentNode.insertBefore(container, target);
            inserted = true;
        }
    }

    function startUploadUI() {
        if (isUploading) return;
        isUploading = true;
        insertContainer();
        uploadStartTime = Date.now();
        container.classList.add('active');

        const bar = document.getElementById('upload-progress-bar');
        const pct = document.getElementById('upload-progress-pct');
        const label = document.getElementById('upload-progress-label');

        // Animated indeterminate progress that slows down
        function animate() {
            if (!isUploading) return;
            const elapsed = (Date.now() - uploadStartTime) / 1000;
            const mins = Math.floor(elapsed / 60);
            const secs = Math.floor(elapsed % 60);
            const timeStr = mins > 0 ? `${mins}m ${secs}s` : `${secs}s`;

            // Asymptotic progress: approaches 99% slowly over minutes
            const fakePercent = Math.min(99, Math.round(100 * (1 - Math.exp(-elapsed / 120))));
            if (bar) bar.style.width = fakePercent + '%';
            if (pct) pct.textContent = `~${fakePercent}% • ${timeStr} elapsed`;
            if (label) label.textContent = '📤 Uploading file to server...';

            animFrame = requestAnimationFrame(animate);
        }
        animate();
    }

    function stopUploadUI(success) {
        isUploading = false;
        if (animFrame) cancelAnimationFrame(animFrame);

        const bar = document.getElementById('upload-progress-bar');
        const pct = document.getElementById('upload-progress-pct');
        const label = document.getElementById('upload-progress-label');

        if (success) {
            if (bar) bar.style.width = '100%';
            if (label) label.textContent = '✅ Upload complete!';
            const elapsed = uploadStartTime ? ((Date.now() - uploadStartTime) / 1000).toFixed(1) : '?';
            if (pct) pct.textContent = `Done in ${elapsed}s`;
        } else {
            if (label) label.textContent = '❌ Upload failed';
            if (pct) pct.textContent = '';
        }

        setTimeout(() => {
            container.classList.remove('active');
            if (bar) bar.style.width = '0%';
        }, 3000);
    }

    // Watch for Gradio's upload indicators in the DOM
    const observer = new MutationObserver((mutations) => {
        // Look for upload state changes
        const fileAreas = document.querySelectorAll('[data-testid="file"], .file-preview, .upload-text');
        const allText = document.body.innerText;

        // Detect "Uploading" text appearing in file component
        const uploadingEls = document.querySelectorAll('.uploading, .progress-text, .file-upload');
        let foundUploading = false;

        // Check all text nodes for "Uploading" in the file area
        document.querySelectorAll('span, p, div').forEach(el => {
            const t = el.textContent || '';
            if (t.includes('Uploading') && t.includes('file') && el.offsetParent !== null) {
                foundUploading = true;
            }
        });

        if (foundUploading && !isUploading) {
            startUploadUI();
        } else if (!foundUploading && isUploading) {
            stopUploadUI(true);
        }
    });

    // Start observing after Gradio renders
    setTimeout(() => {
        insertContainer();
        observer.observe(document.body, {
            childList: true,
            subtree: true,
            characterData: true,
        });
    }, 2000);
}
"""

with gr.Blocks(
    title="BloomOne — AI Neoantigen Vaccine Design",
    theme=gr.themes.Soft(),
    css=CUSTOM_CSS,
    js=CUSTOM_JS,
) as demo:

    # ── Header ───────────────────────────────────────────────────────
    gr.Markdown(
        """
        <div class="header-section">

        # 🧬 BloomOne

        ### Personalized Neoantigen mRNA Vaccine Pipeline

        Powered by **Gemma 4 31B** on Modal — ask me to design a
        personalized mRNA vaccine from tumor mutations.

        </div>
        """,
    )

    # ── Chat ─────────────────────────────────────────────────────────

    chatbot = gr.Chatbot(
        type="messages",
        height=500,
        show_label=False,
        show_copy_button=True,
        avatar_images=(None, "🧬"),
        placeholder=(
            "💡 **Try asking:**\n\n"
            "• *Run the neoantigen pipeline for TCGA-BF-A3DL-01*\n"
            "• *What data do you need to design a neoantigen vaccine?*\n"
            "• *Explain the pipeline stages*"
        ),
    )

    # Full OpenAI message history (persists tool calls across turns)
    full_history = gr.State([])

    # Track uploaded file path on Modal volume
    uploaded_file_path = gr.State(None)

    with gr.Row():
        msg = gr.Textbox(
            placeholder="Describe your neoantigen analysis...",
            show_label=False,
            container=False,
            scale=7,
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

    # Upload status indicator
    upload_status = gr.Markdown(
        "",
        elem_classes=["upload-status"],
        visible=False,
    )

    gr.Markdown(
        '<p class="disclaimer-bar">'
        "⚠️ All outputs are for <strong>RESEARCH USE ONLY</strong>. "
        "Not validated for clinical use. "
        "Backend: Gemma 4 31B on Modal."
        "</p>"
    )

    # ── Examples ─────────────────────────────────────────────────────

    gr.Examples(
        examples=[
            "Run the neoantigen vaccine pipeline for melanoma case "
            "TCGA-BF-A3DL-01 with HLA-A*02:01,HLA-B*07:02,HLA-C*07:01",
            "What data do you need to design a neoantigen vaccine?",
            "Explain the 7 pipeline stages",
        ],
        inputs=msg,
    )

    # ── Event Handlers ───────────────────────────────────────────────

    def handle_file_upload(file, current_path, progress=gr.Progress()):
        """Upload file to Modal backend and return the volume path."""
        if file is None:
            return current_path, gr.update(), gr.update(visible=False)

        import pathlib
        file_size = pathlib.Path(file).stat().st_size
        size_mb = file_size / (1024 * 1024)
        filename = pathlib.Path(file).name

        progress(0.3, desc=f"📤 Forwarding {filename} ({size_mb:.1f} MB) to backend...")

        result = upload_to_backend(file)

        if "error" in result:
            progress(1.0, desc="❌ Upload failed")
            return current_path, gr.update(
                value=None,
                label="Upload MAF/VCF",
            ), gr.update(
                value=f"❌ Upload failed: {result['error']}",
                visible=True,
            )

        progress(1.0, desc="✅ Done!")
        return result["path"], gr.update(
            value=None,
            label="Upload MAF/VCF",
        ), gr.update(
            value=(
                f"✅ **Uploaded:** `{result['filename']}` "
                f"({result.get('size_bytes', 0) / (1024*1024):.1f} MB) — "
                f"ready to use in chat"
            ),
            visible=True,
        )

    def user_submit(message, display_history, openai_messages, file_path):
        """Show user message immediately and clear input."""
        if not message.strip() and not file_path:
            return "", display_history, openai_messages, file_path

        content = message.strip()
        if file_path:
            file_notice = f"[User uploaded a MAF file to: {file_path}]"
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
        openai_messages = list(openai_messages) + [
            {"role": "user", "content": content}
        ]
        return "", display_history, openai_messages, None

    def bot_respond(display_history, openai_messages):
        """Call the Modal backend and display the response."""
        # Show "thinking" state
        yield (
            display_history
            + [{"role": "assistant", "content": "🔄 *Thinking...*"}],
            openai_messages,
        )

        # Call backend API
        result = call_backend(openai_messages)

        # Build response with status updates
        response_text = ""
        if result.get("status_updates"):
            response_text = "\n".join(result["status_updates"])
            response_text += "\n\n---\n\n"
        response_text += result.get("response", "")

        # Update state
        updated_messages = result.get("updated_messages", openai_messages)

        yield (
            display_history
            + [{"role": "assistant", "content": response_text}],
            updated_messages,
        )

    # ── Wire Events ──────────────────────────────────────────────────

    file_upload.change(
        handle_file_upload,
        inputs=[file_upload, uploaded_file_path],
        outputs=[uploaded_file_path, file_upload, upload_status],
    )

    msg.submit(
        user_submit,
        inputs=[msg, chatbot, full_history, uploaded_file_path],
        outputs=[msg, chatbot, full_history, uploaded_file_path],
    ).then(
        bot_respond,
        inputs=[chatbot, full_history],
        outputs=[chatbot, full_history],
    )

    send_btn.click(
        user_submit,
        inputs=[msg, chatbot, full_history, uploaded_file_path],
        outputs=[msg, chatbot, full_history, uploaded_file_path],
    ).then(
        bot_respond,
        inputs=[chatbot, full_history],
        outputs=[chatbot, full_history],
    )


if __name__ == "__main__":
    demo.launch()
