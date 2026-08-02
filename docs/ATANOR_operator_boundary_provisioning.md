# 운영자 경계 프로비저닝 + SL-1 승격 절차서

**대상** 사장님(운영자) 단독 실행 · **2026-07-28** · 이 절차 없이는 `--swap`이 영구히 막혀 있습니다.

shipped 그래프 게이트는 default-deny이고, 레포 **바깥**에 있는 Ed25519 키로만 열립니다. 그 경계가 한 번도
프로비저닝된 적이 없어서 지금까지 어떤 승격도 물리적으로 불가능했습니다. 이 문서가 그것을 엽니다.

## 왜 제(Claude)가 아니라 사장님이 실행하는가

코드가 스스로 그렇게 말합니다:

> `OperatorTrustRoot`: "Supplying a key file alone is not an authority boundary: **ATANOR could
> create a different key file.** The caller must also supply the expected key ID from an
> operator-controlled channel."
>
> `promote_staging_to_shipped.py`: "`--i-am-operator` is only a presence gesture; it is never
> authority." / "**An external operator signer** must place these exact values in an unexpired v3
> document."

제가 키를 만들고 서명하고 swap하면 게이트는 통과하지만 2자 구조가 1자로 붕괴합니다. 그리고 같은 이유로
**서명 도구도 레포 안에 두지 않습니다** — 레포 안에 있으면 ATANOR가 자기가 서명받을 내용을 바꿀 수
있습니다. 아래 구조는 그것을 막습니다:

* 레포 도구(`promote_staging_to_shipped.py`)는 **읽기전용으로 값을 출력만** 합니다.
* 바깥 도구는 그 값을 **감싸서 서명만** 하고, 레포 코드를 일절 import하지 않습니다.

## 지금 상태

| 항목 | 값 |
|---|---|
| 배치 | `runtime/graph_mutation_spool/batches/gmb_9efbce84eac11a27a9526c2de95ef714` (stage=`staged`) |
| 내용 | additions 130 (`atanor has_a <organ>`), retractions 0 |
| 후보 | `data/graph_scale/kg_triples.staged_merge.gmb_9efbce84eac11a27a9526c2de95ef714.20260728_164558` |
| 검증 | exact_additions / subject_index / base_operation_contract / live_unchanged 전부 ok |
| 라이브 | **무변경** (`ed2abd99…` 그대로) |

---

## STEP 0 — 사전 조건

```bash
python -c "import cryptography; print(cryptography.__version__)"
```

그리고 **엔진·워치독을 정지**하십시오. Windows는 프로세스가 memory-map한 디렉터리를 rename하지 못합니다.
STEP 5 직전까지만 정지하면 됩니다.

## STEP 1 — 바깥 서명 도구 저장

`%USERPROFILE%\.atanor\operator\atanor_sign.py` 로 저장하십시오. **레포 안에 두지 마십시오.**

```python
# -*- coding: utf-8 -*-
"""ATANOR operator signer. Lives OUTSIDE the repository on purpose. Imports no repo code."""
import argparse, base64, hashlib, json, os, secrets, subprocess, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

HOME = Path(os.path.expanduser("~")) / ".atanor" / "operator"
PRIV = HOME / "shipped_graph_operator_ed25519.pem"
PD   = Path(r"C:\ProgramData\ATANOR")
PUB  = PD / "operator-boundary" / "shipped_graph_operator_ed25519.pub.pem"
CFG  = PD / "operator-boundary" / "shipped_graph_promotion.v1.json"
LED  = PD / "promotion-ledger"
TARGET = "atanor:graph-scale:kg-triples-primary"
PHRASE = "PROMOTE REVIEWED CANDIDATES TO VERIFIED STAGING"
INVARIANTS = {
    "authorization_scope": "staging_only", "auto_promote": False,
    "cryptographically_signed": False, "external_llm": False, "external_sllm": False,
    "human_approval_required": True, "merge_authorized": False,
    "production_store_mutated": False, "proof_only": True, "rollback_required": True,
    "shipped_graph_write": False, "signed_manifest_required": True,
}

def compact(o):  # boundary config + ledger identity format
    return json.dumps(o, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")

def provision(a):
    if PRIV.exists() and not a.rotate:
        sys.exit(f"REFUSING: key already exists at {PRIV}. --rotate retires it.")
    HOME.mkdir(parents=True, exist_ok=True)
    k = Ed25519PrivateKey.generate()
    PRIV.write_bytes(k.private_bytes(serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    if os.name == "nt":
        subprocess.run(["icacls", str(PRIV), "/inheritance:r", "/grant:r",
                        f"{os.environ['USERNAME']}:(R,W)"], capture_output=True)
    else:
        PRIV.chmod(0o600)
    raw = k.public_key().public_bytes(serialization.Encoding.Raw,
                                      serialization.PublicFormat.Raw)
    h = hashlib.sha256(raw).hexdigest()
    key_id, ledger_id = f"ed25519:{h[:24]}", f"atanor:promotion-ledger:{h[:32]}"
    PUB.parent.mkdir(parents=True, exist_ok=True)
    PUB.write_bytes(k.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    (LED / "claims").mkdir(parents=True, exist_ok=True)
    lock = LED / ".shipped-store-promotion.lock"
    if not lock.exists() or lock.stat().st_size < 1:
        lock.write_bytes(b"atanor.promotion-lock.v1\n")
    (LED / "promotion-nonce-ledger-identity.json").write_bytes(compact({
        "schema_version": "atanor.promotion-nonce-ledger-identity.v1",
        "ledger_id": ledger_id, "target_store_id": TARGET,
        "lock_relative_path": ".shipped-store-promotion.lock",
        "claims_relative_path": "claims"}))
    CFG.write_bytes(compact({
        "schema_version": "atanor.shipped-graph-operator-boundary-config.v1",
        "boundary_id": f"atanor-shipped-graph-boundary-{h[:20]}",
        "target_store_id": TARGET, "operator_public_key_path": str(PUB),
        "operator_key_id": key_id, "nonce_ledger_path": str(LED),
        "nonce_ledger_id": ledger_id}))
    print(json.dumps({"ok": True, "operator_key_id": key_id, "ledger_id": ledger_id,
                      "boundary_config": str(CFG), "private_key": str(PRIV)}, indent=2))

def receipt(a):
    payload = json.loads(Path(a.payload).read_text(encoding="utf-8"))
    item_id = f"graph_store_candidate:{payload['candidate_digest_sha256'][:32]}"
    entries = [{"item_id": item_id, "production_store_mutated": False,
                "status": "pending_operator_signature", "payload": payload}]
    digest = hashlib.sha256((json.dumps(tuple(entries), ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), default=str) + "::" + a.operator_id.strip()
        ).encode("utf-8")).hexdigest()[:24]
    batch_id = f"nightly_promotion_confirmed_{digest}"
    r = {**INVARIANTS, "batch_id": batch_id,
         "confirmed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
         "operator_id": a.operator_id, "operator_confirmed": True, "signed": False,
         "staging_allowed": True, "status": "operator_confirmed_staged",
         "attestation_level": "interactive_confirmation",
         "required_confirmation_phrase": PHRASE, "item_ids": [item_id], "item_count": 1,
         "entries": entries, "note": a.note}
    out = Path(a.outdir) / f"{batch_id}.json"      # filename MUST equal batch_id
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(json.dumps(r, ensure_ascii=False, indent=2,
                               sort_keys=True).encode("utf-8"))   # indent=2, NOT compact
    print(json.dumps({"ok": True, "receipt": str(out)}, indent=2))

def sign(a):
    ctx = json.loads(Path(a.context).read_text(encoding="utf-8"))
    now = datetime.now(timezone.utc)
    doc = {"schema_version": "atanor.shipped-graph-promotion-document.v3",
           "purpose": "atanor.shipped-graph-promotion.v3",
           "merge_authorized": True, "production_store_mutated": False,
           "rollback_required": True,
           **{k: ctx[k] for k in ("staging_receipt_sha256", "candidate_digest_sha256",
              "mutation_batch_manifest_sha256", "item_ids", "target_store_id",
              "operator_boundary_id", "operator_boundary_config_sha256", "base_revision",
              "rollback_artifact_sha256", "nonce_replay_domain")},
           "issued_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
           "expires_at": (now + timedelta(minutes=a.ttl)).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "nonce": f"sl1-{secrets.token_hex(16)}"}
    payload = json.dumps(doc, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"), allow_nan=False).encode("utf-8")
    k = serialization.load_pem_private_key(PRIV.read_bytes(), password=None)
    raw = k.public_key().public_bytes(serialization.Encoding.Raw,
                                      serialization.PublicFormat.Raw)
    doc["operator_signature"] = {"scheme": "ed25519",
        "key_id": f"ed25519:{hashlib.sha256(raw).hexdigest()[:24]}",
        "payload_sha256": hashlib.sha256(payload).hexdigest(),
        "signature": base64.b64encode(k.sign(payload)).decode("ascii")}
    Path(a.out).write_bytes(compact(doc))
    print(json.dumps({"ok": True, "document": a.out, "expires_at": doc["expires_at"]}, indent=2))

ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest="c", required=True)
p = sub.add_parser("provision"); p.add_argument("--rotate", action="store_true"); p.set_defaults(f=provision)
p = sub.add_parser("receipt"); p.add_argument("--payload", required=True)
p.add_argument("--outdir", required=True); p.add_argument("--operator-id", default="owner")
p.add_argument("--note", default="SL-1 self-projection: 130 (atanor, has_a, <organ>) edges.")
p.set_defaults(f=receipt)
p = sub.add_parser("sign"); p.add_argument("--context", required=True)
p.add_argument("--out", required=True); p.add_argument("--ttl", type=int, default=30)
p.set_defaults(f=sign)
a = ap.parse_args(); a.f(a)
```

## STEP 2 — 경계 프로비저닝 (키 생성)

```bash
python "$USERPROFILE/.atanor/operator/atanor_sign.py" provision
```

출력의 `operator_key_id`를 **따로 기록해 두십시오.** 이것이 앞으로 모든 shipped 그래프 승격의 지문입니다.
개인키는 `%USERPROFILE%\.atanor\operator\shipped_graph_operator_ed25519.pem` 에 생깁니다 —
**이 키를 쥔 자가 ATANOR의 세계를 다시 쓸 수 있습니다.** 백업하고, 레포에 넣지 마십시오.

`C:\ProgramData` 쓰기가 거부되면 관리자 PowerShell에서 한 번만:
```bash
mkdir "C:\ProgramData\ATANOR"
```

## STEP 3 — 큐 영수증

레포 도구가 payload를 출력합니다. JSON 본문만 파일로 저장하십시오(제목줄·안내문 제외).

```bash
cd "C:/0.ASKIM ALL-VIN/27., ATANOR DEMO" && python scripts/promote_staging_to_shipped.py --receipt-payload --merged "data/graph_scale/kg_triples.staged_merge.gmb_9efbce84eac11a27a9526c2de95ef714.20260728_164558"
```

저장한 파일을 `payload.json`이라 하면:

```bash
python "$USERPROFILE/.atanor/operator/atanor_sign.py" receipt --payload payload.json --outdir "$USERPROFILE/.atanor/operator/receipts"
```

## STEP 4 — 서명 문맥 → 서명

```bash
cd "C:/0.ASKIM ALL-VIN/27., ATANOR DEMO" && python scripts/promote_staging_to_shipped.py --swap-context --merged "data/graph_scale/kg_triples.staged_merge.gmb_9efbce84eac11a27a9526c2de95ef714.20260728_164558" --staging-receipt "<STEP 3에서 만들어진 receipt 경로>"
```

출력 JSON 본문을 `context.json`으로 저장한 뒤:

```bash
python "$USERPROFILE/.atanor/operator/atanor_sign.py" sign --context context.json --out "$USERPROFILE/.atanor/operator/promotion.json" --ttl 30
```

**서명은 30분 유효합니다.** STEP 5를 그 안에 끝내십시오. 지나면 STEP 4를 다시 하면 됩니다.

## STEP 5 — SWAP (여기서 실제로 바뀝니다)

엔진·워치독이 정지되어 있는지 다시 확인하십시오.

```bash
cd "C:/0.ASKIM ALL-VIN/27., ATANOR DEMO" && python scripts/promote_staging_to_shipped.py --swap --i-am-operator --merged "data/graph_scale/kg_triples.staged_merge.gmb_9efbce84eac11a27a9526c2de95ef714.20260728_164558" --mutation-batch "runtime/graph_mutation_spool/batches/gmb_9efbce84eac11a27a9526c2de95ef714" --promotion-document "$USERPROFILE/.atanor/operator/promotion.json" --staging-receipt "<receipt 경로>"
```

이전 라이브 스토어는 `data/graph_scale/kg_triples.prev.<ts>` 로 보존됩니다. in-process 롤백은
설계상 비활성이므로, 문제가 생기면 그 디렉터리가 복구 수단입니다.

## STEP 6 — 검증

```bash
cd "C:/0.ASKIM ALL-VIN/27., ATANOR DEMO" && python scripts/self_model_calibration.py
```

`parts_self`가 `I don't hold a grounded parts fact for atanor yet.` → 실제 기관 목록으로 바뀌면
성공입니다. 그때 알려주시면 제가 나머지(메타인지 조합, alias 정리)를 이어가겠습니다.

---

## 자주 걸리는 함정

| 증상 | 원인 |
|---|---|
| `operator boundary config fields are not exact` | 필드 7개 정확히, 추가/누락 불가 |
| `operator boundary config is not canonical JSON` | 경계 설정·원장 identity는 **compact**(`separators=(",",":")`, sort_keys) |
| `staging receipt bytes are not the queue's canonical format` | 영수증만 **`indent=2`** — 위와 다릅니다 |
| `staging receipt batch identity or exclusive path is invalid` | 파일명이 `<batch_id>.json`이어야 함 |
| `staging receipt does not bind the current bulk-store candidate` | payload를 손대면 안 됨 — `--receipt-payload` 출력 그대로 |
| `authorization_expired` | TTL 초과 → STEP 4 재실행 |
| `operator boundary config must be outside the mutable repository` | 레포 안에 두면 거부 |
| swap 중 rename 실패 | 엔진이 살아있음 |
| `nonce` 재사용 실패 | 서명 1회용 — 재시도는 STEP 4부터 |

## 이 키가 생긴 뒤 달라지는 것

지금까지 shipped 그래프는 **아무도 바꿀 수 없었습니다** — 게이트가 닫혀 있었으니까요. STEP 2 이후로는
그 키를 가진 주체가 바꿀 수 있습니다. 그러니 이 절차의 진짜 산출물은 130개 엣지가 아니라 **권한의
소재**입니다. 키는 사장님이, 후보 제작과 검증은 제가 — 그 분리가 유지되는 한 게이트는 의미를 갖습니다.
