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
    # 1년치 실수집에서 발견된 오탐 유형
    ("First Report of <i>Fusarium fujikuroi</i> Causing Wilt of Norway spruce Seedlings in Korea",
     "F. fujikuroi is the causal agent of bakanae disease of rice.",
     dict(relevant=False)),          # 작물은 초록이 아닌 제목으로만 판정
    ("Renal Trichodinosis in the Japanese Rice Fish, Oryzias latipes: First Report", "",
     dict(relevant=False)),
    ("Corrigendum to \"Seed-borne transmission of Pantoea in rice\"", "",
     dict(relevant=False)),
    ("Pathogenicity of <i>Bipolaris sorokiniana</i> isolates on barley",
     "Seed-borne inoculum was the main source.",
     dict(relevant=True, seed_borne=True)),   # 작물은 제목, 종자전염은 초록 허용
    # 1년치 점검에서 발견된 누락 유형 (실제 제목)
    ("Report on Rice Yellowing Syndrome Caused by Coinfection of Rice Grassy Stunt Virus and "
     "Rice Ragged Stunt Virus in Oryza sativa in the Philippines", "",
     dict(relevant=True, countries=["Philippines"])),
    ("Molecular Detection and Phylogenetic Analysis of Rice Hoja Blanca Virus Infecting Rice in Ecuador", "",
     dict(relevant=True, first_report=True, countries=["Ecuador"])),
    ("Identification of <i>Fusarium armeniacum</i> Causing Fusarium Head Blight and Crown Rot on "
     "Winter Wheat (<i>Triticum aestivum</i>) in China", "",
     dict(relevant=True, first_report=True, pathogens=["Fusarium armeniacum"])),
    ("Emergence of Southern Rice Black Streak Dwarf Virus in Sugarcane and Jungle Rice Reveals New Alternate Hosts", "",
     dict(relevant=True, first_report=True)),
    ("Transmission of <i>Xanthomonas translucens</i> Associated with Wheat and Barley Seed", "",
     dict(relevant=True, seed_borne=True)),
    ("Identification of sources of Fusarium head blight resistance in Ethiopian wheat cultivars", "",
     dict(relevant=False)),   # 국가명이 아닌 형용사(Ethiopian) → 발생보고 아님
    ("First Report of <i>Calonectria</i> Causing Damping-off of Soybean Seedlings in Korea", "",
     dict(relevant=False)),   # seedling ≠ seed, 대상 작물 아님
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
