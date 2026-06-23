"""
Transcriber — Faster-Whisper, transcription locale côté serveur.
"""

import logging
import tempfile

from faster_whisper import WhisperModel

log = logging.getLogger(__name__)

_MODEL_CACHE: dict[str, WhisperModel] = {}


def get_model(model_size: str = "base") -> WhisperModel:
    if model_size not in _MODEL_CACHE:
        log.info(f"Chargement du modèle Whisper '{model_size}'...")
        _MODEL_CACHE[model_size] = WhisperModel(model_size, device="cpu", compute_type="int8")
    return _MODEL_CACHE[model_size]


class Transcriber:
    def __init__(self, model_size: str = "base", language: str | None = "fr"):
        self.model = get_model(model_size)
        self.language = language

    def transcribe_file(self, audio_path: str) -> str:
        """Transcrit un fichier audio complet (wav/mp3/m4a...) et retourne le texte."""
        segments, _info = self.model.transcribe(
            audio_path,
            language=self.language,
            vad_filter=True,
        )
        return " ".join(seg.text.strip() for seg in segments)

    def transcribe_bytes(self, audio_bytes: bytes, suffix: str = ".wav") -> str:
        """Transcrit un blob audio brut (ex: bloc micro de 10-15s) en passant par un fichier temporaire."""
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as tmp:
            tmp.write(audio_bytes)
            tmp.flush()
            return self.transcribe_file(tmp.name)
