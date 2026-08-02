/** @type {import('next').NextConfig} */
const desktopExport = process.env.HOMAGE_TAURI_EXPORT === "1";

const nextConfig = {
  reactStrictMode: false,
  ...(desktopExport
    ? {
        output: "export",
        images: {
          unoptimized: true,
        },
        // The desktop bundle is a packaging step, not the type/lint gate — those run
        // strictly in the normal build and in dev. Don't let a latent type error in a
        // runtime-only WebGL viewer (works in dev, never SSR'd) block the installer.
        typescript: { ignoreBuildErrors: true },
        eslint: { ignoreDuringBuilds: true },
      }
    : {}),
};

export default nextConfig;
