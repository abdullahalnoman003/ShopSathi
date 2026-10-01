"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState, type FormEvent } from "react";
import { Button, ErrorMessage, Field, SuccessMessage } from "@/components/ui";
import { ApiError, apiPost } from "@/lib/api/client";

function ResetForm() {
  const token = useSearchParams().get("token") ?? "";
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    if (f.get("password") !== f.get("confirm")) {
      setError("Passwords do not match");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const res = await apiPost<{ message: string }>("/auth/password-reset/confirm", {
        token,
        new_password: String(f.get("password")),
      });
      setDone(res.message);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong");
    }
    setBusy(false);
  }

  if (!token) {
    return <ErrorMessage message="This reset link is missing its token. Request a new link." />;
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4">
      <ErrorMessage message={error} />
      <SuccessMessage message={done} />
      {!done && (
        <>
          <Field label="New password (at least 8 characters)" name="password" type="password" required minLength={8} autoComplete="new-password" />
          <Field label="Confirm new password" name="confirm" type="password" required minLength={8} autoComplete="new-password" />
          <Button type="submit" disabled={busy} className="w-full">
            {busy ? "Saving…" : "Set new password"}
          </Button>
        </>
      )}
    </form>
  );
}

export default function ResetPasswordPage() {
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Set a new password</h1>
      <Suspense>
        <ResetForm />
      </Suspense>
      <p className="text-center text-sm">
        <Link href="/login" className="text-emerald-700 underline dark:text-emerald-400">
          Go to log in
        </Link>
      </p>
    </div>
  );
}
