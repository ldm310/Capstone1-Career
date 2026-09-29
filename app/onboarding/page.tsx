import Link from "next/link";
import { GrowthHub } from "@/components/growth/growth-hub";
export default function Page() {
  return (
    <main
      className="career-workspace"
      style={{ maxWidth: 1100, margin: "40px auto", padding: 24 }}
    >
      <Link href="/">Career · 홈으로</Link>
      <GrowthHub demo view="start" />
    </main>
  );
}
