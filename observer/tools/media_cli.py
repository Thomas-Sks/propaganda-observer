"""CLI : enrichit les vidéos d'un événement (transcription + OCR + empreintes d'images).

    uv run python -m observer.tools.media_cli <slug> --max 10 [--max-usd 0.5]
"""
from __future__ import annotations

import argparse
import asyncio
import logging

from observer.core import llm
from observer.tools.media import enrich_event


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("slug")
    ap.add_argument("--max", type=int, default=10, help="nombre maximal de vidéos à traiter")
    ap.add_argument("--max-usd", type=float, default=None, help="plafond de dépense pour cette passe")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    before = llm.spent()
    done, stats = asyncio.run(enrich_event(a.slug, a.max, a.max_usd))
    for s in stats:
        print(f"{s.uid:45} {'ok' if s.ok else 'ÉCHEC':5} whisper={s.usd_transcribe:.4f}$ ocr={s.usd_ocr:.4f}$ "
              f"phash={len(s.phashes)} transcript={len(s.transcript)}c ocr={len(s.ocr_text)}c {s.error}")
        if s.transcript:
            print("   T:", s.transcript[:160].replace("\n", " "))
        if s.ocr_text:
            print("   O:", s.ocr_text[:160].replace("\n", " | "))
    print(f"{len(done)}/{len(stats)} vidéos enrichies ; dépense mesurée {llm.spent() - before:.4f} $ "
          f"(reste {llm.remaining():.2f} $)")


if __name__ == "__main__":
    main()
