#!/usr/bin/env python3
"""Build + install real Graph Hub cartridges: a niche EXPERT graph and an agent PERSONA graph.

Demonstrates the Graph Hub's purpose — inject domain-specialist subgraphs and agent-character
graphs the base engine doesn't have. Produces valid .graphpack cartridges (make_graph_cartridge
schema), installs them via the real installer, and verifies. Read/write is local, gated behind
the installer's schema + entitlement checks (both are 'free' here).
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from packages.graph_hub.cartridge_format import make_graph_cartridge, validate_cartridge_schema, write_cartridge  # noqa: E402
from packages.graph_hub.installer import install_cartridge_from_path, list_installed_cartridges    # noqa: E402
from packages.graph_hub.attachment import attach_cartridge                                          # noqa: E402
from packages.graph_hub.sandbox_trial import start_sandbox_trial, run_sandbox_trial_query          # noqa: E402
from packages.graph_hub.registry import refresh_local_catalog                                       # noqa: E402

# Write to exported/ so refresh_local_catalog() surfaces them in the Graph Hub catalog grid
# (it scans samples + exported/, not authored/). author.verified defaults True -> "Verified".
OUT = REPO_ROOT / "data" / "graph_hub" / "exported"


def _n(nid, label, aliases=None, desc=None):
    return {"id": nid, "label": label, "aliases": aliases or [], "short_description": desc or ""}


def _e(s, r, t):
    return {"source": s, "relation": r, "target": t, "confidence": 0.9}


def coffee_expert() -> dict:
    nodes = [
        _n("coffee", "커피", ["coffee"], "볶은 커피 원두를 우려낸 음료."),
        _n("espresso", "에스프레소", ["espresso"], "곱게 간 원두에 고압의 물을 통과시켜 추출한 진한 커피."),
        _n("arabica", "아라비카", ["arabica"], "향미가 풍부한 대표 커피 품종."),
        _n("robusta", "로부스타", ["robusta"], "카페인이 높고 쓴맛이 강한 커피 품종."),
        _n("bean", "원두", ["coffee bean"], "커피나무 열매의 씨앗을 볶은 것."),
        _n("roasting", "로스팅", ["roasting", "배전"], "생두를 볶아 향미를 끌어내는 과정."),
        _n("drip", "드립커피", ["drip", "핸드드립"], "물을 원두에 부어 여과 추출하는 방식."),
        _n("coldbrew", "콜드브루", ["cold brew"], "찬물로 장시간 우려낸 커피."),
        _n("caffeine", "카페인", ["caffeine"], "각성 효과가 있는 알칼로이드."),
        _n("crema", "크레마", ["crema"], "에스프레소 위에 형성되는 황금빛 거품층."),
        _n("latte", "라떼", ["latte", "카페라떼"], "에스프레소에 데운 우유를 섞은 음료."),
        _n("barista", "바리스타", ["barista"], "커피를 전문적으로 추출하는 사람."),
    ]
    edges = [
        _e("espresso", "is_a", "coffee"), _e("drip", "is_a", "coffee"), _e("coldbrew", "is_a", "coffee"),
        _e("arabica", "is_a", "bean"), _e("robusta", "is_a", "bean"),
        _e("bean", "produced_by", "roasting"), _e("coffee", "contains", "caffeine"),
        _e("robusta", "has_more", "caffeine"), _e("espresso", "has", "crema"),
        _e("latte", "contains", "espresso"), _e("barista", "makes", "espresso"),
    ]
    return make_graph_cartridge(
        cartridge_id="expert.coffee.ko.v1", name="커피 전문 그래프",
        subtitle="원두·추출·품종의 니치 전문 지식 그래프",
        description="에스프레소/드립/콜드브루, 아라비카/로부스타, 로스팅·크레마 등 커피 도메인 전문 개념과 관계.",
        category="food_drink", pricing={"model": "free"}, tags=["coffee", "expert", "niche", "ko"],
        contents={
            "semantic_graph": {"nodes": nodes, "edges": edges},
            "surface_graph": {"constructions": [], "discourse_moves": [], "lemma_choices": [], "style_profiles": []},
            "reasoning_patterns": [{"id": "domain_specialist_lookup", "name": "커피 도메인 개념·관계 우선 조회"}],
        },
        provenance={"source_type": "authored_expert_graph", "domain": "coffee", "authored": True},
        permissions={"write_local_brain": False, "attach_to_working_memory": True, "export_allowed": True},
        safety={"default_read_only": True, "requires_user_approval_for_local_write": True, "risk_level": "low"},
    )


def socratic_persona() -> dict:
    # A persona graph = the agent's CHARACTER as a graph: a persona root + trait + style nodes.
    nodes = [
        _n("persona.socratic", "소크라테스식 교사", ["socratic teacher"], "답을 직접 주기보다 질문으로 스스로 깨닫게 이끄는 교사 페르소나."),
        _n("trait.inquiry", "질문 중심", [], "단정 대신 되묻기로 사고를 유도한다."),
        _n("trait.humility", "지적 겸손", [], "모르는 것은 모른다고 인정한다 (무지의 지)."),
        _n("trait.patience", "인내", [], "학습자의 속도에 맞춰 단계적으로."),
        _n("trait.clarity", "명료함", [], "군더더기 없이 핵심을 짚는다."),
        _n("style.counter_question", "반문", [], "학습자의 주장에 반례·되물음을 던진다."),
        _n("style.stepwise", "단계적 유도", [], "작은 합의를 쌓아 결론으로."),
        _n("value.honesty", "정직", [], "근거 없는 단정은 하지 않는다 — abstain과 정합."),
    ]
    edges = [
        _e("persona.socratic", "has_trait", "trait.inquiry"),
        _e("persona.socratic", "has_trait", "trait.humility"),
        _e("persona.socratic", "has_trait", "trait.patience"),
        _e("persona.socratic", "has_trait", "trait.clarity"),
        _e("persona.socratic", "uses_style", "style.counter_question"),
        _e("persona.socratic", "uses_style", "style.stepwise"),
        _e("persona.socratic", "upholds", "value.honesty"),
        _e("trait.inquiry", "expressed_as", "style.counter_question"),
    ]
    return make_graph_cartridge(
        cartridge_id="persona.socratic.ko.v1", name="소크라테스식 교사 페르소나",
        subtitle="질문으로 이끄는 에이전트 성격 그래프",
        description="에이전트의 성격을 그래프로: 질문중심·지적겸손·인내·명료 트레잇과 반문·단계적유도 스타일, 정직 가치.",
        category="persona", pricing={"model": "free"}, tags=["persona", "agent", "teacher", "ko"],
        contents={
            "semantic_graph": {"nodes": nodes, "edges": edges},
            "surface_graph": {"constructions": [], "discourse_moves": ["counter_question", "stepwise_guide"],
                              "lemma_choices": [], "style_profiles": [{"id": "socratic", "tone": "inquisitive_humble"}]},
            "reasoning_patterns": [{"id": "socratic_elicitation", "name": "직답 대신 질문으로 유도"}],
        },
        provenance={"source_type": "authored_persona_graph", "persona": "socratic_teacher", "authored": True},
        permissions={"write_local_brain": False, "attach_to_working_memory": True, "export_allowed": True},
        safety={"default_read_only": True, "requires_user_approval_for_local_write": True, "risk_level": "low"},
    )


def analyst_persona() -> dict:
    # A DIFFERENT persona -> a different tone, proving the realization is graph-driven.
    nodes = [
        _n("persona.analyst", "냉철한 분석가", ["analyst"], "결론과 핵심을 먼저 제시하고 근거로 뒷받침하는 분석가 페르소나."),
        _n("trait.direct", "직설", [], "결론부터 명확히 제시한다."),
        _n("trait.rigor", "엄밀", [], "근거와 조건을 분명히 한다."),
        _n("value.honesty2", "정직", [], "근거 없는 단정은 하지 않는다."),
    ]
    edges = [
        _e("persona.analyst", "has_trait", "trait.direct"),
        _e("persona.analyst", "has_trait", "trait.rigor"),
        _e("persona.analyst", "upholds", "value.honesty2"),
    ]
    return make_graph_cartridge(
        cartridge_id="persona.analyst.ko.v1", name="냉철한 분석가 페르소나",
        subtitle="결론-우선 분석가 성격 그래프",
        description="에이전트 성격: 직설·엄밀 트레잇, 결론부터 제시하는 analytical_direct 톤, 정직 가치.",
        category="persona", pricing={"model": "free"}, tags=["persona", "agent", "analyst", "ko"],
        contents={
            "semantic_graph": {"nodes": nodes, "edges": edges},
            "surface_graph": {"constructions": [], "discourse_moves": [],
                              "lemma_choices": [], "style_profiles": [{"id": "analyst", "tone": "analytical_direct"}]},
            "reasoning_patterns": [{"id": "conclusion_first", "name": "결론 먼저, 근거 뒤"}],
        },
        provenance={"source_type": "authored_persona_graph", "persona": "analyst", "authored": True},
        permissions={"write_local_brain": False, "attach_to_working_memory": True, "export_allowed": True},
        safety={"default_read_only": True, "requires_user_approval_for_local_write": True, "risk_level": "low"},
    )


def _expert(cartridge_id, name, subtitle, description, category, domain, tags, nodes, edges) -> dict:
    return make_graph_cartridge(
        cartridge_id=cartridge_id, name=name, subtitle=subtitle, description=description,
        category=category, pricing={"model": "free"}, tags=tags,
        contents={
            "semantic_graph": {"nodes": nodes, "edges": edges},
            "surface_graph": {"constructions": [], "discourse_moves": [], "lemma_choices": [], "style_profiles": []},
            "reasoning_patterns": [{"id": "domain_specialist_lookup", "name": f"{domain} 도메인 개념·관계 우선 조회"}],
        },
        provenance={"source_type": "authored_expert_graph", "domain": domain, "authored": True},
        permissions={"write_local_brain": False, "attach_to_working_memory": True, "export_allowed": True},
        safety={"default_read_only": True, "requires_user_approval_for_local_write": True, "risk_level": "low"},
    )


def astronomy_expert() -> dict:
    nodes = [
        _n("solar_system", "태양계", ["solar system"], "태양과 그 중력에 묶인 천체들의 계."),
        _n("sun", "태양", ["sun"], "태양계 중심의 항성."),
        _n("star", "항성", ["star"], "핵융합으로 스스로 빛을 내는 천체."),
        _n("planet", "행성", ["planet"], "항성을 도는 큰 천체."),
        _n("earth", "지구", ["earth"], "생명이 사는 세 번째 행성."),
        _n("mars", "화성", ["mars"], "붉은 네 번째 행성."),
        _n("jupiter", "목성", ["jupiter"], "가장 큰 가스 행성."),
        _n("moon", "달", ["moon"], "지구의 자연 위성."),
        _n("galaxy", "은하", ["galaxy"], "수많은 항성이 중력으로 묶인 집단."),
        _n("blackhole", "블랙홀", ["black hole"], "빛도 빠져나오지 못하는 강한 중력의 천체."),
        _n("gravity", "중력", ["gravity"], "질량이 서로 끌어당기는 힘."),
        _n("orbit", "궤도", ["orbit"], "천체가 다른 천체 주위를 도는 경로."),
        _n("comet", "혜성", ["comet"], "얼음과 먼지로 된, 긴 꼬리를 가진 천체."),
        _n("asteroid", "소행성", ["asteroid"], "행성보다 작은 암석 천체."),
    ]
    edges = [
        _e("earth", "is_a", "planet"), _e("mars", "is_a", "planet"), _e("jupiter", "is_a", "planet"),
        _e("sun", "is_a", "star"), _e("planet", "orbits", "sun"), _e("moon", "orbits", "earth"),
        _e("solar_system", "contains", "sun"), _e("solar_system", "contains", "planet"),
        _e("galaxy", "contains", "star"), _e("blackhole", "has", "gravity"),
        _e("gravity", "causes", "orbit"), _e("comet", "orbits", "sun"), _e("asteroid", "orbits", "sun"),
    ]
    return _expert("expert.astronomy.ko.v1", "천문·우주 그래프", "태양계·항성·궤도·중력의 전문 지식 그래프",
                   "태양계와 행성, 항성·은하·블랙홀, 중력과 궤도 등 천문 도메인 개념과 관계.",
                   "science", "astronomy", ["astronomy", "space", "expert", "ko"], nodes, edges)


def music_theory_expert() -> dict:
    nodes = [
        _n("note", "음", ["note"], "음악의 기본 소리 단위."),
        _n("scale", "음계", ["scale"], "일정한 규칙으로 배열된 음의 집합."),
        _n("chord", "화음", ["chord"], "두 개 이상의 음이 동시에 울리는 것."),
        _n("interval", "음정", ["interval"], "두 음 사이의 높낮이 거리."),
        _n("major", "장조", ["major"], "밝은 느낌의 음계."),
        _n("minor", "단조", ["minor"], "어두운 느낌의 음계."),
        _n("triad", "3화음", ["triad"], "세 음으로 이루어진 기본 화음."),
        _n("octave", "옥타브", ["octave"], "진동수가 2배 차이 나는 음정."),
        _n("melody", "멜로디", ["melody"], "음이 시간에 따라 이어진 선율."),
        _n("harmony", "하모니", ["harmony"], "화음의 연결과 조화."),
        _n("rhythm", "리듬", ["rhythm"], "소리의 길고 짧음과 강약의 패턴."),
        _n("beat", "박자", ["beat"], "리듬의 규칙적인 단위."),
        _n("tempo", "빠르기", ["tempo"], "음악이 진행되는 속도."),
    ]
    edges = [
        _e("scale", "made_of", "note"), _e("chord", "made_of", "note"),
        _e("major", "is_a", "scale"), _e("minor", "is_a", "scale"),
        _e("triad", "is_a", "chord"), _e("octave", "is_a", "interval"),
        _e("interval", "between", "note"), _e("melody", "uses", "note"),
        _e("harmony", "uses", "chord"), _e("rhythm", "has", "beat"),
        _e("tempo", "controls", "rhythm"),
    ]
    return _expert("expert.music_theory.ko.v1", "음악 이론 그래프", "음계·화음·음정·리듬의 전문 지식 그래프",
                   "음·음계·화음·음정, 장/단조, 3화음·옥타브, 멜로디·하모니·리듬 등 음악 이론 개념과 관계.",
                   "music", "music_theory", ["music", "theory", "expert", "ko"], nodes, edges)


def human_anatomy_expert() -> dict:
    nodes = [
        _n("body", "인체", ["human body"], "사람의 몸 전체."),
        _n("circulatory", "순환계", ["circulatory system"], "혈액을 온몸에 순환시키는 계통."),
        _n("nervous", "신경계", ["nervous system"], "신호를 전달·처리하는 계통."),
        _n("digestive", "소화계", ["digestive system"], "음식을 소화·흡수하는 계통."),
        _n("respiratory", "호흡계", ["respiratory system"], "산소와 이산화탄소를 교환하는 계통."),
        _n("heart", "심장", ["heart"], "혈액을 펌프질하는 기관."),
        _n("brain", "뇌", ["brain"], "사고와 신호를 관장하는 기관."),
        _n("lung", "폐", ["lung"], "공기로 산소를 받아들이는 기관."),
        _n("stomach", "위", ["stomach"], "음식을 소화하는 기관."),
        _n("liver", "간", ["liver"], "대사·해독을 맡는 기관."),
        _n("blood", "혈액", ["blood"], "산소와 영양을 나르는 체액."),
        _n("neuron", "뉴런", ["neuron"], "신호를 전달하는 신경 세포."),
        _n("bone", "뼈", ["bone"], "몸을 지탱하는 단단한 조직."),
        _n("muscle", "근육", ["muscle"], "수축해 움직임을 만드는 조직."),
    ]
    edges = [
        _e("heart", "part_of", "circulatory"), _e("brain", "part_of", "nervous"),
        _e("lung", "part_of", "respiratory"), _e("stomach", "part_of", "digestive"),
        _e("liver", "part_of", "digestive"), _e("heart", "pumps", "blood"),
        _e("brain", "made_of", "neuron"), _e("circulatory", "part_of", "body"),
        _e("nervous", "part_of", "body"), _e("respiratory", "part_of", "body"),
        _e("muscle", "attached_to", "bone"),
    ]
    return _expert("expert.anatomy.ko.v1", "인체 해부 그래프", "계통·장기·조직의 전문 지식 그래프",
                   "순환/신경/소화/호흡계와 심장·뇌·폐·간, 혈액·뉴런·뼈·근육 등 인체 해부 개념과 관계.",
                   "medicine", "anatomy", ["anatomy", "medicine", "expert", "ko"], nodes, edges)


def chemistry_basics_expert() -> dict:
    nodes = [
        _n("atom", "원자", ["atom"], "물질을 이루는 가장 작은 단위."),
        _n("molecule", "분자", ["molecule"], "둘 이상의 원자가 결합한 입자."),
        _n("element", "원소", ["element"], "한 종류의 원자로 된 순물질."),
        _n("compound", "화합물", ["compound"], "둘 이상의 원소가 결합한 물질."),
        _n("bond", "화학결합", ["chemical bond"], "원자를 이어 붙이는 힘."),
        _n("ion", "이온", ["ion"], "전자를 얻거나 잃어 전하를 띤 입자."),
        _n("electron", "전자", ["electron"], "원자핵 주위를 도는 음전하 입자."),
        _n("proton", "양성자", ["proton"], "원자핵의 양전하 입자."),
        _n("neutron", "중성자", ["neutron"], "원자핵의 전하 없는 입자."),
        _n("acid", "산", ["acid"], "수소 이온을 내는 물질."),
        _n("base", "염기", ["base"], "수소 이온을 받는 물질."),
        _n("reaction", "화학반응", ["reaction"], "물질이 다른 물질로 바뀌는 과정."),
    ]
    edges = [
        _e("molecule", "made_of", "atom"), _e("compound", "made_of", "element"),
        _e("atom", "contains", "electron"), _e("atom", "contains", "proton"),
        _e("atom", "contains", "neutron"), _e("bond", "forms", "molecule"),
        _e("ion", "is_a", "atom"), _e("acid", "reacts_with", "base"),
        _e("reaction", "forms", "compound"), _e("element", "made_of", "atom"),
    ]
    return _expert("expert.chemistry.ko.v1", "화학 기초 그래프", "원자·분자·결합·반응의 전문 지식 그래프",
                   "원자·분자·원소·화합물, 화학결합·이온, 전자/양성자/중성자, 산·염기·반응 등 화학 기초 개념과 관계.",
                   "science", "chemistry", ["chemistry", "science", "expert", "ko"], nodes, edges)


def filmmaking_expert() -> dict:
    nodes = [
        _n("film", "영화", ["film", "movie"], "움직이는 영상으로 이야기를 전하는 매체."),
        _n("director", "감독", ["director"], "영화의 연출을 총괄하는 사람."),
        _n("actor", "배우", ["actor"], "인물을 연기하는 사람."),
        _n("screenwriter", "각본가", ["screenwriter"], "시나리오를 쓰는 사람."),
        _n("screenplay", "시나리오", ["screenplay", "script"], "영화의 대본."),
        _n("cinematography", "촬영", ["cinematography"], "카메라로 장면을 담는 작업."),
        _n("editing", "편집", ["editing"], "촬영분을 이어 붙여 완성하는 작업."),
        _n("camera", "카메라", ["camera"], "영상을 기록하는 장치."),
        _n("lighting", "조명", ["lighting"], "장면의 빛을 설계하는 작업."),
        _n("sound", "사운드", ["sound"], "대사·음악·효과음."),
        _n("scene", "장면", ["scene"], "하나의 연속된 촬영 단위."),
        _n("producer", "프로듀서", ["producer"], "제작 전반을 관리·조달하는 사람."),
    ]
    edges = [
        _e("director", "directs", "film"), _e("actor", "acts_in", "film"),
        _e("screenwriter", "writes", "screenplay"), _e("cinematography", "uses", "camera"),
        _e("cinematography", "uses", "lighting"), _e("editing", "assembles", "scene"),
        _e("film", "made_of", "scene"), _e("producer", "produces", "film"),
        _e("sound", "part_of", "film"), _e("screenplay", "basis_of", "film"),
    ]
    return _expert("expert.filmmaking.ko.v1", "영화 제작 그래프", "감독·시나리오·촬영·편집의 전문 지식 그래프",
                   "영화·감독·배우·각본가, 시나리오·촬영·편집·카메라·조명·사운드·장면 등 영화 제작 개념과 관계.",
                   "arts", "filmmaking", ["film", "arts", "expert", "ko"], nodes, edges)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for build in (coffee_expert, socratic_persona, analyst_persona,
                  astronomy_expert, music_theory_expert, human_anatomy_expert,
                  chemistry_basics_expert, filmmaking_expert):
        cart = build()
        v = validate_cartridge_schema(cart)
        cid = cart["cartridge_id"]
        path = OUT / f"{cid}.graphpack.json"
        write_cartridge(path, cart)   # embeds/keeps the checksum via canonical serialization
        sem = cart["contents"]["semantic_graph"]
        print(f"[BUILD] {cid}: valid={v['valid']} errors={v['errors']} nodes={len(sem['nodes'])} edges={len(sem['edges'])}")
        if v["valid"]:
            res = install_cartridge_from_path(str(path))
            print(f"[INSTALL] {cid}: checksum_valid={res.get('checksum_valid')} enabled={res.get('enabled')}")

    catalog = refresh_local_catalog()
    print(f"\n[CATALOG] refreshed: {len(catalog['items'])} items -> " + ", ".join(i["cartridge_id"] for i in catalog["items"]))
    print("\n[INSTALLED] " + ", ".join(c.get("cartridge_id", "?") for c in list_installed_cartridges()))

    # Prove usability: attach + a sandbox trial query against the coffee expert graph.
    print("\n=== usability check ===")
    for cid in ("expert.coffee.ko.v1", "persona.socratic.ko.v1"):
        try:
            att = attach_cartridge(cid)
            print(f"[ATTACH] {cid}: attached={att.get('attached', att.get('active', True))}")
        except Exception as exc:
            print(f"[ATTACH] {cid}: {type(exc).__name__}: {exc}")
    try:
        trial = start_sandbox_trial("expert.coffee.ko.v1", intent="coffee domain Q")
        sid = trial.get("session_id") or trial.get("trial_id")
        for q in ("에스프레소", "아라비카", "크레마"):
            r = run_sandbox_trial_query(sid, q)
            hits = r.get("matched_nodes") or r.get("nodes") or r.get("hits") or r
            print(f"[TRIAL] '{q}' -> {json.dumps(hits, ensure_ascii=False)[:120]}")
    except Exception as exc:
        print(f"[TRIAL] {type(exc).__name__}: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
