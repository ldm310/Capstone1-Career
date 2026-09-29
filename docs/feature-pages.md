# Independent feature pages

- `/jobs`: public catalog, saved postings, personal comparison (`?tab=jobs`). No guest session needed to browse.
- `/my-skills`: sources, reviewed skills/evidence, portfolio sharing.
- `/preparation`: choose a next task, ongoing tasks, weekly plan, interview preparation.
- `/application-tracker`: applications/resumes and deadline/interview schedule.
- `/growth`: summary, completed-task/point history, growth rankings.

`featureSections` defines the permitted tabs for each section. The feature layout has a shared top navigation and only that section's secondary navigation; it does not use the old all-purpose sidebar. Invalid tabs fall back to that section's first tab. `/career?tab=...` bookmarks redirect and retain the job URL parameter. Workspace data and guest session ownership stay shared across pages.

The home page shows at most three compact job previews. Search, bookmark lists, pagination and filtering live on `/jobs`. Search/location/workplace/role and sorting are applied to the full collected feed before pagination in `/api/jobs`. Workplace filters accept the existing Korean display values through `workplaceKey`. Saved cards are independent browser-local snapshots and their filters/sorting do not depend on loaded pages.

## Data limits

The catalog only includes the currently integrated official providers, not all Korean job boards. Provider outages are shown and a previously collected snapshot may be used. Popularity, salary and experience filters were not fabricated because those fields are not available in a consistent form. The job card covers are category graphics and company initials, not company office photographs. Original postings remain linked. Automated level verification and real point approval retain their previous integration limitations.
