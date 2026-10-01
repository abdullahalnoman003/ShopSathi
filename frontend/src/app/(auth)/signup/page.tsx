"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { Button, ErrorMessage, Field } from "@/components/ui";
import { ApiError } from "@/lib/api/client";
import { useAuth } from "@/lib/auth/AuthProvider";

export default function SignupPage() {
  const { signup } = useAuth();
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    setBusy(true);
    setError(null);
    try {
      await signup({
        shop_name: String(f.get("shop_name")),
        owner_name: String(f.get("owner_name")),
        email: String(f.get("email")),
        password: String(f.get("password")),
      });
      router.push("/dashboard");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong");
      setBusy(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4">
      <h1 className="text-xl font-semibold">Create your shop account</h1>
      <ErrorMessage message={error} />
      <Field label="Shop name" name="shop_name" required maxLength={200} />
      <Field label="Owner name" name="owner_name" required maxLength={200} autoComplete="name" />
      <Field label="Email" name="email" type="email" required autoComplete="email" />
      <Field label="Password (at least 8 characters)" name="password" type="password" required minLength={8} autoComplete="new-password" />
      <Button type="submit" disabled={busy} className="w-full">
        {busy ? "Creating…" : "Sign up"}
      </Button>
      <p className="text-center text-sm">
        Already have an account?{" "}
        <Link href="/login" className="text-emerald-700 underline dark:text-emerald-400">
          Log in
        </Link>
      </p>
    </form>
  );
}
