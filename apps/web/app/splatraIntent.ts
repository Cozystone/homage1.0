// 3D 공간 제어 인텐트 — 메인 컴포저(DemoChat)와 /studio3d가 공유한다.
// 보수적으로: 명백한 3D 신호가 있을 때만 잡고, 나머지는 전부 언어 엔진으로
// 흘려보낸다 (일반 질문을 가로채면 안 된다).

export type SplatraCmd =
  | { kind: "avatar" }                      // 아토 소환 (기계 자신의 캐릭터)
  | { kind: "generate"; prompt: string }
  | { kind: "anim"; style: string }
  | { kind: "gesture"; name: string }       // 기존 몸에서 한 부위만 움직임 (재생성 금지)
  | { kind: "stop" }
  | { kind: "reset" };

const OBJECT_WORDS =
  /토러스|torus|큐브|cube|구체|sphere|나선|spiral|그래프|graph|피카츄|pikachu|공룡|강아지|고양이|새\b|bird|dragon|드래곤/i;
const THREE_D_CUES = /3d|3디|파티클|홀로그램|hologram|입체|모형|particle/i;
const MAKE_VERBS = /만들|생성|빚|소환|그려|띄워|보여/;

export function parse3DIntent(raw: string): SplatraCmd | null {
  const q = raw.trim();
  const t = q.toLowerCase();

  // 아토: the machine's own character — summon by name
  if (/아토|ato\b/i.test(t) && /(나와|불러|소환|보여|나타나|와줘|등장)/.test(t))
    return { kind: "avatar" };

  // greeting -> wave the ARM of the existing body. Handlers only honor this
  // when the particle field is already open; otherwise 안녕 is normal chat.
  if (/^(안녕|안녕하세요|반가워|하이|헬로|hello|hi)[!~.?\s]*$/i.test(t))
    return { kind: "gesture", name: "wave" };
  if (/(손( )?흔들|인사해)/.test(t)) return { kind: "gesture", name: "wave" };

  // gesture / material / control — unambiguous 3D verbs
  if (/(멈춰|정지|그만)\s*$/.test(t)) return null;          // too generic alone
  if (/(파티클|홀로그램|3d|아토|모형|모델).*(멈춰|정지)|((멈춰|정지).*(파티클|홀로그램|모형))/.test(t))
    return { kind: "stop" };
  if (/물처럼|녹여봐|녹아내려|액체로/.test(t)) return { kind: "anim", style: "water" };
  if (/흙처럼|모래처럼|부서져|가루로/.test(t)) return { kind: "anim", style: "soil" };
  if (/흔들어|춤춰|춤을|살아있는 것처럼|움직여봐/.test(t)) return { kind: "anim", style: "rig" };
  if (/걸어봐|걸어다녀/.test(t)) return { kind: "anim", style: "walk" };
  if (/돌려봐|회전시켜/.test(t)) return { kind: "anim", style: "spin" };
  if (/원래대로|되돌려|얼려|굳혀/.test(t)) return { kind: "reset" };

  // generation: a maker verb PLUS either an explicit 3D cue or a known object
  if (MAKE_VERBS.test(t) && (THREE_D_CUES.test(t) || OBJECT_WORDS.test(t)))
    return { kind: "generate", prompt: q };

  return null;
}

export function describeCmd(cmd: SplatraCmd, ko: boolean): string {
  switch (cmd.kind) {
    case "avatar": return ko ? "아토를 부를게요." : "Summoning Ato.";
    case "generate": return ko ? "파티클로 빚는 중…" : "Sculpting particles…";
    case "anim": return ko ? `움직임: ${cmd.style}` : `Motion: ${cmd.style}`;
    case "gesture": return ko ? "👋" : "👋";
    case "stop": return ko ? "파티클 정지." : "Particles stopped.";
    case "reset": return ko ? "원래 모습으로." : "Back to rest.";
  }
}
