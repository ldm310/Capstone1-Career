"use client";
import { useEffect, useState } from "react";
import { LoadingSpinner } from "@/components/shared/loading-spinner";
import type { PostingSection, PublicJob } from "@/types/public-job";
import { OriginalLink } from "@/components/jobs/original-link";

// 공고 본문을 섹션별로 보여준다. 본문이 없는 실제 공고는 원문에서 불러온다.
export function JobPosting({
  job,
  posting,
}: {
  job: PublicJob;
  posting?: PostingSection[];
}) {
  const [loaded, setLoaded] = useState<PostingSection[] | null>(null);
  const [error, setError] = useState("");
  const sections = posting ?? job.posting ?? loaded;
  useEffect(() => {
    if (posting || job.posting) return;
    let active = true;
    fetch(`/api/jobs/posting?url=${encodeURIComponent(job.url)}`)
      .then(async (r) => {
        const d = await r.json();
        if (!r.ok) throw Error(d.error);
        if (active) setLoaded(d.posting);
      })
      .catch((e) => {
        if (active) setError(e.message || "공고를 불러오지 못했어요.");
      });
    return () => {
      active = false;
    };
  }, [job, posting]);
  if (error)
    return (
      <section className="study-requirements">
        <p role="alert">{error}</p>
        <OriginalLink job={job} />
      </section>
    );
  if (!sections) return <LoadingSpinner inline />;
  return (
    <section className="study-requirements job-posting">
      {sections.map((s) => (
        <div key={s.title} className="job-posting-section">
          <h3>{s.title}</h3>
          <ul>
            {s.items.map((item, i) => (
              <li key={i}>{item}</li>
            ))}
          </ul>
        </div>
      ))}
    </section>
  );
}
