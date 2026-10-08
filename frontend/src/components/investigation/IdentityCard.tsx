import { ChevronRight } from "lucide-react";
import { useState } from "react";
import { useEvidence } from "../../context/evidence";
import { IDENTITY_GROUPS, attributeLabel } from "../../lib/meta";
import type { IdentityAttribute } from "../../lib/types";
import { ConfidenceBadge } from "../ui/indicators";
import { Card, EmptyState } from "../ui/primitives";

const VALUES_SHOWN = 3;

function AttributeRow({ attr, values }: { attr: string; values: IdentityAttribute[] }) {
  const { open } = useEvidence();
  const [expanded, setExpanded] = useState(false);
  const shown = expanded ? values : values.slice(0, VALUES_SHOWN);
  return (
    <div className="grid grid-cols-[110px_1fr] gap-3 border-t border-line py-2 first:border-t-0 first:pt-0">
      <div className="pt-1 text-xs text-muted">{attributeLabel(attr)}</div>
      <ul className="min-w-0 space-y-0.5">
        {shown.map((v) => (
          <li key={v.normalized_value}>
            <button
              type="button"
              onClick={() => open({ type: "attribute", attribute: v })}
              className="group flex w-full items-center gap-3 rounded-md px-2 py-1 text-left hover:bg-surface-2"
              aria-label={`${attributeLabel(attr)} ${v.value}: show evidence`}
            >
              <span className={`min-w-0 flex-1 text-[13px] text-fg ${attr === "bio" ? "line-clamp-2" : "truncate"}`}>
                {v.value}
              </span>
              <span className="hidden shrink-0 text-[11px] text-subtle sm:inline">
                {v.source_count} source{v.source_count === 1 ? "" : "s"}
              </span>
              <ConfidenceBadge score={v.confidence} level={v.level} />
              <ChevronRight className="size-3.5 shrink-0 text-subtle opacity-0 group-hover:opacity-100" aria-hidden />
            </button>
          </li>
        ))}
        {values.length > VALUES_SHOWN && (
          <li>
            <button type="button" onClick={() => setExpanded((e) => !e)} className="px-2 text-[11px] text-subtle hover:text-fg">
              {expanded ? "Show fewer" : `+${values.length - VALUES_SHOWN} more`}
            </button>
          </li>
        )}
      </ul>
    </div>
  );
}

export function IdentityCard({ attributes }: { attributes: IdentityAttribute[] }) {
  const byAttr = new Map<string, IdentityAttribute[]>();
  for (const a of attributes) byAttr.set(a.attribute, [...(byAttr.get(a.attribute) ?? []), a]);
  const known = new Set(IDENTITY_GROUPS.flatMap((g) => g.attributes));
  const other = [...byAttr.keys()].filter((k) => !known.has(k));
  const groups = [...IDENTITY_GROUPS, { title: "Other", attributes: other }]
    .map((g) => ({ ...g, attributes: g.attributes.filter((a) => byAttr.has(a)) }))
    .filter((g) => g.attributes.length > 0);

  return (
    <Card title="Identity" actions={<span className="text-[11px] text-subtle">Click any value for evidence</span>}>
      {groups.length === 0 ? (
        <EmptyState title="No corroborated attributes yet" className="py-6">
          Attributes appear once sources return public information that can be linked to the subject.
        </EmptyState>
      ) : (
        <div className="space-y-5">
          {groups.map((g) => (
            <div key={g.title}>
              <div className="label-caps mb-2">{g.title}</div>
              {g.attributes.map((a) => (
                <AttributeRow key={a} attr={a} values={byAttr.get(a)!} />
              ))}
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}
