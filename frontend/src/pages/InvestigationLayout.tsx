import { SearchX } from "lucide-react";
import { Link, Outlet, useOutletContext, useParams } from "react-router";
import { InvestigationHeader } from "../components/investigation/InvestigationHeader";
import { EmptyState, ErrorNotice, Skeleton } from "../components/ui/primitives";
import { isActive, useInvestigation, useProfile } from "../hooks/queries";
import { ApiError } from "../lib/api";
import type { InvestigationDetail, ProfileView } from "../lib/types";

export interface InvestigationContext {
  inv: InvestigationDetail;
  profile: ProfileView | undefined;
  profileLoading: boolean;
  active: boolean;
}

export const useInvestigationContext = () => useOutletContext<InvestigationContext>();

export function InvestigationLayout() {
  const { id } = useParams();
  const { data: inv, error, isLoading } = useInvestigation(id);
  const active = isActive(inv?.status);
  const profileQuery = useProfile(id!, active);

  if (isLoading) {
    return (
      <div className="mx-auto max-w-[1400px] space-y-4 p-6">
        <div className="flex gap-5">
          <Skeleton className="size-[88px]" />
          <div className="flex-1 space-y-2">
            <Skeleton className="h-4 w-40" />
            <Skeleton className="h-7 w-72" />
            <Skeleton className="h-4 w-96" />
          </div>
        </div>
        <Skeleton className="h-20" />
        <Skeleton className="h-64" />
      </div>
    );
  }
  if (error instanceof ApiError && error.status === 404) {
    return (
      <EmptyState icon={<SearchX className="size-8" />} title="Investigation not found" className="mt-16"
        action={<Link to="/investigations" className="text-accent hover:underline">Back to investigations</Link>}>
        It may have been deleted.
      </EmptyState>
    );
  }
  if (error || !inv) {
    return (
      <div className="p-6">
        <ErrorNotice error={error} />
      </div>
    );
  }

  const ctx: InvestigationContext = {
    inv,
    profile: profileQuery.data,
    profileLoading: profileQuery.isLoading,
    active,
  };
  return (
    <div className="flex min-h-full flex-col">
      <InvestigationHeader inv={inv} profile={profileQuery.data} />
      <Outlet context={ctx} />
    </div>
  );
}
