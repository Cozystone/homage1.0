/* Node battery for the browser mini-ATANOR engine: proves the 0%-ABSTENTION floor
   (every input yields a grounded fact / exact calc / honest engagement — never a
   bare shrug, never a fabricated fact) and EXACT arithmetic. Run: node test_mini_engine.cjs
   Shims the browser globals the IIFE touches, then drives window.MiniAtanor directly. */
"use strict";
const fs = require("fs");
const path = require("path");

// --- browser shims (the engine is a browser IIFE) ---
global.window = {};
global.performance = { now: () => 0 };
global.document = { querySelector: () => null };      // -> initUI() returns early (no DOM)
global.fetch = () => Promise.reject(new Error("offline in test"));  // web lane rejects -> engage floor
global.LANG = "ko";

const dir = __dirname;
const code = fs.readFileSync(path.join(dir, "assets/mini_atanor.js"), "utf8");
// eslint-disable-next-line no-eval
eval(code);                                            // attaches global.window.MiniAtanor
const M = global.window.MiniAtanor;
const pack = M.buildIndex(JSON.parse(fs.readFileSync(path.join(dir, "assets/mini_brain.json"), "utf8")));

const ABSTAIN = /모르겠|답변\s*불가|알\s*수\s*없|대답할\s*수\s*없|여기서\s*멈춥|찾지\s*못했|잘\s*모르|no\s*idea|cannot answer|don'?t know/i;
let fail = 0;

// ---- 1) 0%-abstention battery: diverse inputs, NONE may abstain ----
const battery = [
  // pack facts + follow-up context
  "일본의 수도는?", "대한민국의 인구는?", "커피가 뭐야?", "미국의 면적은?",
  // exact reasoning (pack can never hold these)
  "2의 10승은?", "17 곱하기 23", "144 나누기 12는?", "100 더하기 250",
  "50 빼기 8", "3.5 곱하기 2", "10 나누기 3", "300의 20%는?", "2^64",
  // opinion / philosophy (no verified fact — must engage honestly, not assert)
  "인생이란 뭘까?", "행복이 뭐라고 생각해?", "뭐가 더 좋을까?",
  // unknown entity (beyond pack + web offline in test -> engage floor)
  "쿼카가 뭐야?", "블록체인 알려줘", "제임스 웹 망원경은?",
  // chit-chat + identity
  "안녕", "심심해", "너 누구야?", "뭐 할 수 있어?",
  // non-Korean + gibberish (must still engage, never dead-end)
  "hello", "what is the capital of Japan", "asdfqwer", "ㅁㄴㅇㄹ", "?", "ㅋㅋㅋ",
];

function resolve(q) {                                   // mirror the UI: web lane falls to engage
  let r = M.answer(pack, q);
  if (r && r.kind === "web") r = M.engage(pack, r.q, r.entity);
  return r;
}

console.log("── 0%-abstention battery ──");
let abstain = 0;
for (const q of battery) {
  const r = resolve(q);
  const text = (r && r.text) || "";
  const bad = !text.trim() || ABSTAIN.test(text);
  if (bad) { abstain++; fail++; console.log("  ABSTAIN ✗", JSON.stringify(q), "->", JSON.stringify(text.slice(0, 60))); }
}
console.log(`  abstention: ${abstain}/${battery.length}` + (abstain === 0 ? "  ✓ ZERO" : "  ✗"));

// ---- 2) arithmetic must be EXACT (computed, not guessed) ----
console.log("── exact arithmetic ──");
const calc = [
  ["2의 10승은?", "1,024"], ["17 곱하기 23", "391"], ["144 나누기 12는?", "12"],
  ["100 더하기 250", "350"], ["50 빼기 8", "42"], ["300의 20%는?", "60"],
  ["10 나누기 3", "몫 3, 나머지 1"], ["2^64", "18,446,744,073,709,551,616"],
  ["3.5 곱하기 2", "7"],
];
for (const [q, want] of calc) {
  const r = resolve(q);
  const ok = r && r.kind === "calc" && r.text.indexOf(want) !== -1;
  if (!ok) { fail++; console.log("  ✗", JSON.stringify(q), "-> got", JSON.stringify(r && r.text), "want", want); }
  else console.log("  ✓", q, "->", r.text);
}

// ---- 3) relation-path (2-hop) composition on a synthetic pack (both legs are facts) ----
console.log("── 2-hop relation composition ──");
const mini = M.buildIndex({
  counts: { triples: 2 }, rel_ko: { capital: "수도", 인구: "인구" },
  concepts: {}, triples: [["프랑스", "capital", "파리"], ["파리", "인구", "2,100,000"]],
});
const hop = M.answer(mini, "프랑스의 수도의 인구는?");
const hopOk = hop && hop.text && hop.text.indexOf("파리") !== -1 && hop.text.indexOf("2,100,000") !== -1;
if (!hopOk) { fail++; console.log("  ✗ 2-hop ->", hop && hop.text); }
else console.log("  ✓ 2-hop ->", hop.text);

// ---- 4) honesty: engage must NOT assert an invented fact for an unknown entity ----
console.log("── honesty (engage states it doesn't have the fact) ──");
const e = M.engage(pack, "쿼카가 뭐야?", null);
const honest = e.text.indexOf("없") !== -1 || e.text.indexOf("지어내") !== -1;
if (!honest) { fail++; console.log("  ✗ engage not honest ->", e.text); }
else console.log("  ✓", e.text.slice(0, 70) + "…");

// ---- 5) confident-wrong traps: an entity name glued inside a longer word must
//         NOT misfire to that entity's fact (worse than abstention) ----
console.log("── confident-wrong traps (no misfire to a wrong entity) ──");
const traps = [["인생이란 뭘까?", "이란"], ["인도적 지원이 뭐야?", "인도"],
               ["중국집 추천해줘", "중국"], ["미국적인 게 뭐야?", "미국"]];
for (const [q, wrong] of traps) {
  const ent = M.spotEntity(pack, q);
  if (ent === wrong) { fail++; console.log("  ✗ MISFIRE", JSON.stringify(q), "-> spotted", ent); }
  else console.log("  ✓", q, "-> entity:", ent === null ? "(none, engages)" : ent);
}
// and the normal cases must STILL spot correctly (no over-rejection)
const keep = [["일본의 수도는?", "일본"], ["대한민국의 인구는?", "대한민국"], ["커피가 뭐야?", "커피"]];
for (const [q, want] of keep) {
  const ent = M.spotEntity(pack, q);
  if (ent !== want) { fail++; console.log("  ✗ LOST", JSON.stringify(q), "-> got", ent, "want", want); }
  else console.log("  ✓", q, "-> entity:", ent);
}

// ---- 6) live-feedback fixes (owner tested atanor.kr): reactions, 'x' multiply, meta/self ----
console.log("── live-feedback fixes ──");
const fb = [
  ["200x240", "calc", "48,000"],          // 'x' as multiply
  ["3*4", "calc", "12"],                   // '*' as multiply (not pow)
  ["48000나누기 4", "calc", "12,000"],      // no space before operator
  ["오오 신기하다", "chat", "신기"],          // reaction, NOT unknown-entity engage
  ["너는 어떻게 수학을 할 수 있지?", "chat", "추론"],  // meta/self-capability, explains HOW
];
for (const [q, kind, want] of fb) {
  let r = M.answer(pack, q);
  if (r && r.kind === "web") r = M.engage(pack, r.q, r.entity);
  const gotKind = r && (r.kind || (r.grounded ? "fact" : "?"));
  const ok = r && r.text.indexOf(want) !== -1 &&
             (kind === "calc" ? gotKind === "calc" : gotKind === "chat");
  if (!ok) { fail++; console.log("  ✗", JSON.stringify(q), "-> kind", gotKind, JSON.stringify((r && r.text || "").slice(0, 60))); }
  else console.log("  ✓", q, "->", r.text.slice(0, 46));
}

console.log(fail === 0 ? "\nALL PASS ✓  (0% abstention, exact reasoning, honest, no confident-wrong)" : `\n${fail} FAILURES ✗`);
process.exit(fail === 0 ? 0 : 1);
