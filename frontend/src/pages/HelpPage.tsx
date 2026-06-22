import { useState } from "react";
import { Link } from "react-router-dom";

/* ─── Data ─── */
const SECTIONS = [
  {
    id: "overview",
    title: "What is FlowForge?",
    content: [
      {
        type: "p",
        text: "FlowForge is a workflow automation platform. You define a process as a series of states and transitions, attach rules that automatically block or redirect work based on data, then track every case (instance) as it moves through that process — with a full audit trail of who did what and when.",
      },
      {
        type: "p",
        text: "Two demo workflows are pre-loaded: a simple Employee Leave Request (3 states) and a complex Insurance Claim (6 states, branching paths, and a value-based escalation rule).",
      },
    ],
  },
  {
    id: "quickstart",
    title: "Quick start (5-minute demo)",
    content: [
      { type: "step", n: "1", text: "Log in as admin@flowforge.dev / Admin1234!" },
      { type: "step", n: "2", text: "Open Workflows → Insurance Claim. Note the state graph and the rule that blocks claims over £10,000." },
      { type: "step", n: "3", text: "Click + New CLM to create a new insurance claim instance." },
      { type: "step", n: "4", text: "Open the new instance. In the Metadata panel, add a field claim_value = 15000, then save." },
      { type: "step", n: "5", text: "Try clicking \"Approve Standard\" — the rule engine blocks it with the configured message." },
      { type: "step", n: "6", text: "Click \"Escalate\" instead to route to Director Approval, then \"Director Approve\" to close the claim." },
      { type: "step", n: "7", text: "Add a comment at any point to record a decision rationale. It appears in the Timeline below." },
    ],
  },
  {
    id: "workflows",
    title: "Building workflows",
    content: [
      {
        type: "heading",
        text: "States",
      },
      {
        type: "p",
        text: "Every workflow needs exactly one Start state and at least one End (terminal) state. Intermediate states represent stages work passes through — e.g. Draft, Under Review, Director Approval.",
      },
      {
        type: "heading",
        text: "Transitions",
      },
      {
        type: "p",
        text: "A transition is a named edge between two states — e.g. \"Submit\" goes from Draft to Under Review. Mark a transition as Requires Approval if only users with the Approver role can fire it.",
      },
      {
        type: "heading",
        text: "Using the visual builder",
      },
      {
        type: "p",
        text: "Go to New Workflow. Drag from the right-hand handle of a state node to the left-hand handle of another to draw a transition. A dialog asks you to name it. Click any node or edge to edit its properties in the right panel. Set a state as Start or End using the checkboxes. Fill in the workflow name and prefix at the top, then click Save Workflow.",
      },
      {
        type: "heading",
        text: "Reference prefix",
      },
      {
        type: "p",
        text: "The prefix (e.g. CLM, LVE) is prepended to auto-generated case numbers: CLM-2026-00001. Keep it 2–6 uppercase letters.",
      },
    ],
  },
  {
    id: "instances",
    title: "Working with instances",
    content: [
      {
        type: "p",
        text: "An instance is a single live case running through a workflow — e.g. Bob's leave request, or a specific insurance claim. Each instance gets a unique reference number and tracks its current state.",
      },
      {
        type: "heading",
        text: "Metadata",
      },
      {
        type: "p",
        text: "Metadata is a free-form JSON object attached to the instance — claim_value, days_requested, claimant name, etc. You can add, edit, or delete fields at any time using the Edit button on the Metadata panel. Values are automatically typed: numbers are saved as numbers, true/false as booleans, everything else as strings.",
      },
      {
        type: "heading",
        text: "Metadata and rules",
      },
      {
        type: "p",
        text: "Rules read from metadata at transition time. If you set claim_value = 15000 and there is a rule blocking \"Approve Standard\" when claim_value > 10000, the rule fires the moment you try the transition — the instance does not move and the reason is shown in red.",
      },
      {
        type: "heading",
        text: "Comments",
      },
      {
        type: "p",
        text: "Any authenticated user can add a comment to an instance at any time regardless of its current state. Comments appear in the Timeline with a 💬 icon and the commenter's email. Use them for decision rationale, escalation notes, or audit evidence.",
      },
      {
        type: "heading",
        text: "Timeline",
      },
      {
        type: "p",
        text: "Every action — instance created, transition fired, rule triggered, comment posted, metadata updated — is recorded as an immutable audit log entry. Entries cannot be edited or deleted.",
      },
    ],
  },
  {
    id: "rules",
    title: "Rules engine",
    content: [
      {
        type: "p",
        text: "Rules are configured per workflow on the Workflow Detail page. Each rule has a condition (evaluated against instance metadata), an action, and a priority.",
      },
      {
        type: "heading",
        text: "Condition operators",
      },
      {
        type: "table",
        headers: ["Operator", "Meaning", "Example"],
        rows: [
          ["gt", "greater than (numeric)", "claim_value gt 10000"],
          ["gte", "greater than or equal", "days_requested gte 30"],
          ["lt", "less than", "risk_score lt 0.5"],
          ["lte", "less than or equal", "priority lte 2"],
          ["eq", "equals", "category eq Health"],
          ["ne", "not equals", "status ne draft"],
          ["contains", "string contains", "description contains urgent"],
          ["starts_with", "string starts with", "reference starts_with CLM"],
          ["is_true", "boolean is true", "high_priority is_true"],
          ["is_false", "boolean is false", "verified is_false"],
        ],
      },
      {
        type: "heading",
        text: "Action types",
      },
      {
        type: "table",
        headers: ["Action", "Effect"],
        rows: [
          ["block_transition", "Prevents the transition and shows the configured reason to the user"],
          ["assign_role", "Automatically assigns the task created by the target state to the specified role"],
        ],
      },
      {
        type: "heading",
        text: "Priority",
      },
      {
        type: "p",
        text: "Rules with lower priority numbers run first. If a block_transition rule fires, evaluation stops and the transition is prevented. Use priority 1 for your most important guards.",
      },
      {
        type: "heading",
        text: "Trigger scope",
      },
      {
        type: "p",
        text: "Set a rule to trigger on a specific transition (e.g. only \"Approve Standard\") or leave it as \"All transitions\" to evaluate on every step.",
      },
    ],
  },
  {
    id: "roles",
    title: "Roles & permissions",
    content: [
      {
        type: "table",
        headers: ["Role", "Comment", "Fire transitions", "Fire approval transitions", "Manage users/workflows"],
        rows: [
          ["viewer", "✓", "—", "—", "—"],
          ["participant", "✓", "✓", "—", "—"],
          ["approver", "✓", "✓", "✓", "—"],
          ["workflow_designer", "✓", "✓", "✓", "Workflows only"],
          ["platform_admin", "✓", "✓", "✓", "✓"],
        ],
      },
      {
        type: "p",
        text: "A user can hold multiple roles simultaneously. Assign roles on the Users page (Administration → Users). Changes take effect on the user's next page load.",
      },
      {
        type: "p",
        text: "On the instance page, transitions that require a role the current user doesn't have are shown grayed-out under \"Requires higher role\" so it's clear what exists but isn't accessible.",
      },
    ],
  },
  {
    id: "faq",
    title: "FAQ",
    content: [
      {
        type: "faq",
        q: "I set up a rule but it isn't blocking anything.",
        a: "Check that (1) the metadata field name matches exactly — rules are case-sensitive, (2) the value type is correct — a string \"10000\" is not greater than a numeric 10000, and (3) the rule's trigger transition matches the one you're attempting. Add the field to the instance's Metadata panel with the expected value and retry.",
      },
      {
        type: "faq",
        q: "The state graph shows all nodes as grey.",
        a: "Grey means unvisited. The graph relies on the audit trail to know which states were actually passed through. Instances created before audit logging was enabled (or via direct DB import) have no history. Run python manage.py seed --reset to regenerate demo data with full audit trails.",
      },
      {
        type: "faq",
        q: "Can I edit a workflow after instances have been created?",
        a: "Currently, editing a workflow definition (adding states/transitions) after instances exist is not prevented by the UI, but it can cause inconsistency. In production, the recommended approach is to publish a new workflow version and migrate open instances. Workflow versioning is on the roadmap.",
      },
      {
        type: "faq",
        q: "What does 'requires approval' on a transition mean?",
        a: "It restricts who can fire that transition to users with the approver, workflow_designer, or platform_admin role. Participants and viewers see the transition grayed-out. This is enforced in the frontend — the backend does not yet enforce role checks at the API level.",
      },
      {
        type: "faq",
        q: "Can I run this without Docker?",
        a: "Yes — that's the default dev setup. Run the Django backend with python manage.py runserver --settings=config.settings.local_sqlite (SQLite, no container needed), the Vite frontend with npm run dev, and optionally the FastAPI rules microservice with uvicorn main:app --port 8001. See the README for full instructions.",
      },
      {
        type: "faq",
        q: "Where is data stored?",
        a: "In local dev mode, everything is stored in backend/dev.sqlite3. No external services are required. The FastAPI rules microservice is optional — if it is not running, rule evaluation falls back to the local Python engine automatically.",
      },
    ],
  },
];

/* ─── Components ─── */
function FAQItem({ q, a }: { q: string; a: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div style={{
      border: "1px solid var(--border)", borderRadius: 10, overflow: "hidden",
      marginBottom: 8,
    }}>
      <button
        onClick={() => setOpen(v => !v)}
        style={{
          width: "100%", textAlign: "left", padding: "12px 16px",
          background: open ? "rgba(99,102,241,0.06)" : "var(--bg-elevated)",
          border: "none", cursor: "pointer", color: "var(--text-primary)",
          fontWeight: 600, fontSize: "0.88rem", display: "flex", justifyContent: "space-between", alignItems: "center",
        }}
      >
        <span>{q}</span>
        <span style={{ color: "var(--accent-light)", fontSize: "1rem", flexShrink: 0, marginLeft: 12 }}>{open ? "−" : "+"}</span>
      </button>
      {open && (
        <div style={{
          padding: "12px 16px", borderTop: "1px solid var(--border)",
          fontSize: "0.85rem", color: "var(--text-secondary)", lineHeight: 1.7,
          background: "var(--bg-surface)",
        }}>
          {a}
        </div>
      )}
    </div>
  );
}

function renderContent(item: any, i: number) {
  switch (item.type) {
    case "p":
      return <p key={i} style={{ color: "var(--text-secondary)", lineHeight: 1.7, marginBottom: 12, fontSize: "0.88rem" }}>{item.text}</p>;
    case "heading":
      return <h4 key={i} style={{ color: "var(--text-primary)", marginBottom: 6, marginTop: 16, fontSize: "0.88rem", fontWeight: 700 }}>{item.text}</h4>;
    case "step":
      return (
        <div key={i} style={{ display: "flex", gap: 12, marginBottom: 10, alignItems: "flex-start" }}>
          <div style={{
            width: 24, height: 24, borderRadius: "50%", background: "rgba(99,102,241,0.2)",
            color: "var(--accent-light)", fontSize: "0.75rem", fontWeight: 700,
            display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, marginTop: 1,
          }}>{item.n}</div>
          <p style={{ color: "var(--text-secondary)", fontSize: "0.88rem", lineHeight: 1.6, margin: 0 }}>{item.text}</p>
        </div>
      );
    case "table":
      return (
        <div key={i} style={{ overflowX: "auto", marginBottom: 14 }}>
          <table className="table" style={{ fontSize: "0.82rem" }}>
            <thead><tr>{item.headers.map((h: string) => <th key={h}>{h}</th>)}</tr></thead>
            <tbody>
              {item.rows.map((row: string[], ri: number) => (
                <tr key={ri}>
                  {row.map((cell, ci) => (
                    <td key={ci} style={{ fontFamily: ci === 0 ? "monospace" : undefined, color: ci === 0 ? "var(--accent-light)" : undefined }}>
                      {cell}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
    case "faq":
      return <FAQItem key={i} q={item.q} a={item.a} />;
    default:
      return null;
  }
}

/* ─── Page ─── */
export default function HelpPage() {
  const [activeSection, setActiveSection] = useState("overview");

  return (
    <div>
      <div className="page-header">
        <div className="page-header-left">
          <h2>User Guide</h2>
          <p>How to use FlowForge — workflows, rules, roles, and the demo walkthrough</p>
        </div>
        <Link to="/dashboard" className="btn-secondary btn-sm">← Dashboard</Link>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "200px 1fr", gap: 20, alignItems: "start" }}>
        {/* Sidebar nav */}
        <div className="card" style={{ position: "sticky", top: 16, padding: "8px 0" }}>
          {SECTIONS.map(s => (
            <a
              key={s.id}
              href={`#${s.id}`}
              onClick={() => setActiveSection(s.id)}
              style={{
                display: "block", padding: "8px 16px", fontSize: "0.82rem", textDecoration: "none",
                color: activeSection === s.id ? "var(--accent-light)" : "var(--text-secondary)",
                background: activeSection === s.id ? "rgba(99,102,241,0.08)" : "transparent",
                borderLeft: activeSection === s.id ? "2px solid var(--accent)" : "2px solid transparent",
                transition: "all 0.15s",
                fontWeight: activeSection === s.id ? 600 : 400,
              }}
            >
              {s.title}
            </a>
          ))}
        </div>

        {/* Content */}
        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          {SECTIONS.map(s => (
            <div key={s.id} id={s.id} className="card" onClick={() => setActiveSection(s.id)}>
              <h3 style={{ marginBottom: 16, fontSize: "1rem", color: "var(--accent-light)" }}>{s.title}</h3>
              {s.content.map((item, i) => renderContent(item, i))}
            </div>
          ))}

          {/* Demo credentials */}
          <div className="card" style={{ background: "rgba(99,102,241,0.05)", borderColor: "rgba(99,102,241,0.25)" }}>
            <h3 style={{ marginBottom: 14, fontSize: "1rem" }}>Demo credentials</h3>
            <table className="table" style={{ fontSize: "0.83rem" }}>
              <thead><tr><th>Email</th><th>Password</th><th>Roles</th></tr></thead>
              <tbody>
                {[
                  { email: "admin@flowforge.dev",  pw: "Admin1234!", roles: "platform_admin" },
                  { email: "alice@flowforge.dev",  pw: "Alice1234!", roles: "approver" },
                  { email: "bob@flowforge.dev",    pw: "Bob12345!",  roles: "participant" },
                  { email: "carol@flowforge.dev",  pw: "Carol123!",  roles: "approver" },
                ].map(u => (
                  <tr key={u.email}>
                    <td style={{ fontFamily: "monospace" }}>{u.email}</td>
                    <td style={{ fontFamily: "monospace" }}>{u.pw}</td>
                    <td><span className={`badge badge-role-${u.roles}`}>{u.roles}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
