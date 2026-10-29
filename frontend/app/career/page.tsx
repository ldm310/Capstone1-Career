import { redirect } from "next/navigation";
import { legacyDestination } from "@/lib/feature-sections";
export default async function Page({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  let destination = legacyDestination(
    typeof params.tab === "string" ? params.tab : null,
  );
  if (typeof params.url === "string")
    destination += `${destination.includes("?") ? "&" : "?"}url=${encodeURIComponent(params.url)}`;
  redirect(destination);
}
