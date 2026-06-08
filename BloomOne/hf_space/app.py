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

# Timeout: pipeline stages can take minutes (especially binding prediction)
API_TIMEOUT = httpx.Timeout(300.0, connect=30.0)


# ── API Client ───────────────────────────────────────────────────────────────


def call_backend(messages: list[dict]) -> dict:
    """
    Call the Modal-hosted BloomOne chat API.

    Returns dict with: response, status_updates, updated_messages
    """
    try:
        resp = httpx.post(
            API_CHAT_URL,
            json={"messages": messages},
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

footer { display: none !important; }
"""

with gr.Blocks(
    title="BloomOne — AI Neoantigen Vaccine Design",
    theme=gr.themes.Soft(),
    css=CUSTOM_CSS,
) as demo:

    # ── Header ───────────────────────────────────────────────────────
    gr.Markdown(
        """
        <div class="header-section">

        # 🧬 BloomOne

        ### Personalized Neoantigen mRNA Vaccine Pipeline

        Powered by **Gemma 4 27B** on Modal — ask me to design a
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

    with gr.Row():
        msg = gr.Textbox(
            placeholder="Describe your neoantigen analysis...",
            show_label=False,
            container=False,
            scale=9,
            autofocus=True,
        )
        send_btn = gr.Button(
            "Send",
            variant="primary",
            scale=1,
            min_width=80,
        )

    gr.Markdown(
        '<p class="disclaimer-bar">'
        "⚠️ All outputs are for <strong>RESEARCH USE ONLY</strong>. "
        "Not validated for clinical use. "
        "Backend: Gemma 4 27B on Modal GPU."
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

    def user_submit(message, display_history, openai_messages):
        """Show user message immediately and clear input."""
        if not message.strip():
            return "", display_history, openai_messages
        display_history = list(display_history) + [
            {"role": "user", "content": message}
        ]
        openai_messages = list(openai_messages) + [
            {"role": "user", "content": message}
        ]
        return "", display_history, openai_messages

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

    msg.submit(
        user_submit,
        inputs=[msg, chatbot, full_history],
        outputs=[msg, chatbot, full_history],
    ).then(
        bot_respond,
        inputs=[chatbot, full_history],
        outputs=[chatbot, full_history],
    )

    send_btn.click(
        user_submit,
        inputs=[msg, chatbot, full_history],
        outputs=[msg, chatbot, full_history],
    ).then(
        bot_respond,
        inputs=[chatbot, full_history],
        outputs=[chatbot, full_history],
    )


if __name__ == "__main__":
    demo.launch()
