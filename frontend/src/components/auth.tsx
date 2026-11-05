"use client";
import { createContext, useContext, useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, post } from "@/lib/api";
import { Button } from "./ui/button";
import { ErrorBox, Loading } from "./common";

type User = {
  id: string;
  username: string;
  role: "admin" | "editor" | "viewer";
  active: boolean;
};
type Session = {
  enabled: boolean;
  user: User | null;
  setup_required?: boolean;
  deployment?: "local" | "vercel";
};
const AuthContext = createContext<Session>({ enabled: false, user: null });
export const useAuth = () => useContext(AuthContext);

export function AuthGate({ children }: { children: React.ReactNode }) {
  const client = useQueryClient();
  const session = useQuery({
    queryKey: ["session"],
    queryFn: () => api<Session>("/auth/me"),
    retry: false,
    refetchInterval: 60000,
  });
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const login = useMutation({
    mutationFn: () => post("/auth/login", { username, password }),
    onSuccess: () => {
      setPassword("");
      client.clear();
      void session.refetch();
    },
  });
  useEffect(() => {
    const refresh = () => {
      client.clear();
      void session.refetch();
    };
    window.addEventListener("autorca-session-expired", refresh);
    return () => window.removeEventListener("autorca-session-expired", refresh);
  }, [client]);
  if (session.isPending) return <Loading />;
  if (session.data?.user)
    return (
      <AuthContext.Provider value={session.data}>
        {children}
      </AuthContext.Provider>
    );
  return (
    <main id="main-content" className="auth-page">
      <section className="panel panel-body auth-card">
        <div className="eyebrow">AUTORCA-X · SHARED WORKSPACE</div>
        <h1>Sign in</h1>
        <p>Use your workspace account to investigate and review incidents.</p>
        <ErrorBox error={session.error || login.error} />
        {session.data?.setup_required ? (
          <div className="inline-notice">
            <div>
              <strong>Create your first administrator</strong>
              {session.data.deployment === "vercel" ? (
                <p>The workspace administrator needs to finish database setup before sign-in is available.</p>
              ) : <>
              <p>
                Run this command in the project root, then choose a
                username and password locally.
              </p>
              <code>
                PYTHONPATH=backend backend/.venv/bin/python -m app.manage create-admin --username admin
              </code>
              <p>
                For Docker:{" "}
                <code>
                  docker compose exec backend python -m app.manage create-admin
                  --username admin
                </code>
              </p>
              </>}
              <Button variant="outline" onClick={() => session.refetch()}>
                Check setup
              </Button>
            </div>
          </div>
        ) : (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              login.mutate();
            }}
          >
            <label htmlFor="username">Username</label>
            <input
              id="username"
              autoComplete="username"
              required
              value={username}
              onChange={(e) => setUsername(e.target.value)}
            />
            <label htmlFor="password">Password</label>
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            <Button
              className="full-width"
              disabled={login.isPending || !!session.error}
            >
              Sign in
            </Button>
          </form>
        )}
      </section>
    </main>
  );
}

export function AccountControls() {
  const { user, enabled } = useAuth();
  const client = useQueryClient();
  const logout = useMutation({
    mutationFn: () => post("/auth/logout"),
    onSuccess: () => {
      client.clear();
      window.location.assign("/");
    },
  });
  return (
    <div>
      {enabled && (
        <Button
          variant="ghost"
          title={`Sign out ${user?.username}`}
          onClick={() => logout.mutate()}
          disabled={logout.isPending}
        >
          Sign out
        </Button>
      )}
      <ErrorBox error={logout.error} />
    </div>
  );
}

export function UserManagement() {
  const { user, enabled } = useAuth();
  const client = useQueryClient();
  const users = useQuery({
    queryKey: ["users"],
    queryFn: () => api<{ items: User[] }>("/users"),
    enabled: enabled && user?.role === "admin",
  });
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<User["role"]>("viewer");
  const [current, setCurrent] = useState("");
  const [replacement, setReplacement] = useState("");
  const create = useMutation({
    mutationFn: () => post("/users", { username, password, role }),
    onSuccess: () => {
      setPassword("");
      setUsername("");
      void client.invalidateQueries({ queryKey: ["users"] });
    },
  });
  const update = useMutation({
    mutationFn: (u: User) =>
      api(`/users/${u.id}`, {
        method: "PUT",
        body: JSON.stringify({ role: u.role, active: u.active }),
      }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["users"] }),
  });
  const change = useMutation({
    mutationFn: () =>
      post("/auth/password", {
        current_password: current,
        new_password: replacement,
      }),
    onSuccess: () => {
      setCurrent("");
      setReplacement("");
      client.clear();
      window.location.assign("/");
    },
  });
  if (!enabled)
    return (
      <p className="inline-notice">
        Authentication is disabled for this development workspace.
      </p>
    );
  return (
    <section className="panel panel-body">
      <h2>Workspace accounts</h2>
      <p>
        All accounts share this workspace. Administrators manage users and
        settings; editors investigate and review; viewers have read access.
      </p>
      <ErrorBox
        error={users.error || create.error || update.error || change.error}
      />
      {user?.role === "admin" && (
        <>
          {users.data?.items.map((u) => (
            <div className="account-row" key={u.id}>
              <strong>{u.username}</strong>
              <select
                aria-label={`Role for ${u.username}`}
                disabled={update.isPending}
                value={u.role}
                onChange={(e) =>
                  update.mutate({ ...u, role: e.target.value as User["role"] })
                }
              >
                {["viewer", "editor", "admin"].map((r) => (
                  <option key={r}>{r}</option>
                ))}
              </select>
              <Button
                variant="outline"
                disabled={update.isPending}
                onClick={() => update.mutate({ ...u, active: !u.active })}
              >
                {u.active ? "Deactivate" : "Reactivate"}
              </Button>
            </div>
          ))}
          <form
            className="account-form"
            onSubmit={(e) => {
              e.preventDefault();
              create.mutate();
            }}
          >
            <h3>Add an account</h3>
            <label>
              New username
              <input
                required
                pattern="[a-zA-Z0-9_.-]{3,64}"
                autoComplete="off"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
              />
            </label>
            <label>
              Temporary password
              <input
                required
                type="password"
                minLength={12}
                maxLength={256}
                autoComplete="new-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </label>
            <label>
              Role
              <select
                value={role}
                onChange={(e) => setRole(e.target.value as User["role"])}
              >
                {["viewer", "editor", "admin"].map((r) => (
                  <option key={r}>{r}</option>
                ))}
              </select>
            </label>
            <Button disabled={create.isPending}>Create account</Button>
          </form>
        </>
      )}
      <form
        className="account-form"
        onSubmit={(e) => {
          e.preventDefault();
          change.mutate();
        }}
      >
        <h3>Change your password</h3>
        <label>
          Current password
          <input
            type="password"
            required
            autoComplete="current-password"
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
          />
        </label>
        <label>
          New password
          <input
            type="password"
            required
            minLength={12}
            maxLength={256}
            autoComplete="new-password"
            value={replacement}
            onChange={(e) => setReplacement(e.target.value)}
          />
        </label>
        <Button variant="outline" disabled={change.isPending}>
          Change password and sign out
        </Button>
      </form>
    </section>
  );
}
