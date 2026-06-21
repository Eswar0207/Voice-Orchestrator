import { useState } from "react";
import LogViewer from "./LogViewer.jsx";

const STATUS_STYLES = {
  PENDING: "bg-signal-pending/15 text-signal-pending",
  CALL_INITIATED: "bg-signal-initiated/15 text-signal-initiated",
  QUALIFIED: "bg-signal-qualified/15 text-signal-qualified",
  NOT_INTERESTED: "bg-signal-notinterested/15 text-signal-notinterested",
  FAILED: "bg-signal-failed/15 text-signal-failed",
  NEEDS_REVIEW: "bg-signal-review/15 text-signal-review",
};

function StatusBadge({ status }) {
  const cls = STATUS_STYLES[status] || "bg-zinc-700/30 text-zinc-300";
  return <span className={`status-badge ${cls}`}>{status.replace(/_/g, " ")}</span>;
}

export default function LeadTable({ customers, loading }) {
  const [logViewerCustomer, setLogViewerCustomer] = useState(null);

  const hasLogs = (status) =>
    ["QUALIFIED", "NOT_INTERESTED", "NEEDS_REVIEW"].includes(status);

  return (
    <div className="glass-panel overflow-hidden">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-line/60 text-left text-xs font-mono uppercase tracking-wide text-zinc-500">
            <th className="px-5 py-3 font-medium">Name</th>
            <th className="px-5 py-3 font-medium">Phone</th>
            <th className="px-5 py-3 font-medium">Status</th>
            <th className="px-5 py-3 font-medium text-right">Logs</th>
          </tr>
        </thead>
        <tbody>
          {loading && customers.length === 0 && (
            <tr>
              <td colSpan={4} className="px-5 py-8 text-center text-zinc-500">
                Loading leads…
              </td>
            </tr>
          )}
          {!loading && customers.length === 0 && (
            <tr>
              <td colSpan={4} className="px-5 py-8 text-center text-zinc-500">
                No leads for this tenant yet.
              </td>
            </tr>
          )}
          {customers.map((c) => (
            <tr
              key={c.id}
              className="border-b border-line/30 last:border-0 hover:bg-white/[0.02] transition-colors"
            >
              <td className="px-5 py-3.5 text-zinc-100 font-medium">{c.name}</td>
              <td className="px-5 py-3.5">
                <a
                  href={`tel:${c.phone_number}`}
                  className="text-accent-soft hover:text-accent font-mono text-xs"
                >
                  {c.phone_number}
                </a>
              </td>
              <td className="px-5 py-3.5">
                <StatusBadge status={c.status} />
              </td>
              <td className="px-5 py-3.5 text-right">
                {hasLogs(c.status) ? (
                  <button
                    onClick={() => setLogViewerCustomer(c)}
                    className="text-xs font-mono text-accent-soft hover:text-accent underline underline-offset-2"
                  >
                    View Logs
                  </button>
                ) : (
                  <span className="text-xs text-zinc-600">—</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {logViewerCustomer && (
        <LogViewer
          customer={logViewerCustomer}
          onClose={() => setLogViewerCustomer(null)}
        />
      )}
    </div>
  );
}
