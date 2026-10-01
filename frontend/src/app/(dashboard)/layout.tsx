"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { useAuth } from "@/lib/auth/AuthProvider";

// Only modules that exist get a nav item. Later prompts add theirs here.
const NAV = [{ href: "/dashboard", label: "Dashboard" }];

export default function DashboardLayout({ children }: { children: ReactNode }) {
  const { user, shop, loading, logout } = useAuth();
  const router = useRouter();
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);

  if (loading || !user) {
    return <p className="p-6 text-center opacity-70">Loading…</p>;
  }

  async function onLogout() {
    await logout();
    router.replace("/login");
  }

  return (
    <div className="flex min-h-full flex-1 flex-col">
      <header className="border-b border-black/15 dark:border-white/20">
        <div className="mx-auto flex max-w-5xl items-center justify-between gap-3 px-4 py-3">
          <div className="min-w-0">
            <p className="truncate font-semibold">{shop?.name ?? "ShopSathi"}</p>
            <p className="truncate text-xs opacity-70">{user.full_name}</p>
          </div>
          <button
            type="button"
            className="rounded-md border border-black/20 px-3 py-1 text-sm sm:hidden dark:border-white/25"
            aria-expanded={open}
            aria-controls="main-nav"
            onClick={() => setOpen((o) => !o)}
          >
            Menu
          </button>
          <nav
            id="main-nav"
            className={`${open ? "flex" : "hidden"} absolute inset-x-0 top-[61px] z-10 flex-col gap-2 border-b border-black/15 bg-background p-4 sm:static sm:flex sm:flex-row sm:items-center sm:gap-4 sm:border-0 sm:bg-transparent sm:p-0 dark:border-white/20`}
          >
            {NAV.map((n) => (
              <Link key={n.href} href={n.href} onClick={() => setOpen(false)} className="text-sm hover:underline">
                {n.label}
              </Link>
            ))}
            <button type="button" onClick={onLogout} className="rounded-md border border-black/20 px-3 py-1 text-left text-sm dark:border-white/25">
              Log out
            </button>
          </nav>
        </div>
      </header>
      <div className="mx-auto w-full max-w-5xl flex-1 px-4 py-6">{children}</div>
    </div>
  );
}
