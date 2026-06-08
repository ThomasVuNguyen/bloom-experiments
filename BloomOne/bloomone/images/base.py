"""
Base Modal image — shared Python dependencies for all stages.
"""

import modal

base_image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install(
        "pandas>=2.2.0",
        "requests>=2.32.0",
        "pydantic>=2.10.0",
        "biopython>=1.84",
    )
)
