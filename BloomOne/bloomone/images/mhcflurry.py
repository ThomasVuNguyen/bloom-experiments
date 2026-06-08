"""
MHCflurry Modal image — HLA-I binding prediction with GPU support.
"""

import modal

mhcflurry_image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install(
        "mhcflurry>=2.2.0",
        "torch>=2.4.0",
        "pandas>=2.2.0",
        "requests>=2.32.0",
        "pydantic>=2.10.0",
    )
    .run_commands(
        "mhcflurry-downloads fetch models_class1_presentation",
    )
)
