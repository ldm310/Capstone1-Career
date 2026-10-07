import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { homeFeatures, type HomeFeatureId } from "@/lib/home-navigation";

// A shared duotone SVG system: rounded geometry, one stroke weight, no image fonts.
function FeatureIcon({ kind }: { kind: HomeFeatureId }) {
  return (
    <span className={`feature-art feature-art-${kind}`} aria-hidden="true">
      <svg
        viewBox="0 0 64 64"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.3"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        {kind === "jobs" && (
          <>
            <rect
              className="icon-back"
              x="18"
              y="14"
              width="34"
              height="38"
              rx="7"
              stroke="none"
            />
            <rect
              className="icon-front"
              x="11"
              y="22"
              width="39"
              height="29"
              rx="6"
            />
            <path d="M24 22v-5a4 4 0 0 1 4-4h6a4 4 0 0 1 4 4v5M11 33c10 7 29 7 39 0" />
            <rect
              x="26"
              y="32"
              width="9"
              height="7"
              rx="2"
              className="icon-front"
            />
          </>
        )}
        {kind === "studies" && (
          <>
            <rect
              className="icon-back"
              x="13"
              y="15"
              width="42"
              height="38"
              rx="10"
              stroke="none"
            />
            <circle className="icon-front" cx="25" cy="24" r="7" />
            <path d="M12 49v-5a13 13 0 0 1 26 0v5M42 18a7 7 0 0 1 0 14m3 5a11 11 0 0 1 8 11" />
          </>
        )}
        {kind === "skills" && (
          <>
            <rect
              className="icon-back"
              x="17"
              y="11"
              width="33"
              height="40"
              rx="7"
              stroke="none"
            />
            <path d="M20 14h-5a4 4 0 0 0-4 4v7m0 16v5a4 4 0 0 0 4 4h6m24-36h5a4 4 0 0 1 4 4v6" />
            <circle className="icon-front" cx="30" cy="30" r="12" />
            <path d="m25 30 4 4 7-8m3 13 12 12" />
          </>
        )}
        {kind === "prepare" && (
          <>
            <path
              className="icon-back"
              stroke="none"
              d="M12 43h13V30h13V16h15v38H12z"
            />
            <path d="M11 50h14V37h13V24h14M15 29l25-17m-11 0h11v11" />
            <circle className="icon-front" cx="12" cy="50" r="4" />
          </>
        )}
        {kind === "applications" && (
          <>
            <rect
              className="icon-back"
              x="17"
              y="13"
              width="36"
              height="39"
              rx="7"
              stroke="none"
            />
            <rect
              className="icon-front"
              x="11"
              y="18"
              width="38"
              height="35"
              rx="6"
            />
            <path d="M11 29h38M21 12v12m18-12v12m-20 13h4m7 0h4m-15 9h4" />
            <circle className="icon-front" cx="48" cy="46" r="10" />
            <path d="m44 46 3 3 5-6" />
          </>
        )}
        {kind === "growth" && (
          <>
            <rect
              className="icon-back"
              x="11"
              y="10"
              width="43"
              height="43"
              rx="12"
              stroke="none"
            />
            <path d="M15 51h38" />
            <rect
              className="icon-front"
              x="18"
              y="36"
              width="7"
              height="15"
              rx="2"
            />
            <rect
              className="icon-front"
              x="31"
              y="28"
              width="7"
              height="23"
              rx="2"
            />
            <rect
              className="icon-front"
              x="44"
              y="18"
              width="7"
              height="33"
              rx="2"
            />
            <path d="m15 27 12-11 7 5 11-11m-7 0h7v7" />
          </>
        )}
      </svg>
    </span>
  );
}
export function FeatureNavigation() {
  return (
    <section
      className="home-features home-width"
      id="features"
      aria-labelledby="features-title"
    >
      <div className="home-section-heading">
        <h2 id="features-title">무엇을 도와드릴까요?</h2>
        <p>기능을 선택하면 바로 시작할 수 있어요</p>
      </div>
      <div className="home-feature-grid">
        {homeFeatures.map((feature) => (
          <Link
            key={feature.id}
            href={feature.href}
            className={`home-feature-card ${feature.id === "skills" ? "recommended" : ""}`}
          >
            <div className="home-feature-top">
              <FeatureIcon kind={feature.id} />
              {feature.id === "skills" && (
                <span className="first-visit-badge">처음이라면 여기부터</span>
              )}
            </div>
            <h3>{feature.title}</h3>
            <p>{feature.question}</p>
            <small>{feature.detail}</small>
            <span className="feature-action">
              {feature.action}
              <ArrowRight size={16} />
            </span>
          </Link>
        ))}
      </div>
      <div className="home-start-guide" id="how-it-works">
        <strong>자료 하나로 시작할 수 있어요.</strong>
        <ol>
          {["직무 선택", "자료 추가", "결과 확인", "필요한 준비"].map(
            (label, i) => (
              <li key={label}>
                {i > 0 && <ArrowRight size={14} aria-hidden="true" />}
                {label}
              </li>
            ),
          )}
        </ol>
        <Link href="/my-skills">
          시작하기 <ArrowRight size={16} />
        </Link>
      </div>
    </section>
  );
}
