"use client";

import { marked } from "marked";
import { useParams } from "next/navigation";
import { Module, PageIntro } from "@/components/hds";
import { api } from "@/lib/api";
import { DOCS } from "@/lib/docs";
import { useApi } from "@/lib/hooks";

export default function DocPage() {
  const { slug } = useParams<{ slug: string }>();
  const meta = DOCS.find(d => d.slug === slug);
  const { data, error } = useApi(() => api.doc(slug), [slug]);
  // Docs are our own repository files, rendered as-is.
  const html = data ? (marked.parse(data.markdown.replace(/^# .*\n/, "")) as string) : "";
  return (
    <>
      <PageIntro kicker={meta?.read ?? "Document"} title={meta?.title ?? slug} />
      <Module tone="light">
        {error && <p className="mono red">{error}</p>}
        {!data && !error && <span className="spinner" />}
        <article className="usa-prose doc-body" style={{ maxWidth: 860 }} dangerouslySetInnerHTML={{ __html: html }} />
      </Module>
    </>
  );
}
