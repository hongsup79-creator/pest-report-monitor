# 벼·맥류 병해충 국내외 신규보고 모니터

벼·맥류의 국내외 신규 병해충 발생보고와 종자 관련 논문을 매일 자동 수집합니다.

- **수집원**: Crossref(국내외 식물병리·곤충 학술지 12종: 해외 9종 + 식물병연구·Mycobiology·한국응용곤충학회지) + PubMed(키워드 검색)
- **수집 기준**: 대상 작물(벼·밀·보리) + (신규보고 또는 종자전염)
- **자동 태깅**: 작물 / 병원체 / 국가 / 신규보고 / 종자전염 / 국내·인접국 여부
- **저장**: `data/items.json` (제목·서지정보·링크만 저장, 초록은 저장하지 않음)

## 파일 구성

| 파일 | 역할 |
|---|---|
| `config.json` | 작물·저널·키워드·국가 사전 (범위를 바꿀 때 이 파일만 수정) |
| `tagger.py` | 제목에서 작물·병원체·국가·보고유형 태깅 |
| `collect.py` | 수집·병합·저장 |
| `tests/test_tagger.py` | 태깅 정확도 시험 사례 |
| `.github/workflows/collect.yml` | 매일 06:17(KST) 자동 실행 |

## 수동 실행

Actions 탭 → **병해충 신규보고 수집** → **Run workflow** → 기간(일) 입력.
초기에는 `365`로 1년치를 수집합니다.

## 선택 설정 (Settings → Secrets and variables → Actions)

- `CONTACT_EMAIL`: Crossref·PubMed에 전달하는 연락처 (권장)
- `NCBI_API_KEY`: PubMed 요청 한도 상향용
