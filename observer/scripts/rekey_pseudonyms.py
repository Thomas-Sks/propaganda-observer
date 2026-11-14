"""Migration unique : applique la clé secrète PSEUDO_KEY aux pseudonymes déjà stockés (items et narratifs).

Usage : uv run python -m observer.scripts.rekey_pseudonyms
Idempotent : un marqueur Redis retient l'empreinte de la clé déjà appliquée. Ensuite : redémarrer l'API, relancer
les enquêtes IA voulues (leur cache dépend des libellés) et republier la démo (l'instantané est vidé ici).
"""
from __future__ import annotations

import asyncio
import hashlib

from sqlalchemy import select, text, update

from observer.core import db, llm
from observer.core.models import rekey
from observer.core.settings import settings

FLAG = "observer:pseudo:rekeyed"


async def main() -> None:
    key = settings().pseudo_key
    if not key:
        raise SystemExit("PSEUDO_KEY is not set in .env")
    fp = hashlib.sha256(key.encode()).hexdigest()[:12]
    if llm._r().get(FLAG) == fp:
        print("already migrated with this key")
        return
    async with db.engine().begin() as conn:
        olds = [r[0] for r in (await conn.execute(select(db.items.c.author_pseudo).distinct())).all()]
        mapping = {o: rekey(o) for o in olds}
        await conn.execute(text("CREATE TEMP TABLE pseudo_map (old text primary key, new text) ON COMMIT DROP"))
        await conn.execute(text("INSERT INTO pseudo_map VALUES (:old, :new)"), [{"old": o, "new": n} for o, n in mapping.items()])
        n_items = (await conn.execute(text(
            "UPDATE items i SET author_pseudo = m.new, data = jsonb_set(i.data, '{author_pseudo}', to_jsonb(m.new)) "
            "FROM pseudo_map m WHERE i.author_pseudo = m.old"))).rowcount
        n_cl = 0
        for cid, data in (await conn.execute(select(db.clusters.c.id, db.clusters.c.data))).all():
            authors = data.get("authors") or []
            data["authors"] = [mapping.get(a, rekey(a)) for a in authors]
            await conn.execute(update(db.clusters).where(db.clusters.c.id == cid).values(data=data))
            n_cl += 1
        n_snap = (await conn.execute(db.snapshots.delete())).rowcount
    llm._r().set(FLAG, fp)
    print(f"accounts {len(mapping)} · items {n_items} · narratives {n_cl} · snapshot rows removed {n_snap}")


if __name__ == "__main__":
    asyncio.run(main())
