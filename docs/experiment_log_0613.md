# ATANOR Experiment Log 2026-06-13

Google Docs target: https://docs.google.com/document/d/1m9phn1au8DpfBP1X2S-teNYSh_AA5gc2UQulgebeLGs/edit?usp=drivesdk

This file is the local fallback when Google Docs connector append is unavailable.

## Connector Status

- 2026-06-13 15:19 KST: Google Docs readback succeeded for document `6/13 test log`.
- 2026-06-13 15:19 KST: Google Docs append failed because the current connector connection is missing write scopes. Local fallback logging remains active.


### [?ㅽ뿕 ?ъ씠??#1] - 媛???ㅼ젙 諛?寃利?濡쒓렇
* **?쒖옉 ?쒓컙:** 2026-06-13 15:19:20 ??쒕?援??쒖???
* **醫낅즺 ?쒓컙:** 2026-06-13 15:19:30 ??쒕?援??쒖???

#### 1. 媛???ㅼ젙 (Hypothesis)
* limit=50,000 ?곹깭?먯꽌 FastAPI SSE, daemon status, GraphRAG query, WebGL persistent buffer ?낅젰 寃쎈줈媛 1,232+ ?몃뱶/7,132+ ?먯? 洹쒕え源뚯? wipe ?놁씠 ?좎??쒕떎.

#### 2. 寃利?怨쇱젙 諛?痢≪젙 ?곗씠??(Verification & Metrics)
* ?ㅽ뻾 ?꾧뎄/?섍꼍: FastAPI 127.0.0.1:8500 / Tauri desktop artifact / Python automation runner
* ?쒕쾭/API ?곹깭:
```json
{
  "pipeline_status": 200,
  "pipeline_state": "alpha_active",
  "daemon_status": 200,
  "daemon_state": "idle"
}
```
* 洹몃옒???ㅽ듃由?
```json
{
  "content_type": "text/event-stream; charset=utf-8",
  "first_event": "id: 1781331564181\nevent: graph_snapshot\ndata: {\"nodes\":[{\"id\":\"021f0c9a23ee444122f8ac8eef8555adbc57b873de449f81ee8898a5448925ad\",\"node_hash\":\"021f0c9a23ee444122f8ac8eef8555adbc57b873de449f81ee8898a5448925ad\",\"label\":\"ghost:021f0c9a23ee\",\"type\":\"ghost_hash\",\"count\":1,\"confidence\":0.5,\"x\":-2.06825,\"y\":-2.35563,\"z\":2.13805,\"projection_source\":\"ghost_shell_content_addressed_v1\",\"payload_resolved\":false},{\"id\":\"0252b84901033771a99fae063abde949b7f3298a78fa86238eb880ebe95b666c\",\"node_hash\":\"0252b84901033771a99fae063abde949b7f3298a78fa86238eb880ebe95b666c\",\"label\":\"ghost:0252b8490103\",\"type\":\"ghost_hash\",\"count\":1,\"confidence\":0.5,\"x\":-1.66455,\"y\":2.64042,\"z\":1.06937,\"projection_source\":\"ghost_shell_content_addressed_v1\",\"payload_resolved\":false},{\"id\":\...(truncated)
```
* 由ъ냼??
```json
{
  "desktop_process": {
    "pid": null,
    "state": "not_launched"
  }
}
```
* ?뚯떛/?앹꽦 ?덉쭏:
```json
{
  "fixed_question_set": [
    {
      "query": "?덈뀞",
      "status": 200,
      "body": {
        "state": "completed",
        "started_at": "2026-06-13T06:19:25Z",
        "finished_at": "2026-06-13T06:19:25Z",
        "error": null,
        "last_query": "?덈뀞",
        "confidence": 0.96,
        "result": {
          "query": "?덈뀞",
          "method": "homage-conversation-router-v1",
          "answer": "?덈뀞?섏꽭?? ATANOR ?ㅽ뿕?ㅼ엯?덈떎. 吏湲덉? ?몃? LLM ?놁씠 濡쒖뺄 洹몃옒??硫붾え由ъ? native ?앹꽦湲곕? ?ㅽ뿕?섎뒗 ?곹깭?덉슂.",
          "matched_nodes": [],
          "matched_edges": [],
          "evidence_docs": [],
          "citations": [],
          "graph_paths": [],
          "follow_up_questions": [],
          "retrieval_trace": {
            "strategy": "conversational intent; retrieval skipped",
            "query_terms": [
              "?덈뀞"
            ],
            "expanded_terms": [],
            "ranked_chunk_ids": ...(truncated)
```
* ?ㅻ쪟: ?놁쓬

#### 3. 釉뚮━??諛??ㅼ쓬 議곗튂 (Briefing & Next Step)
* 寃곌낵 ?붿빟: 媛???깃났. ?몃뱶/?ｌ? ?ㅽ듃由? daemon ?곹깭, 濡쒖뺄 ?앹꽦 ?묐떟??湲곗??쇰줈 ?먯젙?덈떎.
* 蹂묐ぉ: ?꾩옱 ?ъ씠?댁뿉??利됱떆 以묐떒??蹂묐ぉ? 媛먯??섏? ?딆쓬.
* 理쒖쟻???쒖븞: ?ㅽ뙣 ??ぉ???덉쑝硫??대떦 API/?뚮뜑留??뚯떛 寃쎈줈瑜??ㅼ쓬 ?ъ씠?댁쓽 ?⑥씪 媛?ㅻ줈 寃⑸━?쒕떎.
--------------------------------------------------
