"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";
import { Button, ErrorMessage, Field, SuccessMessage } from "@/components/ui";
import { ApiError, apiPost } from "@/lib/api/client";

export default function ForgotPasswordPage() {
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    setBusy(true);
    setError(null);
    try {
      const res = await apiPost<{ message: string }>("/auth/password-reset/request", { email: String(f.get("email")) });
      setDone(res.message);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong");
    }
    setBusy(false);
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4">
      <h1 className="text-xl font-semibold">Forgot password</h1>
      <p className="text-sm opacity-70">Enter your email and we will send you a link to set a new password.</p>
      <ErrorMessage message={error} />
      <SuccessMessage message={done} />
      <Field label="Email" name="email" type="email" required autoComplete="email" />
      <Button type="submit" disabled={busy} className="w-full">
        {busy ? "Sending…" : "Send reset link"}
      </Button>
      <p className="text-center text-sm">
        <Link href="/login" className="text-emerald-700 underline dark:text-emerald-400">
          Back to log in
        </Link>
      </p>
    </form>
  );
}
