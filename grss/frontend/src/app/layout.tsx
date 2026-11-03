import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "Sentinel Link", template: "%s | Sentinel Link" },
  description: "Secure ground-link testbed for satellite telemetry recordings.",
  icons: { icon: "/brand/icon.svg" },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
