import Link from "next/link";
import type { ReactNode } from "react";

export default function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <main className="mx-auto flex w-full max-w-md flex-1 flex-col justify-center gap-6 px-4 py-10">
      <Link href="/" className="text-center text-2xl font-bold">
        ShopSathi
      </Link>
      <div className="rounded-lg border border-black/15 p-5 dark:border-white/20">{children}</div>
    </main>
  );
}
