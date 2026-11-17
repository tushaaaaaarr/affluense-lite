"""The 'orchestrator'. It's just a normal function that calls the agents in order.

Decision points (what decides what runs next):
  - no relevant text found in a source        -> skip extraction for that source
  - budget cap hit mid-run                    -> stop calling the model, finish with what we have
  - person is an organisation                 -> goes to a separate "institutions" list, no brief
  - amount can't be estimated                 -> still listed, but ranks low
  - --follow flags                            -> ledger check / web leads for the top few people
"""
import time

from engine.shared import config, costlog
from engine.steps import (briefer, estimator, extractor, fetcher, followon, ranker,
                          resolver)


def _drop_note(url, d):
    who = d.get("name") or "(no name)"
    kept = " (person kept, field removed)" if d.get("kept_person") else ""
    return f"{who}{kept}: {'; '.join(d.get('why') or [])} [{url}]"


def _source(src):
    """A source is a URL string, or {"url": public link, "file": local copy} when the site
    blocks downloads. We read the file but always cite the public URL."""
    if isinstance(src, dict):
        return src.get("file") or src["url"], src["url"]
    return src, src


def run_event(spec, follow_web=False):
    name = spec["name"]
    costlog.new_run()
    t0 = time.time()
    notes = []                       # things that went wrong, shown in the report

    # --- 1. fetch + extract from every source ---------------------------------------------
    all_people, event_info = [], {}
    docs = []                        # (read_from, cite_url) after opening filing pages
    for src in spec["sources"]:
        read_from, url = _source(src)
        if url.upper().startswith("TODO"):
            notes.append(f"skipped placeholder source: {url}")
            continue
        if read_from != url:
            docs.append((read_from, url))
            continue
        try:
            found = fetcher.expand(url)
        except Exception:
            found = [url]                # get_text below will report the real error
        if found != [url]:
            print(f"[fetch]    {url} is a filing page -> {len(found)} document(s)")
        docs += [(u, u) for u in found]

    for read_from, url in docs:
        try:
            text = fetcher.get_text(read_from)
        except Exception as e:
            notes.append(f"could not fetch {url}: {e}")
            print(f"[fetch]    FAILED {url}: {e}")
            continue
        print(f"[fetch]    {url} -> {len(text):,} chars")
        try:
            res = extractor.extract(url, text, name)
        except costlog.BudgetError as e:
            notes.append(str(e))
            break
        except Exception as e:             # model/API error: skip this source, keep the rest
            notes.append(f"extraction failed for {url}: {e}")
            print(f"[extract]  FAILED {url}: {e}")
            continue
        print(f"[extract]  kept {len(res['people'])} people, dropped {len(res['dropped'])} facts "
              f"(cost so far ${costlog.spent(name):.4f})")
        ev = res["event"]
        # first source that gives a field wins; remember which source so the figure has a link
        if event_info.get("price_low") is None and ev.get("price_low") is not None:
            event_info.update(price_low=ev["price_low"], price_high=ev["price_high"],
                              price_quote=ev["price_quote"], price_url=url)
        if event_info.get("date") is None and ev.get("date"):
            event_info.update(date=ev["date"], date_quote=ev["date_quote"], date_url=url)
        for k in ("company", "kind"):
            if event_info.get(k) is None and ev.get(k):
                event_info[k] = ev[k]
        all_people.extend(res["people"])
        for d in res["dropped"]:
            notes.append(_drop_note(url, d))

    # --- 2. match names ---------------------------------------------------------------------
    people = resolver.merge(all_people)
    for p in people:
        p["is_org"] = resolver.is_org(p["name"])
    unsure = sum(1 for p in people if p["possible_matches"])
    print(f"[match]    {len(all_people)} mentions -> {len(people)} people/orgs, {unsure} unsure name matches")

    # --- 3. amounts, timing, confidence (all plain code) ------------------------------------
    for p in people:
        p["amount"] = estimator.estimate_amount(p, event_info)
        p["timing"] = estimator.estimate_timing(p, event_info)
        n_sources = len({e["url"] for e in p["evidence"]})
        p["confidence"], p["confidence_why"] = ranker.confidence(p, n_sources)

    # --- 4. follow-on leads -------------------------------------------------------------------
    for p in people:                                   # ledger is free, so check everyone
        p["earlier_events"] = followon.ledger_hits(p, name)
    if follow_web:
        people.sort(key=lambda p: (p["amount"]["high"] or 0), reverse=True)
        for p in [x for x in people if not x["is_org"]][:config.FOLLOW_MAX_PEOPLE]:
            try:
                urls = followon.web_leads(p, name, depth=0)
            except costlog.BudgetError as e:
                notes.append(str(e))
                break
            except Exception as e:
                notes.append(f"web search for {p['name']} failed: {e}")
                continue
            p["lead_urls"] = urls
            for u in urls:
                try:
                    # charged to THIS event so the $ cap and the totals include it
                    res = extractor.extract(u, fetcher.get_text(u), "any earlier deal",
                                            cost_event=name, stage="followon_extract")
                except costlog.BudgetError as e:
                    notes.append(str(e))
                    break
                except Exception as e:
                    notes.append(f"follow-on {u} failed: {e}")
                    continue
                # kept apart from p["evidence"]: these facts are about a DIFFERENT deal
                for q in res["people"]:
                    if resolver.compare(q["name"], p["name"]) == "same":
                        p.setdefault("follow_on", []).extend(q["evidence"])
    followon.remember(name, people)
    print(f"[follow]   ledger hits for {sum(1 for p in people if p['earlier_events'])} people"
          + (", web leads checked for top people" if follow_web else ""))

    # --- 5. rank + brief ------------------------------------------------------------------------
    persons = [p for p in people if not p["is_org"]]
    orgs = [p for p in people if p["is_org"]]
    for p in persons + orgs:
        p["score"] = ranker.rank_score(p)
    persons.sort(key=lambda p: p["score"], reverse=True)
    orgs.sort(key=lambda p: p["score"], reverse=True)

    results, brief_notes = briefer.write_briefs(persons, name)
    for p, (text, how) in zip(persons, results):
        p["brief"], p["brief_by"] = text, how
    notes += brief_notes

    wall = round(time.time() - t0, 1)
    print(f"[brief]    {len(persons)} briefs written, total cost ${costlog.spent(name):.4f}")
    costlog.log_run(name, wall, len(persons))
    return {"event": name, "event_info": event_info, "people": persons, "institutions": orgs,
            "notes": notes, "cost": costlog.summary(name), "per_person": costlog.per_person(name),
            "wall_seconds": wall}
