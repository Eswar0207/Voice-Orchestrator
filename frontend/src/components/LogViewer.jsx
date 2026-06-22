import { useEffect, useState } from "react";

function parseTranscriptLines(transcript) {
  if (!transcript) return [];
  // Vapi transcripts are typically newline-separated "Role: text" lines.
  return transcript
    .split("\n")
    .filter(Boolean)
    .map((line) => {
      const match = line.match(/^(AI|User|Assistant|Bot|Agent|System|Caller|Callee|Customer|Representative|Salesperson|Lead)\s*:\s*(.*)$/i);
      if (match) {
        const role = /user|customer|lead/i.test(match[1]) ? "User" : "Agent";
        return { role, text: match[2] };
      }
      return { role: "Agent", text: line };
    });
}

export default function LogViewer({ customer, onClose }) {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    fetch(`/api/customers/${customer.id}/logs`)
      .then((r) => r.json())
      .then((data) => setLogs(data))
      .catch(() => setLogs([]))
      .finally(() => setLoading(false));
  }, [customer.id]);

  const latest = logs[logs.length - 1];
  const lines = parseTranscriptLines(latest?.transcript);
  const reasoning = latest?.call_metadata?.reasoning;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm px-4"
      onClick={onClose}
    >
      <div
        className="glass-panel w-full max-w-2xl max-h-[80vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-6 py-4 border-b border-line/60">
          <div>
            <h3 className="font-display text-base font-semibold text-zinc-50">
              {customer.name}
            </h3>
            <p className="text-xs font-mono text-zinc-500">{customer.phone_number}</p>
          </div>
          <button
            onClick={onClose}
            className="text-zinc-500 hover:text-zinc-200 transition-colors text-sm"
          >
            Close
          </button>
        </div>

        <div className="overflow-y-auto px-6 py-4 flex-1 min-h-0 max-h-[55vh]">
          {loading && <p className="text-zinc-500 text-sm">Loading call log…</p>}

          {!loading && logs.length === 0 && (
            <p className="text-zinc-500 text-sm">No call log available yet.</p>
          )}

          {!loading && latest && (
            <div className="flex flex-col gap-5">
              {latest.summary && (
                <div>
                  <h4 className="text-xs font-mono uppercase tracking-wide text-zinc-500 mb-1.5">
                    Summary
                  </h4>
                  <p className="text-sm text-zinc-300">{latest.summary}</p>
                </div>
              )}

              {reasoning && (
                <div>
                  <h4 className="text-xs font-mono uppercase tracking-wide text-zinc-500 mb-1.5">
                    Classification Reasoning
                  </h4>
                  <p className="text-sm text-zinc-300">{reasoning}</p>
                </div>
              )}

              <div>
                <h4 className="text-xs font-mono uppercase tracking-wide text-zinc-500 mb-2">
                  Transcript
                </h4>
                <div className="flex flex-col gap-2">
                  {lines.length === 0 && (
                    <p className="text-sm text-zinc-500">No transcript text recorded.</p>
                  )}
                  {lines.map((line, i) => (
                    <div
                      key={i}
                      className={`flex ${line.role === "User" ? "justify-end" : "justify-start"}`}
                    >
                      <div
                        className={`max-w-[80%] rounded-xl px-3.5 py-2 text-sm ${
                          line.role === "User"
                            ? "bg-accent/15 text-accent-soft"
                            : "bg-white/5 text-zinc-300"
                        }`}
                      >
                        <span className="block text-[10px] font-mono uppercase tracking-wide opacity-60 mb-0.5">
                          {line.role}
                        </span>
                        {line.text}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
