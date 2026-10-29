import Link from "next/link";
export default function NotFound() {
  return (
    <main className="standalone">
      <span className="eyebrow">404</span>
      <h1>페이지가 없어요.</h1>
      <Link href="/" className="cta">
        홈으로
      </Link>
    </main>
  );
}
