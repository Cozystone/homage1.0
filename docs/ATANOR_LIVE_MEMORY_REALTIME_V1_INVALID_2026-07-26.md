# LiveMemory → RealTimeThinker prereg v1 INVALID

상태: `INVALID — no scored response`  
attempt: `2026-07-26T03:54:39.730819Z`  
완료 arm: `0 / 4`

v1은 첫 OFF worker가 어떤 사전등록 질문도 채점하기 전에 checkpoint 로드 단계에서 종료됐다. CPU-only 정책이 Windows subprocess에 `CUDA_VISIBLE_DEVICES=""`를 전달해 CUDA 장치 수를 0으로 만들었지만, `ace_hotpot.pt` 역직렬화 경로가 CUDA device 0을 요구하면서 `RuntimeError`가 발생했다.

이 실패에는 답변, item score, aggregate metric이 하나도 포함되지 않는다. v1의 mechanical retry 허용 횟수는 0이므로 같은 preregistration ID로 재실행하지 않는다. write-once attempt와 failure receipt를 그대로 보존한다.

- `reports/benchmarks/live_memory_realtime_lmrt-novel-single-hop-v1-20260726.attempt.json`
- `reports/benchmarks/live_memory_realtime_lmrt-novel-single-hop-v1-20260726.failure.json`

승인된 평가를 계속하려면 동일한 48+12 문항·candidate·gate를 유지하고, 장치 가시성 설정만 Windows에서 검증된 CPU 비활성값으로 교정한 별도 v2를 결과 실행 전에 봉인해야 한다. v1 실패는 양성·음성 capability 결과가 아니며 mechanism 진전으로도 세지 않는다.
