import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { useEffect, useMemo } from "react";
import { api } from "../../lib/api";

/**
 * Renders an observed image via the backend proxy. The investigator's browser never
 * requests the image from the platform directly (OPSEC), and only observed images can be loaded.
 */
export function ProxiedAvatar({
  observationId,
  label,
  size = 40,
  rounded = "full",
  className,
}: {
  observationId: string | null | undefined;
  label: string;
  size?: number;
  rounded?: "full" | "md";
  className?: string;
}) {
  const { data: blob, isError } = useQuery({
    queryKey: ["image", observationId],
    queryFn: () => api.imageBlob(observationId!),
    enabled: !!observationId,
    staleTime: Infinity,
    gcTime: 10 * 60_000,
    retry: false,
  });
  const src = useMemo(() => (blob ? URL.createObjectURL(blob) : null), [blob]);
  useEffect(() => () => (src ? URL.revokeObjectURL(src) : undefined), [src]);

  const initials = label
    .replace(/^@/, "")
    .split(/[\s._-]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase())
    .join("");

  return (
    <span
      className={clsx(
        "relative inline-flex shrink-0 items-center justify-center overflow-hidden border border-line-strong bg-surface-3 font-semibold text-muted",
        rounded === "full" ? "rounded-full" : "rounded-lg",
        className,
      )}
      style={{ width: size, height: size, fontSize: size * 0.34 }}
    >
      {src && !isError ? (
        <img src={src} alt={`Image observed for ${label}`} className="size-full object-cover" />
      ) : (
        <span aria-hidden>{initials || "?"}</span>
      )}
    </span>
  );
}
