"""
FactCheck Web — Backend FastAPI
Transcription locale (Faster-Whisper) + fact-check via Grok ET Gemini en parallèle.

Sécurité / confidentialité :
- Les clés API (Grok, Gemini) sont fournies par chaque utilisateur à chaque requête.
- Elles ne sont JAMAIS écrites sur disque ni journalisées ; elles vivent en mémoire
  pour la durée du job, puis sont jetées avec lui.
"""

import asyncio
import json
import logging
import time
import uuid
from dataclasses import asdict

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from core.transcriber import Transcriber
from core.factchecker import FactChecker
from core.media import download_from_url, normalize_audio, save_upload
from core.models import JobState

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

app = FastAPI(title="FactCheck Web", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# job_id -> JobState
JOBS: dict[str, JobState] = {}


@app.get("/health")
def health():
    return {"status": "ok", "jobs_actifs": len(JOBS)}


# ─── WebSocket de suivi des résultats d'un job ────────────────────────────

@app.websocket("/ws/{job_id}")
async def websocket_endpoint(websocket: WebSocket, job_id: str):
    await websocket.accept()
    job = JOBS.setdefault(job_id, JobState(job_id=job_id))
    job.clients.add(websocket)
    log.info(f"Client WS connecté au job {job_id}")
    try:
        while True:
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        job.clients.discard(websocket)


async def broadcast(job: JobState, message: dict):
    dead = set()
    for client in job.clients:
        try:
            await client.send_text(json.dumps(message))
        except Exception:
            dead.add(client)
    job.clients -= dead


# ─── Pipeline commun : texte transcrit -> claims -> verdicts (Grok+Gemini) ─

async def run_factcheck_pipeline(job: JobState, transcript: str):
    if not transcript or len(transcript.strip()) < 10:
        return

    await broadcast(job, {"type": "transcript", "text": transcript, "timestamp": time.time()})

    job.transcript_buffer += " " + transcript
    if len(job.transcript_buffer) > 2000:
        job.transcript_buffer = job.transcript_buffer[-2000:]

    checker = FactChecker(grok_key=job.grok_key, gemini_key=job.gemini_key)
    claims = await checker.extract_claims(job.transcript_buffer)
    if not claims:
        return

    log.info(f"[{job.job_id}] {len(claims)} claim(s) détecté(s)")

    for claim in claims:
        if claim in job.checked_claims:
            continue
        job.checked_claims.add(claim)
        if len(job.checked_claims) > 100:
            job.checked_claims.pop()

        await broadcast(job, {"type": "claim_detected", "claim": claim, "timestamp": time.time()})

        verdicts = await checker.check_claim(claim)
        await broadcast(job, {
            "type": "verdict",
            "claim": claim,
            "results": {provider: asdict(v) for provider, v in verdicts.items()},
            "timestamp": time.time(),
        })


# ─── Entrée 1 : Upload de fichier audio/vidéo ─────────────────────────────

@app.post("/upload")
async def upload_audio(
    file: UploadFile = File(...),
    grok_key: str = Form(default=""),
    gemini_key: str = Form(default=""),
    model: str = Form(default="base"),
    language: str = Form(default="fr"),
):
    job_id = uuid.uuid4().hex
    job = JobState(
        job_id=job_id,
        grok_key=grok_key or None,
        gemini_key=gemini_key or None,
        model_size=model,
        language=language or None,
    )
    JOBS[job_id] = job

    suffix = "." + (file.filename.split(".")[-1] if "." in file.filename else "bin")
    raw_bytes = await file.read()
    raw_path = save_upload(raw_bytes, suffix)

    asyncio.create_task(_process_full_file(job, raw_path))

    return {"job_id": job_id}


async def _process_full_file(job: JobState, raw_path: str):
    job.running = True
    try:
        wav_path = normalize_audio(raw_path)
        transcriber = Transcriber(model_size=job.model_size, language=job.language)
        await broadcast(job, {"type": "status", "message": "Transcription en cours…"})
        full_text = transcriber.transcribe_file(wav_path)
        # Découpage simple en tranches pour réutiliser le pipeline (claims par paquet de texte)
        await run_factcheck_pipeline(job, full_text)
        await broadcast(job, {"type": "done", "timestamp": time.time()})
    except Exception as e:
        log.error(f"Erreur pipeline fichier [{job.job_id}] : {e}")
        await broadcast(job, {"type": "error", "message": str(e)})
    finally:
        job.running = False


# ─── Entrée 2 : URL YouTube / Twitch ───────────────────────────────────────

@app.post("/from-url")
async def from_url(
    url: str = Form(...),
    grok_key: str = Form(default=""),
    gemini_key: str = Form(default=""),
    model: str = Form(default="base"),
    language: str = Form(default="fr"),
):
    job_id = uuid.uuid4().hex
    job = JobState(
        job_id=job_id,
        grok_key=grok_key or None,
        gemini_key=gemini_key or None,
        model_size=model,
        language=language or None,
    )
    JOBS[job_id] = job

    asyncio.create_task(_process_url(job, url))

    return {"job_id": job_id}


async def _process_url(job: JobState, url: str):
    job.running = True
    try:
        await broadcast(job, {"type": "status", "message": "Téléchargement de l'audio…"})
        wav_path = download_from_url(url)
        transcriber = Transcriber(model_size=job.model_size, language=job.language)
        await broadcast(job, {"type": "status", "message": "Transcription en cours…"})
        full_text = transcriber.transcribe_file(wav_path)
        await run_factcheck_pipeline(job, full_text)
        await broadcast(job, {"type": "done", "timestamp": time.time()})
    except Exception as e:
        log.error(f"Erreur pipeline URL [{job.job_id}] : {e}")
        await broadcast(job, {"type": "error", "message": str(e)})
    finally:
        job.running = False


# ─── Entrée 3 : Live micro (blocs de 10-15s envoyés via WebSocket binaire) ─

@app.websocket("/live/{job_id}")
async def live_endpoint(websocket: WebSocket, job_id: str):
    """
    Le client envoie d'abord un message JSON texte de config :
      {"grok_key": "...", "gemini_key": "...", "model": "base", "language": "fr"}
    puis envoie en boucle des blocs audio binaires (webm/wav, ~10-15s chacun).
    """
    await websocket.accept()
    job = JOBS.setdefault(job_id, JobState(job_id=job_id))
    job.clients.add(websocket)

    transcriber = None
    try:
        config_raw = await websocket.receive_text()
        config = json.loads(config_raw)
        job.grok_key = config.get("grok_key") or None
        job.gemini_key = config.get("gemini_key") or None
        job.model_size = config.get("model", "base")
        job.language = config.get("language", "fr")
        job.running = True
        transcriber = Transcriber(model_size=job.model_size, language=job.language)

        while True:
            chunk = await websocket.receive_bytes()
            raw_path = save_upload(chunk, ".webm")
            try:
                wav_path = normalize_audio(raw_path)
                text = transcriber.transcribe_file(wav_path)
                await run_factcheck_pipeline(job, text)
            except Exception as e:
                log.error(f"Erreur traitement bloc live [{job_id}] : {e}")
                await broadcast(job, {"type": "error", "message": str(e)})

    except WebSocketDisconnect:
        log.info(f"Live déconnecté [{job_id}]")
    finally:
        job.clients.discard(websocket)
        job.running = False


if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.environ.get("PORT", 7860))  # 7860 = port par défaut Hugging Face Spaces
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")

# Sert le frontend statique (doit être déclaré après toutes les routes API)
app.mount("/", StaticFiles(directory="../frontend", html=True), name="frontend")
