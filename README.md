# video_xtractor (mise à jour 2026)

## Dépendances

- Python (recommandé: version la plus récente stable)
- yt-dlp
- ffmpeg (important: merge / conversion)
- colorama
- PyInstaller (si vous voulez un .exe)

## Installation (dev)

```bash
python -m pip install -U yt-dlp colorama pyinstaller
```

## Structure recommandée

```
project/
  video_xtractor.py
  video_xtractor_def.py
  snake.ico               (optionnel)
  ffmpeg/
    bin/
      ffmpeg.exe
      ffprobe.exe          (optionnel mais recommandé)
      ffplay.exe           (optionnel)
```

## Build EXE (PyInstaller)

1. Générer le .spec si besoin:

```bash
pyinstaller --onefile video_xtractor.py
```

2. Utiliser le `video_xtractor.spec` fourni (il inclut ffmpeg/bin automatiquement si présent):

```bash
pyinstaller video_xtractor.spec
```

Le .exe se trouve ensuite dans `dist/`.

## Variables d'environnement utiles

- `VIDEO_XTRACTOR_OUTPUT_DIR` : dossier de sortie (sinon `./downloads/` ou `~/Downloads/video_xtractor`)
- `VIDEO_XTRACTOR_FFMPEG` : chemin vers ffmpeg.exe (ou le dossier qui le contient)
- `VIDEO_XTRACTOR_FORMAT` : format yt-dlp (par défaut: MP4/H.264 préféré)
- `VIDEO_XTRACTOR_COOKIES_FROM_BROWSER` : ex: `edge` ou `chrome` (utile quand un site exige une session)
- `VIDEO_XTRACTOR_COOKIES_FILE` : chemin vers un cookiefile Netscape
- `VIDEO_XTRACTOR_USER_AGENT` : User-Agent custom (rarement nécessaire)
