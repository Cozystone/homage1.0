from __future__ import annotations

import json
from typing import Any

from .models import SEMANTIC_PATH, SemanticConcept, SemanticRelation, ensure_base_dirs, utc_now_iso


def _concept(
    concept_id: str,
    canonical_name: str,
    aliases: list[str],
    description: str,
    relations: list[tuple[str, str, float]] | None = None,
    *,
    ko: str | None = None,
    en: str | None = None,
    confidence: float = 0.82,
) -> SemanticConcept:
    return SemanticConcept(
        concept_id=concept_id,
        canonical_name=canonical_name,
        aliases=aliases,
        short_description=description,
        relations=[
            SemanticRelation(source=concept_id, relation=relation, target=target, confidence=score)
            for relation, target, score in (relations or [])
        ],
        confidence=confidence,
        labels={"ko": ko or canonical_name, "en": en or canonical_name},
    )


def build_general_semantic_pack_v0() -> dict[str, Any]:
    ensure_base_dirs()
    concepts = [
        _concept(
            "kubernetes",
            "Kubernetes",
            ["쿠버네티스", "k8s", "container orchestration"],
            "Kubernetes deploys, scales, and operates containers across machines.",
            [("is_a", "container_orchestration_system", 0.94), ("manages", "container", 0.92), ("enables", "software_deployment", 0.86)],
            ko="쿠버네티스",
        ),
        _concept("container_orchestration_system", "container orchestration system", ["컨테이너 오케스트레이션", "컨테이너 관리 시스템"], "A system that schedules and manages containerized workloads.", [("used_for", "software_deployment", 0.86)], ko="컨테이너 오케스트레이션 시스템"),
        _concept("container", "container", ["컨테이너", "docker container"], "A lightweight package for running an application with its dependencies.", [("depends_on", "operating_system", 0.72)], ko="컨테이너"),
        _concept("docker", "Docker", ["도커"], "Docker packages and runs applications in containers.", [("produces", "container", 0.9)], ko="도커"),
        _concept("ai_training", "AI model training", ["AI 학습", "모델 학습", "training"], "Training adjusts model parameters from data so future inference can produce useful outputs.", [("contrasts_with", "ai_inference", 0.9)], ko="AI 모델 학습"),
        _concept("ai_inference", "AI inference", ["추론", "inference"], "Inference uses an already built model to produce an output for a new input.", [("requires", "trained_model", 0.82)], ko="AI 추론"),
        _concept("trained_model", "trained model", ["학습된 모델"], "A trained model is a model whose parameters have already been adjusted from data.", [("used_for", "ai_inference", 0.82)], ko="학습된 모델"),
        _concept("spring_boot", "Spring Boot", ["스프링부트", "spring"], "Spring Boot is a Java framework for building production web services quickly.", [("contrasts_with", "express_js", 0.82), ("is_a", "web_framework", 0.83)], ko="스프링부트"),
        _concept("express_js", "Express.js", ["Express", "익스프레스"], "Express.js is a minimal Node.js web framework for HTTP APIs and web apps.", [("is_a", "web_framework", 0.84)], ko="Express.js"),
        _concept("web_framework", "web framework", ["웹 프레임워크"], "A web framework gives structure and tools for building web services.", [("used_for", "api", 0.74)], ko="웹 프레임워크"),
        _concept("database", "database", ["데이터베이스", "db"], "A database stores structured information so it can be queried and updated reliably.", [("example_of", "sqlite", 0.74)], ko="데이터베이스"),
        _concept("sqlite", "SQLite", ["sqlite3", "로컬 sqlite"], "SQLite is an embedded database that stores data in a local file and works well for local-first apps.", [("is_a", "database", 0.88), ("used_for", "local_first_ai", 0.8)], ko="SQLite"),
        _concept("operating_system", "operating system", ["OS", "운영체제"], "An operating system manages hardware resources and provides services for applications.", [("manages", "cpu", 0.78), ("manages", "ram", 0.78)], ko="운영체제"),
        _concept("cpu", "CPU", ["processor", "중앙처리장치"], "A CPU is a general-purpose processor optimized for varied sequential and control-heavy work.", [("contrasts_with", "gpu", 0.84)], ko="CPU"),
        _concept("gpu", "GPU", ["graphics processor", "그래픽카드"], "A GPU is a processor optimized for many parallel operations such as graphics and tensor math.", [("used_for", "ai_inference", 0.75)], ko="GPU"),
        _concept("ram", "RAM", ["memory", "메모리"], "RAM is fast volatile memory used for active programs and data.", [("contrasts_with", "ssd", 0.78)], ko="RAM"),
        _concept("ssd", "SSD", ["storage", "저장장치"], "An SSD is persistent storage that keeps data after power is off.", [("used_for", "payload_vault", 0.74)], ko="SSD"),
        _concept("battery_series_connection", "battery series connection", ["직렬 연결", "battery series"], "Batteries in series add voltage while current capacity is usually limited by the cells.", [("has_property", "voltage", 0.85), ("contrasts_with", "current", 0.72)], ko="배터리 직렬 연결"),
        _concept("voltage", "voltage", ["전압"], "Voltage is electric potential difference, often described as pressure that pushes charge.", [("contrasts_with", "current", 0.8)], ko="전압"),
        _concept("current", "current", ["전류"], "Current is the flow rate of electric charge through a circuit.", [("depends_on", "voltage", 0.65)], ko="전류"),
        _concept("quantum_computer", "quantum computer", ["양자컴퓨터"], "A quantum computer uses quantum states for certain computations, but it is not a universal magic speedup.", [("contrasts_with", "classical_computer", 0.74)], ko="양자컴퓨터"),
        _concept("classical_computer", "classical computer", ["고전 컴퓨터"], "A classical computer computes through ordinary digital states and deterministic instructions.", [("contrasts_with", "quantum_computer", 0.74)], ko="고전 컴퓨터"),
        _concept("graphrag", "GraphRAG", ["그래프RAG", "graph retrieval augmented generation"], "GraphRAG retrieves facts through graph relationships and evidence paths before composing an answer.", [("requires", "semantic_graph", 0.9), ("used_for", "hallucination_reduction", 0.8)], ko="GraphRAG"),
        _concept("ontology", "ontology", ["온톨로지"], "An ontology defines concepts and relationships so knowledge can be organized and reasoned over.", [("is_a", "semantic_graph", 0.76)], ko="온톨로지"),
        _concept("semantic_graph", "semantic graph", ["의미 그래프", "knowledge graph"], "A semantic graph stores meanings as nodes and relationships rather than only raw text.", [("contrasts_with", "surface_graph", 0.82)], ko="의미 그래프"),
        _concept("surface_graph", "surface graph", ["표현 그래프", "Surface Brain"], "A surface graph stores how ideas are expressed: discourse moves, phrasing, tone, and construction choices.", [("used_for", "natural_answer_generation", 0.88)], ko="표현 그래프"),
        _concept("seed_graph", "Seed Graph", ["시드 그래프"], "A Seed Graph provides primitive reasoning moves and relation types used before user data exists.", [("part_of", "base_brain_pack", 0.86)], ko="시드 그래프"),
        _concept("base_brain_pack", "Base Brain Pack", ["기본 브레인 팩"], "A Base Brain Pack is a curated zero-user-data set of general reasoning anchors.", [("contains", "seed_graph", 0.86)], ko="기본 브레인 팩"),
        _concept("local_first_ai", "local-first AI", ["로컬 우선 AI"], "Local-first AI keeps core computation and private data on the user's device whenever possible.", [("used_for", "privacy", 0.9), ("contrasts_with", "cloud_ai", 0.82)], ko="로컬 우선 AI"),
        _concept("cloud_ai", "cloud AI", ["클라우드 AI"], "Cloud AI uses remote servers for storage or computation and can scale broadly when privacy boundaries are clear.", [("contrasts_with", "local_first_ai", 0.82)], ko="클라우드 AI"),
        _concept("privacy", "privacy", ["개인정보 보호", "private data"], "Privacy means limiting exposure of personal data and keeping sensitive information under user control.", [("requires", "local_first_ai", 0.72)], ko="개인정보 보호"),
        _concept("hallucination_reduction", "hallucination reduction", ["환각 감소"], "Hallucination reduction means qualifying or removing claims that are not supported by available evidence.", [("requires", "evidence", 0.82)], ko="환각 감소"),
        _concept("evidence", "evidence", ["근거", "source"], "Evidence is the supporting context used to justify or check a claim.", [("supports", "claim", 0.88)], ko="근거"),
        _concept("claim", "claim", ["주장"], "A claim is a statement that should be supported, qualified, or rejected based on evidence.", [("requires", "evidence", 0.72)], ko="주장"),
        _concept("software_deployment", "software deployment", ["배포"], "Software deployment is the process of packaging, releasing, and running an application for users.", [("requires", "api", 0.52)], ko="소프트웨어 배포"),
        _concept("desktop_app", "desktop app", ["데스크톱 앱"], "A desktop app runs as an installed application on a user's computer.", [("example_of", "tauri", 0.72)], ko="데스크톱 앱"),
        _concept("tauri", "Tauri", ["타우리"], "Tauri packages a web UI with a lightweight native shell for desktop applications.", [("used_for", "desktop_app", 0.86)], ko="Tauri"),
        _concept("api", "API", ["application programming interface"], "An API is a defined interface that lets software components exchange requests and responses.", [("used_for", "software_deployment", 0.7)], ko="API"),
        _concept("web_search", "web search", ["웹 검색"], "Web search finds public internet information and is distinct from local offline graph reasoning.", [("used_for", "needs_external_context", 0.68)], ko="웹 검색"),
        _concept("korean_language", "Korean language", ["한국어"], "Korean uses particles and sentence endings that should be handled natively for natural answers.", [("contrasts_with", "english_language", 0.7)], ko="한국어"),
        _concept("english_language", "English language", ["영어"], "English uses word order and articles differently from Korean, so answers should not be literal translations.", [("contrasts_with", "korean_language", 0.7)], ko="영어"),
        _concept("atanor", "ATANOR", ["아타노르"], "ATANOR is a local-first knowledge engine that separates semantic reasoning from surface expression.", [("is_a", "local_first_ai", 0.86), ("contains", "local_brain", 0.85), ("contains", "cloud_brain", 0.85), ("uses", "semantic_graph", 0.82), ("uses", "surface_graph", 0.82), ("requires", "privacy", 0.78)], ko="ATANOR"),
        _concept("local_brain", "Local Brain", ["로컬 브레인", "저장된 개인 맥락", "private context"], "The private on-device context area that should not be shared without the user.", [("used_for", "privacy", 0.86), ("contrasts_with", "cloud_brain", 0.82)], ko="로컬 브레인"),
        _concept("cloud_brain", "Cloud Brain", ["클라우드 브레인", "공개 지식 보조층", "public knowledge assist"], "The public or shared knowledge-assist layer separated from private user data.", [("contrasts_with", "local_brain", 0.82), ("requires", "evidence", 0.78)], ko="클라우드 브레인"),
        _concept("q_cortex", "Q-Cortex", ["q cortex", "고전 최적화 계층", "quantum-inspired optimizer"], "Q-Cortex is a classical local optimizer for selecting candidate reasoning paths; it is not quantum hardware.", [("contrasts_with", "quantum_computer", 0.84), ("used_for", "semantic_graph", 0.62)], ko="고전 최적화 계층"),
        _concept("graph_hub", "Graph Hub", ["그래프 허브", "graph cartridge system"], "Graph Hub is a cartridge system for graph knowledge: catalog, install, entitlement, read-only attachment, export, and audit.", [("part_of", "atanor", 0.72), ("uses", "semantic_graph", 0.6)], ko="그래프 허브"),
        _concept("atlas", "Atlas", ["아틀라스", "regional relay map"], "Atlas is a privacy-safe visualization of regional relay state for future contributor nodes; it does not share private memory.", [("part_of", "atanor", 0.7), ("contrasts_with", "local_brain", 0.55)], ko="아틀라스"),
        _concept("brain_graph", "Brain Graph", ["브레인 링크", "brain link", "브레인 그래프", "brain graph view"], "Brain Graph materializes tab-aware views of local, cloud, cartridge, and working-memory nodes without pretending they share the same privacy or provenance.", [("part_of", "atanor", 0.72), ("uses", "semantic_graph", 0.6)], ko="브레인 그래프"),
        _concept("machine_learning", "machine learning", ["머신러닝", "기계학습", "ML"], "Machine learning builds models that find patterns in data instead of being explicitly programmed for each case.", [("requires", "ai_training", 0.82), ("used_for", "ai_inference", 0.7)], ko="머신러닝"),
        _concept("neural_network", "neural network", ["신경망", "인공신경망"], "A neural network is a layered model of weighted connections that learns representations from data.", [("is_a", "machine_learning", 0.82), ("used_for", "ai_inference", 0.75)], ko="신경망"),
        _concept("http", "HTTP", ["http protocol", "에이치티티피"], "HTTP is the request-response protocol that web clients and servers use to exchange data.", [("used_for", "api", 0.8)], ko="HTTP"),
        _concept("json", "JSON", ["제이슨", "json format"], "JSON is a lightweight text format for exchanging structured data between systems.", [("used_for", "api", 0.78)], ko="JSON"),
        _concept("git", "Git", ["깃", "git vcs"], "Git is a distributed version-control system that tracks changes to source code over time.", [("used_for", "software_deployment", 0.6)], ko="Git"),
        _concept("linux", "Linux", ["리눅스"], "Linux is an open-source operating system kernel widely used for servers and development.", [("is_a", "operating_system", 0.85)], ko="리눅스"),
        _concept("python", "Python", ["파이썬"], "Python is a high-level programming language widely used for scripting, data work, and AI.", [("used_for", "machine_learning", 0.72)], ko="파이썬"),
        _concept("encryption", "encryption", ["암호화"], "Encryption transforms data so only authorized parties can read it, protecting confidentiality.", [("used_for", "privacy", 0.85)], ko="암호화"),
        _concept("compiler", "compiler", ["컴파일러"], "A compiler translates source code into a lower-level executable form so a machine can run it.", [("used_for", "software_deployment", 0.5)], ko="컴파일러"),
        _concept("virtual_machine", "virtual machine", ["가상머신", "VM"], "A virtual machine emulates a whole computer in software, isolating an operating system and its applications.", [("contrasts_with", "container", 0.7), ("depends_on", "operating_system", 0.6)], ko="가상머신"),
    ]
    pack = {
        "pack_id": "general_semantic_v0",
        "version": "0.1.3",
        "created_at": utc_now_iso(),
        "source_type": "curated_base_pack",
        "provenance": "ATANOR Base Brain v0",
        "concepts": [concept.to_dict() for concept in concepts],
        "relation_count": sum(len(concept.relations) for concept in concepts),
        "honesty": {
            "exhaustive_world_knowledge": False,
            "external_web_used": False,
            "external_llm_used": False,
        },
    }
    SEMANTIC_PATH.write_text(json.dumps(pack, ensure_ascii=False, indent=2), encoding="utf-8")
    return pack
