"use client";
import Link from "next/link";
import { AlertCircle, SearchX } from "lucide-react";
export function Logo({ compact = false }: { compact?: boolean }) {
  return (
    <Link href="/" className="brand" aria-label="Career 홈">
      <span className="brand-mark">
        <span />
        <span />
        <span />
      </span>
      {!compact && <span>Career</span>}
    </Link>
  );
}
export function LinkButton({
  href,
  children,
  secondary = false,
  className = "",
  onClick,
}: {
  href: string;
  children: React.ReactNode;
  secondary?: boolean;
  className?: string;
  onClick?: () => void;
}) {
  return (
    <Link
      href={href}
      onClick={onClick}
      className={`cta ${secondary ? "cta-secondary" : ""} ${className}`}
    >
      {children}
    </Link>
  );
}
export function EmptyState({
  title,
  description,
  action,
  error = false,
}: {
  title: string;
  description: string;
  action?: React.ReactNode;
  error?: boolean;
}) {
  return (
    <div className="empty-state">
      {error ? <AlertCircle /> : <SearchX />}
      <h3>{title}</h3>
      <p>{description}</p>
      {action}
    </div>
  );
}
