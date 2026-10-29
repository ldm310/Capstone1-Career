# Homepage (2026-09-28)

Selected five-destination layout: jobs, evidence, preparation, applications, growth.
`lib/home-navigation.ts` is shared by the header and feature cards. Existing account routes and public job feed remain connected. Bespoke duotone SVG icons are decorative; each destination has a visible text label.

## Shared sky
`SkyBackgroundProvider` owns one index for both the intro and homepage. Every 5 seconds it advances to a successfully preloaded image, crossfading for 1.2 seconds. Entering or replaying the intro never resets the index. Hidden tabs pause the timer. Reduced-motion preference starts paused; an accessible play/pause control is available in both views. Unavailable images are skipped and the original remains the fallback.

Images served locally, no external runtime photo request:
- `career-sky.jpg`: existing project asset, retained unchanged.
- `career-clouds-2.jpg`: https://www.pexels.com/photo/fluffy-white-clouds-in-blue-sky-30570082/
- `career-clouds-3.jpg`: Lisa from Pexels, https://www.pexels.com/photo/blue-sky-and-white-clouds-12657108/
- Photo license: https://www.pexels.com/license/

New cloud photos use a pale blue screen blend and restrained saturation in CSS to match the existing bright sky. Source files are not retouched.

## Login-free review flow

The homepage and `/career?tab=...` now enter without registration. `/sign-in` redirects to `/career`. On a 401 from `/api/career`, the client establishes a browser-specific guest session via origin-checked `POST /api/guest`. Existing authenticated users keep their own workspace. Ownership checks remain active on all document, analysis, sharing and storage APIs. Guest IDs are excluded from real rankings even if their visibility setting is enabled.

The HttpOnly session lasts seven days; this is the access-cookie lifetime, not automatic deletion of stored documents. Clearing cookies starts a different workspace. Guests are told where their data is stored. Real review/point approval limitations are unchanged; `/dashboard` provides the explicitly marked sample completion/reward flow.
