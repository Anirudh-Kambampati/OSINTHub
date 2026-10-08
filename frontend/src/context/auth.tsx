import { useQueryClient } from "@tanstack/react-query";
import { Radar } from "lucide-react";
import { useEffect, type ReactNode } from "react";
import { Navigate, useLocation, useNavigate } from "react-router";
import { Skeleton } from "../components/ui/primitives";
import { keys, useAuthStatus } from "../hooks/queries";
import { setUnauthorizedHandler } from "../lib/api";
import type { AuthStatus, User } from "../lib/types";

/** Any 401 from the API (expired session, revoked user) sends the user back to sign-in. */
export function UnauthorizedRedirect() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const location = useLocation();
  useEffect(() => {
    setUnauthorizedHandler(() => {
      qc.setQueryData<AuthStatus>(keys.auth, (prev) => (prev ? { ...prev, user: null } : prev));
      if (location.pathname !== "/login") navigate("/login", { state: { from: location.pathname } });
    });
    return () => setUnauthorizedHandler(null);
  }, [qc, navigate, location.pathname]);
  return null;
}

export function useCurrentUser(): User | null {
  return useAuthStatus().data?.user ?? null;
}

export function RequireAuth({ children }: { children: ReactNode }) {
  const { data, isLoading } = useAuthStatus();
  const location = useLocation();
  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center gap-3 text-muted">
        <Radar className="size-5 animate-pulse text-accent" aria-hidden />
        <Skeleton className="h-4 w-32" />
      </div>
    );
  }
  if (!data?.user) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  return <>{children}</>;
}
