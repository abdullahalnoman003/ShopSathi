"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { Button, ErrorMessage, Field } from "@/components/ui";
import { ApiError } from "@/lib/api/client";
import { useAuth } from "@/lib/auth/AuthProvider";

export default function LoginPage() {
  const { login } = useAuth();
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    setBusy(true);
    setError(null);
    try {
      await login(String(f.get("email")), String(f.get("password")));
      router.push("/dashboard");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong");
      setBusy(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4">
      <h1 className="text-xl font-semibold">Log in</h1>
      <ErrorMessage message={error} />
      <Field label="Email" name="email" type="email" required autoComplete="email" />
      <Field label="Password" name="password" type="password" required autoComplete="current-password" />
      <Button type="submit" disabled={busy} className="w-full">
        {busy ? "Logging in…" : "Log in"}
      </Button>
      <p className="flex justify-between text-sm">
        <Link href="/forgot-password" className="text-emerald-700 underline dark:text-emerald-400">
          Forgot password?
        </Link>
        <Link href="/signup" className="text-emerald-700 underline dark:text-emerald-400">
          Create an account
        </Link>
      </p>
    </form>
  );
}
