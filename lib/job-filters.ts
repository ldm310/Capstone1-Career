export function workplaceKey(value: string | null) {
  const text = (value || "").toLowerCase();
  if (/hybrid|하이브리드|혼합/.test(text)) return "hybrid";
  if (/remote|원격|재택/.test(text)) return "remote";
  if (/on.?site|사무실|오피스|현장/.test(text)) return "on-site";
  return "unknown";
}
