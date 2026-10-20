"""태깅 정확도 점검용 시험 사례 (오프라인). 실행: python -m pytest -q tests/"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tagger import Tagger, strip_tags, safe_title_html  # noqa: E402

T = Tagger(json.loads((ROOT / "config.json").read_text(encoding="utf-8")))

# (제목, 초록, 기대 결과) — 기대값에 적은 항목만 검사
CASES = [
    ("First Report of <i>Fusarium luffae</i> Causing Bakanae Disease on Rice in Korea", "",
     dict(relevant=True, crops=["벼"], pathogens=["Fusarium luffae"], countries=["Korea"],
          korea=True, first_report=True)),
    ("First report of <i>Pantoea dispersa</i> causing bacterial leaf blight of rice (<i>Oryza sativa</i>) in China", "",
     dict(relevant=True, pathogens=["Pantoea dispersa"], countries=["China"], neighbor=True)),
    ("First Report of Rice Stripe Virus Infecting Wheat in Japan", "",
     dict(relevant=True, crops=["벼", "밀"], pathogens=["Rice Stripe Virus"], countries=["Japan"])),
    ("Seed-borne <i>Bipolaris oryzae</i> reduces germination of rice seed lots in Bangladesh", "",
     dict(relevant=True, seed_borne=True, first_report=False, pathogens=["Bipolaris oryzae"],
          countries=["Bangladesh"])),
    ("First Report of <i>Microdochium nivale</i> Causing Seedling Blight on Barley in Kansas", "",
     dict(relevant=True, crops=["보리"], countries=["USA"])),
    ("A new disease of durum wheat caused by <i>Fusarium</i> spp. in Tunisia", "",
     dict(relevant=True, crops=["밀"], pathogens=["Fusarium spp."], countries=["Tunisia"])),
    ("Occurrence of <i>Tilletia indica</i> on wheat", "Seed transmission was confirmed by grow-out tests.",
     dict(relevant=True, seed_borne=True)),
    # --- 걸러져야 하는 사례 (오탐 방지) ---
    ("Genome-wide association study of Fusarium head blight resistance in wheat", "",
     dict(relevant=False)),
    ("<i>Pseudomonas fluorescens</i> as a biocontrol agent against rice blast", "",
     dict(relevant=False)),
    ("First report of <i>Colletotrichum siamense</i> causing anthracnose on mango in India", "",
     dict(relevant=False)),          # 대상 작물 아님
    ("Effects of commodity price shocks on wheat trade", "", dict(relevant=False)),
    ("First report of tomato brown rugose fruit virus in Indiana greenhouses", "",
     dict(relevant=False, countries=[])),   # Indiana ≠ India
]


def test_cases():
    fails = []
    for title, abstract, exp in CASES:
        tags = T.tag(title, abstract)
        got = dict(tags, relevant=Tagger.is_relevant(tags))
        for k, v in exp.items():
            if got[k] != v:
                fails.append(f"{strip_tags(title)[:60]}…\n    {k}: 기대 {v} / 결과 {got[k]}")
    assert not fails, "\n".join(fails)


def test_html_cleanup():
    raw = '<jats:title>First report of <jats:italic>Fusarium</jats:italic> &amp; rice</jats:title>'
    assert strip_tags(raw) == "First report of Fusarium & rice"
    assert safe_title_html('A <i>B</i> <b>C</b> <script>x</script>') == "A <i>B</i> C x"
