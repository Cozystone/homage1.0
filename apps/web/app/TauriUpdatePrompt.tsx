"use client";

import { useTauriUpdater } from "./hooks/useTauriUpdater";

export function TauriUpdatePrompt() {
  const updater = useTauriUpdater();

  if (!updater.isAvailable && updater.state !== "error") {
    return null;
  }

  return (
    <div className="tauri-update-backdrop" role="presentation">
      <section className="tauri-update-modal" role="dialog" aria-modal="true" aria-label="ATANOR update">
        {updater.state === "error" ? (
          <>
            <p className="tauri-update-eyebrow">업데이트 확인 실패</p>
            <h2>업데이트를 확인하지 못했습니다</h2>
            <p>{updater.error || "네트워크 또는 서명 검증 상태를 확인한 뒤 다시 시도하세요."}</p>
            <button type="button" className="secondaryButton" onClick={updater.dismiss}>
              닫기
            </button>
          </>
        ) : (
          <>
            <p className="tauri-update-eyebrow">시스템 업데이트</p>
            <h2>ATANOR {updater.version} 패치가 준비되었습니다</h2>
            <p>{updater.notes || "패치를 설치하면 앱이 자동으로 재시작됩니다."}</p>
            <div className="tauri-update-actions">
              <button type="button" className="secondaryButton" onClick={updater.dismiss} disabled={updater.isInstalling}>
                나중에
              </button>
              <button type="button" className="primaryButton" onClick={updater.installAndRestart} disabled={updater.isInstalling}>
                {updater.isInstalling ? "설치 중" : "설치 후 재시작"}
              </button>
            </div>
          </>
        )}
      </section>
    </div>
  );
}
