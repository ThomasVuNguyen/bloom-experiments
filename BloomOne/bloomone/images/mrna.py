"""
mRNA design Modal image — codon optimization + RNA structure prediction.
"""

import modal

mrna_image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("libgomp1")
    .pip_install(
        "python-codon-tables>=0.1.12",
        "ViennaRNA>=2.6.0",
        "pandas>=2.2.0",
        "pydantic>=2.10.0",
    )
)
