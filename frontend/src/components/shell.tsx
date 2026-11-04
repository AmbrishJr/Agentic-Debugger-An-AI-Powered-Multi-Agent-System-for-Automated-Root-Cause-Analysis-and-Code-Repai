"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity,
  ArrowUpRight,
  Blocks,
  ChevronDown,
  CircleHelp,
  GitBranch,
  History,
  LayoutDashboard,
  Plus,
  Settings2,
  ShieldCheck,
  Terminal,
  Workflow,
} from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Settings } from "@/types";
import { AccountControls, useAuth } from "./auth";

const links = [
  { href: "/", name: "Overview", icon: LayoutDashboard },
  { href: "/investigations/new", name: "New investigation", icon: Plus },
  { href: "/history", name: "Incident history", icon: History },
  { href: "/settings", name: "Settings", icon: Settings2 },
];
export function Shell({ children }: { children: React.ReactNode }) {
  const { user } = useAuth();
  const path = usePathname();
  const { data, error } = useQuery({
    queryKey: ["settings"],
    queryFn: () => api<Settings>("/settings"),
  });
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Link href="/" className="brand">
          <span className="brand-mark">
            <Workflow size={22} />
          </span>
          <span>
            AutoRCA<span className="brand-x">-X</span>
            <small>ENGINEERING INTELLIGENCE</small>
          </span>
        </Link>
        <div className="workspace-switch">
          <span className="workspace-avatar">A</span>
          <div>
            Local workspace<small>Developer environment</small>
          </div>
          <ChevronDown size={14} />
        </div>
        <span className="nav-caption">WORKSPACE</span>
        <nav aria-label="Main navigation">
          {links.map(({ href, name, icon: Icon }) => (
            <Link
              key={href}
              href={href}
              className={`nav-link ${path === href ? "active" : ""}`}
              aria-current={path === href ? "page" : undefined}
            >
              <Icon size={18} />
              {name}
              {path === href && <span className="nav-dot" />}
            </Link>
          ))}
        </nav>
        <div className="sidebar-note">
          <div className="note-icon">
            <ShieldCheck size={19} />
          </div>
          <strong>Built for human oversight</strong>
          <p>Evidence first. Every proposed fix stays in your control.</p>
          <Link href="/settings">
            View configuration <ArrowUpRight size={13} />
          </Link>
        </div>
        <div className="sidebar-bottom">
          <div className="system-state">
            <span className={`status-dot ${error ? "offline" : ""}`} />
            {error ? "Backend unavailable" : "Local development"}
            <span>v0.1</span>
          </div>
          <div className="profile">
            <span className="profile-avatar">
              <Terminal size={18} />
            </span>
            <div>{user?.username}<small>{user?.role} access</small></div>
            <GitBranch size={16} />
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumb">
            <Blocks size={16} />
            <span>Workspace</span>
            <span>/</span>
            <strong>
              {path === "/"
                ? "Overview"
                : path.startsWith("/history")
                  ? "Incident history"
                  : path.startsWith("/settings")
                    ? "Settings"
                    : path.endsWith("/new")
                      ? "New investigation"
                      : "Investigation"}
            </strong>
          </div>
          <div className="topbar-right">
            <AccountControls />
            <span className="environment-label">
              <span className="status-dot" /> LOCAL
            </span>
            <Link href="/settings" className="mode-pill">
              <Activity size={13} />
              {data?.default_mode === "live"
                ? "Live AI configured"
                : "Demo available"}
            </Link>
            <Link href="/settings" aria-label="Configuration and help">
              <CircleHelp size={18} />
            </Link>
          </div>
        </header>
        <main id="main-content">{children}</main>
        <footer>
          <span>AutoRCA-X · Explainable root cause analysis</span>
          <span>Investigate. Understand. Review.</span>
        </footer>
      </div>
    </div>
  );
}
