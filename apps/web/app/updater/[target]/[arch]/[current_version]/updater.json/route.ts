import { NextResponse } from "next/server";

type UpdateParams = {
  target: string;
  arch: string;
  current_version: string;
};

export const dynamic = "force-dynamic";

export async function GET(
  _request: Request,
  { params }: { params: Promise<UpdateParams> },
) {
  const resolvedParams = await params;
  const currentVersion = decodeURIComponent(resolvedParams.current_version || "0.1.0").replace(/^v/, "");

  return NextResponse.json(
    {
      version: currentVersion,
      notes:
        "ATANOR alpha updater channel is live. No newer signed patch is published for this desktop channel yet.",
      pub_date: "2026-06-13T00:00:00Z",
      platforms: {},
    },
    {
      headers: {
        "Cache-Control": "no-store, max-age=0",
      },
    },
  );
}
