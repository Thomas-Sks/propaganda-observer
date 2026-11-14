"""Télécharge (une seule fois, en cache dans data/raw/eval/) les jeux étiquetés de l'onglet Reliability.

Usage : uv run python -m eval.fetch [--keep-zip]

- Cresci-2017 (Bot Repository, 466 Mo) : on n'en garde qu'un échantillon équilibré de ~2 000 comptes
  (1 000 humains, 1 000 bots répartis entre les 7 familles de bots) dans cresci2017_sample.csv.
- Lin et al. 2023 (domain_pc1.csv), Iffy+ (CSV Google Sheets), réseau Pravda (CheckFirst, liste allDomains).
Les fichiers sont cités, non redistribués (data/raw/ est ignoré par git).
"""
from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path

import httpx
import pandas as pd

RAW = Path(__file__).resolve().parent.parent / "data" / "raw" / "eval"
SEED = 42
N_PER_CLASS = 1000

SOURCES = {
    "cresci-2017.csv.zip": "https://botometer.osome.iu.edu/bot-repository/datasets/cresci-2017/cresci-2017.csv.zip",
    "lin_domain_pc1.csv": "https://raw.githubusercontent.com/hauselin/domain-quality-ratings/main/data/domain_pc1.csv",
    "iffy.csv": "https://docs.google.com/spreadsheets/d/1ck1_FZC-97uDLIlvRJDTrGqBk0FuDe9yHkluROgpGS8/gviz/tq"
                "?tqx=out:csv&sheet=Iffy-news",
    "pravda_viz.json": "https://raw.githubusercontent.com/CheckFirstHQ/pravda-network/main/json/"
                       "francais.news-pravda.com_viz.json",
}
SAMPLE = "cresci2017_sample.csv"
BOT_GROUPS = ["social_spambots_1", "social_spambots_2", "social_spambots_3", "traditional_spambots_1",
              "traditional_spambots_2", "traditional_spambots_3", "traditional_spambots_4", "fake_followers"]
KEEP = ["id", "group", "label", "statuses_count", "followers_count", "friends_count", "favourites_count",
        "listed_count", "default_profile", "default_profile_image", "verified", "has_description", "has_url",
        "created_at", "observed_at"]
TW_FMT = "%a %b %d %H:%M:%S %z %Y"


def download(name: str, url: str) -> Path:
    """Téléchargement en flux vers un .part, renommé une fois complet (idempotent)."""
    dest = RAW / name
    if dest.exists():
        return dest
    RAW.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with httpx.stream("GET", url, follow_redirects=True, timeout=120,
                      headers={"User-Agent": "reliability-eval/0.1"}) as r:
        r.raise_for_status()
        with tmp.open("wb") as f:
            for chunk in r.iter_bytes(1 << 20):
                f.write(chunk)
    tmp.rename(dest)
    return dest


def _users(outer: zipfile.ZipFile, group: str) -> pd.DataFrame:
    """Lit uniquement users.csv dans le zip imbriqué d'une famille (les tweets sont ignorés)."""
    inner = zipfile.ZipFile(io.BytesIO(outer.read(f"datasets_full.csv/{group}.csv.zip")))
    name = next(n for n in inner.namelist() if n.endswith("/users.csv") and not n.startswith("__MACOSX"))
    df = pd.read_csv(io.BytesIO(inner.read(name)), dtype=str, encoding_errors="replace")
    df["group"] = group
    return df


def _clean(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame({"id": df["id"], "group": df["group"]})
    out["label"] = (df["group"] != "genuine_accounts").astype(int)  # 1 = bot
    for c in ["statuses_count", "followers_count", "friends_count", "favourites_count", "listed_count"]:
        out[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype(int)
    for c in ["default_profile", "default_profile_image", "verified"]:
        out[c] = (df[c].fillna("") == "1").astype(int)
    out["has_description"] = df["description"].fillna("").str.strip().ne("").astype(int)
    out["has_url"] = df["url"].fillna("").str.strip().ne("").astype(int)
    created = pd.to_datetime(df["created_at"], format=TW_FMT, errors="coerce", utc=True)
    if "timestamp" in df:  # certaines familles n'ont que l'horodatage local
        created = created.fillna(pd.to_datetime(df["timestamp"], errors="coerce", utc=True))
    # Date d'observation : date de collecte si fournie, sinon dernière mise à jour du profil
    obs = pd.to_datetime(df["crawled_at"], errors="coerce", utc=True) if "crawled_at" in df else None
    upd = pd.to_datetime(df["updated"], errors="coerce", utc=True)
    observed = obs.fillna(upd) if obs is not None else upd
    out["created_at"] = created.dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    out["observed_at"] = observed.dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    return out.dropna(subset=["created_at", "observed_at"])


def cresci_sample(keep_zip: bool = False) -> Path:
    dest = RAW / SAMPLE
    if dest.exists():
        return dest
    z = download("cresci-2017.csv.zip", SOURCES["cresci-2017.csv.zip"])
    with zipfile.ZipFile(z) as outer:
        humans = _clean(_users(outer, "genuine_accounts")).sample(N_PER_CLASS, random_state=SEED)
        bots = {g: _clean(_users(outer, g)) for g in BOT_GROUPS}
    # Répartition équilibrée entre familles (les petites familles donnent tout ce qu'elles ont)
    quota, left, parts = {}, N_PER_CLASS, sorted(bots, key=lambda g: len(bots[g]))
    for k, g in enumerate(parts):
        quota[g] = min(len(bots[g]), left // (len(parts) - k))
        left -= quota[g]
    sample = pd.concat([humans] + [bots[g].sample(quota[g], random_state=SEED) for g in BOT_GROUPS])
    sample[KEEP].to_csv(dest, index=False)
    if not keep_zip:
        z.unlink()  # on ne garde que l'échantillon léger
    return dest


def main() -> None:
    for name, url in SOURCES.items():
        if name != "cresci-2017.csv.zip":
            print("ok", download(name, url))
    print("ok", cresci_sample(keep_zip="--keep-zip" in sys.argv))


if __name__ == "__main__":
    main()
