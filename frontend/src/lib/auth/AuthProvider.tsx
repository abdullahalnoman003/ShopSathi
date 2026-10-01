"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { apiFetch, apiPost } from "@/lib/api/client";
import { clearToken, getToken, setToken } from "./storage";

export interface User {
  id: number;
  email: string;
  full_name: string;
  role: "owner" | "moderator" | "platform_admin";
  shop_id: number | null;
  is_active: boolean;
}

export interface Shop {
  id: number;
  name: string;
  status: "active" | "suspended";
  created_at: string;
}

interface Me {
  user: User;
  shop: Shop | null;
}

interface AuthResponse extends Me {
  access_token: string;
}

export interface SignupInput {
  shop_name: string;
  owner_name: string;
  email: string;
  password: string;
}

interface AuthContextValue extends Partial<Me> {
  /** true until the stored token has been checked */
  loading: boolean;
  signup: (input: SignupInput) => Promise<void>;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const check = getToken() ? apiFetch<Me>("/auth/me") : Promise.resolve(null);
    check
      .then(setMe)
      .catch(() => clearToken())
      .finally(() => setLoading(false));
  }, []);

  const accept = useCallback((res: AuthResponse) => {
    setToken(res.access_token);
    setMe({ user: res.user, shop: res.shop });
  }, []);

  const signup = useCallback(async (input: SignupInput) => accept(await apiPost<AuthResponse>("/auth/signup", input)), [accept]);

  const login = useCallback(
    async (email: string, password: string) => accept(await apiPost<AuthResponse>("/auth/login", { email, password })),
    [accept],
  );

  const logout = useCallback(async () => {
    try {
      await apiPost("/auth/logout");
    } catch {
      /* token already invalid: still log out locally */
    }
    clearToken();
    setMe(null);
  }, []);

  const value = useMemo(
    () => ({ user: me?.user, shop: me?.shop, loading, signup, login, logout }),
    [me, loading, signup, login, logout],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
