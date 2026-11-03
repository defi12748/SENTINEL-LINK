import type { Metadata } from "next";

export const metadata: Metadata = { title: "Live Demo" };

/** Full-screen presenter deck in the Horizon Design System: same stylesheet, no site header or footer. */
export default function DemoLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="hds-site">
      {/* eslint-disable-next-line @next/next/no-css-tags */}
      <link rel="stylesheet" href="/hds/hds.css" />
      {children}
    </div>
  );
}
