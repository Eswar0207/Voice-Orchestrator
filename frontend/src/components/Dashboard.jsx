import LeadTable from "./LeadTable.jsx";

const STATUS_ORDER = ["PENDING", "QUALIFIED", "NOT_INTERESTED", "NEEDS_REVIEW"];
const STATUS_LABELS = {
  PENDING: "Pending",
  QUALIFIED: "Qualified",
  NOT_INTERESTED: "Not Interested",
  NEEDS_REVIEW: "Needs Review",
};

function StatCard({ label, value, accentClass }) {
  return (
    <div className="glass-panel px-5 py-4 flex flex-col gap-1">
      <span className="text-xs font-mono uppercase tracking-wide text-zinc-500">
        {label}
      </span>
      <span className={`font-display text-2xl font-semibold ${accentClass}`}>
        {value}
      </span>
    </div>
  );
}

export default function Dashboard({
  company,
  customers,
  loading,
  onTriggerCampaign,
  triggering,
  triggerMessage,
  onResetCampaign,
  resetting,
}) {
  if (!company) {
    return (
      <div className="glass-panel px-6 py-10 text-center text-zinc-500">
        Loading tenants…
      </div>
    );
  }

  const total = customers.length;
  const counts = STATUS_ORDER.reduce((acc, s) => {
    acc[s] = customers.filter((c) => c.status === s).length;
    return acc;
  }, {});
  const pendingCount = counts.PENDING || 0;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h2 className="font-display text-lg font-semibold text-zinc-50">
            {company.name}
          </h2>
          <p className="text-sm text-zinc-500 max-w-xl mt-1">
            {company.prompt_instructions}
          </p>
        </div>

        <div className="flex flex-col items-end gap-2">
          <div className="flex items-center gap-3">
            <button
              onClick={onResetCampaign}
              disabled={resetting || triggering}
              className="px-4 py-2.5 rounded-xl border border-line bg-transparent text-zinc-300 font-semibold text-sm
                         hover:bg-zinc-800 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {resetting ? "Resetting…" : "Reset Leads"}
            </button>
            <button
              onClick={onTriggerCampaign}
              disabled={triggering || resetting || pendingCount === 0}
              className="px-5 py-2.5 rounded-xl bg-accent text-ink font-semibold text-sm
                         hover:bg-accent-soft transition-colors disabled:opacity-40
                         disabled:cursor-not-allowed shadow-[0_0_24px_rgba(110,155,255,0.25)]"
            >
              {triggering
                ? "Dispatching…"
                : `Trigger Outbound Campaign (${pendingCount} pending)`}
            </button>
          </div>
          {triggerMessage && (
            <span className="text-xs text-zinc-400 font-mono">{triggerMessage}</span>
          )}
        </div>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
        <StatCard label="Total Leads" value={total} accentClass="text-zinc-100" />
        <StatCard label="Pending" value={counts.PENDING || 0} accentClass="text-signal-pending" />
        <StatCard label="Qualified" value={counts.QUALIFIED || 0} accentClass="text-signal-qualified" />
        <StatCard
          label="Not Interested"
          value={counts.NOT_INTERESTED || 0}
          accentClass="text-signal-notinterested"
        />
        <StatCard
          label="Needs Review"
          value={counts.NEEDS_REVIEW || 0}
          accentClass="text-signal-review"
        />
      </div>

      <LeadTable customers={customers} loading={loading} />
    </div>
  );
}

export { STATUS_LABELS };
