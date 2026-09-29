import { ArrowRight } from "lucide-react";
import { LinkButton } from "@/components/shared/primitives";
import { SkyBackground, SkyPlayback } from "./sky-background";
export function SkyHero() {
  return (
    <section className="sky-hero career-home-hero">
      <SkyBackground className="home-sky-photo" />
      <div className="sky-hero-copy home-width">
        <span className="sky-eyebrow">내 경험에서 시작하는 다음 커리어</span>
        <h1 tabIndex={-1}>
          쌓아온 경험을,
          <br />
          다음 기회로.
        </h1>
        <p>내 기술을 확인하고, 원하는 직무에 필요한 준비를 시작하세요.</p>
        <div className="sky-hero-actions">
          <LinkButton href="/my-skills">
            내 역량 확인하기 <ArrowRight size={17} />
          </LinkButton>
          <LinkButton href="/dashboard" secondary>
            예시로 둘러보기
          </LinkButton>
        </div>
      </div>
      <SkyPlayback />
    </section>
  );
}
