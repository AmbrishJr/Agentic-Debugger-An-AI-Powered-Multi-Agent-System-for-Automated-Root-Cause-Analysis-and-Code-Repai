"use client";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  ArrowRight,
  ArrowUpRight,
  CheckCheck,
  Clock3,
  FlaskConical,
  GitPullRequest,
  Plus,
  ScanLine,
  ShieldCheck,
  Workflow,
} from "lucide-react";
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { api } from "@/lib/api";
import { Stats } from "@/types";
import { Button } from "@/components/ui/button";
import { Badge, ErrorBox, IncidentTable, Loading } from "@/components/common";
import { date } from "@/lib/utils";

const colors = ["#fb7185", "#f9a76c", "#e3c769", "#69c8b6"];
export default function Dashboard() {
  const { data, error, isPending } = useQuery({
    queryKey: ["dashboard"],
    queryFn: () => api<Stats>("/dashboard/stats"),
    refetchInterval: 10000,
  });
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">
            <span /> YOUR ENGINEERING COMMAND CENTER
          </div>
          <h1>From incident to insight.</h1>
          <p>Understand what broke. Know why. Move forward with confidence.</p>
        </div>
        <Button asChild>
          <Link href="/investigations/new">
            <Plus size={16} /> New investigation
          </Link>
        </Button>
      </div>
      <ErrorBox error={error} />
      {isPending ? (
        <Loading />
      ) : (
        data && (
          <>
            <div className="demo-banner">
              <div>
                <FlaskConical size={19} />
                <span>
                  <strong>A complete investigation, without an API key.</strong>{" "}
                  Try the bundled checkout incident in Demo Mode.
                </span>
              </div>
              <Link href="/investigations/new?sample=1">
                Explore the demo <ArrowRight size={15} />
              </Link>
            </div>
            <div className="metrics-grid">
              {[
                {
                  name: "Total incidents",
                  value: data.total,
                  icon: ScanLine,
                  note: `${data.demo_count} deterministic demo records`,
                },
                {
                  name: "Open incidents",
                  value: data.open,
                  icon: Activity,
                  note: "Investigating or awaiting action",
                },
                {
                  name: "Pending approvals",
                  value: data.pending_approvals,
                  icon: GitPullRequest,
                  note: "Ready for your review",
                },
                {
                  name: "Workflow completion",
                  value:
                    data.success_rate === null ? "—" : `${data.success_rate}%`,
                  icon: CheckCheck,
                  note: "Completed runs / finished attempts",
                },
              ].map(({ name, value, icon: Icon, note }) => (
                <div className="metric-card" key={name}>
                  <div className="metric-top">
                    <span>{name}</span>
                    <Icon size={17} />
                  </div>
                  <strong>{value}</strong>
                  <small>{note}</small>
                </div>
              ))}
            </div>
            <div className="dashboard-grid">
              <section className="panel recent-panel">
                <div className="panel-heading">
                  <div>
                    <h2>
                      Recent incidents{" "}
                      <span className="count-pill">{data.total}</span>
                    </h2>
                    <p>Your latest investigations, all in one place.</p>
                  </div>
                  <Link href="/history" className="subtle-link">
                    View all <ArrowUpRight size={15} />
                  </Link>
                </div>
                <IncidentTable incidents={data.recent} />
              </section>
              <section className="panel severity-panel">
                <div className="panel-heading">
                  <div>
                    <h2>Severity breakdown</h2>
                    <p>Across stored incidents</p>
                  </div>
                  <Activity size={16} />
                </div>
                <div className="chart-container">
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        isAnimationActive={false}
                        data={
                          data.total
                            ? data.severity
                            : [{ name: "No incidents", value: 1 }]
                        }
                        dataKey="value"
                        innerRadius={65}
                        outerRadius={84}
                        paddingAngle={data.total ? 5 : 0}
                        stroke="none"
                      >
                        {(data.total ? data.severity : [{ name: "empty" }]).map(
                          (item, index) => (
                            <Cell
                              key={item.name}
                              fill={data.total ? colors[index] : "#242d31"}
                            />
                          ),
                        )}
                      </Pie>
                      <Tooltip
                        contentStyle={{
                          background: "#172024",
                          border: "1px solid #344146",
                          borderRadius: 8,
                          color: "#f0f4f3",
                        }}
                      />
                    </PieChart>
                  </ResponsiveContainer>
                  <div className="chart-label">
                    <strong>{data.total}</strong>
                    <span>incidents</span>
                  </div>
                </div>
                <div className="chart-legend">
                  {data.severity.map((s, i) => (
                    <div key={s.name}>
                      <span>
                        <i style={{ background: colors[i] }} />
                        {s.name}
                      </span>
                      <strong>{s.value}</strong>
                    </div>
                  ))}
                </div>
              </section>
            </div>
            <div className="dashboard-bottom">
              <section className="panel">
                <div className="panel-heading">
                  <div>
                    <h2>Investigation pipeline</h2>
                    <p>Seven specialized agents. One traceable workflow.</p>
                  </div>
                  <Workflow size={18} />
                </div>
                <div className="pipeline">
                  {[
                    "Triage",
                    "Evidence",
                    "Memory",
                    "Analysis",
                    "Fix",
                    "Validate",
                    "Report",
                  ].map((name, i) => (
                    <div key={name}>
                      <span>{String(i + 1).padStart(2, "0")}</span>
                      <strong>{name}</strong>
                      {i < 6 && <ArrowRight size={12} />}
                    </div>
                  ))}
                </div>
                <div className="pipeline-footer">
                  <ShieldCheck size={16} />
                  <span>Human review is the final gate.</span>
                  <span>
                    {data.approved} approved · {data.resolved} verified resolved
                  </span>
                </div>
              </section>
              <section className="panel">
                <div className="panel-heading">
                  <div>
                    <h2>Latest activity</h2>
                    <p>Updates from your workspace</p>
                  </div>
                  <Clock3 size={16} />
                </div>
                <div className="activity-list">
                  {data.activity.length ? (
                    data.activity.slice(0, 3).map((a) => (
                      <Link key={a.id} href={`/investigations/${a.id}`}>
                        <span className="activity-dot" />
                        <div>
                          <strong>{a.title}</strong>
                          <small>{date(a.time)}</small>
                        </div>
                        <Badge value={a.status} />
                      </Link>
                    ))
                  ) : (
                    <div className="quiet-state">
                      <Clock3 size={20} />
                      <p>Your investigation activity will appear here.</p>
                    </div>
                  )}
                </div>
              </section>
            </div>
            <p className="analytics-note">{data.note}</p>
          </>
        )
      )}
    </>
  );
}
