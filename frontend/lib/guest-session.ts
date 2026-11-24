// Coalesce React Strict Mode bootstrap requests; a failed attempt may be retried.
let pending: Promise<Response> | null = null;
export async function openCareerSpace() {
  const existing = await fetch("/api/career");
  if (existing.status !== 401) return existing;
  if (!pending) {
    pending = fetch("/api/guest", { method: "POST" });
    pending
      .finally(() => {
        pending = null;
      })
      .catch(() => {});
  }
  return (await pending).clone();
}
