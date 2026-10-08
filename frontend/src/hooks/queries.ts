import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { api } from "../lib/api";
import type { InvestigationStatus, SeedType } from "../lib/types";

export const ACTIVE_STATUSES: InvestigationStatus[] = ["pending", "running"];
export const isActive = (status: InvestigationStatus | undefined) => !!status && ACTIVE_STATUSES.includes(status);

export const keys = {
  investigations: ["investigations"] as const,
  investigation: (id: string) => ["investigation", id] as const,
  profile: (id: string) => ["investigation", id, "profile"] as const,
  mentions: (id: string, opts: object) => ["investigation", id, "mentions", opts] as const,
  timeline: (id: string, kind: string) => ["investigation", id, "timeline", kind] as const,
  graph: (id: string, mentions: boolean) => ["investigation", id, "graph", mentions] as const,
  sources: (id: string) => ["investigation", id, "sources"] as const,
  evidence: (entityId: string) => ["entity", entityId, "evidence"] as const,
  connectors: ["connectors"] as const,
};

export function useInvestigations() {
  return useQuery({
    queryKey: keys.investigations,
    queryFn: api.investigations,
    refetchInterval: (q) => (q.state.data?.some((i) => isActive(i.status)) ? 3000 : false),
  });
}

/** Polls quickly while running; when the run finishes, refreshes every derived view once. */
export function useInvestigation(id: string | undefined) {
  const qc = useQueryClient();
  const query = useQuery({
    queryKey: keys.investigation(id ?? ""),
    queryFn: () => api.investigation(id!),
    enabled: !!id,
    refetchInterval: (q) => (isActive(q.state.data?.status) ? 1500 : false),
  });
  const status = query.data?.status;
  const previous = useRef(status);
  useEffect(() => {
    if (id && isActive(previous.current) && status && !isActive(status)) {
      qc.invalidateQueries({ queryKey: ["investigation", id] });
      qc.invalidateQueries({ queryKey: keys.investigations });
    }
    previous.current = status;
  }, [id, status, qc]);
  return query;
}

const liveInterval = (active: boolean) => (active ? 4000 : false);

export function useProfile(id: string, active: boolean) {
  return useQuery({ queryKey: keys.profile(id), queryFn: () => api.profile(id), refetchInterval: liveInterval(active) });
}

export function useMentions(
  id: string,
  opts: { category?: string; sort?: string; limit?: number; offset?: number },
  active: boolean,
) {
  return useQuery({
    queryKey: keys.mentions(id, opts),
    queryFn: () => api.mentions(id, opts),
    refetchInterval: liveInterval(active),
    placeholderData: (prev) => prev,
  });
}

export function useTimeline(id: string, kind: string, active: boolean) {
  return useQuery({
    queryKey: keys.timeline(id, kind),
    queryFn: () => api.timeline(id, kind || undefined),
    refetchInterval: liveInterval(active),
    placeholderData: (prev) => prev,
  });
}

export function useGraph(id: string, includeMentions: boolean, active: boolean) {
  return useQuery({
    queryKey: keys.graph(id, includeMentions),
    queryFn: () => api.graph(id, includeMentions),
    refetchInterval: active ? 6000 : false,
  });
}

export function useSources(id: string, active: boolean) {
  return useQuery({ queryKey: keys.sources(id), queryFn: () => api.sources(id), refetchInterval: liveInterval(active) });
}

export function useEntityEvidence(entityId: string | null) {
  return useQuery({
    queryKey: keys.evidence(entityId ?? ""),
    queryFn: () => api.evidence(entityId!),
    enabled: !!entityId,
  });
}

export function useConnectors() {
  return useQuery({ queryKey: keys.connectors, queryFn: api.connectors, staleTime: 60_000 });
}

export function useCreateInvestigation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ seed, seedType }: { seed: string; seedType?: SeedType }) => api.createInvestigation(seed, seedType),
    onSuccess: (inv) => {
      qc.setQueryData(keys.investigation(inv.id), inv);
      qc.invalidateQueries({ queryKey: keys.investigations });
    },
  });
}

export function useRerun(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.rerun(id),
    onSuccess: (inv) => qc.setQueryData(keys.investigation(id), inv),
  });
}

export function useDeleteInvestigation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.deleteInvestigation(id),
    onSuccess: (_, id) => {
      qc.removeQueries({ queryKey: ["investigation", id] });
      qc.invalidateQueries({ queryKey: keys.investigations });
    },
  });
}
