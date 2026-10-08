import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { EvidenceContent, evidenceTitle } from "../components/investigation/EvidencePanel";
import { Drawer } from "../components/ui/Drawer";
import type { IdentityAttribute, ImageCandidate, Mention, Presence } from "../lib/types";

export type EvidenceTarget =
  | { type: "entity"; id: string }
  | { type: "attribute"; attribute: IdentityAttribute }
  | { type: "images"; images: ImageCandidate[]; label: string }
  | { type: "mention"; mention: Mention }
  | { type: "presence"; presence: Presence };

interface EvidenceApi {
  open: (target: EvidenceTarget) => void;
  close: () => void;
}

const EvidenceContext = createContext<EvidenceApi | null>(null);

export function EvidenceProvider({ children }: { children: ReactNode }) {
  // A small stack lets the user drill from an attribute into an entity and back.
  const [stack, setStack] = useState<EvidenceTarget[]>([]);
  const open = useCallback((t: EvidenceTarget) => setStack((s) => [...s, t]), []);
  const close = useCallback(() => setStack([]), []);
  const back = useCallback(() => setStack((s) => s.slice(0, -1)), []);
  const value = useMemo(() => ({ open, close }), [open, close]);
  const current = stack[stack.length - 1];
  const { title, subtitle } = current ? evidenceTitle(current) : { title: "", subtitle: undefined };

  return (
    <EvidenceContext.Provider value={value}>
      {children}
      <Drawer open={!!current} onClose={close} title={title} subtitle={subtitle}>
        {current && <EvidenceContent target={current} onBack={stack.length > 1 ? back : undefined} />}
      </Drawer>
    </EvidenceContext.Provider>
  );
}

export function useEvidence(): EvidenceApi {
  const ctx = useContext(EvidenceContext);
  if (!ctx) throw new Error("useEvidence must be used inside EvidenceProvider");
  return ctx;
}
