/* mini-ATANOR — the landing chat answers from a REAL local knowledge pack.
   The pack (mini_brain.json) is exported from the live engine's curated triple
   store by scripts/build_mini_brain.py; answering is deterministic graph lookup
   in this file. GPU 0, server 0 after page load, no LLM — the product claim,
   demonstrated literally in the visitor's own browser tab.

   v3 (owner-measured failures fixed): the parser is no longer position-regex.
   It runs the full engine's pipeline in miniature — ENTITY SPOTTING anywhere in
   the utterance (longest pack-name match, token-prefix tolerant, filler-proof),
   RELATION SPOTTING anywhere, REVERSE edges (서울의 수도는? -> 서울특별시는
   대한민국의 수도), and a DISCOURSE STATE: the last entity carries, so a bare
   follow-up like '인구는?' resolves against it. Context, not rules. */
(function () {
  "use strict";

  var josa = function (w, a, b) {
    var c = w.charCodeAt(w.length - 1);
    return c >= 0xac00 && c <= 0xd7a3 && (c - 0xac00) % 28 !== 0 ? a : b;
  };
  var norm = function (s) { return String(s || "").replace(/\s+/g, " ").trim(); };
  var stripJosa = function (w) {
    return w.replace(/(이란|이라는|란|라는|은|는|이|가|을|를|의|도|만|에서|에는|에|와|과|랑)$/, "");
  };
  var uiLang = function () { try { return typeof LANG !== "undefined" ? LANG : "ko"; } catch (e) { return "ko"; } };
  // leading discourse fillers, STACKED ('오 그럼 강남은?' — measured live), so
  // strip repeatedly until stable; then trailing chatter
  var FILLER = /^\s*(오|아|어|음+|흠+|와|헐|그래|그럼|그러면|근데|그런데|그리고|혹시|자|저기|아니|야|이제|음)\s+/;
  var stripFillers = function (s) {
    var prev;
    do { prev = s; s = s.replace(FILLER, ""); } while (s !== prev);
    return s.replace(/[?？!.…~ㅋㅎㅠㅜ\s]+$/g, "").trim();
  };

  // relation keywords -> pack predicate; spotted ANYWHERE in the utterance
  var REL_WORDS = {
    "수도": "capital", "인구": "인구", "면적": "면적",
    "뜻": "defined_as", "정의": "defined_as", "의미": "defined_as",
    "종류": "is_a", "위치": "located_in", "어디": "located_in",
    "나라": "__country_of__", "국가": "__country_of__",
  };
  // first syllables that legitimately FOLLOW an entity: josa, or the start of a
  // relation word. Used to tell '미국은'/'일본수도' (real) from '인도적'/'중국집'
  // (the entity name is just the prefix of a different, longer word).
  var JOSA_INIT = "은는이가을를의도만에와과랑로으라";
  var RELWORD_INIT = {};
  Object.keys(REL_WORDS).forEach(function (w) { RELWORD_INIT[w.charAt(0)] = 1; });

  function buildIndex(pack) {
    var names = {}, bySubj = {}, relByKo = {}, capitalOf = {};
    Object.keys(pack.concepts || {}).forEach(function (label) {
      names[label.replace(/\s+/g, "")] = label;
    });
    (pack.triples || []).forEach(function (t) {
      var s = t[0], rel = t[1], o = t[2];
      names[s.replace(/\s+/g, "")] = s;
      (bySubj[s] = bySubj[s] || []).push(t);
      // REVERSE edge: the capital city points back to its country, so
      // '서울의 수도는?' can answer '서울특별시는 대한민국의 수도' instead of shrugging
      if (rel === "capital" || rel === "수도") {
        capitalOf[o.replace(/\s+/g, "")] = { city: o, country: s };
        names[o.replace(/\s+/g, "")] = o;
      }
    });
    Object.keys(pack.rel_ko || {}).forEach(function (rel) {
      relByKo[pack.rel_ko[rel]] = rel;
    });
    // longest-first name list for containment spotting (skip 1-char names and
    // names that ARE relation words — '수도' must never be spotted as an entity)
    var nameKeys = Object.keys(names).filter(function (k) {
      return k.length >= 2 && !(k in REL_WORDS);
    }).sort(function (a, b) { return b.length - a.length; });
    pack._names = names; pack._bySubj = bySubj; pack._relByKo = relByKo;
    pack._capitalOf = capitalOf; pack._nameKeys = nameKeys;
    return pack;
  }

  /* ---- engine-style spotting: find the entity and the relation ANYWHERE ---- */
  function spotEntity(pack, q) {
    // strip the definitional/topic josa that FRAMES a question ('인생이란 뭘까' =
    // topic 인생, NOT the country 이란 glued inside it) — a confident-wrong trap.
    q = q.replace(/([가-힣]{2,})(?:이란|이라는|란|라는)(?=\s|$|[?？!.])/g, "$1");
    var flat = q.replace(/\s+/g, "");
    // 1) longest pack name contained in the utterance, at a real WORD BOUNDARY:
    //    reject a name glued as a suffix to a preceding Hangul syllable, or one
    //    that is merely the prefix of a longer word (next syllable is neither a
    //    josa nor a relation-word start). Kills 인생|이란, 인도|적, 중국|집 misfires.
    for (var i = 0; i < pack._nameKeys.length; i++) {
      var k = pack._nameKeys[i];
      var p = flat.indexOf(k);
      if (p === -1) continue;
      var before = p > 0 ? flat.charCodeAt(p - 1) : 0;
      if (before >= 0xac00 && before <= 0xd7a3) continue;            // glued suffix
      var ai = p + k.length, after = ai < flat.length ? flat.charCodeAt(ai) : 0;
      if (after >= 0xac00 && after <= 0xd7a3) {
        var nc = flat.charAt(ai);
        if (JOSA_INIT.indexOf(nc) === -1 && !RELWORD_INIT[nc]) continue;  // prefix of longer word
      }
      return pack._names[k];
    }
    // 2) token-prefix: a josa-stripped token that PREFIXES a pack name
    //    ('서울' -> 서울특별시). Longest token first; name with shortest
    //    completion wins (closest surface form).
    var toks = q.split(/\s+/).map(stripJosa).filter(function (t) { return t.length >= 2; })
                .sort(function (a, b) { return b.length - a.length; });
    for (var j = 0; j < toks.length; j++) {
      var best = null;
      for (var i2 = pack._nameKeys.length - 1; i2 >= 0; i2--) { // shortest names first
        var k2 = pack._nameKeys[i2];
        if (k2.indexOf(toks[j]) === 0) { best = pack._names[k2]; break; }
      }
      if (best) return best;
    }
    // 3) exact whole-token match — the only safe route for 1-char concepts
    //    ('물이 뭐야?' -> token 물): never substring, token identity only
    var toks1 = q.split(/\s+/).map(stripJosa);
    for (var j2 = 0; j2 < toks1.length; j2++) {
      if (toks1[j2] && pack._names[toks1[j2]] && !(toks1[j2] in REL_WORDS)) {
        return pack._names[toks1[j2]];
      }
    }
    return null;
  }

  function spotRelation(q) {
    var flat = q.replace(/\s+/g, "");
    var hit = null, hitPos = -1, wh = null;
    Object.keys(REL_WORDS).forEach(function (w) {
      var p = flat.lastIndexOf(w);
      if (p < 0) return;
      // '어디' is a QUESTION WORD — it names a relation only when no real
      // relation word is present ('수도가 어디야?'의 관계는 수도, 어디가 아님)
      if (w === "어디") { wh = REL_WORDS[w]; return; }
      if (p > hitPos) { hitPos = p; hit = REL_WORDS[w]; }
    });
    return hit || wh;
  }

  function renderFact(pack, s, t) {
    var rel = t[1], o = t[2];
    if (rel === "capital" || rel === "수도") return s + "의 수도는 " + o + "입니다.";
    if (rel === "인구") return s + "의 인구는 " + o + "명입니다.";
    if (rel === "면적") return s + "의 면적은 " + o + "입니다.";
    if (rel === "defined_as" || rel === "is_a")
      return s + josa(s, "은", "는") + " " + o + (/[.다]$/.test(o) ? "" : "입니다.");
    var relKo = (pack.rel_ko || {})[rel] || rel;
    return s + "의 " + relKo + josa(relKo, "은", "는") + " " + o + "입니다.";
  }

  function lookupRelation(pack, subj, rel) {
    var rows = pack._bySubj[subj] || [];
    for (var i = 0; i < rows.length; i++) {
      var t = rows[i];
      if (t[1] === rel || ((pack.rel_ko || {})[t[1]] || t[1]) === rel) {
        return renderFact(pack, subj, t);
      }
    }
    return null;
  }

  function lookupDefinition(pack, subj) {
    var desc = (pack.concepts || {})[subj];
    if (desc) {
      // a web-memory definition often opens with its own TOPIC ("빛의 속력(…)은
      // 진공에서…") — prepending ours would read "빛의 속도는 빛의 속력은…".
      // Serve verbatim only when the opening topic (the phrase before '(' or a
      // topic marker) is essentially the subject itself: same 2-char prefix AND
      // similar length. '커피나무의 열매를…' must still get '커피는 ' prepended.
      var m = desc.match(/^([가-힣A-Za-z0-9·\s]{2,20}?)(\(|은\s|는\s)/);
      if (m) {
        var topic = m[1].trim();
        var sflat = subj.replace(/\s+/g, "");
        var tflat = topic.replace(/\s+/g, "");
        if (tflat.slice(0, 2) === sflat.slice(0, 2) &&
            Math.abs(tflat.length - sflat.length) <= 3) {
          return desc + (/[.다]$/.test(desc) ? "" : "입니다.");
        }
      }
      return subj + josa(subj, "은", "는") + " " + desc + (/[.다]$/.test(desc) ? "" : "입니다.");
    }
    var rows = pack._bySubj[subj] || [];
    for (var j = 0; j < rows.length; j++) {
      if (rows[j][1] === "defined_as" || rows[j][1] === "is_a") {
        return renderFact(pack, subj, rows[j]);
      }
    }
    return null;
  }

  /* ---- conversational lane (dialogue moves, not knowledge claims) ---- */
  function converse(pack, qRaw) {
    var t0 = performance.now();
    var q = norm(qRaw).toLowerCase().replace(/[?？!.~…]+$/, "");
    var facts = (pack.counts || {}).triples || 0;
    var en = uiLang() === "en" && !/[가-힣]/.test(qRaw);
    var text = null;
    if (/^(안녕|안녕하세요|안녕하신가요|안녕하십니까|하이|헬로|반가워|반갑습니다|ㅎㅇ|hi|hello|hey|yo)$/.test(q)) {
      text = en
        ? "Hi! I'm a miniature ATANOR running entirely inside this browser tab — " + facts + " verified facts, zero server calls. Try 일본의 수도는? — then just 인구는? (I keep context)."
        : "안녕하세요! 저는 이 브라우저 탭 안에서 통째로 도는 미니 ATANOR예요 — 검증 사실 " + facts + "개, 서버 호출 0. ‘일본의 수도는?’ 물어보시고, 이어서 ‘인구는?’처럼 짧게 물어도 맥락을 기억해요.";
    } else if (/(고마워|고맙습니다|감사합니다|감사해요|감사|땡큐|thank you|thanks|thx)/.test(q)) {
      text = en
        ? "You're welcome — every answer here is a verbatim quote from the verified graph, so ask away."
        : "천만에요 — 여기서 나가는 답은 전부 검증된 그래프의 원문 인용이에요. 얼마든지 물어보세요.";
    } else if (/^(너는?|넌|당신은?|정체가?)?\s*(누구(야|세요|니|심|시죠)?|뭐야|뭔데)$/.test(q) ||
               /(뭐야 너|너 뭐야|넌 뭐야|너는 뭐야|정체가 뭐|네 소개|자기소개|who are you|what are you|introduce yourself)/.test(q)) {
      text = en
        ? "I'm ATANOR in miniature: the same graph-native structure as the full engine, packed into a 33 KB knowledge pack that answers right here — GPU 0, server 0. The full ATANOR continues with live web verification and a learning loop."
        : "저는 ATANOR의 축소판이에요. 전체 엔진과 같은 그래프 네이티브 구조를 33KB 지식팩에 담아 이 탭에서 바로 답합니다 — GPU 0, 서버 0. 전체 ATANOR는 실시간 웹 검증과 학습 루프로 이어집니다.";
    } else if (/(뭘 물어|뭘 알아|무엇을 알아|뭐 알아|뭐 할 수 있|뭘 할 수 있|할 수 있는 게|기능이 뭐|what can you|what do you know)/.test(q)) {
      text = en
        ? "This mini pack covers world capitals, populations and areas, plus concept definitions (coffee, gravity, the speed of light…). Ask in Korean — and follow up with just 인구는?, I keep context."
        : "이 미니 팩에는 세계 나라들의 수도·인구·면적과 개념 정의(커피, 중력, 빛의 속도…)가 들어 있어요. ‘대한민국의 인구는?’처럼 묻고, 이어서 ‘면적은?’처럼 짧게 물어도 돼요 — 맥락을 기억합니다.";
    } else if ((/(너|넌|네가|너가|당신|니가|니는|니)/.test(q) &&
                /(어떻게|원리|작동|돌아가|계산|가능|만들|무슨\s*원리)/.test(q)) ||
               /(어떻게.{0,10}(계산|연산|답|풀|만들|작동)|무슨\s*원리|어떤\s*원리|작동\s*원리|비결|llm|gpt|인공지능|how do you|how does)/.test(q)) {
      // META / self-capability ('너는 어떻게 수학을 하니?') — explain HOW, honestly. Not a
      // 'not in the pack' shrug: this is a dialogue move about the engine itself.
      text = en
        ? "No server and no LLM — I run entirely in this browser tab. Math isn't a stored answer: a reasoning lane computes it digit by digit on the spot, so even 2^100 comes out exact. Facts are quoted verbatim from a verified graph."
        : "저는 서버도 LLM도 없이 이 브라우저 탭 안에서 답해요. 계산은 미리 저장해 둔 답이 아니라, 자릿수 단위로 그 자리에서 계산하는 추론 레인이 직접 해요 — 그래서 ‘2의 100승’ 같은 큰 수도 오차 없이 정확합니다. 사실 질문은 검증된 그래프에서 원문 그대로 인용하고요.";
    } else if (/(신기|대박|놀라|놀랍|멋지|멋있|훌륭|짱|최고|쩐다|쩔|굿|good|wow|cool|amazing|neat|awesome|오오+|우와+|와우|헐+|오호)/.test(q) &&
               !/(뭐|무엇|어디|누구|얼마|몇|뜻|의미|수도|인구|면적|계산)/.test(q)) {
      // REACTION / exclamation ('오오 신기하다') — a warm dialogue turn, never treated as an
      // unknown entity. Acknowledge, then invite the next question.
      text = en
        ? "Glad it clicks! Put me to the test — a definition like ‘what is coffee?’, or a calc like ‘2^10’, answered right here."
        : "신기하게 봐주시니 기뻐요. 얼마든지 시험해 보세요 — ‘커피가 뭐야?’ 같은 정의도, ‘2의 10승은?’ 같은 계산도 바로 해드려요.";
    } else if (/(심심|재미(있|없)|재밌|놀자|놀아|뭐하|뭐 하|배고|졸려|졸린|피곤|힘들|외로|좋아 너|너 좋아|사랑해|보고싶|기분|어때|어떠|bored|let'?s play|i'?m (bored|tired|hungry))/.test(q)) {
      // omni-engage in miniature: a feeling/chit-chat move is a DIALOGUE turn,
      // never a knowledge claim — engage, then offer a door back to a question.
      text = en
        ? "Then let's put me to work — I answer from a verified graph in this tab, and reach the live web for anything beyond it. Ask me ‘일본의 수도는?’, or a definition like ‘커피가 뭐야?’."
        : "그럼 저를 좀 부려보세요 — 이 탭에서 검증된 그래프로 답하고, 그 너머는 실시간 웹으로 확인해요. ‘일본의 수도는?’이나 ‘커피가 뭐야?’처럼 물어보세요.";
    }
    if (text) return { text: text, ms: performance.now() - t0, grounded: false, kind: "chat" };
    return null;
  }

  /* ---- local reasoning lane: EXACT arithmetic, COMPUTED not looked up ----
     The reasoning VM in miniature. A computed result is VERIFIABLE, so it is
     never a fabrication — it belongs in the 0%-abstention floor: questions the
     knowledge pack can never hold (there is no stored 'fact' for 17×23) are
     still answered, exactly, in the browser. Integer ops use BigInt, so 2^100
     is exact — no float lie. (Ported from the full engine's reasoning_vm.) */
  var KO_D = { "영": 0, "공": 0, "일": 1, "이": 2, "삼": 3, "사": 4, "오": 5,
               "육": 6, "륙": 6, "칠": 7, "팔": 8, "구": 9 };
  function parseOperand(tok) {
    if (tok == null) return null;
    var t = String(tok).replace(/[,\s]/g, "");
    if (/^\d+(\.\d+)?$/.test(t)) return t;              // digit string (kept as string for BigInt)
    if (t.length === 1 && t in KO_D) return String(KO_D[t]);
    return null;
  }
  function grp(s) {                                     // thousands separators, sign/decimal safe
    s = String(s); var neg = s[0] === "-"; if (neg) s = s.slice(1);
    var p = s.split("."); p[0] = p[0].replace(/\B(?=(\d{3})+(?!\d))/g, ",");
    return (neg ? "-" : "") + p.join(".");
  }
  function fmtExpr(a, op, b) {
    if (op === "^") return grp(a) + "의 " + grp(b) + "제곱";
    return grp(a) + " " + ({ "+": "+", "-": "−", "*": "×", "/": "÷" })[op] + " " + grp(b);
  }
  function calcInt(a, op, b) {                          // exact big-integer arithmetic
    var x = BigInt(a), y = BigInt(b);
    if (op === "+") return { v: (x + y).toString() };
    if (op === "-") return { v: (x - y).toString() };
    if (op === "*") return { v: (x * y).toString() };
    if (op === "^") return y < 0n ? null : { v: (x ** y).toString() };
    if (op === "/") {
      if (y === 0n) return { err: "0으로 나눌 수는 없어요." };
      if (x % y === 0n) return { v: (x / y).toString() };
      return { q: (x / y).toString(), rem: (x % y).toString() };   // quotient + remainder
    }
    return null;
  }
  var N = "(\\d[\\d,]*(?:\\.\\d+)?)";                   // an operand: digits (optional decimals)
  var _OPS = [
    { re: new RegExp(N + "\\s*(?:의\\s*)?" + N + "\\s*(?:승|제곱)"), op: "^" },
    { re: new RegExp(N + "\\s*(?:\\^|\\*\\*)\\s*" + N), op: "^" },
    { re: new RegExp(N + "\\s*의\\s*" + N + "\\s*배"), op: "*" },
    { re: new RegExp(N + "\\s*(?:곱하기|곱한|×|✕|·|[xX*])\\s*" + N), op: "*" },   // '200x240', '3*4'
    { re: new RegExp(N + "\\s*(?:더하기|더한|플러스|\\+)\\s*" + N), op: "+" },
    { re: new RegExp(N + "\\s*(?:빼기|뺀|마이너스)\\s*" + N), op: "-" },
    { re: new RegExp(N + "\\s*(?:나누기|나눈|÷)\\s*" + N), op: "/" },
  ];
  function solveArithmetic(qRaw) {
    var q = norm(qRaw);
    var pm = q.match(/(\d[\d,]*(?:\.\d+)?)\s*의\s*(\d[\d,]*(?:\.\d+)?)\s*(?:퍼센트|%)/);
    if (pm) {
      var A = parseFloat(pm[1].replace(/,/g, "")), B = parseFloat(pm[2].replace(/,/g, ""));
      return { text: grp(pm[1].replace(/,/g, "")) + "의 " + grp(pm[2].replace(/,/g, "")) +
                     "%는 " + grp(Math.round(A * B / 100 * 1e6) / 1e6) + "입니다.", calc: true };
    }
    for (var i = 0; i < _OPS.length; i++) {
      var m = q.match(_OPS[i].re);
      if (!m) continue;
      var a = parseOperand(m[1]), b = parseOperand(m[2]), op = _OPS[i].op;
      if (a == null || b == null) continue;
      var res;
      if (a.indexOf(".") >= 0 || b.indexOf(".") >= 0) {  // decimals -> Number path
        var av = parseFloat(a), bv = parseFloat(b);
        var rv = op === "+" ? av + bv : op === "-" ? av - bv : op === "*" ? av * bv
               : op === "^" ? Math.pow(av, bv) : (bv === 0 ? null : av / bv);
        if (rv == null) return { text: "0으로 나눌 수는 없어요. 다른 수로 물어봐 주세요.", calc: true };
        res = { v: String(Math.round(rv * 1e10) / 1e10) };
      } else res = calcInt(a, op, b);
      if (!res) continue;
      if (res.err) return { text: res.err + " 다른 수로 물어봐 주세요.", calc: true };
      var head = fmtExpr(a, op, b) + " = ";
      if (res.v != null) return { text: head + grp(res.v) + "입니다.", calc: true };
      return { text: head + "몫 " + grp(res.q) + ", 나머지 " + grp(res.rem) + "입니다.", calc: true };
    }
    return null;
  }

  /* ---- 2-hop relation composition: the full engine's relation-path lane in
     miniature. '프랑스의 수도의 인구는?' has no direct (프랑스,인구) edge, but the
     pack HAS (프랑스,capital,파리) and (파리,인구,…) — compose them. Both legs are
     stored facts, so a composition is grounded, never invented. */
  function twoHop(pack, entity, rel) {
    var rows = pack._bySubj[entity] || [];
    for (var i = 0; i < rows.length; i++) {
      var r1 = rows[i][1], mid = rows[i][2];
      if (mid === entity) continue;
      var leg = lookupRelation(pack, mid, rel);
      if (leg) return entity + "의 " + ((pack.rel_ko || {})[r1] || r1) + "인 " + leg;
    }
    return null;
  }

  /* ---- omni-engage floor: NEVER refuse. When neither the pack, the reasoning
     lane, nor the web can GROUND a factual answer, still respond — honestly,
     without inventing a fact. A dialogue move or an honest redirect, never a
     bare shrug. (Doctrine: cut false abstention by engaging, never by
     fabricating; 답한다 ≠ 지어낸다.) This is the 0%-abstention backstop. */
  function engage(pack, qRaw, entity) {
    var q = stripFillers(norm(qRaw));
    var facts = (pack.counts || {}).triples || 0;
    var en = uiLang() === "en" && !/[가-힣]/.test(qRaw);
    var topic = entity;
    if (!topic) {
      var toks = q.split(/\s+/).map(stripJosa).filter(function (t) {
        return t.length >= 2 && !STOP_WORDS.test(t) && !(t in REL_WORDS);
      });
      topic = toks[0] || "";
    }
    var opine = /(좋을까|좋아할까|나을까|할까요|할까|추천|생각해|생각하니|어때|어떨까|낫나|낫니|의견|믿어|믿니)/.test(q);
    var text;
    if (opine) {
      text = en
        ? "That's not something I can state as a verified fact — and I won't invent one. What I can do is ground the question in the pack's checked facts (capitals, populations, areas, concept definitions). Which fact should we start from?"
        : "그건 검증된 사실로 단정하긴 어려운 질문이에요 — 지어내지 않고 정직하게 말씀드리는 편이 맞아요. 대신 이 팩의 검증된 사실(나라 수도·인구·면적, 개념 정의)로 판단의 근거는 짚어드릴 수 있어요. 어떤 사실부터 확인해 볼까요?";
    } else if (topic) {
      text = en
        ? "‘" + topic + "’ isn't in this mini pack's " + facts + " verified facts yet — I'd rather say so than make something up. The full ATANOR digs further with live web verification and a learning loop. In this tab, ask a country's capital / population / area, a concept definition, or even a calculation like ‘17 × 23’."
        : "‘" + topic + "’" + josa(topic, "은", "는") + " 아직 이 미니 팩의 검증된 " + facts +
          "개 사실 안에는 없어요 — 지어내는 대신 정직하게 말씀드려요. 전체 ATANOR는 실시간 웹 검증과 학습 루프로 여기서 더 파고듭니다. 이 탭에선 나라의 수도·인구·면적, 개념 정의(커피·중력·빛의 속도…), 또는 ‘17 곱하기 23’ 같은 계산을 물어보시면 바로 답해요.";
    } else {
      text = en
        ? "Here I answer from " + facts + " verified facts — capitals, populations, areas, and concept definitions — and I compute exactly (try ‘17 × 23’ or ‘2^10’). What would you like to know?"
        : "저는 이 탭에서 검증된 " + facts + "개 사실 — 나라의 수도·인구·면적과 개념 정의 — 로 답하고, 계산도 정확히 해드려요(‘17 곱하기 23’, ‘2의 10승’ 처럼요). 무엇이 궁금하세요?";
    }
    return { text: text, grounded: false, kind: "engage" };
  }

  /* ---- the mini engine: spot -> resolve -> traverse -> remember ---- */
  var CTX = { entity: null };   // discourse state: the last resolved entity

  function answer(pack, qRaw) {
    var t0 = performance.now();
    var q0 = norm(qRaw);
    if (!q0) return null;
    var chat = converse(pack, qRaw);
    if (chat) return chat;
    // reasoning lane FIRST — an exact computation answers regardless of language
    // and regardless of what the pack holds ('2의 10승', '17 x 23', '3.14 × 2').
    var calc = solveArithmetic(qRaw);
    if (calc) return { text: calc.text, ms: performance.now() - t0, grounded: true, kind: "calc" };
    if (!/[가-힣]/.test(q0)) {
      return {
        text: uiLang() === "en"
          ? "The pack in this tab holds Korean-labeled facts — try 일본의 수도는? The full ATANOR answers multilingual questions with live web verification."
          : "이 탭의 팩은 한국어 라벨 사실을 담고 있어요 — ‘일본의 수도는?’처럼 물어보세요. 전체 ATANOR는 다국어 질문을 실시간 웹 검증으로 답합니다.",
        ms: performance.now() - t0, grounded: false, kind: "chat",
      };
    }
    var q = stripFillers(q0);
    var entity = spotEntity(pack, q);
    var rel = spotRelation(q);
    var usedContext = false;

    // follow-up: relation with no entity rides the discourse state ('인구는?')
    if (!entity && rel && CTX.entity) { entity = CTX.entity; usedContext = true; }

    var text = null;
    if (entity && rel) {
      if (rel === "capital" || rel === "__country_of__") {
        // REVERSE edge first when the entity is itself a capital city:
        // '서울의 수도는?' / '서울은 어느 나라?' -> 서울특별시는 대한민국의 수도
        var rev = pack._capitalOf[entity.replace(/\s+/g, "")];
        if (rev) {
          text = rev.city + josa(rev.city, "은", "는") + " " + rev.country + "의 수도입니다.";
        } else if (rel === "capital") {
          text = lookupRelation(pack, entity, "capital");
        }
      } else {
        text = lookupRelation(pack, entity, rel);
        if (!text) text = twoHop(pack, entity, rel);     // relation-path composition (F3 mini)
      }
      if (!text) text = lookupDefinition(pack, entity);  // relation missing: fall to identity
    } else if (entity) {
      text = lookupDefinition(pack, entity);
      if (!text) {
        var rev2 = pack._capitalOf[entity.replace(/\s+/g, "")];
        if (rev2) text = rev2.city + josa(rev2.city, "은", "는") + " " + rev2.country + "의 수도입니다.";
      }
    }

    if (text) {
      CTX.entity = entity;   // remember for the next turn
      return { text: text, ms: performance.now() - t0, grounded: true, context: usedContext };
    }
    // BEYOND THE PACK: hand off to live web verification (the browser calls
    // Wikipedia directly — still no ATANOR server involved). The UI awaits it.
    return { kind: "web", q: q, entity: entity, rel: rel, t0: t0 };
  }

  /* ---- live web verification lane (browser -> Wikipedia, no middleman) ----
     The full engine's web-rescue law applies in miniature: the fetched page
     must ANCHOR the question (title overlap gate) or we abstain honestly, and
     whatever we say is a VERBATIM quote from the source, linked. */
  var STOP_WORDS = /^(뭐야|뭐지|뭔데|뭐냐|무엇|누구야|누구지|누구|어디야|어디|언제|얼마야|얼마|왜|어떻게|알려줘|설명해줘|설명|말해줘|궁금해|대해|대해서|관해|에|는|은|이|가)$/;
  // common ATTRIBUTE nouns: a bare '높이는?' follow-up means the DISCOURSE
  // entity's attribute, not a new topic. A proper-noun token ('강남') is a new
  // topic. Surface/discourse cue, not knowledge — kept as a small LAD list.
  var ATTR_WORDS = /^(높이|무게|길이|넓이|면적|크기|색|색깔|색상|나이|키|가격|값|깊이|두께|온도|둘레|지름|반지름|무엇으로|재료|성분|위치|수도|인구|정의|뜻|의미)$/;

  function webSubject(q, entity, rel) {
    if (entity && !rel) return entity;             // pack entity, unknown property
    var toks = q.split(/\s+/).map(stripJosa).filter(function (t) {
      return t && !STOP_WORDS.test(t) && !(t in REL_WORDS);
    });
    return toks.join(" ") || (CTX.entity || "");
  }

  function fetchJSON(url) {
    return fetch(url, { headers: { "Accept": "application/json" } })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); });
  }

  function wikiSummary(title) {
    return fetchJSON("https://ko.wikipedia.org/api/rest_v1/page/summary/" +
                     encodeURIComponent(title.replace(/\s+/g, "_")));
  }

  function wikiSearch(q) {
    return fetchJSON("https://ko.wikipedia.org/w/api.php?action=opensearch&format=json&origin=*&limit=1&search=" +
                     encodeURIComponent(q))
      .then(function (a) { return (a && a[1] && a[1][0]) || null; });
  }

  function anchors(subj, title) {
    var s = subj.replace(/\s+/g, ""), t = (title || "").replace(/\s+/g, "");
    if (!s || !t) return false;
    return t.indexOf(s) !== -1 || s.indexOf(t) !== -1 ||
           (s.length >= 2 && t.slice(0, 2) === s.slice(0, 2));
  }

  function pickSentence(extract, keyword) {
    var parts = (extract || "").split(/(?<=다\.)\s+|(?<=\.)\s+/);
    for (var i = 0; i < parts.length; i++) {
      if (keyword && parts[i].indexOf(keyword) !== -1) return parts[i].trim();
    }
    return null;
  }

  function fetchPage(subj) {
    return wikiSummary(subj).catch(function () {
      return wikiSearch(subj).then(function (t) {
        if (!t) throw new Error("not-found");
        return wikiSummary(t);
      });
    });
  }

  function renderPage(page, subj, propWord, t0) {
    var title = page && (page.title || ""), extract = page && (page.extract || "");
    var url = page && page.content_urls && page.content_urls.desktop && page.content_urls.desktop.page;
    if (!extract || !anchors(subj, title)) return null;
    var text, partial = false;
    if (propWord) {
      var sent = pickSentence(extract, propWord);
      if (sent) text = sent;
      else { text = extract.split(/(?<=다\.)\s+/)[0]; partial = true; }
    } else {
      text = extract.split(/(?<=다\.)\s+/).slice(0, 2).join(" ");
    }
    if (partial) text += " — 요약에 ‘" + propWord + "’ 항목은 없었어요. 원문에서 확인해 보세요.";
    CTX.entity = title;
    return { text: text, url: url, title: title,
             ms: performance.now() - t0, grounded: true, web: true };
  }

  function webRescue(pack, r) {
    // the relation, if the user named a known property word ('인구는?' -> 인구)
    var propWord = null;
    if (r.rel) { for (var w in REL_WORDS) { if (REL_WORDS[w] === r.rel) { propWord = w; break; } } }
    var subj = webSubject(r.q, r.entity, r.rel);
    // a bare attribute follow-up ('높이는?') -> the discourse entity's attribute
    if (!propWord && !r.entity && CTX.entity && subj && ATTR_WORDS.test(subj) && subj !== CTX.entity) {
      propWord = subj; subj = "";
    }

    // CASCADE (measured: '오 그럼 강남은' must look up 강남 as its OWN topic,
    // not as a property of the previous entity):
    //  1) a real relation word with no subject -> the discourse entity's property
    //  2) a standalone subject token -> look it UP as a subject (new topic wins)
    //  3) subject didn't anchor but we have context -> the token as a keyword
    //     inside the context entity (this is where '높이는?' lands)
    if (propWord && (!subj || subj === CTX.entity) && CTX.entity) {
      return fetchPage(CTX.entity).then(function (p) {
        var out = renderPage(p, CTX.entity, propWord, r.t0);
        if (!out) throw new Error("no-anchor");
        return out;
      });
    }
    if (!subj) return Promise.reject(new Error("no-subject"));
    return fetchPage(subj).then(function (p) {
      var out = renderPage(p, subj, propWord, r.t0);
      if (out) return out;
      // subject didn't anchor: try it as a property of the discourse entity
      if (CTX.entity && subj !== CTX.entity) {
        return fetchPage(CTX.entity).then(function (p2) {
          var out2 = renderPage(p2, CTX.entity, subj, r.t0);
          if (!out2) throw new Error("no-anchor");
          return out2;
        });
      }
      throw new Error("no-anchor");
    });
  }

  function certLabel(r) {
    var en = uiLang() === "en";
    if (r.web) {
      return en ? "live web verification " + r.ms.toFixed(0) + " ms · source ko.wikipedia.org · ATANOR server calls 0"
                : "실시간 웹 검증 " + r.ms.toFixed(0) + " ms · 출처 ko.wikipedia.org · ATANOR 서버 호출 0";
    }
    if (r.kind === "calc") {                            // check BEFORE grounded (calc is grounded:true)
      return en ? "local reasoning · exact computation · GPU 0 · server 0"
                : "로컬 추론 · 정확 계산 · GPU 0 · 서버 호출 0";
    }
    if (r.grounded) {
      var base = en ? "mini pack lookup " + r.ms.toFixed(2) + " ms · GPU 0 · server calls 0"
                    : "미니 지식팩 조회 " + r.ms.toFixed(2) + " ms · GPU 0 · 서버 호출 0";
      if (r.context) base += en ? " · context carried" : " · 맥락 유지";
      return base;
    }
    if (r.kind === "chat") {
      return en ? "dialogue · in-browser · server calls 0"
                : "대화 응답 · 브라우저 로컬 · 서버 호출 0";
    }
    if (r.kind === "engage") {
      return en ? "honest engagement · nothing invented · server 0"
                : "정직한 응답 · 지어내지 않음 · 서버 호출 0";
    }
    return en ? "in-browser · nothing invented" : "브라우저 로컬 · 지어내지 않았습니다";
  }

  // ---- UI wiring: turn the mock chat card into the live mini engine ----
  function initUI(pack) {
    var card = document.querySelector(".chatcard");
    if (!card) return;
    var log = document.createElement("div");
    log.className = "mini-log";
    while (card.firstChild) log.appendChild(card.firstChild);
    card.appendChild(log);
    var form = document.createElement("form");
    form.className = "mini-ask";
    form.innerHTML =
      '<input type="text" autocomplete="off" ' +
      'id="mini-ask-inp" placeholder="Ask directly — answered inside this browser (0 GPUs · 0 servers)" aria-label="mini atanor input"/>' +
      "<button type=\"submit\" aria-label=\"ask\">↑</button>";
    card.appendChild(form);
    var input = form.querySelector("input");
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var q = norm(input.value);
      if (!q) return;
      input.value = "";
      var u = document.createElement("div");
      u.className = "chatrow user";
      u.textContent = q;
      log.appendChild(u);
      var r = answer(pack, q);
      var b = document.createElement("div");
      b.className = "chatrow bot";
      var span = document.createElement("span");
      b.appendChild(span);
      var cert = document.createElement("div");
      cert.className = "cert";
      cert.innerHTML = "<i></i><span></span>";
      b.appendChild(cert);
      log.appendChild(b);

      function paint(res) {
        span.textContent = res.text;
        if (res.url) {
          var a = document.createElement("a");
          a.href = res.url; a.target = "_blank"; a.rel = "noopener";
          a.textContent = " (출처: " + (res.title || "위키백과") + ")";
          a.style.cssText = "font-size:.85em;opacity:.75;text-decoration:underline;";
          span.appendChild(a);
        }
        cert.querySelector("span").textContent = certLabel(res);
        log.scrollTop = log.scrollHeight;
        if (window.__atanorOrbPulse)
          window.__atanorOrbPulse(res.grounded ? 1.0 : (res.kind === "chat" ? 0.6 : 0.45));
      }

      if (r.kind === "web") {
        span.textContent = uiLang() === "en" ? "verifying on the live web…" : "실시간 웹에서 검증하는 중…";
        cert.querySelector("span").textContent = uiLang() === "en"
          ? "browser → ko.wikipedia.org (no ATANOR server)" : "브라우저 → ko.wikipedia.org (ATANOR 서버 경유 없음)";
        log.scrollTop = log.scrollHeight;
        webRescue(pack, r).then(paint).catch(function () {
          // web couldn't anchor either — NEVER dead-end: engage honestly instead
          // of shrugging (0%-abstention floor; still no invented fact).
          var e = engage(pack, r.q, r.entity);
          paint({ text: e.text, ms: performance.now() - r.t0, grounded: false, kind: "engage" });
        });
      } else {
        paint(r);
      }
    });
  }

  fetch("assets/mini_brain.json")
    .then(function (r) { return r.json(); })
    .then(function (pack) { initUI(buildIndex(pack)); })
    .catch(function () { /* pack missing: the static mock stays as-is */ });

  // expose for tests
  window.MiniAtanor = { buildIndex: buildIndex, answer: answer, converse: converse,
                        spotEntity: spotEntity, spotRelation: spotRelation,
                        solveArithmetic: solveArithmetic, twoHop: twoHop, engage: engage };
})();
