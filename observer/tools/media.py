"""Enrichissement des vidéos (YouTube/Shorts, TikTok, Reels) : transcription, texte incrusté, empreintes d'images.

Objectif : relier une vidéo à un article ou à un post même sans texte commun dans la légende.
- `transcript` : audio (≤ 3 min) transcrit par `whisper-1-eu` via l'AI Router (SDK OpenAI) ;
- `ocr_text`   : texte incrusté lu sur 3 images (début/milieu/fin) par un modèle Claude vision peu coûteux ;
- `links`      : `frame-phash:<hex>` (dHash 64 bits) → `tools/links.py` regroupe les réuploads identiques.
Toute dépense passe par `llm._charge` / `llm.create` et respecte le plafond `llm.remaining()`.
Les fichiers sont téléchargés dans `data/raw/media/` (ignoré par git) et supprimés après usage.
"""
from __future__ import annotations

import base64
import logging
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from observer.core import llm
from observer.core.models import ContentItem
from observer.core.settings import ROOT, settings

log = logging.getLogger("observer.media")
logging.getLogger("yt_dlp").setLevel(logging.CRITICAL)

MEDIA_DIR = ROOT / "data" / "raw" / "media"
MAX_AUDIO_S = 180  # on ne transcrit que les 3 premières minutes
FFMPEG = shutil.which("ffmpeg") or "/usr/bin/ffmpeg"
FFPROBE = shutil.which("ffprobe") or "/usr/bin/ffprobe"
WHISPER_USD_PER_MIN = 0.006 * 2  # estimation prudente (×2 du tarif public) si le Router ne renvoie pas le coût
PHASH_PREFIX = "frame-phash:"
DONE_KEY = "observer:media:done"  # uid déjà tentés sans succès (évite de retélécharger en boucle)
VIEW_KEYS = ("view_count", "playCount", "videoPlayCount", "videoViewCount")


@dataclass
class MediaFiles:
    workdir: Path
    audio: Path | None = None
    frames: list[Path] = field(default_factory=list)
    duration: float = 0.0

    def cleanup(self) -> None:
        shutil.rmtree(self.workdir, ignore_errors=True)


@dataclass
class EnrichStat:
    uid: str
    ok: bool
    usd_transcribe: float = 0.0
    usd_ocr: float = 0.0
    error: str = ""
    transcript: str = ""
    ocr_text: str = ""
    phashes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------- sélection

def is_video(it: ContentItem) -> bool:
    if it.platform in ("youtube", "tiktok"):
        return True
    if it.platform == "instagram":
        return it.format in ("reel", "video") or "/reel/" in (it.url or "") or any(
            k in it.metrics for k in ("videoPlayCount", "videoViewCount"))
    return False


def views(it: ContentItem) -> int:
    return max((it.metrics.get(k) or 0 for k in VIEW_KEYS), default=0)


def is_enriched(it: ContentItem) -> bool:
    return it.transcript is not None or it.ocr_text is not None


def pick(items: list[ContentItem], max_items: int, priority_uids: set[str] | None = None,
         skip_uids: set[str] | None = None, min_relevance: float = 0.0) -> list[ContentItem]:
    """Vidéos non traitées et pertinentes : d'abord celles d'un narratif/cluster, puis les plus vues."""
    pri, skip = priority_uids or set(), skip_uids or set()
    cand = [i for i in items if is_video(i) and i.url and not is_enriched(i) and i.uid not in skip
            and (i.relevance is None or i.relevance >= min_relevance)]
    cand.sort(key=lambda i: (i.uid in pri, views(i)), reverse=True)
    return cand[:max_items]


# ---------------------------------------------------------------- téléchargement

def _run(cmd: list[str], timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, timeout=timeout, check=True)


def _probe_duration(path: Path) -> float:
    try:
        out = _run([FFPROBE, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)], 30)
        return float(out.stdout.decode().strip() or 0)
    except Exception:
        return 0.0


def _has_stream(path: Path, kind: str) -> bool:
    try:
        out = _run([FFPROBE, "-v", "error", "-select_streams", kind, "-show_entries", "stream=index",
                    "-of", "csv=p=0", str(path)], 30)
        return bool(out.stdout.strip())
    except Exception:
        return False


def _js_runtimes() -> dict:
    """node (souvent via nvm, hors PATH des services) sinon deno, le défaut de yt-dlp."""
    import glob
    node = shutil.which("node") or next(iter(sorted(glob.glob(str(Path.home() / ".nvm/versions/node/*/bin/node")),
                                                    reverse=True)), None)
    return {"node": {"path": node}} if node else {"deno": {}}


def fetch_media(item: ContentItem) -> MediaFiles | None:
    """Télécharge un extrait (≤ 3 min, basse qualité) puis en tire l'audio mono et 3 images.
    Renvoie None en cas d'échec (vidéo privée, login requis, blocage…) : jamais bloquant."""
    import yt_dlp
    from yt_dlp.utils import download_range_func

    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    mf = MediaFiles(workdir=Path(tempfile.mkdtemp(prefix=item.uid.replace(":", "_") + "-", dir=MEDIA_DIR)))
    opts = {
        "quiet": True, "no_warnings": True, "noprogress": True, "logger": logging.getLogger("yt_dlp"),
        "outtmpl": str(mf.workdir / "src.%(ext)s"), "max_filesize": 60 * 1024 * 1024,
        # Petite qualité avec audio et image (360p YouTube « 18 », sinon le plus petit format complet)
        "format": "bv*[height<=360][height>=240][vcodec^=avc1]+ba/bv*[height<=360]+ba/18"
                  "/worst[vcodec!=none][acodec!=none]/worst",
        "download_ranges": download_range_func(None, [(0, MAX_AUDIO_S)]),
        "socket_timeout": 30, "retries": 2,
        "js_runtimes": _js_runtimes(),  # YouTube : sans runtime JS, la plupart des formats sont absents
    }
    try:
        with yt_dlp.YoutubeDL(opts) as y:
            y.extract_info(item.url, download=True)
        src = next((p for p in mf.workdir.iterdir() if p.name.startswith("src.") and not p.name.endswith(".part")), None)
        if src is None:
            raise RuntimeError("aucun fichier téléchargé")
        mf.duration = min(_probe_duration(src), MAX_AUDIO_S)
        if _has_stream(src, "a"):
            # WAV PCM mono 16 kHz (~5,8 Mo pour 3 min, limite Whisper 25 Mo). Le pare-feu Cloudflare de
            # l'AI Router renvoie 403 sur les envois mp3/flac/ogg/m4a : seul le WAV passe (testé le 14/11/2026).
            mf.audio = mf.workdir / "audio.wav"
            _run([FFMPEG, "-v", "error", "-y", "-i", str(src), "-t", str(MAX_AUDIO_S), "-vn", "-ac", "1",
                  "-ar", "16000", "-c:a", "pcm_s16le", str(mf.audio)])
        if _has_stream(src, "v"):
            d = mf.duration or 1.0
            for k, t in enumerate((min(1.0, d * 0.1), d * 0.5, max(d - 1.0, d * 0.9))):
                out = mf.workdir / f"frame{k}.jpg"
                _run([FFMPEG, "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", str(src), "-frames:v", "1",
                      "-vf", "scale=512:-2", "-q:v", "4", str(out)], 60)
                if out.exists() and out.stat().st_size > 0:
                    mf.frames.append(out)
        src.unlink(missing_ok=True)  # on ne garde que l'audio réduit et les images
        if mf.audio is None and not mf.frames:
            raise RuntimeError("ni audio ni image exploitable")
        return mf
    except Exception as e:
        log.info("média indisponible %s : %s", item.uid, str(e)[:160])
        mf.cleanup()
        return None


# ---------------------------------------------------------------- transcription (Whisper)

def _credits_from(usage: dict | None) -> float | None:
    if not isinstance(usage, dict):
        return None
    c = usage.get("credits_charged")
    return float(c) if c is not None else None


AUDIO_LLM_MODEL = "gemini-3.5-flash-lite-eu"  # repli : audio en base64 dans une requête JSON (passe le pare-feu)
# Consigne en anglais et sans échappatoire trop facile : en français avec « réponds AUCUN », Gemini renvoyait
# AUCUN sur des reportages parlés (constaté sur 2 vidéos YouTube sur 4).
AUDIO_LLM_PROMPT = ("Generate a verbatim transcript of all the speech in this audio, in its original language "
                    "(do not translate, summarize or comment). Output only the transcript. "
                    "Only if there is no human speech at all, output exactly: [NO SPEECH]")
_whisper_blocked = False  # mémorise le blocage Cloudflare pour ne pas réessayer à chaque vidéo


def _whisper(path: Path, duration_s: float | None) -> tuple[str, float]:
    model = settings().model_transcribe
    with open(path, "rb") as f:
        raw = llm.openai_client().audio.transcriptions.with_raw_response.create(
            model=model, file=f, response_format="json")
    try:
        data = raw.http_response.json()
    except Exception:
        data = {"text": raw.parse().text}
    usage = data.get("usage") or {}
    credits = _credits_from(usage)
    if credits is None:  # le Router ne renvoie que `duration` : estimation prudente à partir de la durée
        secs = usage.get("seconds") or data.get("duration") or duration_s or _probe_duration(path) or MAX_AUDIO_S
        credits = (float(secs) / 60 * WHISPER_USD_PER_MIN) / settings().usd_per_credit
    usd = llm._charge(model, 0, 0, credits, "media.transcribe")
    return (data.get("text") or "").strip(), usd


def _audio_llm(path: Path) -> tuple[str, float]:
    """Transcription par un modèle multimodal (audio mp3 64 kb/s en base64, ~1,4 Mo pour 3 min)."""
    mp3 = path.with_suffix(".mp3")
    _run([FFMPEG, "-v", "error", "-y", "-i", str(path), "-ac", "1", "-b:a", "48k", str(mp3)])
    b64 = base64.b64encode(mp3.read_bytes()).decode()
    raw = llm.openai_client().chat.completions.with_raw_response.create(
        model=AUDIO_LLM_MODEL, max_completion_tokens=2000, messages=[{"role": "user", "content": [
            {"type": "text", "text": AUDIO_LLM_PROMPT},
            {"type": "input_audio", "input_audio": {"data": b64, "format": "mp3"}}]}])
    data = raw.http_response.json()
    u = data.get("usage") or {}
    usd = llm._charge(AUDIO_LLM_MODEL, u.get("prompt_tokens", 0), u.get("completion_tokens", 0),
                      _credits_from(u), "media.transcribe")
    txt = (data["choices"][0]["message"].get("content") or "").strip()
    return ("" if txt.strip(" .[]").upper() in ("NO SPEECH", "AUCUN", "NONE") else txt), usd


def transcribe(path: Path, duration_s: float | None = None) -> tuple[str, float]:
    """Transcrit un fichier audio. Renvoie (texte, coût USD). Lève BudgetExceeded si plafond atteint.
    Whisper d'abord ; si le pare-feu du Router le bloque (403, constaté sur tout audio réel), repli Gemini."""
    global _whisper_blocked
    if llm.remaining() <= 0:
        raise llm.BudgetExceeded(f"Plafond LLM atteint ({llm.spent():.4f} $)")
    if not _whisper_blocked:
        try:
            return _whisper(path, duration_s)
        except Exception as e:
            if getattr(e, "status_code", None) != 403:
                raise
            _whisper_blocked = True
            log.info("Whisper bloqué par le pare-feu du Router (403) : repli sur %s", AUDIO_LLM_MODEL)
    return _audio_llm(path)


# ---------------------------------------------------------------- OCR (Claude vision)

OCR_PROMPT = ("Ces images sont extraites d'une même vidéo (début, milieu, fin). Recopie fidèlement tout le texte "
              "incrusté visible (sous-titres, titres, bandeaux, légendes, filigranes), dans sa langue d'origine, "
              "sans traduire ni commenter, une ligne par bloc, sans doublons. Réponds uniquement par ce texte brut. "
              "S'il n'y a aucun texte lisible, réponds exactement : AUCUN")


def _usage_usd(usage) -> float:
    c = getattr(usage, "credits_charged", None)
    if c is None:  # même estimation pessimiste que llm._charge
        c = usage.input_tokens * 0.0006 + usage.output_tokens * 0.003
    return float(c) * settings().usd_per_credit


def ocr_frames(paths: list[Path]) -> tuple[str, float]:
    """Texte incrusté des images en une seule requête. Renvoie (texte, coût USD)."""
    if not paths:
        return "", 0.0
    content: list[dict] = [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                        "data": base64.b64encode(p.read_bytes()).decode()}}
                           for p in paths]
    content.append({"type": "text", "text": OCR_PROMPT})
    # NB : pas de `temperature` (refusée par les modèles Claude 5 via le Router) ; la consigne suffit.
    resp = llm.create(model=settings().model_triage, max_tokens=600, purpose="media.ocr",
                      messages=[{"role": "user", "content": content}])
    txt = llm.text(resp).strip()
    if txt.strip(" .«»\"'").upper() in ("AUCUN", "NONE") or len(txt) < 3:  # « K » isolé = bruit
        txt = ""
    return txt, _usage_usd(resp.usage)


# ---------------------------------------------------------------- empreintes perceptuelles

def dhash_bits(pixels: bytes | list[int], w: int = 9, h: int = 8) -> str:
    """dHash : pour chaque ligne, 1 si un pixel est plus clair que son voisin de droite. Renvoie 16 hex."""
    bits = 0
    for r in range(h):
        row = pixels[r * w:(r + 1) * w]
        for c in range(w - 1):
            bits = (bits << 1) | (1 if row[c] > row[c + 1] else 0)
    return f"{bits:0{(h * (w - 1) + 3) // 4}x}"


def _gray_9x8(path: Path) -> bytes:
    """Image réduite à 9x8 en niveaux de gris (Pillow si présent, sinon ffmpeg)."""
    try:
        from PIL import Image
        return Image.open(path).convert("L").resize((9, 8), Image.Resampling.LANCZOS).tobytes()
    except ImportError:
        out = _run([FFMPEG, "-v", "error", "-i", str(path), "-vf", "scale=9:8:flags=area,format=gray",
                    "-f", "rawvideo", "-"], 30).stdout
        if len(out) < 72:
            raise RuntimeError(f"ffmpeg : {len(out)} octets au lieu de 72")
        return out[:72]


def informative(h: str) -> bool:
    """Écarte les images quasi uniformes (écran noir, fondu) : leur hash collisionne entre vidéos sans lien."""
    ones = bin(int(h, 16)).count("1")
    return 6 <= ones <= 58


def phash_frames(paths: list[Path]) -> list[str]:
    out: list[str] = []
    for p in paths:
        try:
            try:
                import imagehash
                from PIL import Image
                h = str(imagehash.dhash(Image.open(p)))
            except ImportError:
                h = dhash_bits(_gray_9x8(p))
        except Exception as e:
            log.info("hash %s : %s", p.name, e)
            continue
        if informative(h) and h not in out:
            out.append(h)
    return out


def phash_links(hashes: list[str]) -> list[str]:
    return [f"{PHASH_PREFIX}{h}" for h in hashes]


def add_links(item: ContentItem, hashes: list[str]) -> None:
    """Ajoute les `frame-phash:` sans doublons (et remplace d'anciens hash éventuels)."""
    keep = [l for l in item.links if not l.startswith(PHASH_PREFIX)]
    item.links = keep + [l for l in phash_links(hashes) if l not in keep]


# ---------------------------------------------------------------- orchestration

def enrich_one(item: ContentItem) -> EnrichStat:
    """Un échec d'API laisse le champ à None (nouvel essai à la prochaine passe) ; "" = traité, rien trouvé."""
    st = EnrichStat(uid=item.uid, ok=False)
    mf = fetch_media(item)
    if mf is None:
        st.error = "téléchargement impossible"
        return st
    transcript = ocr = None
    try:
        if mf.audio is not None:
            try:
                transcript, st.usd_transcribe = transcribe(mf.audio, mf.duration)
            except llm.BudgetExceeded:
                raise
            except Exception as e:
                st.error = f"transcription : {str(e)[:120]}"
        else:
            transcript = ""  # vidéo muette
        if mf.frames:
            try:
                ocr, st.usd_ocr = ocr_frames(mf.frames)
            except llm.BudgetExceeded:
                raise
            except Exception as e:
                st.error += f" ocr : {str(e)[:120]}"
            st.phashes = phash_frames(mf.frames)
    finally:
        mf.cleanup()
    st.transcript, st.ocr_text = transcript or "", ocr or ""
    if transcript is None and ocr is None and not st.phashes:
        return st  # rien d'exploitable : l'item reste « à faire »
    item.transcript, item.ocr_text = transcript, ocr
    add_links(item, st.phashes)
    st.ok = True
    return st


def enrich(items: list[ContentItem], max_items: int = 10, priority_uids: set[str] | None = None,
           max_usd: float | None = None, min_relevance: float = 0.0) -> tuple[list[ContentItem], list[EnrichStat]]:
    """Bloquant (à appeler via asyncio.to_thread). Modifie les items en place et renvoie ceux enrichis.
    `max_usd` borne la dépense de cette passe en plus du plafond global."""
    r = llm._r()
    try:
        skip = set(r.smembers(DONE_KEY))
    except Exception:
        skip = set()
    done, stats, total = [], [], 0.0
    for it in pick(items, max_items, priority_uids, skip, min_relevance):
        if llm.remaining() <= 0 or (max_usd is not None and total >= max_usd):
            log.warning("enrichissement média arrêté : budget atteint (%.4f $ dépensés)", total)
            break
        try:
            st = enrich_one(it)
        except llm.BudgetExceeded as e:
            log.warning("enrichissement média : %s", e)
            break
        stats.append(st)
        total += st.usd_transcribe + st.usd_ocr
        if st.ok:
            done.append(it)
        else:
            try:
                r.sadd(DONE_KEY, it.uid)
                r.expire(DONE_KEY, 24 * 3600)  # on retente les échecs le lendemain
            except Exception:
                pass
    return done, stats


async def enrich_event(slug: str, max_items: int = 10, max_usd: float | None = None,
                       items: list[ContentItem] | None = None) -> tuple[list[ContentItem], list[EnrichStat]]:
    """Charge les items de l'événement, priorise ceux des clusters, enrichit et persiste (upsert)."""
    import asyncio

    from observer.core import db
    if items is None:
        items = await db.load_items(slug, limit=8000)
    from observer.tools import relevance
    try:
        pri = {u for c in await db.load_clusters(slug) for u in c.item_uids}
    except Exception:
        pri = set()
    ev = await db.get_event(slug)
    thr = relevance.threshold(ev["config"]) if ev else 0.0  # pas de dépense sur les hors-sujets
    done, stats = await asyncio.to_thread(enrich, items, max_items, pri, max_usd, thr)
    if done:
        await db.save_items_returning(done)
    return done, stats
