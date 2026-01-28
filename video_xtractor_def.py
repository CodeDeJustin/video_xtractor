import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

from colorama import init, Fore, Style

try:
    import yt_dlp
except Exception as _e:  # pragma: no cover
    yt_dlp = None  # type: ignore


# INITIALISATION DE COLORAMA
init(autoreset=True)

# (Optionnel) liste pour affichage / warning seulement.
BASE_SITES = (
    "https://www.youtube.com",
    "https://youtu.be",
    "https://www.tiktok.com",
    "https://www.instagram.com",
    "https://www.twitch.tv",
    "https://www.dailymotion.com",
)

# Choix de format « 2026-proof »:
# - On préfère MP4 (conteneur) + H.264 (avc1) quand dispo, sinon MP4 sans contrainte de codec, sinon best.
# Les filtres de formats (vcodec/ext/etc.) font partie du système de sélection de formats de yt-dlp.
DEFAULT_FORMAT = (
    "bv*[vcodec^=avc1][ext=mp4]+ba[ext=m4a]/"
    "bv*[ext=mp4]+ba[ext=m4a]/"
    "b[ext=mp4]/b"
)

# ------------------------------------------------------------
# Utilitaires chemins (PyInstaller / dev)
# ------------------------------------------------------------

def _is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _app_dir() -> Path:
    """Dossier de l'app (dossier du .exe si PyInstaller, sinon dossier du script)."""
    if _is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _output_root() -> Path:
    """Dossier racine de sortie.

    - VIDEO_XTRACTOR_OUTPUT_DIR : override (recommandé si tu veux tout diriger ailleurs)
    - sinon: <dossier_app>/downloads
    - sinon fallback: ~/Downloads/video_xtractor
    """
    env = os.getenv("VIDEO_XTRACTOR_OUTPUT_DIR")
    if env:
        p = Path(env).expanduser()
        p.mkdir(parents=True, exist_ok=True)
        return p

    candidate = _app_dir() / "downloads"
    try:
        candidate.mkdir(parents=True, exist_ok=True)
        # Test minimal d'écriture
        testfile = candidate / ".write_test"
        testfile.write_text("ok", encoding="utf-8")
        testfile.unlink(missing_ok=True)
        return candidate
    except Exception:
        fallback = Path.home() / "Downloads" / "video_xtractor"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


def sanitize_filename(name: str, max_len: int = 120) -> str:
    """Nettoie un nom pour Windows (sans dépendance externe)."""
    name = (name or "").strip()
    # Enlever les caractères interdits Windows
    name = re.sub(r'[\\/*?:"<>|]', "", name)
    # Normaliser espaces -> underscores
    name = re.sub(r"\s+", " ", name).strip()
    name = name.replace(" ", "_")
    # Mini-cosmétiques
    name = name.replace("&", "and").replace("'", "")
    name = re.sub(r"_+", "_", name).strip("_")

    if not name:
        name = "video"

    if len(name) > max_len:
        name = name[:max_len].rstrip("_")

    return name


# ------------------------------------------------------------
# FFmpeg (recherche + exécution)
# ------------------------------------------------------------

def get_ffmpeg_path() -> Path:
    """Trouve ffmpeg.exe (ou ffmpeg) dans plusieurs emplacements usuels."""
    # Override explicite
    env = os.getenv("VIDEO_XTRACTOR_FFMPEG")
    candidates: List[Path] = []

    if env:
        p = Path(env).expanduser()
        if p.is_dir():
            candidates.append(p / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg"))
        else:
            candidates.append(p)

    # Cas PyInstaller onefile: ressources extraites dans sys._MEIPASS
    if _is_frozen() and hasattr(sys, "_MEIPASS"):
        meipass = Path(getattr(sys, "_MEIPASS"))
        candidates.extend(
            [
                meipass / "ffmpeg" / "bin" / "ffmpeg.exe",
                meipass / "ffmpeg" / "bin" / "ffmpeg",
                meipass / "ffmpeg" / "ffmpeg.exe",
                meipass / "ffmpeg" / "ffmpeg",
            ]
        )

    # Projet (dev) ou distribution onedir
    ad = _app_dir()
    candidates.extend(
        [
            ad / "ffmpeg" / "bin" / "ffmpeg.exe",
            ad / "ffmpeg" / "bin" / "ffmpeg",
            ad / "ffmpeg.exe",
            ad / "ffmpeg",
            Path.cwd() / "ffmpeg" / "bin" / "ffmpeg.exe",
            Path.cwd() / "ffmpeg" / "bin" / "ffmpeg",
            Path.cwd() / "ffmpeg.exe",
            Path.cwd() / "ffmpeg",
        ]
    )

    for c in candidates:
        if c.exists():
            return c

    # Dernier recours: PATH système
    which = shutil.which("ffmpeg")
    if which:
        return Path(which)

    raise FileNotFoundError(
        "ffmpeg est introuvable.\n"
        "- Si tu utilises l'exe PyInstaller, assure-toi d'inclure ffmpeg dans le build.\n"
        "- Sinon, installe ffmpeg et ajoute-le au PATH, ou définis VIDEO_XTRACTOR_FFMPEG."
    )


def _hide_file_windows(path: Path) -> None:
    """Cache un fichier sous Windows (best-effort)."""
    if os.name != "nt":
        return
    try:
        os.system(f'attrib +h "{path}"')
    except Exception:
        pass


def run_ffmpeg_command(args: List[str], description: str, progress_step: int, total_steps: int) -> None:
    ffmpeg = get_ffmpeg_path()
    cmd = [str(ffmpeg)] + args

    print(f"{Fore.MAGENTA}Exécution ({description}) : {Fore.CYAN}{' '.join(cmd)}{Style.RESET_ALL}")

    try:
        completed = subprocess.run(
            cmd,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        # ffmpeg parle beaucoup. On affiche seulement si ça a du contenu (ça aide en debug).
        out = (completed.stdout or "").strip()
        if out:
            print(out)

        pct = int((progress_step / total_steps) * 100)
        print(f"{Fore.GREEN}{description} terminé {Fore.CYAN}({progress_step}/{total_steps} - {pct}%){Style.RESET_ALL}")

    except FileNotFoundError as e:
        raise FileNotFoundError(f"Impossible de lancer ffmpeg: {e}") from e
    except subprocess.CalledProcessError as e:
        out = (e.stdout or "").strip()
        raise RuntimeError(f"FFmpeg a échoué ({description}).\n{out}") from e


# ------------------------------------------------------------
# Entrée utilisateur
# ------------------------------------------------------------

def get_video_url_from_user() -> List[str]:
    raw = input(
        f"{Style.BRIGHT}{Fore.GREEN}Entrez les URL des vidéos à télécharger (séparées par des virgules) : {Style.RESET_ALL}"
    ).strip()

    # Acceptable: virgules + espaces
    parts = [p.strip() for p in re.split(r"[\s,]+", raw) if p.strip()]

    valid: List[str] = []
    for url in parts:
        if not re.match(r"^https?://", url, flags=re.IGNORECASE):
            print(f"{Fore.RED}ERREUR : '{url}' ne ressemble pas à une URL http(s).{Style.RESET_ALL}")
            continue

        if not any(url.lower().startswith(base) for base in BASE_SITES):
            # Pas bloquant: yt-dlp supporte énormément de sites.
            print(
                f"{Fore.YELLOW}Note : '{url}' n'est pas dans la liste de plateformes 'connues' du script.\n"
                f"      Je tente quand même via yt-dlp (ça marche souvent).{Style.RESET_ALL}"
            )

        valid.append(url)

    if not valid:
        print(f"{Fore.RED}Aucune URL valide détectée, veuillez réessayer.{Style.RESET_ALL}")
        return get_video_url_from_user()

    return valid


# ------------------------------------------------------------
# yt-dlp: progression et options
# ------------------------------------------------------------

def on_download_progress(d: dict) -> None:
    status = d.get("status")
    if status == "downloading":
        percent = d.get("_percent_str", "?")
        speed = d.get("_speed_str", "")
        eta = d.get("_eta_str", "")
        msg = f"Téléchargement : {percent} {speed} ETA {eta}"
        print(f"{Fore.CYAN}\r{msg:80}{Style.RESET_ALL}", end="")
    elif status == "finished":
        print(f"{Fore.CYAN}\rTéléchargement : 100% - post-traitement...{' ':30}{Style.RESET_ALL}")


def _build_ydl_opts(output_dir: Path, base_name: str) -> dict:
    ffmpeg = get_ffmpeg_path()

    ydl_opts = {
        # Format selection (cf. docs yt-dlp)
        "format": os.getenv("VIDEO_XTRACTOR_FORMAT", DEFAULT_FORMAT),
        "outtmpl": str(output_dir / f"{base_name}.%(ext)s"),
        # yt-dlp sait recevoir un chemin vers le binaire OU le dossier contenant ffmpeg
        "ffmpeg_location": str(ffmpeg),
        "merge_output_format": "mp4",
        "progress_hooks": [on_download_progress],
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "noplaylist": True,
        # Fichiers Windows: évite les caractères débiles dans les noms.
        "windowsfilenames": True,
    }

    # Optionnel: cookies / headers
    cookies_from_browser = os.getenv("VIDEO_XTRACTOR_COOKIES_FROM_BROWSER")
    if cookies_from_browser:
        # En CLI: --cookies-from-browser BROWSER[+KEYRING][:PROFILE][::CONTAINER]
        ydl_opts["cookiesfrombrowser"] = cookies_from_browser

    cookie_file = os.getenv("VIDEO_XTRACTOR_COOKIES_FILE")
    if cookie_file:
        # Param historique (youtube-dl/yt-dlp): cookiefile
        ydl_opts["cookiefile"] = cookie_file

    user_agent = os.getenv("VIDEO_XTRACTOR_USER_AGENT")
    if user_agent:
        ydl_opts.setdefault("http_headers", {})["User-Agent"] = user_agent

    return ydl_opts


def _safe_mkdir_unique(root: Path, folder_name: str) -> Path:
    folder = root / folder_name
    if not folder.exists():
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    # Si tu retélécharges la même vidéo, on évite de mélanger les fichiers.
    i = 2
    while True:
        candidate = root / f"{folder_name}_{i}"
        if not candidate.exists():
            candidate.mkdir(parents=True, exist_ok=True)
            return candidate
        i += 1


def _find_downloaded_media_file(output_dir: Path, base_name: str) -> Path:
    # On cherche un fichier qui commence par base_name et qui ressemble à une vidéo.
    media_exts = {".mp4", ".mkv", ".webm", ".mov", ".m4v", ".flv"}

    matches = []
    for p in output_dir.iterdir():
        if not p.is_file():
            continue
        if p.suffix.lower() not in media_exts:
            continue
        if p.name.startswith(base_name):
            matches.append(p)

    if not matches:
        # fallback: prendre le plus gros fichier média du dossier
        candidates = [p for p in output_dir.iterdir() if p.is_file() and p.suffix.lower() in media_exts]
        if not candidates:
            raise FileNotFoundError("Impossible de trouver le fichier téléchargé (aucun média détecté).")

        candidates.sort(key=lambda x: x.stat().st_size, reverse=True)
        return candidates[0]

    matches.sort(key=lambda x: x.stat().st_size, reverse=True)
    return matches[0]


# ------------------------------------------------------------
# Pipeline principal
# ------------------------------------------------------------

def download_video(url: str) -> None:
    if yt_dlp is None:
        raise RuntimeError(
            "Le module 'yt_dlp' n'est pas importable.\n"
            "Installe-le via: pip install -U yt-dlp\n"
            "(ou rebuild ton exe PyInstaller avec yt-dlp inclus)"
        )

    # 1) Récup info (titre / id) - avec options d'auth éventuelles (cookies)
    info_opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
    }

    # Optionnel: cookies / headers (utile surtout pour Instagram/TikTok/etc.)
    cookies_from_browser = os.getenv("VIDEO_XTRACTOR_COOKIES_FROM_BROWSER")
    if cookies_from_browser:
        info_opts["cookiesfrombrowser"] = cookies_from_browser

    cookie_file = os.getenv("VIDEO_XTRACTOR_COOKIES_FILE")
    if cookie_file:
        info_opts["cookiefile"] = cookie_file

    user_agent = os.getenv("VIDEO_XTRACTOR_USER_AGENT")
    if user_agent:
        info_opts.setdefault("http_headers", {})["User-Agent"] = user_agent

    try:
        with yt_dlp.YoutubeDL(info_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            # yt-dlp ne garantit pas que extract_info retourne un dict JSON-serializable.
            # sanitize_info stabilise un peu le format.
            if hasattr(ydl, "sanitize_info"):
                info = ydl.sanitize_info(info)

        if not isinstance(info, dict):
            raise TypeError(f"Type inattendu retourné par yt-dlp: {type(info)}")

        title = (info.get("title") or info.get("fulltitle") or "video")
        video_id = (info.get("id") or "id")
    except Exception as e:
        raise RuntimeError(
            "Impossible d'extraire les infos de la vidéo (titre/id).\n"
            "Astuce: certaines plateformes exigent des cookies (voir VIDEO_XTRACTOR_COOKIES_FROM_BROWSER).\n"
            f"Détail: {e}"
        ) from e

    safe_title = sanitize_filename(title, max_len=120)
    safe_id = sanitize_filename(str(video_id), max_len=40)

    folder_name = f"{safe_title}__{safe_id}"
    base_name = folder_name  # même base pour les fichiers

    output_dir = _safe_mkdir_unique(_output_root(), folder_name)

    print(f"{Style.BRIGHT}{Fore.MAGENTA}\n=== {title} ==={Style.RESET_ALL}")
    print(f"{Fore.CYAN}Dossier de sortie : {output_dir}{Style.RESET_ALL}")

    # 2) Télécharger via yt-dlp
    ydl_opts = _build_ydl_opts(output_dir, base_name)

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.extract_info(url, download=True)

    print()  # ligne après le \r

    downloaded_file = _find_downloaded_media_file(output_dir, base_name)
    print(f"{Fore.GREEN}Fichier téléchargé : {downloaded_file.name}{Style.RESET_ALL}")

    # 3) Post-traitement FFmpeg (audio + conteneurs)
    total_steps = 7
    step = 1

    audio_temp = output_dir / f"{base_name}_TEMP_AUDIO.m4a"
    audio_mp3 = output_dir / f"{base_name}_AUDIO.mp3"
    audio_aac = output_dir / f"{base_name}_AUDIO.aac"
    audio_flac = output_dir / f"{base_name}_AUDIO.flac"
    video_mp4 = output_dir / f"{base_name}_VIDEO.mp4"
    video_mkv = output_dir / f"{base_name}_VIDEO.mkv"

    # Extraction audio (AAC dans un conteneur m4a)
    run_ffmpeg_command(
        ["-y", "-i", str(downloaded_file), "-vn", "-c:a", "aac", "-b:a", "192k", str(audio_temp)],
        "Extraction de l'audio temporaire",
        step,
        total_steps,
    )
    _hide_file_windows(audio_temp)
    step += 1

    # MP3 (libmp3lame si dispo, sinon fallback)
    try:
        run_ffmpeg_command(
            ["-y", "-i", str(audio_temp), "-c:a", "libmp3lame", "-q:a", "0", str(audio_mp3)],
            "Création du fichier MP3",
            step,
            total_steps,
        )
    except RuntimeError:
        run_ffmpeg_command(
            ["-y", "-i", str(audio_temp), "-c:a", "mp3", "-q:a", "0", str(audio_mp3)],
            "Création du fichier MP3 (fallback)",
            step,
            total_steps,
        )
    step += 1

    # FLAC
    run_ffmpeg_command(
        ["-y", "-i", str(audio_temp), "-c:a", "flac", str(audio_flac)],
        "Création du fichier FLAC",
        step,
        total_steps,
    )
    step += 1

    # AAC (sortie .aac en ADTS)
    run_ffmpeg_command(
        ["-y", "-i", str(audio_temp), "-c:a", "aac", "-b:a", "192k", "-f", "adts", str(audio_aac)],
        "Création du fichier AAC",
        step,
        total_steps,
    )
    step += 1

    # MP4 (copie si possible, sinon re-encode h264/aac)
    try:
        run_ffmpeg_command(
            [
                "-y",
                "-i",
                str(downloaded_file),
                "-map",
                "0:v:0",
                "-map",
                "0:a:0?",
                "-c",
                "copy",
                "-movflags",
                "+faststart",
                str(video_mp4),
            ],
            "Création du fichier MP4",
            step,
            total_steps,
        )
    except RuntimeError:
        # Dernier recours: ré-encodage (nécessite un ffmpeg avec libx264)
        run_ffmpeg_command(
            [
                "-y",
                "-i",
                str(downloaded_file),
                "-map",
                "0:v:0",
                "-map",
                "0:a:0?",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "20",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-movflags",
                "+faststart",
                str(video_mp4),
            ],
            "Création du fichier MP4 (ré-encodage)",
            step,
            total_steps,
        )
    step += 1

    # MKV (remux rapide)
    run_ffmpeg_command(
        [
            "-y",
            "-i",
            str(downloaded_file),
            "-map",
            "0:v:0",
            "-map",
            "0:a:0?",
            "-c",
            "copy",
            str(video_mkv),
        ],
        "Création du fichier MKV",
        step,
        total_steps,
    )
    step += 1

    print(f"{Fore.MAGENTA}Téléchargement et conversion terminés pour: {title} ({total_steps}/{total_steps} - 100%){Style.RESET_ALL}")

    # Nettoyage
    try:
        audio_temp.unlink(missing_ok=True)
    except Exception:
        pass
