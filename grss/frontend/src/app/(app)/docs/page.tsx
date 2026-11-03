import { PageIntro, TopicGrid } from "@/components/hds";
import { DOCS } from "@/lib/docs";
import { PHOTO_LIST, PHOTOS } from "@/lib/photos";

export default function DocsPage() {
  return (
    <>
      <PageIntro kicker="Deliverables" title="Documentation" image={PHOTOS.aurora} />
      <TopicGrid dark heading="Six Deliverables and a Compliance Matrix" button="Results" buttonHref="/results"
        cards={DOCS.map((d, i) => ({ title: d.short, href: `/docs/${d.slug}`, image: PHOTO_LIST[(i + 3) % PHOTO_LIST.length] }))} />
    </>
  );
}
