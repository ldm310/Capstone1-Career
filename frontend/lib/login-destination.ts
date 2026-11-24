// Only app page destinations are allowed. Never redirect to an external origin/API.
export function loginDestination(value: string | null | undefined): string {
  if (
    !value ||
    value.length > 3000 ||
    !value.startsWith("/") ||
    value.startsWith("//") ||
    /[\\\u0000-\u001f\u007f]/.test(value)
  )
    return "/analysis";
  try {
    const url = new URL(value, "https://career.invalid");
    return url.origin === "https://career.invalid" &&
      ["/jobs", "/analysis", "/comparison", "/my-page"].includes(url.pathname)
      ? url.pathname + url.search
      : "/analysis";
  } catch {
    return "/analysis";
  }
}
export function signInUrl(destination: string) {
  return (
    "/sign-in?" + new URLSearchParams({ next: loginDestination(destination) })
  );
}
