"""제목(및 초록)에서 작물·병원체·국가·보고유형을 자동 태깅한다."""
import html
import re

CROP_BINOMIALS = {"oryza sativa", "triticum aestivum", "triticum durum", "hordeum vulgare"}
VIRUS_RE = re.compile(
    r"\b((?:[A-Za-z]+ ){1,5}(?:virus|viroid))\b", re.IGNORECASE)
PHYTOPLASMA_RE = re.compile(r"\b(?:Candidatus\s+)?Phytoplasma(?:\s+[a-z]+)?\b")
VIRUS_STOPWORDS = {"of", "the", "a", "an", "and", "by", "caused", "causing", "on", "in",
                   "first", "report", "new", "infected", "infecting", "with", "novel"}


def strip_tags(text):
    """Crossref 제목의 <i>, <sub> 등 태그와 HTML 엔티티 제거."""
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def safe_title_html(text):
    """화면 표시용: 이탤릭(<i>)만 남기고 나머지 태그 제거."""
    if not text:
        return ""
    text = re.sub(r"<(/?)(?:[a-z]+:)?(?:i|em|italic)(?:\s[^>]*)?>", r"<\1i>", text, flags=re.I)
    text = re.sub(r"<(?!/?i>)[^>]+>", "", text)
    return re.sub(r"\s+", " ", text).strip()


class Tagger:
    def __init__(self, cfg):
        self.crops = {
            name: [re.compile(r"\b" + re.escape(k) + r"\b", re.I) for k in kws]
            for name, kws in cfg["crops"].items()
        }
        self.first_report = [re.compile(p, re.I) for p in cfg["first_report_patterns"]]
        self.seed = [re.compile(p, re.I) for p in cfg["seed_patterns"]]
        genera = "|".join(sorted(cfg["pathogen_genera"], key=len, reverse=True))
        # 속명 + (선택) 종소명/약어: "Fusarium luffae", "F. luffae"는 별도 처리
        self.genus_re = re.compile(
            r"\b(" + genera + r")(?:\s+(?!sp\b|spp\b)([a-z][a-z-]{2,}))?(?:\s+(spp?)\.)?")
        self.countries = {
            name: [re.compile(r"(?<![A-Za-z])" + re.escape(k) + r"(?![A-Za-z])", re.I) for k in kws]
            for name, kws in cfg["countries"].items()
        }
        self.neighbors = set(cfg.get("neighbor_countries", []))
        self.species_stop = {"causing", "and", "on", "in", "from", "associated", "isolated",
                             "species", "strains", "isolates", "the", "with", "as", "infecting"}

    # ---------- 개별 태거 ----------
    def tag_crops(self, text):
        return [name for name, pats in self.crops.items() if any(p.search(text) for p in pats)]

    def is_first_report(self, text):
        return any(p.search(text) for p in self.first_report)

    def is_seed(self, text):
        return any(p.search(text) for p in self.seed)

    def tag_pathogens(self, text):
        found = []
        for m in self.genus_re.finditer(text):
            genus, species, sp = m.group(1), m.group(2), m.group(3)
            if species and species.lower() not in self.species_stop:
                name = f"{genus} {species}"
            elif sp:
                name = f"{genus} {sp}."
            else:
                name = genus
            if name.lower() not in CROP_BINOMIALS:
                found.append(name)
        for m in VIRUS_RE.finditer(text):
            words = m.group(1).split()
            # 앞쪽 불용어 제거: "of rice stripe virus" → "rice stripe virus"
            while words and words[0].lower() in VIRUS_STOPWORDS:
                words.pop(0)
            if len(words) >= 2:
                found.append(" ".join(words))
        for m in PHYTOPLASMA_RE.finditer(text):
            found.append(m.group(0))
        # 같은 속의 "Fusarium"과 "Fusarium luffae"가 함께 잡히면 구체적인 쪽만 유지
        uniq = list(dict.fromkeys(found))
        return [n for n in uniq
                if not any(o != n and o.startswith(n + " ") for o in uniq)]

    def tag_countries(self, text):
        return [name for name, pats in self.countries.items() if any(p.search(text) for p in pats)]

    # ---------- 종합 ----------
    def tag(self, title, abstract=""):
        """제목은 국가·병원체·보고유형 판정, 초록은 작물·종자전염 보조 판정에만 사용."""
        t = strip_tags(title)
        full = t + " " + strip_tags(abstract)
        countries = self.tag_countries(t)
        return {
            "crops": self.tag_crops(full),
            "pathogens": self.tag_pathogens(t),
            "countries": countries,
            "first_report": self.is_first_report(t),
            "seed_borne": self.is_seed(full),
            "korea": "Korea" in countries,
            "neighbor": any(c in self.neighbors for c in countries),
        }

    @staticmethod
    def is_relevant(tags):
        """수집 기준: 대상 작물이면서 (신규보고 또는 종자전염)."""
        return bool(tags["crops"]) and (tags["first_report"] or tags["seed_borne"])
