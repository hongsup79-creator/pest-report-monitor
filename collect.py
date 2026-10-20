"""병해충 신규 보고 수집기 — Crossref(저널별) + PubMed(키워드) → data/items.json

사용 예:
  python collect.py                 # 최근 7일 수집 (매일 실행용, 겹치는 기간은 자동 중복 제거)
  python collect.py --days 365      # 최근 1년 초기 수집(backfill)
  python collect.py --since 2025-01-01 --until 2025-12-31

환경변수(선택):
  CONTACT_EMAIL   Crossref·PubMed 예절상 연락처 (권장)
  NCBI_API_KEY    PubMed 요청 한도 상향용
"""
import argparse
import datetime as dt
import json
import os
import sys
import time
from pathlib import Path

import requests

from tagger import Tagger, safe_title_html, strip_tags

ROOT = Path(__file__).parent
CFG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
DATA_FILE = ROOT / "data" / "items.json"
EMAIL = os.environ.get("CONTACT_EMAIL", "")
NCBI_KEY = os.environ.get("NCBI_API_KEY", "")
UA = f"pest-report-monitor/1.0 (mailto:{EMAIL})" if EMAIL else "pest-report-monitor/1.0"

STATS = {"fetched": {}, "crossref_total": {}, "errors": []}   # 실행 기록(run_stats.json)

session = requests.Session()
session.headers["User-Agent"] = UA


def get_json(url, params, retries=3):
    for attempt in range(retries):
        try:
            r = session.get(url, params=params, timeout=60)
            if r.status_code == 429 or r.status_code >= 500:
                raise requests.HTTPError(f"HTTP {r.status_code}")
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError) as e:
            if attempt == retries - 1:
                print(f"  ! 요청 실패: {url} ({e})", file=sys.stderr)
                return None
            time.sleep(5 * (attempt + 1))


# ---------------------------------------------------------------- Crossref
def date_from_parts(obj):
    try:
        p = obj["date-parts"][0]
        return f"{p[0]:04d}-{(p[1] if len(p) > 1 else 1):02d}-{(p[2] if len(p) > 2 else 1):02d}"
    except (KeyError, IndexError, TypeError):
        return None


def parse_crossref(w, journal):
    titles = [t for t in (w.get("title") or []) + (w.get("original-title") or []) if t]
    title = titles[0] if titles else ""
    authors = w.get("author") or []
    first = (authors[0].get("family") or authors[0].get("name", "")) if authors else ""
    return {
        "doi": (w.get("DOI") or "").lower(),
        "pmid": None,
        "title_raw": title,
        "title_alt": " / ".join(dict.fromkeys(titles[1:])),   # 국내 학회지의 영문·한글 병기 제목
        "abstract": w.get("abstract", ""),
        "journal": journal,
        "date": date_from_parts(w.get("published-online") or w.get("published-print")
                                or w.get("published") or w.get("created") or {}),
        "first_author": first,
        "n_authors": len(authors),
        "source": "crossref",
    }


def fetch_crossref(since, until):
    out = []
    for journal, issns in CFG["crossref_journals"].items():
        seen = set()
        for issn in issns:
            cursor, n = "*", 0
            while cursor:
                params = {
                    "filter": f"from-created-date:{since},until-created-date:{until},type:journal-article",
                    "rows": 1000, "cursor": cursor,
                    "select": "DOI,title,original-title,abstract,author,published,published-online,published-print,created",
                }
                if EMAIL:
                    params["mailto"] = EMAIL
                js = get_json(f"https://api.crossref.org/journals/{issn}/works", params)
                if not js:
                    STATS["errors"].append(f"Crossref {journal} ({issn})")
                    break
                if cursor == "*":
                    STATS["crossref_total"][f"{journal} ({issn})"] = js["message"].get("total-results")
                items = js["message"].get("items", [])
                for w in items:
                    doi = (w.get("DOI") or "").lower()
                    if doi and doi not in seen:
                        seen.add(doi)
                        out.append(parse_crossref(w, journal))
                n += len(items)
                cursor = js["message"].get("next-cursor") if items else None
                time.sleep(0.3)
        print(f"  Crossref {journal}: {len(seen)}건")
        STATS["fetched"][journal] = len(seen)
    return out


# ---------------------------------------------------------------- PubMed
def fetch_pubmed(since, until):
    base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
    common = {"db": "pubmed", "retmode": "json", "tool": "pest-report-monitor"}
    if EMAIL:
        common["email"] = EMAIL
    if NCBI_KEY:
        common["api_key"] = NCBI_KEY
    js = get_json(base + "esearch.fcgi", {
        **common, "term": CFG["pubmed_query"], "datetype": "edat",
        "mindate": since.replace("-", "/"), "maxdate": until.replace("-", "/"), "retmax": 5000,
    })
    if not js:
        STATS["errors"].append("PubMed esearch")
    ids = js["esearchresult"]["idlist"] if js else []
    out = []
    for i in range(0, len(ids), 200):
        chunk = ids[i:i + 200]
        sj = get_json(base + "esummary.fcgi", {**common, "id": ",".join(chunk)})
        time.sleep(0.4)
        if not sj:
            continue
        for uid in sj["result"].get("uids", []):
            r = sj["result"][uid]
            doi = next((a["value"].lower() for a in r.get("articleids", [])
                        if a.get("idtype") == "doi"), "")
            sort = r.get("sortpubdate", "")[:10].replace("/", "-")
            authors = r.get("authors") or []
            out.append({
                "doi": doi, "pmid": uid,
                "title_raw": r.get("title", ""), "abstract": "",
                "journal": r.get("fulljournalname") or r.get("source", ""),
                "date": sort or None,
                "first_author": authors[0]["name"].split()[0] if authors else "",
                "n_authors": len(authors),
                "source": "pubmed",
            })
    print(f"  PubMed: {len(out)}건")
    STATS["fetched"]["PubMed"] = len(out)
    return out


# ---------------------------------------------------------------- 병합·저장
def build_item(rec, tagger):
    alt = rec.get("title_alt", "")
    tags = tagger.tag(rec["title_raw"] + (" / " + alt if alt else ""), rec["abstract"])
    if not Tagger.is_relevant(tags):
        return None
    tags.pop("excluded")
    tags["domestic_source"] = rec["journal"] in CFG.get("domestic_journals", [])
    # 국내 학회지에서 나라 이름이 없는 제목(예: "...in Haenam")은 국내 연구로 판단
    if tags["domestic_source"] and not tags["countries"]:
        tags["countries"], tags["korea"] = ["Korea"], True
    key = rec["doi"] or f"pmid:{rec['pmid']}"
    authors = rec["first_author"] + (" et al." if rec["n_authors"] > 1 else "")
    return {
        "id": key,
        "doi": rec["doi"] or None,
        "pmid": rec["pmid"],
        "title": strip_tags(rec["title_raw"]),
        "title_html": safe_title_html(rec["title_raw"]),
        "title_alt": strip_tags(alt) or None,
        "journal": rec["journal"],
        "date": rec["date"],
        "authors": authors.strip(),
        "url": f"https://doi.org/{rec['doi']}" if rec["doi"]
               else f"https://pubmed.ncbi.nlm.nih.gov/{rec['pmid']}/",
        "sources": [rec["source"]],
        **tags,
        "domestic_status": None,   # 4단계(국내 기록 대조)에서 채움
    }
    # 초록은 태깅에만 쓰고 저장하지 않음(저작권)


def merge(existing, new_items, today):
    by_id = {it["id"]: it for it in existing}
    added = 0
    for it in new_items:
        old = by_id.get(it["id"])
        if old:
            old["sources"] = sorted(set(old["sources"]) | set(it["sources"]))
            old["pmid"] = old["pmid"] or it["pmid"]
            for k in ("crops", "pathogens", "countries"):
                old[k] = list(dict.fromkeys(old[k] + it[k]))
            for k in ("first_report", "seed_borne", "korea", "neighbor", "watch", "domestic_source"):
                old[k] = old[k] or it[k]
        else:
            it["first_seen"] = today
            by_id[it["id"]] = it
            added += 1
    items = sorted(by_id.values(), key=lambda x: (x["date"] or "", x["id"]), reverse=True)
    return items, added


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--since")
    ap.add_argument("--until")
    ap.add_argument("--no-pubmed", action="store_true")
    ap.add_argument("--rebuild", action="store_true",
                    help="기존 누적 데이터를 버리고 새로 구성(설정·태깅 규칙 변경 후 사용)")
    args = ap.parse_args()

    today = dt.date.today()
    until = args.until or today.isoformat()
    since = args.since or (today - dt.timedelta(days=args.days)).isoformat()
    print(f"수집 기간: {since} ~ {until}")

    raw = fetch_crossref(since, until)
    if not args.no_pubmed:
        raw += fetch_pubmed(since, until)

    tagger = Tagger(CFG)
    # 같은 DOI가 두 소스에 있으면 하나로 합침 (merge 단계에서 처리)
    candidates = [it for it in (build_item(r, tagger) for r in raw) if it]

    existing = []
    if DATA_FILE.exists() and not args.rebuild:
        existing = json.loads(DATA_FILE.read_text(encoding="utf-8")).get("items", [])
    items, added = merge(existing, candidates, today.isoformat())

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    DATA_FILE.parent.mkdir(exist_ok=True)
    DATA_FILE.write_text(json.dumps({
        "updated": now, "count": len(items), "items": items,
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    # 키워드 점검용: 아깝게 빠진 제목(신규보고·종자전염이지만 대상 작물 미검출 / 대상 작물+병원체지만 보고유형 미검출)
    kept = {it["id"] for it in candidates}
    review = {"missing_crop": [], "missing_report_type": []}
    for r in raw:
        key = r["doi"] or f"pmid:{r['pmid']}"
        if key in kept:
            continue
        full_title = r["title_raw"] + (" / " + r["title_alt"] if r.get("title_alt") else "")
        t = tagger.tag(full_title)
        row = {"date": r["date"], "journal": r["journal"], "title": strip_tags(full_title)}
        if (t["first_report"] or t["seed_borne"]) and not t["crops"]:
            review["missing_crop"].append(row)
        elif t["crops"] and t["pathogens"] and not t["excluded"]:
            review["missing_report_type"].append(row)
    (DATA_FILE.parent / "review.json").write_text(
        json.dumps(review, ensure_ascii=False, indent=1), encoding="utf-8")

    STATS.update(updated=now, period=[since, until], raw=len(raw),
                 relevant=len(candidates), added=added, total=len(items),
                 review_counts={k: len(v) for k, v in review.items()})
    (DATA_FILE.parent / "run_stats.json").write_text(
        json.dumps(STATS, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"원자료 {len(raw)}건 → 해당 {len(candidates)}건 → 신규 추가 {added}건 (누적 {len(items)}건)")


if __name__ == "__main__":
    main()
