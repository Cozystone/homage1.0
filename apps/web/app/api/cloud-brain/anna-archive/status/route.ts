import { NextResponse } from "next/server";
import { proxyJson } from "../../../_backend";

const FALLBACK = {
  provider: "anna_archive",
  mode: "metadata_only",
  status: "disabled_or_unconfigured",
  config: {
    enabled: false,
    configured: false,
    metadata_only: true,
    full_text_downloads_allowed: false,
    local_brain_write: false,
  },
  policy: {
    full_text_downloads: false,
    raw_text_storage: false,
    download_url_storage: false,
    local_brain_write: false,
  },
};

export async function GET() {
  const proxied = await proxyJson("/api/cloud-brain/anna-archive/status");
  return NextResponse.json(proxied?.body ?? FALLBACK, { status: proxied?.status ?? 200 });
}
