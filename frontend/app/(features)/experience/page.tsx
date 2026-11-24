import { JobDetail } from "@/components/jobs/job-detail";
import { experienceJob } from "@/mock/posting-experience";
export default function Experience() {
  return <JobDetail id={experienceJob.id} experience />;
}
