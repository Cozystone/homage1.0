"""Small self-authored Korean corpus for CGSR Stage 1 verification.

The corpus is intentionally local and license-clear.  It is not a downloaded
web corpus.  Stage 1 uses it only to verify the induction/dedupe pipeline.
"""

from __future__ import annotations

BASE_SENTENCES = [
    "쉽게 말하면 쿠버네티스는 컨테이너를 관리하는 시스템입니다.",
    "간단히 말해 쿠버네티스는 컨테이너를 관리하는 플랫폼입니다.",
    "쉽게는 쿠버네티스는 컨테이너 운영을 돕는 도구죠.",
    "핵심은 그래프가 근거를 연결한다는 점입니다.",
    "중요한 점은 그래프가 답변의 근거를 보존한다는 점입니다.",
    "예를 들어 GraphRAG는 문서 조각을 노드와 연결합니다.",
    "예를 들면 GraphRAG는 근거 문서를 먼저 찾습니다.",
    "다만 검증되지 않은 주장은 낮은 신뢰도로 남깁니다.",
    "하지만 근거가 부족하면 답변을 보류합니다.",
    "정리하면 로컬 브레인은 개인 데이터를 저장합니다.",
    "요약하면 클라우드 브레인은 공개 지식을 다룹니다.",
    "표층 브레인은 같은 의미를 더 자연스럽게 말합니다.",
    "구문 은행은 반복되는 표현 패턴을 모읍니다.",
    "시드 그래프는 질문을 해석하는 기준점입니다.",
    "큐 코텍스는 후보 조합을 고전적으로 선택합니다.",
    "아틀라스는 원격 상태를 시각적으로 보여줍니다.",
]

TOPICS = [
    ("쿠버네티스", "컨테이너", "관리 시스템"),
    ("GraphRAG", "근거 문서", "검증 방법"),
    ("시드 그래프", "기본 개념", "정렬 기준"),
    ("표층 브레인", "표현 패턴", "선택 장치"),
    ("로컬 브레인", "개인 문맥", "보호 저장소"),
    ("클라우드 브레인", "공개 지식", "확장 공간"),
    ("큐 코텍스", "후보", "선택 최적화기"),
    ("코텍스 G2", "작업 기억", "활성화 회로"),
    ("답변 품질 랩", "답변 품질", "측정 도구"),
    ("표층 수리 루프", "표현 누출", "수리 절차"),
    ("그래프 허브", "지식 카트리지", "탐색 공간"),
    ("아틀라스", "지역 신호", "시각화 지도"),
]

FRAMES = [
    "쉽게 말하면 {topic} {obj} 관리와 관련된 {desc}입니다.",
    "간단히 말해 {topic} {obj} 관리와 관련된 {desc}입니다.",
    "핵심은 {subject} {obj_acc} 안정적으로 다룬다는 점입니다.",
    "중요한 점은 {subject} {obj_acc} 검증 가능한 방식으로 다룬다는 점입니다.",
    "예를 들어 {topic} 먼저 {obj_acc} 확인합니다.",
    "다만 {topic} 검증되지 않은 {obj_acc} 바로 믿지 않습니다.",
    "정리하면 {topic} {obj}와 연결됩니다.",
    "요약하면 {topic} {obj_acc} 다룹니다.",
    "{topic} {obj_acc} 기준으로 다음 단계를 고릅니다.",
    "{subject} {obj_acc} 다룰 때 근거를 먼저 확인합니다.",
]


def _has_final(word: str) -> bool:
    for char in reversed(word):
        code = ord(char)
        if 0xAC00 <= code <= 0xD7A3:
            return ((code - 0xAC00) % 28) != 0
        if char.isalnum():
            return char.lower() not in {"a", "e", "i", "o", "u"}
    return False


def _josa(word: str, pair: tuple[str, str]) -> str:
    return pair[0] if _has_final(word) else pair[1]


def stage1_corpus() -> list[str]:
    """Return the deterministic Stage 1 verification corpus."""

    generated = [
        frame.format(
            topic=f"{a}{_josa(a, ('은', '는'))}",
            subject=f"{a}{_josa(a, ('이', '가'))}",
            obj=b,
            obj_acc=f"{b}{_josa(b, ('을', '를'))}",
            desc=c,
        )
        for a, b, c in TOPICS
        for frame in FRAMES
    ]
    return BASE_SENTENCES + generated


def corpus_metadata() -> dict[str, object]:
    """Return corpus source metadata."""

    corpus = stage1_corpus()
    return {
        "source": "self_authored_stage1_verification_corpus",
        "license": "project-local test fixture; no third-party corpus downloaded",
        "sentence_count": len(corpus),
        "external_download": False,
    }
