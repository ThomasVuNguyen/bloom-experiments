"""
BloomOne Modal Deployment — MCP server + AI chatbot.

Deploy with: modal deploy bloomone/deploy.py
Serve locally with: modal serve bloomone/deploy.py
"""

from __future__ import annotations

import pathlib

import modal

from bloomone.config import APP_NAME, VOLUME_MOUNT, volume

# ── Modal App ────────────────────────────────────────────────────────────────

app = modal.App(APP_NAME)

# Path to the bloomone package source
BLOOMONE_SRC = pathlib.Path(__file__).parent

# ── Images ───────────────────────────────────────────────────────────────────

# MCP server image — core pipeline (Stages 3, 5, 6 run here)
mcp_image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install(
        "pandas>=2.2.0",
        "requests>=2.32.0",
        "pydantic>=2.10.0",
        "biopython>=1.84",
        "fastmcp>=2.0.0",
        "fastapi>=0.115.0",
    )
    .add_local_dir(BLOOMONE_SRC, remote_path="/root/bloomone")
)

# MHCflurry image — GPU binding prediction
mhcflurry_image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install(
        "mhcflurry>=2.2.0",
        "pandas>=2.2.0",
        "pydantic>=2.10.0",
        "requests>=2.32.0",
    )
    .run_commands("mhcflurry-downloads fetch models_class1_presentation")
    .add_local_dir(BLOOMONE_SRC, remote_path="/root/bloomone")
)

# mRNA design image
mrna_image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("libgomp1")
    .pip_install(
        "python-codon-tables>=0.1.12",
        "pandas>=2.2.0",
        "pydantic>=2.10.0",
    )
    .add_local_dir(BLOOMONE_SRC, remote_path="/root/bloomone")
)

# Chatbot image — Gemini API client + pipeline dependencies (no GPU needed)
chatbot_image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install(
        "openai>=1.40.0",
        "google-auth>=2.30.0",
        "gradio",
        "fastapi>=0.115.0",
        "httpx>=0.27.0",
        "pandas>=2.2.0",
        "requests>=2.32.0",
        "pydantic>=2.10.0",
        "biopython>=1.84",
    )
    .add_local_dir(BLOOMONE_SRC, remote_path="/root/bloomone")
)


# ── MCP Server ───────────────────────────────────────────────────────────────


@app.function(
    image=mcp_image,
    volumes={VOLUME_MOUNT: volume},
    timeout=3600,
    memory=4096,
)
@modal.asgi_app()
def web():
    """
    ASGI endpoint serving the BloomOne MCP server.

    The MCP server is served via streamable-http transport,
    accessible by any MCP client (Claude Desktop, Gemini, etc.).
    """
    import sys
    sys.path.insert(0, "/root")
    from bloomone.server import mcp

    return mcp.http_app(stateless_http=True)


# ── Specialized Stage Functions ──────────────────────────────────────────────


@app.function(
    image=mcp_image,
    volumes={VOLUME_MOUNT: volume},
    cpu=8,
    memory=16384,
    timeout=3600,
)
def run_optitype_remote(bam_path: str, patient_id: str) -> list:
    """Run OptiType HLA typing."""
    import sys
    sys.path.insert(0, "/root")
    from bloomone.stages.stage1_ingest import run_optitype

    alleles = run_optitype(bam_path=bam_path, patient_id=patient_id)
    volume.commit()
    return alleles


@app.function(
    image=mcp_image,
    volumes={VOLUME_MOUNT: volume},
    cpu=8,
    memory=32768,
    timeout=7200,
)
def run_strelka2(tumor_bam: str, normal_bam: str, patient_id: str) -> dict:
    """Run Strelka2 variant calling."""
    import sys
    sys.path.insert(0, "/root")
    from bloomone.models import PatientData
    from bloomone.stages.stage2_mutations import call_mutations

    patient_data = PatientData(
        stage=2,
        stage_name="Mutation Calling",
        patient_id=patient_id,
        tumor_path=tumor_bam,
        normal_path=normal_bam,
        hla_alleles=[],
        hla_source="pending",
    )
    result = call_mutations(patient_data)
    volume.commit()
    return result.model_dump()


@app.function(
    image=mhcflurry_image,
    volumes={VOLUME_MOUNT: volume},
    gpu="T4",
    timeout=3600,
)
def run_mhcflurry_remote(peptides_path: str, hla_alleles: list, patient_id: str) -> dict:
    """Run MHCflurry 2.0 binding prediction on GPU."""
    import sys
    sys.path.insert(0, "/root")
    from bloomone.stages.stage4_binding import predict_binding

    result = predict_binding(
        peptides_path=peptides_path,
        hla_alleles=hla_alleles,
        patient_id=patient_id,
        use_mhcflurry=True,
    )
    volume.commit()
    return result.model_dump()


@app.function(
    image=mrna_image,
    volumes={VOLUME_MOUNT: volume},
    timeout=1800,
)
def run_mrna_design_remote(ranked_path: str, patient_id: str, top_n: int = 20) -> dict:
    """Run mRNA construct design with ViennaRNA."""
    import sys
    sys.path.insert(0, "/root")
    from bloomone.stages.stage7_mrna import design_mrna

    result = design_mrna(
        ranked_path=ranked_path,
        patient_id=patient_id,
        top_n=top_n,
    )
    volume.commit()
    return result.model_dump()


# ── AI Chatbot (Gemma 4 26B A4B via OpenRouter) ────────────────────────────

GEMMA_MODEL = "google/gemma-4-31b-it:free"


@app.function(
    image=chatbot_image,
    volumes={VOLUME_MOUNT: volume},
    secrets=[
            modal.Secret.from_name("openrouter-api-key"),
            modal.Secret.from_name("bloomone-api-key"),
            modal.Secret.from_name("cloudrift-api-key"),
            modal.Secret.from_name("coolify-frontend-url", required_keys=["COOLIFY_FRONTEND_URL"]),
        ],
    timeout=1800,
    scaledown_window=120,
)
@modal.concurrent(max_inputs=10)
@modal.asgi_app()
def chatbot():
    """
    AI chatbot: Gradio UI + Gemma 4 26B A4B (OpenRouter) + BloomOne tools.

    Calls Gemma 4 via OpenRouter's OpenAI-compatible endpoint.
    No GPU needed — LLM inference is handled by OpenRouter (free tier).
    Tool calls from the LLM are executed directly against
    BloomOne stage functions (same container).
    """
    import sys

    sys.path.insert(0, "/root")
    from bloomone.chat_ui import create_app

    return create_app(
        llm_url="https://openrouter.ai/api/v1",
        model_name=GEMMA_MODEL,
    )


# ── Local entrypoint ─────────────────────────────────────────────────────


@app.local_entrypoint()
def main():
    """Test entrypoint — prints server info."""
    print("BloomOne MCP Server + AI Chatbot")
    print("=" * 50)
    print(f"App: {APP_NAME}")
    print(f"Volume: bloomone-data → {VOLUME_MOUNT}")
    print(f"Model: {GEMMA_MODEL}")
    print()
    print("Deploy:  modal deploy bloomone/deploy.py")
    print("Serve:   modal serve bloomone/deploy.py")
    print()
    print("Endpoints (after deploy):")
    print("  MCP:     https://<workspace>--bloomone-web.modal.run/mcp/")
    print("  Chatbot: https://<workspace>--bloomone-chatbot.modal.run/")
