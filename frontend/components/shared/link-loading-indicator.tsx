"use client";
import { useLinkStatus } from "next/link";
import { LoadingSpinner } from "./loading-spinner";

export function LinkLoadingIndicator() {
  const { pending } = useLinkStatus();
  return pending ? <LoadingSpinner /> : null;
}
