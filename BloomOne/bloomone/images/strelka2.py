"""
Strelka2 Modal image — somatic variant calling with hg38 reference genome.
"""

import modal

strelka2_image = (
    modal.Image.from_registry(
        "quay.io/biocontainers/strelka:2.9.10--h9ee0642_1",
        add_python="3.12",
    )
    .pip_install(
        "pandas>=2.2.0",
        "requests>=2.32.0",
        "pydantic>=2.10.0",
    )
)
