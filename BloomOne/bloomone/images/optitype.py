"""
OptiType Modal image — HLA-I genotyping from sequencing data.
"""

import modal

optitype_image = (
    modal.Image.from_registry(
        "quay.io/biocontainers/optitype:1.3.5--hdfd78af_3",
        add_python="3.12",
    )
    .pip_install(
        "pandas>=2.2.0",
        "requests>=2.32.0",
        "pydantic>=2.10.0",
    )
)
