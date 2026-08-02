import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ATANOR",
  description: "Transparent Anomy neuro-symbolic local AI engine.",
  icons: {
    icon: "/favicon.ico",
    shortcut: "/favicon.ico",
  },
  other: {
    google: "notranslate",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html className="notranslate" lang="en" translate="no">
      <body>{children}</body>
    </html>
  );
}
