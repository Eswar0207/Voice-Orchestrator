export default function TenantSelector({ companies, activeCompanyId, onChange }) {
  if (companies.length === 0) {
    return (
      <div className="text-sm text-zinc-500 font-mono">No tenants loaded</div>
    );
  }

  return (
    <div className="relative">
      <select
        value={activeCompanyId || ""}
        onChange={(e) => onChange(e.target.value)}
        className="appearance-none glass-panel pl-4 pr-10 py-2.5 text-sm font-medium text-zinc-100
                   cursor-pointer hover:border-accent/50 focus:outline-none focus:ring-2
                   focus:ring-accent/40 transition-colors"
      >
        {companies.map((c) => (
          <option key={c.id} value={c.id} className="bg-panel text-zinc-100">
            {c.name}
          </option>
        ))}
      </select>
      <svg
        className="pointer-events-none absolute right-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500"
        fill="none"
        viewBox="0 0 24 24"
        stroke="currentColor"
      >
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
      </svg>
    </div>
  );
}
