"use client";
import Link from "next/link";
import { motion } from "motion/react";
import {
  ArrowUpRight,
  Sparkles,
  AlertCircle,
  SearchX,
  RefreshCw,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { useCareer } from "./career-provider";
import type { RoleId } from "@/types/career";
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
export function DemoBadge() {
  return (
    <span className="demo-badge">
      <span />
      체험 공간
    </span>
  );
}
export function Tags({ items }: { items: string[] }) {
  return (
    <div className="tags">
      {items.map((item) => (
        <span className="tag" key={item}>
          {item}
        </span>
      ))}
    </div>
  );
}
export function PageHeading({
  eyebrow,
  title,
  description,
  children,
}: {
  eyebrow?: string;
  title: string;
  description: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="page-heading">
      <div>
        {eyebrow && <div className="eyebrow">{eyebrow}</div>}
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {children && <div className="heading-controls">{children}</div>}
    </div>
  );
}
export function Panel({
  title,
  subtitle,
  children,
  action,
  className = "",
}: {
  title?: string;
  subtitle?: string;
  children: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={`panel ${className}`}>
      {title && (
        <div className="panel-header">
          <div>
            <h2>{title}</h2>
            {subtitle && <p>{subtitle}</p>}
          </div>
          {action}
        </div>
      )}
      {children}
    </section>
  );
}
export function ArrowLink({
  href,
  children,
}: {
  href: string;
  children: React.ReactNode;
}) {
  return (
    <Link href={href} className="arrow-link">
      {children}
      <ArrowUpRight size={15} />
    </Link>
  );
}
export function RoleSelect() {
  const { data, profile, setRole } = useCareer();
  return (
    <div className="select-wrap">
      <select
        aria-label="희망 직무"
        value={profile.role}
        onChange={(e) => setRole(e.target.value as RoleId)}
      >
        {(
          data?.roles ?? [
            { id: "data", short: "데이터" },
            { id: "backend", short: "백엔드" },
          ]
        ).map((r) => (
          <option key={r.id} value={r.id}>
            {r.short}
          </option>
        ))}
      </select>
    </div>
  );
}
export function PageMotion({ children }: { children: React.ReactNode }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 7 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25 }}
    >
      {children}
    </motion.div>
  );
}
export function DataBoundary({ children }: { children: React.ReactNode }) {
  const { data, loading, error, reload } = useCareer();
  if (error)
    return (
      <EmptyState
        title="데이터를 불러오지 못했어요"
        description={error}
        error
        action={
          <Button onClick={reload}>
            <RefreshCw />
            다시 시도
          </Button>
        }
      />
    );
  if (loading || !data)
    return (
      <div className="loading-state" role="status">
        <Sparkles className="pulse" />
        <span>Career를 준비하고 있어요…</span>
        <div className="skeleton" />
        <div className="skeleton" />
      </div>
    );
  return <>{children}</>;
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
