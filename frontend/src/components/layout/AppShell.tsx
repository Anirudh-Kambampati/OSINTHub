import clsx from "clsx";
import {
  Archive,
  Code2,
  FileText,
  FolderSearch,
  Globe,
  History,
  LayoutDashboard,
  Network,
  Newspaper,
  Radar,
  Settings,
  Users,
  type LucideIcon,
} from "lucide-react";
import { useEffect } from "react";
import { NavLink, Outlet, useMatch } from "react-router";
import { SearchBar } from "../search/SearchBar";

const LAST_KEY = "osint.lastInvestigation";

function readLast(): string | null {
  try {
    return localStorage.getItem(LAST_KEY);
  } catch {
    return null;
  }
}

/** The investigation the sidebar's workspace links point at: the open one, or the last one opened. */
function useCurrentInvestigationId(): string | null {
  const match = useMatch("/investigations/:id/*");
  const id = match?.params.id ?? null;
  useEffect(() => {
    if (id) {
      try {
        localStorage.setItem(LAST_KEY, id);
      } catch {
        /* storage unavailable */
      }
    }
  }, [id]);
  return id ?? readLast();
}

function NavItem({ to, icon: Icon, label, disabled }: { to: string; icon: LucideIcon; label: string; disabled?: boolean }) {
  if (disabled) {
    return (
      <span
        className="flex h-8 cursor-not-allowed items-center gap-2.5 rounded-md px-2.5 text-[13px] text-subtle/60"
        title="Open an investigation first"
        aria-disabled
      >
        <Icon className="size-4" aria-hidden />
        {label}
      </span>
    );
  }
  return (
    <NavLink
      to={to}
      end={to === "/"}
      className={({ isActive }) =>
        clsx(
          "flex h-8 items-center gap-2.5 rounded-md px-2.5 text-[13px] transition-colors",
          isActive ? "bg-surface-3 text-fg" : "text-muted hover:bg-surface-2 hover:text-fg",
        )
      }
    >
      <Icon className="size-4" aria-hidden />
      {label}
    </NavLink>
  );
}

function NavSection({ title, children }: { title?: string; children: React.ReactNode }) {
  return (
    <div className="space-y-0.5">
      {title && <div className="label-caps px-2.5 pt-4 pb-1.5">{title}</div>}
      {children}
    </div>
  );
}

export function AppShell() {
  const current = useCurrentInvestigationId();
  const ws = (path: string) => (current ? `/investigations/${current}${path}` : "#");
  return (
    <div className="flex h-full">
      <aside className="hidden w-56 shrink-0 flex-col border-r border-line bg-surface md:flex">
        <div className="flex h-12 items-center gap-2 border-b border-line px-4">
          <Radar className="size-4 text-accent" aria-hidden />
          <span className="text-[12px] font-semibold tracking-[0.14em] text-fg">OSINT CONSOLE</span>
        </div>
        <nav className="flex-1 overflow-y-auto p-2" aria-label="Primary">
          <NavSection>
            <NavItem to="/" icon={LayoutDashboard} label="Overview" />
            <NavItem to="/investigations" icon={FolderSearch} label="Investigations" />
            <NavItem to={ws("/profiles")} icon={Users} label="Profiles" disabled={!current} />
            <NavItem to={ws("/mentions")} icon={Newspaper} label="Mentions" disabled={!current} />
            <NavItem to={ws("/timeline")} icon={History} label="Timeline" disabled={!current} />
            <NavItem to={ws("/graph")} icon={Network} label="Graph" disabled={!current} />
          </NavSection>
          <NavSection title="Sources">
            <NavItem to={ws("/sources/social")} icon={Users} label="Social" disabled={!current} />
            <NavItem to={ws("/sources/web")} icon={Globe} label="Web" disabled={!current} />
            <NavItem to={ws("/sources/code")} icon={Code2} label="Code" disabled={!current} />
            <NavItem to={ws("/sources/domains")} icon={Archive} label="Domains" disabled={!current} />
            <NavItem to={ws("/sources/documents")} icon={FileText} label="Documents" disabled={!current} />
          </NavSection>
          <NavSection title="System">
            <NavItem to="/settings" icon={Settings} label="Settings" />
          </NavSection>
        </nav>
        <div className="border-t border-line px-4 py-3 text-[11px] leading-relaxed text-subtle">
          Public information only. Every fact links to its source.
        </div>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-12 shrink-0 items-center gap-3 border-b border-line bg-bg/80 px-4 backdrop-blur">
          <Radar className="size-4 text-accent md:hidden" aria-hidden />
          <div className="w-full max-w-2xl">
            <SearchBar />
          </div>
        </header>
        <main className="min-h-0 flex-1 overflow-y-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
