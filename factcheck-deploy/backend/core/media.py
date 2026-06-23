"""
Media — Téléchargement audio depuis une URL (YouTube/Twitch via yt-dlp)
et normalisation de fichiers audio/vidéo en WAV 16kHz mono via ffmpeg.
"""

import logging
import subprocess
import tempfile
import uuid
from pathlib import Path

import yt_dlp

log = logging.getLogger(__name__)

TMP_DIR = Path(tempfile.gettempdir()) / "factcheck-web"
TMP_DIR.mkdir(exist_ok=True)


def download_from_url(url: str) -> str:
    """
    Télécharge l'audio d'une URL (YouTube, Twitch, etc.) via yt-dlp et le convertit
    en WAV 16kHz mono. Retourne le chemin du fichier WAV résultant.

    Note : respecte les contraintes des plateformes sources ; ne pas utiliser pour
    télécharger du contenu dont la diffusion/redistribution n'est pas autorisée.
    """
    out_id = uuid.uuid4().hex
    out_template = str(TMP_DIR / f"{out_id}.%(ext)s")

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": out_template,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "wav",
            }
        ],
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    wav_path = TMP_DIR / f"{out_id}.wav"
    if not wav_path.exists():
        raise RuntimeError("Échec du téléchargement/extraction audio depuis l'URL fournie")

    return normalize_audio(str(wav_path))


def normalize_audio(input_path: str) -> str:
    """Convertit n'importe quel fichier audio/vidéo en WAV 16kHz mono via ffmpeg."""
    out_path = str(TMP_DIR / f"{uuid.uuid4().hex}_norm.wav")
    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-ac", "1", "-ar", "16000",
        out_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log.error(f"ffmpeg a échoué : {result.stderr[-500:]}")
        raise RuntimeError("Échec de la normalisation audio (ffmpeg)")
    return out_path


def save_upload(file_bytes: bytes, suffix: str) -> str:
    """Sauvegarde un fichier uploadé sur disque (temp) et retourne son chemin."""
    path = TMP_DIR / f"{uuid.uuid4().hex}{suffix}"
    with open(path, "wb") as f:
        f.write(file_bytes)
    return str(path)
