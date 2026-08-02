"use client";

import { useEffect } from "react";

// /lite is a convenience link for the demo. The demo now lives INSIDE the ATANOR
// frame (sidebar/panels kept), toggled by ?profile=demo — so redirect there.
export default function LiteRoute() {
  useEffect(() => {
    window.location.replace("/?profile=demo&section=home");
  }, []);
  return null;
}
