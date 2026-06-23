"""
FactChecker — Extraction de claims (Gemini) + vérification parallèle (Grok + Gemini)

Chaque appelant fournit SA PROPRE clé API. Les clés ne sont jamais stockées sur
disque ni journalisées ; elles ne vivent qu'en mémoire pour la durée de la requête.
"""

import json
import logging
import re

import httpx

from core.models import Verdict

log = logging.getLogger(__name__)

GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
)
GROK_MODEL = "grok-4"
GROK_URL = "https://api.x.ai/v1/chat/completions"

EXTRACT_PROMPT = """Tu analyses une transcription audio en français. Extrais UNIQUEMENT les affirmations factuelles vérifiables (chiffres, dates, citations, événements, statistiques). Ignore les opinions, questions, et banalités.

Réponds STRICTEMENT en JSON, sans aucun texte autour, sous la forme :
{{"claims": ["claim 1", "claim 2"]}}

Si aucune affirmation vérifiable n'est présente, réponds {{"claims": []}}.

Transcription :
\"\"\"{text}\"\"\"
"""

CHECK_PROMPT = """Tu es un fact-checker rigoureux. Vérifie l'affirmation suivante et réponds STRICTEMENT en JSON, sans aucun texte autour :

{{
  "label": "VRAI" | "GLOBALEMENT VRAI" | "FAUX" | "TROMPEUR" | "NON VÉRIFIABLE",
  "explanation": "explication concise en français (2-3 phrases)",
  "sources": ["source 1", "source 2"],
  "confidence": 0.0 à 1.0
}}

Affirmation à vérifier :
\"\"\"{claim}\"\"\"
"""


def _extract_json(text: str) -> dict:
    """Extrait le premier objet JSON valide trouvé dans une réponse de LLM."""
    text = text.strip()
    text = re.sub(r"^```(json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("Pas de JSON trouvé dans la réponse")
    return json.loads(match.group(0))


class FactChecker:
    def __init__(self, grok_key: str | None = None, gemini_key: str | None = None):
        self.grok_key = grok_key
        self.gemini_key = gemini_key

    # ─── Extraction des claims (via Gemini) ──────────────────────────────

    async def extract_claims(self, text: str) -> list[str]:
        if not self.gemini_key:
            log.warning("Pas de clé Gemini fournie, extraction impossible")
            return []

        prompt = EXTRACT_PROMPT.format(text=text)
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{GEMINI_URL}?key={self.gemini_key}",
                    json={"contents": [{"parts": [{"text": prompt}]}]},
                )
                resp.raise_for_status()
                data = resp.json()
                raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
                parsed = _extract_json(raw_text)
                claims = parsed.get("claims", [])
                return [c for c in claims if isinstance(c, str) and c.strip()]
        except Exception as e:
            log.error(f"Erreur extraction claims (Gemini) : {e}")
            return []

    # ─── Vérification d'un claim — Grok + Gemini en parallèle ────────────

    async def check_claim(self, claim: str) -> dict[str, Verdict]:
        """Retourne {'grok': Verdict, 'gemini': Verdict} (selon les clés fournies)."""
        results: dict[str, Verdict] = {}

        tasks = []
        if self.grok_key:
            tasks.append(("grok", self._check_with_grok(claim)))
        if self.gemini_key:
            tasks.append(("gemini", self._check_with_gemini(claim)))

        for provider, coro in tasks:
            try:
                results[provider] = await coro
            except Exception as e:
                log.error(f"Erreur fact-check {provider} : {e}")
                results[provider] = Verdict(
                    provider=provider,
                    label="ERREUR",
                    explanation=f"Échec de la vérification ({provider}) : {e}",
                    sources=[],
                    confidence=0.0,
                )
        return results

    async def _check_with_gemini(self, claim: str) -> Verdict:
        prompt = CHECK_PROMPT.format(claim=claim)
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{GEMINI_URL}?key={self.gemini_key}",
                json={"contents": [{"parts": [{"text": prompt}]}]},
            )
            resp.raise_for_status()
            data = resp.json()
            raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
            parsed = _extract_json(raw_text)
            return Verdict(
                provider="gemini",
                label=parsed.get("label", "NON VÉRIFIABLE"),
                explanation=parsed.get("explanation", ""),
                sources=parsed.get("sources", []),
                confidence=float(parsed.get("confidence", 0.0)),
            )

    async def _check_with_grok(self, claim: str) -> Verdict:
        prompt = CHECK_PROMPT.format(claim=claim)
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                GROK_URL,
                headers={"Authorization": f"Bearer {self.grok_key}"},
                json={
                    "model": GROK_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.0,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            raw_text = data["choices"][0]["message"]["content"]
            parsed = _extract_json(raw_text)
            return Verdict(
                provider="grok",
                label=parsed.get("label", "NON VÉRIFIABLE"),
                explanation=parsed.get("explanation", ""),
                sources=parsed.get("sources", []),
                confidence=float(parsed.get("confidence", 0.0)),
            )
