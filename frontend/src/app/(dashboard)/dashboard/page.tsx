"use client";

import { useAuth } from "@/lib/auth/AuthProvider";

// Placeholder: later prompts add the dashboard sections.
export default function DashboardHome() {
  const { user, shop } = useAuth();
  return (
    <div>
      <h1 className="text-2xl font-bold">Welcome, {user?.full_name}</h1>
      <p className="mt-2 opacity-70">
        {shop ? `Your shop: ${shop.name}` : "Signed in as platform administrator."}
      </p>
    </div>
  );
}
