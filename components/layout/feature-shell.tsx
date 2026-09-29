"use client";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { Header } from "./header";
import {
  featureSections,
  selectedSectionTab,
  type FeatureSection,
} from "@/lib/feature-sections";
export function FeatureShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname(),
    params = useSearchParams();
  const section =
    (Object.keys(featureSections) as FeatureSection[]).find(
      (key) => featureSections[key].path === pathname,
    ) || "skills";
  const info = featureSections[section],
    tab = selectedSectionTab(section, params.get("tab"));
  return (
    <div className="feature-site sky-home">
      <a className="skip-link" href="#feature-content">
        본문으로 바로가기
      </a>
      <Header />
      <main id="feature-content" className="feature-content home-width">
        <div className="feature-breadcrumb">
          <Link href="/">홈</Link>
          <span aria-hidden="true">/</span>
          <span>{info.title}</span>
        </div>
        <header className="feature-page-heading">
          <span>CAREER</span>
          <h1>{info.title}</h1>
          <p>{info.description}</p>
        </header>
        <nav className="feature-tabs" aria-label={`${info.title} 하위 메뉴`}>
          {info.tabs.map(([key, label], index) => (
            <Link
              key={key}
              href={index === 0 ? info.path : `${info.path}?tab=${key}`}
              aria-current={tab === key ? "page" : undefined}
            >
              {label}
            </Link>
          ))}
        </nav>
        <div className="feature-body" key={tab}>
          {children}
        </div>
      </main>
      <footer className="home-footer home-width">
        <Link href="/">Career 홈으로</Link>
        <span>경험에서 시작하는 다음 커리어</span>
      </footer>
    </div>
  );
}
