# FactCheck Web — Déploiement Hugging Face Spaces

Version web de FrenchCheck Desktop : upload de fichier, lien YouTube/Twitch, ou
micro navigateur → transcription locale (Whisper) → fact-check **comparé**
Grok (xAI) + Gemini (Google), chacun avec la clé API de l'utilisateur.

## Déploiement sur Hugging Face Spaces

1. Créer un nouveau Space sur https://huggingface.co/new-space
2. **SDK : Docker** (pas Gradio/Streamlit — indispensable pour FastAPI + ffmpeg + yt-dlp)
3. Visibilité : Public si tu veux que "tout le monde" y accède
4. Pousser ce dossier tel quel (le `Dockerfile` est à la racine) :
   ```bash
   git clone https://huggingface.co/spaces/<ton-username>/<nom-du-space>
   cp -r factcheck-web/* <nom-du-space>/
   cd <nom-du-space>
   git add . && git commit -m "Initial deploy" && git push
   ```
5. Le Space build automatiquement et expose l'app sur le port 7860.

Aucune clé API à configurer côté Space : chaque visiteur fournit la sienne
(Grok et/ou Gemini) directement dans l'interface, en mémoire navigateur.

## Limites importantes à connaître avant d'ouvrir au public

- **CPU partagé gratuit** : la transcription Whisper (même modèle "base") prend
  du temps sur CPU partagé. Avec plusieurs utilisateurs simultanés, attends-toi
  à de la lenteur, voire des timeouts. Pour un usage sérieux, passer sur un
  Space payant avec plus de CPU, ou un GPU (`small`/`medium` deviennent
  réalistes avec un GPU).
- **Mise en veille** : un Space gratuit s'endort après une période d'inactivité
  et redémarre (avec un délai) à la requête suivante.
- **yt-dlp et les ToS des plateformes** : le téléchargement de contenu YouTube
  ou Twitch via un service tiers public peut enfreindre les conditions
  d'utilisation de ces plateformes selon l'usage qui en est fait. À vérifier
  selon ton cas d'usage (privé, restreint, éducatif, etc.).
- **Pas de quota/auth** : actuellement n'importe qui peut lancer une analyse.
  Comme c'est l'utilisateur qui fournit sa clé API, le risque financier pour
  toi est nul, mais rien n'empêche un usage abusif de ton CPU. Pour limiter :
  ajouter un simple rate-limit par IP (ex: `slowapi`) si besoin.
- **Stockage temporaire** : les fichiers audio téléchargés/uploadés sont
  écrits dans `/tmp` et ne sont pas nettoyés automatiquement pour l'instant —
  à ajouter (purge périodique) si le volume devient important.

## Variables d'environnement

Aucune requise. `PORT` est fixé à 7860 par défaut (standard HF Spaces).

## Structure

```
factcheck-web/
├── Dockerfile
├── backend/
│   ├── main.py              # FastAPI : /upload /from-url /live/{id} /ws/{id}
│   ├── requirements.txt
│   └── core/
│       ├── models.py        # JobState, Verdict
│       ├── transcriber.py   # Faster-Whisper
│       ├── factchecker.py   # Extraction claims (Gemini) + vérif (Grok+Gemini)
│       └── media.py         # yt-dlp + normalisation ffmpeg
└── frontend/
    └── index.html           # UI complète (HTML/CSS/JS, sans build)
```
