"use client";

import { useCallback, useEffect, useRef, useState } from "react";

type UpdaterState = "idle" | "checking" | "available" | "installing" | "restarting" | "unavailable" | "error";

type TauriUpdate = {
  available: boolean;
  version: string;
  currentVersion: string;
  body?: string;
  date?: string;
  downloadAndInstall: () => Promise<void>;
};

function isTauriRuntime(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

function shouldSurfaceUpdaterErrors(): boolean {
  return process.env.NEXT_PUBLIC_ATANOR_SHOW_UPDATER_ERRORS === "1" || process.env.NEXT_PUBLIC_HOMAGE_SHOW_UPDATER_ERRORS === "1";
}

export function useTauriUpdater() {
  const updateRef = useRef<TauriUpdate | null>(null);
  const [state, setState] = useState<UpdaterState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [version, setVersion] = useState<string | null>(null);
  const [notes, setNotes] = useState<string | null>(null);

  useEffect(() => {
    if (!isTauriRuntime()) {
      setState("unavailable");
      return;
    }

    let cancelled = false;
    const run = async () => {
      setState("checking");
      setError(null);
      try {
        const updater = await import("@tauri-apps/plugin-updater");
        const update = (await updater.check()) as TauriUpdate | null;
        if (cancelled) return;
        if (update?.available) {
          updateRef.current = update;
          setVersion(update.version);
          setNotes(update.body || null);
          setState("available");
        } else {
          setState("idle");
        }
      } catch (caught) {
        if (cancelled) return;
        const message = caught instanceof Error ? caught.message : String(caught);
        console.info("[ATANOR updater] update check skipped:", message);
        if (shouldSurfaceUpdaterErrors()) {
          setError(message);
          setState("error");
        } else {
          setError(null);
          setState("unavailable");
        }
      }
    };

    void run();
    return () => {
      cancelled = true;
    };
  }, []);

  const installAndRestart = useCallback(async () => {
    if (!updateRef.current) return;
    setState("installing");
    setError(null);
    try {
      await updateRef.current.downloadAndInstall();
      setState("restarting");
      const process = await import("@tauri-apps/plugin-process");
      await process.relaunch();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
      setState("error");
    }
  }, []);

  const dismiss = useCallback(() => {
    if (state === "available" || state === "error") {
      setState("idle");
    }
  }, [state]);

  return {
    state,
    error,
    version,
    notes,
    isAvailable: state === "available",
    isInstalling: state === "installing" || state === "restarting",
    installAndRestart,
    dismiss,
  };
}
