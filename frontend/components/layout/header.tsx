"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ArrowUpRight, Menu, X } from "lucide-react";
import { Logo, LinkButton } from "@/components/shared/primitives";
import { homeFeatures } from "@/lib/home-navigation";
export function Header() {
  const pathname = usePathname();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [account, setAccount] = useState<string | null>(null);
  useEffect(() => {
    let active = true;
    const refresh = () =>
      fetch("/api/account")
        .then((r) => r.json())
        .then((d) => {
          if (active) setAccount(d.user && !d.guest ? d.user.name : null);
        })
        .catch(() => {});
    void refresh();
    // 마이페이지에서 이름을 바꾸면 바로 반영한다.
    window.addEventListener("career:account", refresh);
    return () => {
      active = false;
      window.removeEventListener("career:account", refresh);
    };
  }, [pathname]);
  async function logout() {
    await fetch("/api/account", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "logout" }),
    });
    setAccount(null);
    router.push("/");
    router.refresh();
  }
  return (
    <header className="site-header">
      <div className="site-header-inner">
        <Logo />
        <nav
          aria-label="주 메뉴"
          className={open ? "header-nav open" : "header-nav"}
        >
          <Link
            href="/"
            aria-current={pathname === "/" ? "page" : undefined}
            onClick={() => setOpen(false)}
          >
            홈
          </Link>
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
          <Link
            className="mobile-only"
            href="/my-page"
            aria-current={pathname === "/my-page" ? "page" : undefined}
            onClick={() => setOpen(false)}
          >
            마이페이지
          </Link>
        </nav>
        <div className="header-actions">
          {account ? (
            <>
              <Link
                className="header-user"
                href="/my-page"
                aria-current={pathname === "/my-page" ? "page" : undefined}
              >
                {account}님
              </Link>
              <button className="header-login" onClick={() => void logout()}>
                로그아웃
              </button>
            </>
          ) : (
            <>
              <Link
                className="header-user"
                href="/my-page"
                aria-current={pathname === "/my-page" ? "page" : undefined}
              >
                마이페이지
              </Link>
              <Link className="header-login" href="/sign-in">
                로그인
              </Link>
            </>
          )}
          <LinkButton href="/my-data">
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
