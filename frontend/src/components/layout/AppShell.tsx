import { useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import {
  Archive,
  Code2,
  FileText,
  FolderSearch,
  Globe,
  History,
  LayoutDashboard,
  LogOut,
  Menu,
  Monitor,
  Moon,
  Network,
  Newspaper,
  Radar,
  Settings,
  Sun,
  Users,
  X,
  type LucideIcon,
} from "lucide-react";
import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useMatch, useNavigate } from "react-router";
import { useCurrentUser } from "../../context/auth";
import { api } from "../../lib/api";
import { useTheme, type ThemePref } from "../../lib/theme";
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

const THEMES: { key: ThemePref; icon: LucideIcon; label: string }[] = [
  { key: "dark", icon: Moon, label: "Dark" },
  { key: "light", icon: Sun, label: "Light" },
  { key: "system", icon: Monitor, label: "System" },
];

function UserFooter() {
  const user = useCurrentUser();
  const { pref, setPref } = useTheme();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const signOut = async () => {
    await api.logout().catch(() => undefined);
    qc.clear();
    navigate("/login", { replace: true });
  };
  return (
    <div className="space-y-3 border-t border-line px-3 py-3">
      <div role="radiogroup" aria-label="Theme" className="flex rounded-md border border-line p-0.5">
        {THEMES.map(({ key, icon: Icon, label }) => (
          <button
            key={key}
            type="button"
            role="radio"
            aria-checked={pref === key}
            title={label}
            onClick={() => setPref(key)}
            className={clsx(
              "flex flex-1 items-center justify-center rounded py-1",
              pref === key ? "bg-surface-3 text-fg" : "text-subtle hover:text-fg",
            )}
          >
            <Icon className="size-3.5" aria-hidden />
            <span className="sr-only">{label}</span>
          </button>
        ))}
      </div>
      {user && (
        <div className="flex items-center gap-2">
          <div className="min-w-0 flex-1">
            <div className="truncate text-[12px] font-medium text-fg">{user.name}</div>
            <div className="truncate text-[11px] text-subtle">{user.role === "admin" ? "Administrator" : "Analyst"}</div>
          </div>
          <button
            type="button"
            onClick={signOut}
            title="Sign out"
            aria-label="Sign out"
            className="rounded-md p-1.5 text-subtle hover:bg-surface-2 hover:text-fg"
          >
            <LogOut className="size-4" />
          </button>
        </div>
      )}
    </div>
  );
}

function SidebarContent() {
  const current = useCurrentInvestigationId();
  const ws = (path: string) => (current ? `/investigations/${current}${path}` : "#");
  return (
    <>
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
      <UserFooter />
    </>
  );
}

function Brand() {
  return (
    <div className="flex h-12 items-center gap-2 border-b border-line px-4">
      <Radar className="size-4 text-accent" aria-hidden />
      <span className="text-[12px] font-semibold tracking-[0.14em] text-fg">OSINT CONSOLE</span>
    </div>
  );
}

export function AppShell() {
  const [mobileOpen, setMobileOpen] = useState(false);
  const location = useLocation();
  useEffect(() => setMobileOpen(false), [location.pathname]);

  return (
    <div className="flex h-full">
      <aside className="hidden w-56 shrink-0 flex-col border-r border-line bg-surface md:flex">
        <Brand />
        <SidebarContent />
      </aside>

      {mobileOpen && (
        <div className="fixed inset-0 z-50 md:hidden">
          <div className="absolute inset-0 bg-[var(--overlay)]" onClick={() => setMobileOpen(false)} aria-hidden />
          <aside
            role="dialog"
            aria-modal="true"
            aria-label="Navigation"
            className="relative flex h-full w-64 flex-col border-r border-line bg-surface shadow-2xl"
          >
            <div className="flex items-center justify-between pr-2">
              <Brand />
              <button
                type="button"
                onClick={() => setMobileOpen(false)}
                aria-label="Close navigation"
                className="rounded-md p-1.5 text-muted hover:bg-surface-2"
              >
                <X className="size-4" />
              </button>
            </div>
            <SidebarContent />
          </aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-12 shrink-0 items-center gap-3 border-b border-line bg-bg/80 px-4 backdrop-blur">
          <button
            type="button"
            onClick={() => setMobileOpen(true)}
            aria-label="Open navigation"
            className="-ml-1 rounded-md p-1.5 text-muted hover:bg-surface-2 md:hidden"
          >
            <Menu className="size-5" />
          </button>
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
