"use client";
import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { ArrowUpRight, Menu, X } from "lucide-react";
import { Logo, LinkButton } from "@/components/shared/primitives";
import { homeFeatures } from "@/lib/home-navigation";
export function Header() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  return (
    <header className="site-header">
      <div className="site-header-inner">
        <Logo />
        <nav
          aria-label="주 메뉴"
          className={open ? "header-nav open" : "header-nav"}
        >
          {homeFeatures.map((feature) => (
            <Link
              key={feature.id}
              href={feature.href}
              aria-current={pathname === feature.href ? "page" : undefined}
              onClick={() => setOpen(false)}
            >
              {feature.title}
            </Link>
          ))}
        </nav>
        <div className="header-actions">
          <Link className="sign-in" href="/growth">
            바로 둘러보기
          </Link>
          <LinkButton href="/my-skills">
            시작하기 <ArrowUpRight size={15} />
          </LinkButton>
          <button
            className="icon-button mobile-only"
            aria-label={open ? "메뉴 닫기" : "메뉴 열기"}
            aria-expanded={open}
            onClick={() => setOpen(!open)}
          >
            {open ? <X /> : <Menu />}
          </button>
        </div>
      </div>
    </header>
  );
}
