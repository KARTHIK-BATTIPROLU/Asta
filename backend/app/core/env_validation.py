"""
Environment Validation — Fail fast on missing critical config.

Called at the top of startup_event(). If any REQUIRED var is missing,
the server logs a CRITICAL error and raises, preventing a broken boot.

OPTIONAL vars log a WARNING but allow startup to continue in degraded mode.
"""

import os
import logging

logger = logging.getLogger("EnvValidation")


REQUIRED_VARS = [
    "MONGO_URI",
    "DEEPGRAM_API_KEY",
    "GROQ_API_KEY",
]

OPTIONAL_VARS = {
    "NEO4J_URI": "L3 graph memory disabled",
    "NEO4J_PASSWORD": "L3 graph memory disabled",
    "PINECONE_API_KEY": "Vector search (RAG) disabled",
    "NOTION_API_KEY": "Notion tool disabled",
    "SERPER_API": "Search + News tools disabled",
    "OPENWEATHER_API_KEY": "Weather tool disabled",
    "GEMINI_API_KEY": "Image generation disabled",
    "ANTHROPIC_API_KEY": "Claude deep reasoning disabled",
    "GOOGLE_SA_KEY_PATH": "Calendar tool disabled",
}


def validate_environment():
    """
    Validate environment variables on startup.

    Raises RuntimeError if any REQUIRED var is missing.
    Logs WARNING for missing OPTIONAL vars.
    """
    missing_required = []
    for var in REQUIRED_VARS:
        val = os.getenv(var, "").strip()
        if not val:
            missing_required.append(var)
            logger.critical(f"[ENV] MISSING REQUIRED: {var}")

    if missing_required:
        msg = f"Cannot start ASTA — missing required env vars: {missing_required}"
        logger.critical(msg)
        raise RuntimeError(msg)

    degraded = []
    for var, consequence in OPTIONAL_VARS.items():
        val = os.getenv(var, "").strip()
        if not val:
            degraded.append(f"{var} ({consequence})")
            logger.warning(f"[ENV] OPTIONAL MISSING: {var} — {consequence}")

    if degraded:
        logger.warning(f"[ENV] Starting in DEGRADED mode. Missing: {len(degraded)} optional vars")
    else:
        logger.info("[ENV] All environment variables validated ✓")

    # Validate service account file exists if path is set
    sa_path = os.getenv("GOOGLE_SA_KEY_PATH", "")
    if sa_path and not os.path.exists(sa_path):
        logger.warning(f"[ENV] GOOGLE_SA_KEY_PATH={sa_path} — file not found. Calendar tool will fail.")

    return len(missing_required) == 0
