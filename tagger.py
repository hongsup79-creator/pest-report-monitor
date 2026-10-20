"""제목(및 초록)에서 작물·병원체·국가·보고유형을 자동 태깅한다."""
import html
import re

CROP_BINOMIALS = {"oryza sativa", "triticum aestivum", "triticum durum", "hordeum vulgare"}
HANGUL = re.compile(r"[가-힣]")
HYPHENS ="‐‑‒–—"
VIRUS_RE = re.compile(
    r"\b((?:[A-Za-z][A-Za-z-]* ){1,6}(?:virus|viroid))\b", re.IGNORECASE)
PHYTOPLASMA_RE = re.compile(r"\b(?:Candidatus\s+)?Phytoplasma(?:\s+[a-z]+)?\b")
# 바이러스명은 'virus' 앞에서부터 거꾸로 읽다가 이 단어를 만나면 멈춤
VIRUS_STOPWORDS = {"of", "the", "a", "an", "and", "by", "caused", "causing", "on", "in",
                   "first", "report", "new", "infected", "infecting", "with", "novel",
                   "characterization", "characterisation", "detection", "identification",
                   "occurrence", "emergence", "analysis", "molecular", "record", "from",
                   "to", "for", "as", "is", "are", "natural", "naturally", "mixed", "coinfection"}


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
        # 한글 제목용 규칙(정규식 그대로 사용)
        for name, pats in cfg.get("crops_ko", {}).items():
            self.crops.setdefault(name, []).extend(re.compile(p) for p in pats)
        self.first_report = [re.compile(p, re.I) for p in
                             cfg["first_report_patterns"] + cfg.get("first_report_patterns_ko", [])]
        self.seed = [re.compile(p, re.I) for p in cfg["seed_patterns"]]
        self.exclude = [re.compile(p, re.I) for p in cfg.get("exclude_patterns", [])]
        self.occ_start = [re.compile(p, re.I) for p in cfg.get("occurrence_start_patterns", [])]
        self.seed_title = [re.compile(p, re.I) for p in
                           cfg.get("seed_title_patterns", []) + cfg.get("seed_patterns_ko", [])]
        self.korea_ko = [re.compile(p) for p in cfg.get("korea_ko", [])]
        self.occ_any = [re.compile(p, re.I) for p in cfg.get("occurrence_patterns", [])]
        self.watch = [re.compile(r"\b" + re.escape(n).replace(r"\ ", r"\s+") + r"\b", re.I)
                      for n in cfg.get("watch_pathogens", [])]
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
        vtext = text.translate({ord(h): "-" for h in HYPHENS})
        for m in VIRUS_RE.finditer(vtext):
            words = m.group(1).split()
            # 뒤에서부터 불용어 직전까지만 사용: "Report of Rice Stripe Virus" → "Rice Stripe Virus"
            keep = []
            for w in reversed(words):
                if w.lower() in VIRUS_STOPWORDS:
                    break
                keep.insert(0, w)
            if len(keep) >= 2:
                found.append(" ".join(keep))
        for m in PHYTOPLASMA_RE.finditer(text):
            found.append(m.group(0))
        # 같은 속의 "Fusarium"과 "Fusarium luffae"가 함께 잡히면 구체적인 쪽만 유지
        uniq = list(dict.fromkeys(found))
        return [n for n in uniq
                if not any(o != n and o.startswith(n + " ") for o in uniq)]

    def tag_countries(self, text):
        found = [name for name, pats in self.countries.items() if any(p.search(text) for p in pats)]
        # 한글 제목: '국내·한국'이 있거나, 다른 나라가 없으면 국내 연구로 판단
        if HANGUL.search(text) and "Korea" not in found and (
                any(p.search(text) for p in self.korea_ko) or not found):
            found.insert(0, "Korea")
        return found

    # ---------- 종합 ----------
    def tag(self, title, abstract=""):
        """작물·국가·병원체·신규보고는 제목으로만 판정(초록 언급에 의한 오탐 방지).
        종자전염 여부만 초록까지 확인."""
        t = strip_tags(title)
        full = t + " " + strip_tags(abstract)
        countries = self.tag_countries(t)
        first = self.is_first_report(t) or (
            bool(countries) and any(p.search(t) for p in self.occ_start + self.occ_any))
        seed = self.is_seed(full) or any(p.search(t) for p in self.seed_title)
        return {
            "excluded": any(p.search(t) for p in self.exclude),
            "watch": any(p.search(t) for p in self.watch),
            "crops": self.tag_crops(t),
            "pathogens": self.tag_pathogens(t),
            "countries": countries,
            "first_report": first,
            "seed_borne": seed,
            "korea": "Korea" in countries,
            "neighbor": any(c in self.neighbors for c in countries),
        }

    @staticmethod
    def is_relevant(tags):
        """수집 기준: 대상 작물이면서 (신규보고 또는 종자전염)."""
        """수집 기준: (대상 작물 또는 관심 병원체) + (신규·발생보고 또는 종자 관련)."""
        return (not tags["excluded"]) and (bool(tags["crops"]) or tags["watch"]) and (
            tags["first_report"] or tags["seed_borne"])
