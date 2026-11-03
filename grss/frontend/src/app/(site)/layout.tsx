import { Footer, Header } from "@/components/hds";

/** Landing site: Horizon Design System (nasa.gov) stylesheet, header and footer. */
export default function SiteLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="hds-site">
      {/* eslint-disable-next-line @next/next/no-css-tags */}
      <link rel="stylesheet" href="/hds/hds.css" />
      <Header />
      <main id="main">{children}</main>
      <Footer />
    </div>
  );
}
