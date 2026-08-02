/**
 * Build/runtime profile. ONE codebase, two faces:
 *   - "full" (default): New ATANOR — the central particle orb + 3D + the
 *     infinite-possibility dashboard. The version developed personally.
 *   - "demo": a lean GPT/Gemini/Claude-style chat that showcases the engine
 *     (reasoning + grounded answers) with no orb / particles / 3D in the home.
 *
 * The ENGINE is identical for both (same /api/chat/atanor backend), so engine
 * improvements land in both with zero merge-back. Switch with the env var
 * NEXT_PUBLIC_ATANOR_PROFILE=demo (set per Vercel project / per local port).
 */
export type AtanorProfile = "full" | "demo";

export const ATANOR_PROFILE: AtanorProfile =
  (process.env.NEXT_PUBLIC_ATANOR_PROFILE as AtanorProfile) === "demo" ? "demo" : "full";

export const isDemo = ATANOR_PROFILE === "demo";
