from setuptools import find_packages, setup


RUNTIME_PACKAGE_PATTERNS = [
    "knowledge*",
    "lib*",
    "pipeline_defs*",
    "schemas*",
    "skills*",
    "styles*",
    "tools*",
]

setup(
    name="video-production-buddy",
    version="0.1.0",
    description="AI-Orchestrated Video Production Platform",
    packages=find_packages(include=RUNTIME_PACKAGE_PATTERNS),
    package_data={
        "lib.genui": [
            "static/renderer/index.html",
            "static/renderer/assets/*",
        ],
        "knowledge": ["ad-video/*.json"],
        "pipeline_defs": ["*.yaml"],
        "schemas": ["**/*.json"],
        "skills": ["**/*.md"],
        "styles": ["*.yaml"],
    },
    python_requires=">=3.10",
    install_requires=[
        "pyyaml>=6.0",
        "pydantic>=2.0",
        "jsonschema>=4.20",
        "Pillow>=10.0",
        "requests>=2.31",
        "ag-ui-protocol==0.1.19",
    ],
)
