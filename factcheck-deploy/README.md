---
title: Super Fact Check
emoji: 🔍
colorFrom: blue
colorTo: red
sdk: docker
pinned: false
---

# FactCheck Web

Version web de FrenchCheck Desktop : upload de fichier, lien YouTube/Twitch, ou
micro navigateur → transcription locale (Whisper) → fact-check **comparé**
Grok (xAI) + Gemini (Google), chacun avec la clé API de l'utilisateur.

## Structure

```
├── Dockerfile
├── backend/
│   ├── main.py
│   ├── requirements.txt
│   └── core/
│       ├── models.py
│       ├── transcriber.py
│       ├── factchecker.py
│       └── media.py
└── frontend/
    └── index.html
```
