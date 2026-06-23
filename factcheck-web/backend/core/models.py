"""
Modèles de données — FactCheck Web
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Verdict:
    """Résultat de vérification d'un claim par un LLM donné."""
    provider: str            # "grok" ou "gemini"
    label: str                # VRAI / GLOBALEMENT VRAI / FAUX / TROMPEUR / NON VÉRIFIABLE / ERREUR
    explanation: str
    sources: list[str] = field(default_factory=list)
    confidence: float = 0.0


@dataclass
class JobState:
    """État d'une session de fact-check (un upload, une URL, ou un live)."""
    job_id: str
    grok_key: Optional[str] = None
    gemini_key: Optional[str] = None
    model_size: str = "base"
    language: Optional[str] = "fr"

    running: bool = False
    transcript_buffer: str = ""
    checked_claims: set = field(default_factory=set)
    last_claim_check: float = 0.0

    # WebSocket clients abonnés à ce job
    clients: set = field(default_factory=set)
