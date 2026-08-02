# ATANOR Korean Greeting Quality

Status: proof-only evaluation criteria.

The greeting path must stay local and construction-conditioned. It must not call
external LLMs or sLLMs, and it must not use prompt-specific fixed answer tables.

Preferred greeting behavior:

- short
- natural Korean
- friendly but not clingy
- no machine/internal wording
- no over-explanation
- no memory write
- no consciousness claim

Examples of acceptable style:

- `안녕. 나 여기 있어.`
- `안녕. 편하게 말해줘.`
- `반가워. 오늘은 뭐부터 볼까?`
- `응, 준비됐어.`

Forbidden generic greeting artifacts:

- `여기서 듣고 있어 천천히 말해줘`
- `먼저 의도와 경계를 내부적으로 점검했습니다`
- hidden chain-of-thought references
- real consciousness or AGI claims
- direct memory write promises

The Korean naturalness evaluator rewards short, idiomatic Korean and penalizes
awkward internal telemetry wording, repeated nouns, trace terms, and overly
instructional greetings.
