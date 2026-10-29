import { notFound } from "next/navigation";
import { dummyJobs } from "@/lib/dummy-jobs";
import { examplePosting, studyDemoJobs } from "@/lib/study-prototype";
import "../../postings.css";

// 더미, 예시 공고의 가상 원문 페이지. 실제 기업 채용 페이지가 아니다.
export default async function Posting({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const id = decodeURIComponent((await params).id);
  const dummy = dummyJobs.find((j) => j.id === id);
  const example = studyDemoJobs.find((j) => j.id === id);
  const job = dummy ?? example;
  if (!job) notFound();
  const sections = dummy ? dummy.posting : examplePosting(job);
  return (
    <main className="posting-page">
      <p className="posting-notice">
        예시 원문 페이지예요. 실제 채용 공고가 아니에요.
      </p>
      <header>
        <span>{job.company}</span>
        <h1>{job.title}</h1>
        <p>
          {[job.location, job.employment, job.workplace]
            .filter(Boolean)
            .join(", ")}
          {job.closesAt &&
            `, ${new Date(job.closesAt).toLocaleDateString("ko-KR")} 마감`}
        </p>
      </header>
      {sections.map((s) => (
        <section key={s.title}>
          <h2>{s.title}</h2>
          <ul>
            {s.items.map((item, i) => (
              <li key={i}>{item}</li>
            ))}
          </ul>
        </section>
      ))}
      <button type="button" className="posting-apply" disabled>
        지원하기 (예시)
      </button>
    </main>
  );
}
