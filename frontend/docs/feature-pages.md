# Independent feature pages

- `/jobs`: public catalog, saved postings, personal comparison (`?tab=jobs`). No guest session needed to browse.
- `/my-skills`: sources, reviewed skills/evidence, portfolio sharing.
- `/preparation`: choose a next task, ongoing tasks, weekly plan, interview preparation.
- `/application-tracker`: applications/resumes and deadline/interview schedule.
- `/growth`: summary, completed-task/point history, growth rankings.

`featureSections` defines the permitted tabs for each section. The feature layout has a shared top navigation and only that section's secondary navigation; it does not use the old all-purpose sidebar. Invalid tabs fall back to that section's first tab. `/career?tab=...` bookmarks redirect and retain the job URL parameter. Workspace data and guest session ownership stay shared across pages.

The home page shows at most three compact job previews. Search, bookmark lists, pagination and filtering live on `/jobs`. Search/location/workplace/role and sorting are applied to the full collected feed before pagination in `/api/jobs`. Workplace filters accept the existing Korean display values through `workplaceKey`. Saved cards are independent browser-local snapshots and their filters/sorting do not depend on loaded pages.

## Data limits

The public catalog searches all supported open RDS postings in `job-catalog.ts`; it no longer loads only the first 200 Spring summaries and their full extraction trees. Company/title/current technology search, role/career filtering, sorting and pagination happen in one read-only DB statement. Only visible rows receive their technology lists. The existing Spring detail endpoint still serves a selected posting. Only real external board snapshots participate in the server-side sort/count/page; example postings are never added to the public catalog. Snapshot refresh runs after the response. No public-board fetch blocks catalog search. The browser displays the returned page without filtering it again.

The catalog only includes the currently integrated official providers, not all Korean job boards. Provider outages are shown and a previously collected snapshot may be used. Popularity, salary and experience filters were not fabricated because those fields are not available in a consistent form. The job card covers are category graphics and company initials, not company office photographs. Original postings remain linked. Automated level verification and real point approval retain their previous integration limitations.

## Current catalog and archive policy

Stored `posting.body_html` supplies explicit work locations and modes, parsed into a server cache for 60 seconds. Missing data remains unknown, with separate unknown filters. The public list offers 12 or 24 rows per page over the complete matching set. Frontend SQL and Spring agree that an open posting must have status open and a null deadline or deadline on/after the current Asia/Seoul date. Closed source postings and expired deadlines are retained without changing crawler records. `/admin?tab=closed` and `/api/admin/closed-postings` expose the archive only to administrators, with search, total count and pagination. Signed-out headers hide My Page; signed-in names remain links to My Page.

## Extraction review decisions

`/admin?tab=skipped` collects skipped current extraction reviews. Normal registration writes `review_result=??`; PASS writes `??` and removes the posting from both frontend and Spring public queries. Restore clears review_result/reviewed_at and leaves a dated restoration memo in review_feedback, which changes the revision to reject requests from before the undo. No auxiliary review table is introduced. Only current flagged runs may be changed. Already replaced runs are protected, and undo does not cancel an Airflow job already running. Expired or source-closed postings cannot be approved or requested for re-extraction. Explicit batch PASS handles only pending flagged runs with a deadline before the current Asia/Seoul date; existing decisions remain untouched.

## Catalog usability and login return

Catalog query, role, region, work mode, experience, sort, page size and offset are kept in `/jobs` URL parameters. Detail links preserve those parameters; list navigation and browser Back restore them. Scroll positions are stored only in tab-local sessionStorage when opening a posting, then restored after the list loads. Save results are visible, dismissible notifications in catalog, detail and saved-list screens. Saved-list request failures have an error state with retry, distinct from a successful empty list. Normal unauthenticated access still presents an empty guest list.

Posting comparison sign-in links include a validated internal `next` destination. Email login, Kakao existing-member login and Kakao password-setup signup preserve it. Kakao handoff uses a 10-minute HttpOnly cookie and carries the safe destination through signup/errors; external URLs, API routes and control characters are rejected.
