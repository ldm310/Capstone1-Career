import { Header } from "@/components/layout/header";
import { SkyExperience } from "@/components/landing/sky-experience";
import { SkyHero } from "@/components/landing/sky-hero";
import { FeatureNavigation } from "@/components/landing/feature-navigation";
import { LiveJobsSection } from "@/components/landing/live-jobs-section";
import Link from "next/link";
import "./sky.css";
import "./home.css";
import "./feature-pages.css";
export default function Home() {
  return (
    <SkyExperience>
      <Header />
      <main>
        <SkyHero />
        <FeatureNavigation />
        <LiveJobsSection />
      </main>
      <footer className="home-footer home-width">
        <span>Career · 경험에서 시작하는 다음 커리어</span>
        <Link href="/dashboard">예시로 둘러보기 ↗</Link>
      </footer>
    </SkyExperience>
  );
}
