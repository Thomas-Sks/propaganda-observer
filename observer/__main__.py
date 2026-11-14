"""CLI de développement.

  uv run python -m observer plan "manifestations en France en novembre 2026"
  uv run python -m observer collect <slug>          # une passe de collecte + détection
  uv run python -m observer budget
"""
from __future__ import annotations

import argparse
import asyncio

from observer.core import bus, db, llm


async def cmd_plan(description: str, model: str | None) -> None:
    from observer.agents.planner import plan, validate_keywords
    await db.init_db()
    cfg = plan(description, model=model)
    await bus.publish(cfg.slug, "planner.log", {"msg": f"{len(cfg.keywords)} mots-clés proposés"})
    volumes = await validate_keywords(cfg)
    for k, v in sorted(volumes.items(), key=lambda x: -x[1]):
        print(f"  {'✓' if k in cfg.keywords else '✗'} {v:>4}  {k}")
    await db.upsert_event(cfg.slug, cfg.label, cfg.model_dump() | {"volumes": volumes}, status="planned")
    print(f"\nÉvénement enregistré : {cfg.slug}")


async def cmd_collect(slug: str) -> None:
    from observer.collectors import gnews
    from observer.tools.text import find_copypasta
    ev = await db.get_event(slug)
    if not ev:
        raise SystemExit(f"Événement inconnu : {slug}")
    cfg = ev["config"]
    total = 0
    for kw in cfg["keywords"]:
        items = await gnews.fetch(kw, country=cfg.get("country", "FR"), event=slug)
        n = await db.save_items(items)
        total += n
        for it in items[:n]:
            await bus.publish(slug, "item.new", it.model_dump(mode="json"))
    all_items = await db.load_items(slug)
    clusters = find_copypasta(all_items, min_authors=2)
    await db.save_clusters(slug, clusters)
    for c in clusters:
        await bus.publish(slug, "cluster.updated", c.model_dump(mode="json"))
    print(f"{total} nouveaux items ({len(all_items)} au total), {len(clusters)} clusters copypasta")
    for c in clusters[:5]:
        print(f"  {c.id} : {len(c.authors)} sources, {len(c.item_uids)} items")


def main() -> None:
    p = argparse.ArgumentParser(prog="observer")
    sub = p.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("plan"); sp.add_argument("description"); sp.add_argument("--model")
    sc = sub.add_parser("collect"); sc.add_argument("slug")
    sub.add_parser("budget")
    sub.add_parser("telegram-login")
    a = p.parse_args()
    if a.cmd == "plan":
        asyncio.run(cmd_plan(a.description, a.model))
    elif a.cmd == "collect":
        asyncio.run(cmd_collect(a.slug))
    elif a.cmd == "telegram-login":
        from observer.collectors import telegram
        asyncio.run(telegram.login())
    elif a.cmd == "budget":
        print(f"Dépensé : {llm.spent():.4f} / plafond {llm.settings().llm_budget_usd} (reste {llm.remaining():.4f})")


if __name__ == "__main__":
    main()
