import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
import { createHiringCohort, meanKeywordLevels } from "@/mock/hiring-cohort";
import {
  skillCategories,
  categoryKeywords,
  categoryLevels,
} from "@/lib/skill-categories";
import { GET } from "@/app/api/jobs/benchmark/route";

test("50 distinct synthetic successful profiles are part of the applicant population", () => {
  const cohort = createHiringCohort("test-job");
  expect(cohort.passed).toHaveLength(50);
  expect(cohort.people).toHaveLength(150);
  expect(new Set(cohort.people.map((person) => person.id)).size).toBe(150);
  expect(
    cohort.passed.every(
      (person) => person.synthetic && cohort.people.includes(person),
    ),
  ).toBe(true);
  expect(cohort).toEqual(createHiringCohort("test-job"));
  expect(cohort.people).toEqual(createHiringCohort("another-job").people);
  const means = meanKeywordLevels(cohort.passed, categoryKeywords);
  for (const keyword of categoryKeywords) {
    expect(means[keyword]).toBe(
      Math.round(
        cohort.passed.reduce(
          (sum, person) => sum + person.keywordLevels[keyword],
          0,
        ) / 50,
      ),
    );
  }
  expect(categoryLevels(means).O).toBe(
    Math.round((means.Docker + means.AWS + means.Kubernetes) / 3),
  );
});

test("ten chart categories match the backend taxonomy and do not split frontend/apps", () => {
  const snapshot = JSON.parse(
    readFileSync(
      "../backend/src/main/resources/skill-categories/reviewed-20261119.json",
      "utf8",
    ),
  );
  expect(skillCategories.map(({ code, name }) => ({ code, name }))).toEqual(
    snapshot.catalog.categories.map(
      ({ code, name }: { code: string; name: string }) => ({ code, name }),
    ),
  );
  expect(skillCategories).toHaveLength(10);
});

test("benchmark API separates empty/synthetic data and validates input", async () => {
  const response = GET(
    new Request("http://localhost/api/jobs/benchmark?jobId=demo"),
  );
  const data = await response.json();
  expect(data.source).toBe("SYNTHETIC");
  expect(data.passed).toHaveLength(50);
  const empty = await GET(
    new Request("http://localhost/api/jobs/benchmark?jobId=demo&cohort=empty"),
  ).json();
  expect(empty.passed).toEqual([]);
  expect(empty.applicants).toHaveLength(100);
  expect(
    empty.applicants.every(
      (person: { outcome: string }) => person.outcome !== "passed",
    ),
  ).toBe(true);
  expect(GET(new Request("http://localhost/api/jobs/benchmark")).status).toBe(
    400,
  );
  expect(
    GET(
      new Request(
        "http://localhost/api/jobs/benchmark?jobId=demo&cohort=invalid",
      ),
    ).status,
  ).toBe(400);
});
