"use client";

/* Horizon Design System blocks: same DOM and classes as nasa.gov, our content. */
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { Mark } from "./SiteHeader";

const ARROW = "M8 16.956h12.604l-3.844 4.106 1.252 1.338L24 16l-5.988-6.4-1.252 1.338 3.844 4.106H8v1.912z";

export const NAV = [
  { href: "/demo", label: "Live Demo" },
  { href: "/challenge", label: "Challenge" },
  { href: "/attack-lab", label: "Attack Lab" },
  { href: "/nasa", label: "NASA Modules" },
  { href: "/trust", label: "Trust" },
  { href: "/results", label: "Results" },
  { href: "/passes", label: "Passes" },
  { href: "/docs", label: "Docs" },
];

export function Arrow({ topic = false }: { topic?: boolean }) {
  return (
    <svg viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
      <circle className={topic ? "color-nasa-red" : "button-primary-circle"} cx="16" cy="16" r="16" />
      <path d={ARROW} className="color-spacesuit-white" />
    </svg>
  );
}

export function PrimaryLink({ href, children, size = "", white = false }: {
  href: string; children: ReactNode; size?: "" | "sm" | "md"; white?: boolean;
}) {
  return (
    <Link className={`button-primary ${size ? `button-primary-${size}` : ""} link-external-false`} href={href}>
      <span className={`line-height-alt-1 ${white ? "color-spacesuit-white-important" : ""}`}>{children}</span>
      <Arrow />
    </Link>
  );
}

function NavLink({ href, label }: { href: string; label: string }) {
  const path = usePathname();
  const active = path === href || (href !== "/" && path.startsWith(href));
  return (
    <li className="usa-nav__primary-item">
      <Link href={href} className="usa-nav__link heading-16 color-spacesuit-white padding-y-2 padding-x-2 display-flex flex-align-center"
        style={{ whiteSpace: "nowrap", boxShadow: active ? "inset 0 -3px 0 #f64137" : undefined }}>
        <span>{label}</span>
      </Link>
    </li>
  );
}

export function Header() {
  const left = NAV.slice(0, 4);
  const right = NAV.slice(4);
  return (
    <>
      <header className="hds-nasa-header usa-header usa-header-mobile color-spacesuit-white bg-carbon-black display-block desktop:display-none padding-x-2 padding-y-2">
        <div className="display-flex flex-justify-center margin-bottom-1">
          <Link href="/" className="usa-logo display-block margin-0"><Mark size={46} /></Link>
        </div>
        <nav aria-label="Primary navigation" style={{ overflowX: "auto" }}>
          <ul className="usa-nav__primary display-flex" style={{ listStyle: "none", margin: 0, padding: 0, justifyContent: "flex-start" }}>
            {NAV.map(l => <NavLink key={l.href} {...l} />)}
          </ul>
        </nav>
      </header>
      <header className="usa-header usa-header--basic usa-header-primary padding-y-2 padding-x-2 bg-carbon-black color-spacesuit-white display-none desktop:display-block">
        <div className="usa-nav-container padding-0 grid-container grid-container-extrawide grid-row">
          <nav aria-label="Primary navigation" className="grid-col-5 display-flex flex-align-center" style={{ minWidth: 0 }}>
            <ul className="hds-nav-primary color-spacesuit-white usa-nav__primary display-flex" style={{ listStyle: "none", margin: 0, padding: 0 }}>
              {left.map(l => <NavLink key={l.href} {...l} />)}
            </ul>
          </nav>
          <div className="grid-col-2 display-flex flex-justify-center flex-align-center">
            <Link id="header-logo" href="/" className="usa-logo tablet:display-block margin-0" style={{ width: 60, position: "relative", zIndex: 10 }}
              onClick={() => { if (window.location.pathname === "/") window.scrollTo({ top: 0, behavior: "smooth" }); }}><Mark size={56} /></Link>
          </div>
          <nav aria-label="Secondary navigation" className="grid-col-5 display-flex flex-align-center flex-justify-end" style={{ minWidth: 0 }}>
            <ul className="hds-nav-primary color-spacesuit-white usa-nav__primary display-flex" style={{ listStyle: "none", margin: 0, padding: 0 }}>
              {right.map(l => <NavLink key={l.href} {...l} />)}
            </ul>
          </nav>
        </div>
      </header>
    </>
  );
}

export function LinkStrip({ when, title, text, image, href }: { when: ReactNode; title: string; text: string; image: string; href: string }) {
  return (
    <div className="hds-featured-link-list bg-spacesuit-white padding-x-2 tablet:padding-x-3 desktop:padding-x-4 padding-y-5 desktop:padding-y-6 hds-module hds-module-full alignfull wp-block-nasa-blocks-featured-link-list">
      <div className="grid-container grid-container-block padding-0">
        <div className="margin-bottom-4"><h2 className="heading-22">{when}</h2></div>
        <div className="grid-row padding-y-2 border-top-1px border-color-carbon-30-important">
          <div className="grid-row featured-link-list-row width-full flex-align-center">
            <div className="grid-col-2 desktop:grid-col-1 tablet:padding-right-3 desktop:padding-right-5">
              <div className="width-full">
                <div className="hds-cover-wrapper width-full ratio-1x1 radius-pill overflow-hidden">
                  <figure className="hds-media-background"><img alt="" src={image} style={{ objectFit: "cover" }} /></figure>
                </div>
              </div>
            </div>
            <div className="grid-col-8 desktop:grid-col-10 padding-left-3 desktop:padding-left-0">
              <div className="grid-row flex-align-center">
                <div className="grid-col-12 desktop:grid-col-6"><h2 className="heading-36 margin-0">{title}</h2></div>
                <div className="grid-col-12 desktop:grid-col-6"><p className="p-md margin-0 color-carbon-black">{text}</p></div>
              </div>
            </div>
            <div className="grid-col-2 desktop:grid-col-1 display-flex flex-justify-end">
              <Link aria-label={title} href={href}>
                <svg className="hds-featured-link-list-button margin-left-auto margin-right-0" fill="none" viewBox="0 0 32 32" width="40" height="40">
                  <circle className="button-primary-circle" cx="16" cy="16" r="16" />
                  <path d={ARROW} className="color-spacesuit-white" />
                </svg>
              </Link>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export interface MagSlide {
  title: string; text: string; cta: string; href: string; thumb: string;
  media: ReactNode; cols: { label: string; link: string; href: string }[];
}

/** NASA Mag: full-bleed slides with auto-advance and progress-ring thumbnails. */
export function MagHero({ slides, interval = 9000 }: { slides: MagSlide[]; interval?: number }) {
  const [i, setI] = useState(0);
  const [paused, setPaused] = useState(false);
  const [t0, setT0] = useState(() => Date.now());
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (paused) return;
    const id = setInterval(() => {
      const n = Date.now();
      setNow(n);
      if (n - t0 >= interval) { setI(k => (k + 1) % slides.length); setT0(n); }
    }, 100);
    return () => clearInterval(id);
  }, [paused, t0, interval, slides.length]);
  const s = slides[i];
  const frac = paused ? 0 : Math.min(1, (now - t0) / interval);
  return (
    <div className="hds-nasa-mag padding-0 hds-module hds-module-full alignfull wp-block-nasa-blocks-nasa-mag">
      <div className="hds-carousel-wrapper" role="group" aria-roledescription="carousel" aria-label="Highlights">
        <div className="hds-nasa-mag-wrapper hds-cover-wrapper width-full maxw-full bg-carbon-black minh-tablet color-mode-dark" style={{ minHeight: "min(84vh, 820px)" }}>
          <div className="hds-foreground-wrapper display-flex flex-column">
            <div className="hds-nasa-mag-slide-inner grid-row grid-container width-full grid-container-extrawide margin-y-auto padding-x-3 desktop:padding-x-3 desktop:padding-top-6 desktop:padding-bottom-3 z-400">
              <div className="grid-row width-full maxw-full">
                <div className="grid-col-12 tablet:grid-col-6 desktop:grid-col-6">
                  <h2 className="display-72 margin-bottom-1 color-spacesuit-white">{s.title}</h2>
                  <p className="maxw-tablet color-spacesuit-white">{s.text}</p>
                  <Link className="usa-button usa-button--secondary bg-nasa-red" href={s.href}>{s.cta}</Link>
                </div>
              </div>
            </div>
            <div className="hds-mag-nav-cols grid-container grid-row width-full grid-container-extrawide margin-top-auto margin-bottom-0 padding-x-3 padding-bottom-2 desktop:padding-bottom-5 z-400">
              {s.cols.map(c => (
                <div key={c.label} className="hds-nasa-mag-col grid-col-12 tablet:grid-col-4 desktop:grid-col-3 padding-right-2">
                  <div className="hds-nasa-mag-col-inner border-top-1px padding-y-1 desktop:padding-bottom-0 desktop:padding-top-2">
                    <h3 className="label color-spacesuit-white">{c.label}</h3>
                    <Link className="button-primary button-primary-sm link-external-false" href={c.href}>
                      <span className="line-height-alt-1 color-spacesuit-white-important">{c.link}</span><Arrow />
                    </Link>
                  </div>
                </div>
              ))}
            </div>
          </div>
          <div className="skrim-overlay skrim-left mobile-skrim-top z-200" />
          <figure className="hds-media-background">{s.media}</figure>
          <div className="hds-mag-progress-wrapper" style={{ position: "absolute", right: "1.5rem", bottom: "2.5rem", zIndex: 500, display: "flex", gap: ".6rem" }}>
            {slides.map((sl, k) => (
              <button key={sl.title} aria-label={`Show ${sl.title}`} className="hds-mag-progress" onClick={() => { setI(k); setT0(Date.now()); }}
                style={{ width: 50, height: 50, borderRadius: "50%", overflow: "hidden", position: "relative", padding: 0, cursor: "pointer",
                  border: k === i ? "2px solid #fff" : "2px solid transparent", background: "#000" }}>
                <img alt="" src={sl.thumb} style={{ width: "100%", height: "100%", objectFit: "cover", opacity: k === i ? 1 : .6 }} />
                {k === i && (
                  <svg width="50" height="50" style={{ position: "absolute", inset: -2, transform: "rotate(-90deg)" }} aria-hidden="true">
                    <circle cx="25" cy="25" r="23" fill="transparent" stroke="#f64137" strokeWidth="3"
                      strokeDasharray={144.5} strokeDashoffset={144.5 * (1 - frac)} />
                  </svg>
                )}
              </button>
            ))}
            <button aria-label={paused ? "Play slideshow" : "Pause slideshow"} className="hds-mag-progress hds-mag-pause-play"
              onClick={() => { setPaused(!paused); setT0(Date.now()); }}
              style={{ width: 50, height: 50, borderRadius: "50%", background: "#000", border: 0, display: "grid", placeItems: "center", cursor: "pointer" }}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="#fff" aria-hidden="true">
                {paused ? <path d="M8 5v14l11-7z" /> : <path d="m2 1v22h7v-22zm13 0v22h7v-22z" />}
              </svg>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export interface NewsItem { kind: string; meta: string; title: string; image: string; href: string }
export interface BubbleItem { meta: string; title: string; date: string; kind: string; image: string; href: string }

function NewsCard({ item, className }: { item: NewsItem; className: string }) {
  return (
    <Link className={className} href={item.href}>
      <div className="hds-cover-wrapper cover-hover-zoom bg-carbon-black">
        <div className="skrim-overlay skrim-overlay-dark skrim-left mobile-skrim-top padding-3 display-flex flex-column flex-align-start flex-justify-start z-200">
          <div className="display-flex flex-align-center label color-spacesuit-white margin-bottom-auto"><span>{item.kind}</span></div>
          <div className="display-block">
            <div className="label margin-bottom-1">{item.meta}</div>
            <p className="heading-22 color-spacesuit-white margin-0"><span>{item.title}</span></p>
          </div>
        </div>
        <figure className="hds-media-background"><img alt="" src={item.image} style={{ objectFit: "cover" }} /></figure>
      </div>
    </Link>
  );
}

export function FeaturedNews({ heading, button, buttonHref, items, bubbles = [] }: {
  heading: string; button: string; buttonHref: string; items: NewsItem[]; bubbles?: BubbleItem[];
}) {
  const [a, b, c, d] = items;
  return (
    <div className="nasa-gb-align-full maxw-full width-full padding-y-6 padding-x-3 hds-color-mode-light color-mode-light bg-spacesuit-white hds-module hds-module-full alignfull wp-block-nasa-blocks-news-manual">
      <div className="grid-container grid-container-block">
        <div className="grid-row flex-align-center margin-bottom-3">
          <div className="desktop:grid-col margin-bottom-2 desktop:margin-bottom-0"><h2 className="section-heading-md">{heading}</h2></div>
          <div className="desktop:grid-col display-flex flex-align-center desktop:flex-justify-end">
            <PrimaryLink href={buttonHref}>{button}</PrimaryLink>
          </div>
        </div>
        <div className="grid-col">
          <div className="grid-row latest-news-items">
            {a && (
              <div className="grid-col mobile:grid-col tablet:grid-col-12 desktop:grid-col latest-news-item latest-news-item-0 margin-bottom-2 desktop:margin-bottom-0 padding-right-0 desktop:padding-right-2">
                <NewsCard item={a} className="tablet:grid-col latest-news-item news-item tablet:padding-right-0" />
              </div>
            )}
            <div className="tablet:grid-col grid-row latest-news-items">
              {b && <NewsCard item={b} className="tablet:grid-col latest-news-item news-item margin-bottom-2 tablet:margin-bottom-0 desktop:margin-bottom-0 tablet:padding-right-2 desktop:padding-right-2" />}
              <div className="grid-col news-item-stack">
                {c && <NewsCard item={c} className="tablet:grid-col latest-news-item news-item tablet:margin-right-0 desktop:margin-right-0 margin-bottom-2" />}
                {d && <NewsCard item={d} className="tablet:grid-col latest-news-item news-item tablet:margin-right-0 desktop:margin-right-0 margin-bottom-2 desktop:margin-bottom-0" />}
              </div>
            </div>
          </div>
        </div>
        {bubbles.length > 0 && (
          <div className="grid-row padding-top-2 desktop:padding-top-3">
            {bubbles.map(bb => (
              <Link key={bb.title} href={bb.href} className="mobile:grid-col-6 tablet:grid-col-6 desktop:grid-col padding-left-0 padding-right-0 desktop:padding-right-2 padding-bottom-4 desktop:padding-bottom-0">
                <div className="display-flex hds-news-item-bubble">
                  <div className="padding-right-3">
                    <div className="hds-cover-wrapper cover-hover-zoom bg-carbon-black circle-10 minw-10 maxh-10 minh-10">
                      <figure className="hds-media-background"><img alt="" src={bb.image} style={{ objectFit: "cover" }} /></figure>
                    </div>
                  </div>
                  <div>
                    <div className="label margin-bottom-1 color-carbon-black">{bb.meta}</div>
                    <p className="heading-14 color-carbon-black line-height-md margin-top-1 margin-bottom-1">{bb.title}</p>
                    <div className="display-flex flex-align-center label color-carbon-60 margin-bottom-1 margin-top-1">{bb.date}</div>
                    <div className="display-flex flex-align-center label color-carbon-60 margin-bottom-auto"><span>{bb.kind}</span></div>
                  </div>
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export function Callout({ title, text, button, href, image }: { title: string; text: string; button: string; href: string; image: string }) {
  return (
    <div className="width-full maxw-full bg-carbon-05 hds-cover-wrapper minh-tablet-lg hds-module hds-module-full alignfull wp-block-nasa-blocks-callout">
      <div className="hds-foreground-wrapper padding-bottom-9 padding-top-9 display-flex">
        <div className="grid-row grid-container grid-container-block margin-top-auto width-full maxw-desktop-lg padding-y-9 padding-x-3 z-400">
          <div className="grid-col-12 tablet:grid-col-12 desktop:grid-col-6 z-400">
            <div className="margin-0">
              <h2 className="page-heading-md font-weight-extrabold line-height-heading-1 color-spacesuit-white-important">{title}</h2>
              <p className="p-lg margin-top-2 padding-0 margin-bottom-4 color-spacesuit-white-important">{text}</p>
              <PrimaryLink href={href} white>{button}</PrimaryLink>
            </div>
          </div>
        </div>
      </div>
      <div className="skrim-overlay skrim-left mobile-skrim-top z-200" />
      <figure className="hds-media-background"><img alt="" src={image} style={{ objectFit: "cover", transform: "scale(1.1)" }} /></figure>
    </div>
  );
}

export function TopicGrid({ heading, button, buttonHref, dark = true, cards }: {
  heading: string; button: string; buttonHref: string; dark?: boolean; cards: { title: string; href: string; image: string }[];
}) {
  return (
    <div className={`hds-card-grid padding-top-7 padding-bottom-3 padding-x-0 ${dark ? "hds-color-mode-dark color-mode-dark bg-carbon-90" : "hds-color-mode-light color-mode-light bg-spacesuit-white"} hds-module hds-module-full alignfull wp-block-nasa-blocks-card-grid`}>
      <div className="hds-card-grid-header grid-container grid-container-block">
        <div className="grid-row flex-align-start margin-bottom-5">
          <div className="desktop:grid-col-8 margin-bottom-2 desktop:margin-bottom-0">
            <div className="margin-bottom-1"><h2 className="section-heading-sm line-height-sm">{heading}</h2></div>
          </div>
          <div className="desktop:grid-col display-flex flex-align-center desktop:flex-justify-end">
            <PrimaryLink href={buttonHref} white={dark}>{button}</PrimaryLink>
          </div>
        </div>
      </div>
      <div className="hds-card-grid-cards grid-container grid-container-block">
        <div className="hds-cards-included grid-row">
          {cards.map(c => (
            <Link key={c.title} href={c.href} className="hds-card-topic hds-card margin-bottom-4 desktop:margin-bottom-5 mobile:grid-col-12 tablet:grid-col-6 desktop:grid-col-3 margin-bottom-6">
              <div className="hds-card-inner">
                <div className="hds-foreground-wrapper z-300 display-flex flex-direction-column flex-align-end flex-justify-end">
                  <div className="hds-card-content padding-3">
                    <h3 className="heading-29 hds-topic-card-heading color-spacesuit-white"><span>{c.title}</span><Arrow topic /></h3>
                  </div>
                </div>
                <div className="hds-card-thumbnail">
                  <div className="skrim-overlay skrim-overlay-dark skrim-left mobile-skrim-top padding-3 display-flex flex-align-end flex-justify-start z-200" />
                  <figure className="hds-media-background"><img alt="" src={c.image} style={{ objectFit: "cover" }} /></figure>
                </div>
              </div>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}

export function GalleryGrid({ heading, button, buttonHref, cards }: {
  heading: string; button: string; buttonHref: string; cards: { title: string; count: string; images: string[]; href: string }[];
}) {
  return (
    <div className="hds-card-grid padding-top-7 padding-bottom-3 padding-x-0 hds-color-mode-light color-mode-light bg-spacesuit-white hds-module hds-module-full alignfull wp-block-nasa-blocks-card-grid">
      <div className="hds-card-grid-header grid-container grid-container-block">
        <div className="grid-row flex-align-start margin-bottom-5">
          <div className="desktop:grid-col-8 margin-bottom-2 desktop:margin-bottom-0"><h2 className="section-heading-sm line-height-sm">{heading}</h2></div>
          <div className="desktop:grid-col display-flex flex-align-center desktop:flex-justify-end"><PrimaryLink href={buttonHref}>{button}</PrimaryLink></div>
        </div>
      </div>
      <div className="hds-card-grid-cards grid-container grid-container-block">
        <div className="hds-cards-included grid-row">
          {cards.map(c => (
            <Link key={c.title} href={c.href} className="hds-card-gallery hds-card margin-bottom-4 desktop:margin-bottom-5 mobile:grid-col-12 tablet:grid-col-6 desktop:grid-col-4 margin-bottom-6">
              <div className="hds-card-inner">
                <div className="hds-card-gallery-images margin-bottom-2">
                  {c.images.slice(0, 3).map((im, k) => (
                    <figure key={k} className={`hds-media-background hds-card-thumbnail hds-card-gallery-image-${k + 1}`}>
                      <img alt="" src={im} style={{ objectFit: "cover" }} />
                    </figure>
                  ))}
                </div>
                <div className="padding-right-0">
                  <div className="margin-bottom-1"><h3 className="heading-16 color-carbon-black">{c.title}</h3></div>
                  <div className="display-flex color-carbon-50 label"><div className="margin-right-2">{c.count}</div></div>
                </div>
              </div>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}

export function ImageOfTheDay({ kicker, heading, title, text, image, button, href }: {
  kicker: string; heading: string; title: string; text: string; image: string; button: string; href: string;
}) {
  return (
    <div className="hds-image-of-the-day color-mode-light hds-color-mode-light hds-module hds-module-full alignfull bg-spacesuit-white wp-block-nasa-blocks-image-of-the-day">
      <div className="grid-container grid-container-block padding-y-9 padding-x-3">
        <div className="grid-row">
          <div className="grid-col-12 desktop:grid-col-4 desktop:padding-right-5 margin-bottom-6 desktop:margin-bottom-0">
            <div className="margin-bottom-10 display-none tablet:display-block desktop:display-block">
              <h3 className="label">{kicker}</h3>
              <h2 className="display-41 margin-0">{heading}</h2>
            </div>
            <p className="heading-22 margin-bottom-2">{title}</p>
            <p className="p-md">{text}</p>
            <div className="margin-top-1 margin-bottom-1"><PrimaryLink href={href} size="sm">{button}</PrimaryLink></div>
          </div>
          <div className="grid-col-12 desktop:grid-col-8 desktop:padding-left-5">
            <div className="hds-image-download-wrapper width-full display-block">
              <div className="hds-media-wrapper margin-left-auto margin-right-auto">
                <figure className="hds-media-inner hds-cover-wrapper hds-media-ratio-fit">
                  <img alt="" src={image} style={{ width: "100%" }} />
                </figure>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export function SubscriptionBanner({ title, text, button, href }: { title: string; text: string; button: string; href: string }) {
  return (
    <div className="hds-cover-wrapper hds-subscription z-400 width-full maxw-full padding-x-3 padding-y-4 bg-carbon-black color-spacesuit-white hds-module hds-module-full alignfull wp-block-nasa-blocks-subscription-banner">
      <div className="hds-subscription-inner grid-container-block width-full grid-container padding-y-3 padding-x-0 desktop:padding-y-6 desktop:padding-x-4 z-400">
        <div className="grid-col-12 desktop:grid-col-5 desktop:padding-right-5 desktop:margin-bottom-0">
          <div className="margin-bottom-5"><h2 className="display-41 line-height-normal">{title}</h2></div>
          <div className="margin-bottom-5"><p className="heading-16 hds-subscription-subheading">{text}</p></div>
          <PrimaryLink href={href} size="md" white>{button}</PrimaryLink>
        </div>
      </div>
    </div>
  );
}

export function Story({ subtitle, title, lead, text, image, caption, credit, button, href }: {
  subtitle: string; title: string; lead: string; text: string; image: string; caption: string; credit: string; button: string; href: string;
}) {
  return (
    <div className="hds-story width-full maxw-full bg-carbon-05 hds-module hds-module-full alignfull wp-block-nasa-blocks-story">
      <div className="grid-container grid-container-block padding-y-9 padding-x-4">
        <div className="grid-row">
          <div className="grid-col-12 desktop:grid-col-6 desktop:padding-right-5 margin-bottom-6 desktop:margin-bottom-0">
            <div className="margin-bottom-2"><h3 className="subtitle-md">{subtitle}</h3></div>
            <div className="margin-bottom-2"><h2 className="display-48">{title}</h2></div>
            <div className="margin-bottom-2"><p className="heading-18 line-height-md">{lead}</p></div>
            <p className="p-md">{text}</p>
            <PrimaryLink href={href} size="md">{button}</PrimaryLink>
          </div>
          <div className="grid-col-12 desktop:grid-col-6 desktop:padding-left-5">
            <div className="width-full display-block">
              <div className="hds-media-wrapper margin-left-auto margin-right-auto">
                <figure className="hds-media-inner hds-cover-wrapper hds-media-ratio-cover">
                  <img alt="" src={image} style={{ width: "100%", objectFit: "cover" }} />
                </figure>
                <figcaption className="hds-caption padding-y-2">
                  <div className="hds-caption-text p-sm margin-0">{caption}</div>
                  <div className="hds-credits">{credit}</div>
                </figcaption>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

/** Interior-page header in the HDS article style. */
export function PageIntro({ kicker, title, text, image }: { kicker: string; title: string; text?: string; image?: string }) {
  const body = (
    <div className="grid-container grid-container-block margin-top-auto width-full padding-x-3 padding-y-6">
      <h3 className="label color-nasa-red margin-bottom-2">{kicker}</h3>
      <h1 className="display-72 margin-0 color-spacesuit-white">{title}</h1>
      {text && <p className="p-lg maxw-tablet margin-top-2 color-spacesuit-white">{text}</p>}
    </div>
  );
  if (!image) return <div className="bg-carbon-black color-spacesuit-white padding-top-4">{body}</div>;
  return (
    <div className="hds-cover-wrapper width-full maxw-full bg-carbon-black color-spacesuit-white color-mode-dark" style={{ minHeight: 420 }}>
      <div className="hds-foreground-wrapper display-flex flex-column z-400" style={{ minHeight: 420 }}>{body}</div>
      <div className="skrim-overlay skrim-left mobile-skrim-top z-200" />
      <figure className="hds-media-background"><img alt="" src={image} style={{ objectFit: "cover" }} /></figure>
    </div>
  );
}

export function Module({ id, tone = "dark", children }: { id?: string; tone?: "dark" | "black" | "light" | "grey"; children: ReactNode }) {
  const cls = {
    dark: "bg-carbon-90 color-mode-dark hds-color-mode-dark color-spacesuit-white",
    black: "bg-carbon-black color-mode-dark hds-color-mode-dark color-spacesuit-white",
    light: "bg-spacesuit-white color-mode-light hds-color-mode-light",
    grey: "bg-carbon-05 color-mode-light hds-color-mode-light",
  }[tone];
  return (
    <div id={id} className={`hds-module hds-module-full alignfull width-full maxw-full padding-y-9 ${cls}`}>
      <div className="grid-container grid-container-block padding-x-3">{children}</div>
    </div>
  );
}

export function SectionHead({ title, button, href }: { title: string; button?: string; href?: string }) {
  return (
    <div className="grid-row flex-align-center margin-bottom-5">
      <div className="desktop:grid-col margin-bottom-2 desktop:margin-bottom-0"><h2 className="section-heading-md">{title}</h2></div>
      {button && href && (
        <div className="desktop:grid-col display-flex flex-align-center desktop:flex-justify-end"><PrimaryLink href={href}>{button}</PrimaryLink></div>
      )}
    </div>
  );
}

export function Footer() {
  return (
    <footer className="usa-footer bg-carbon-black-important padding-x-3 padding-y-7">
      <div className="usa-footer__primary-section bg-carbon-black-important">
        <div className="grid-container grid-container-widescreen padding-x-0 margin-bottom-2"><Mark size={64} /></div>
        <div className="grid-container grid-container-widescreen">
          <div className="grid-row">
            <div className="grid-col-12 tablet:grid-col-6 desktop:grid-col-4 margin-bottom-5 padding-right-0 tablet:padding-right-2 desktop:margin-bottom-0 color-spacesuit-white">
              <div className="hds-footer-details">
                <h3 className="heading-22 line-height-md">Sentinel Link</h3>
                <p className="p-sm color-carbon-30">Secure ground-link testbed.</p>
                <PrimaryLink href="/attack-lab" size="sm" white>Try the Attack Lab</PrimaryLink>
              </div>
            </div>
            <div className="grid-col-12 tablet:grid-col-6 desktop:grid-col-6 margin-bottom-5 desktop:margin-bottom-0 padding-0">
              <div className="desktop:padding-left-5 desktop:padding-right-5 grid-row color-spacesuit-white">
                <div className="grid-col">
                  <ul className="hds-footer-menu hds-menu-col-3 usa-unstyled-list">
                    <li><Link href="/"><span>Home</span></Link></li>
                    {NAV.map(l => <li key={l.href}><Link href={l.href}><span>{l.label}</span></Link></li>)}
                  </ul>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </footer>
  );
}
