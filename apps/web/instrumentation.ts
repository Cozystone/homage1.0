// Process-level resilience for the Next server.
//
// Why: the dashboard's API routes proxy the local engine (:8502). When the engine
// is briefly down (watchdog memory-recycle, a reboot, a manual restart), those
// `await fetch(:8502)` calls reject with `fetch failed` / ECONNREFUSED. If a route
// lets that reject escape, Next's dev error-normalizer then trips on read-only
// `error.message` ("Cannot set property message ... which has only a getter") and
// the escaped rejection takes down the whole `next dev` process — the engine coming
// back does NOT bring the frontend back. This turns a transient backend blip into a
// full frontend outage.
//
// This registers Node-level handlers so a transient network rejection is logged and
// swallowed instead of crashing the server. Real programming errors are left to
// surface normally.
export function register() {
  if (process.env.NEXT_RUNTIME !== "nodejs") return;

  const TRANSIENT =
    /ECONNREFUSED|ECONNRESET|fetch failed|socket hang up|UND_ERR|ETIMEDOUT|EPIPE|Cannot set property message/i;

  const describe = (err: unknown): string => {
    if (err && typeof err === "object") {
      const e = err as { message?: unknown; cause?: unknown };
      return `${String(e.message ?? err)} | cause=${String(e.cause ?? "")}`;
    }
    return String(err);
  };

  process.on("unhandledRejection", (reason) => {
    // A rejected promise never corrupts process state — always safe to swallow.
    // Log so the outage is still visible in the server log.
    console.warn("[instrumentation] swallowed unhandledRejection:", describe(reason));
  });

  process.on("uncaughtException", (err) => {
    const text = describe(err);
    if (TRANSIENT.test(text)) {
      console.warn("[instrumentation] swallowed transient uncaughtException:", text);
      return;
    }
    // Not a known-transient network error — let it surface as a real bug.
    console.error("[instrumentation] uncaughtException (non-transient):", err);
    throw err;
  });
}
