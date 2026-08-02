import { NextResponse } from "next/server";
import { proxyJson } from "../../../_backend";

export async function POST(request: Request) {
  const body = await request.json().catch(() => ({}));
  const proxied = await proxyJson("/api/cloud-brain/anna-archive/search", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return NextResponse.json(
    proxied?.body ?? {
      provider: "anna_archive",
      mode: "metadata_only",
      status: "disabled_or_unconfigured",
      records: [],
      rejected: 0,
      policy: {
        full_text_downloads: false,
        raw_text_storage: false,
        download_url_storage: false,
        local_brain_write: false,
      },
    },
    { status: proxied?.status ?? 200 },
  );
}
