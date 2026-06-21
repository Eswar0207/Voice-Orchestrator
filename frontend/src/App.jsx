import { useEffect, useState, useCallback, useRef } from "react";
import TenantSelector from "./components/TenantSelector.jsx";
import Dashboard from "./components/Dashboard.jsx";

const POLL_INTERVAL_MS = 5000;

export default function App() {
  const [companies, setCompanies] = useState([]);
  const [activeCompanyId, setActiveCompanyId] = useState(null);
  const [customers, setCustomers] = useState([]);
  const [loadingCustomers, setLoadingCustomers] = useState(false);
  const [triggering, setTriggering] = useState(false);
  const [triggerMessage, setTriggerMessage] = useState(null);
  const pollRef = useRef(null);

  // Load tenants once on mount
  useEffect(() => {
    fetch("/api/companies")
      .then((r) => r.json())
      .then((data) => {
        setCompanies(data);
        if (data.length > 0) setActiveCompanyId(data[0].id);
      })
      .catch(() => setCompanies([]));
  }, []);

  const fetchCustomers = useCallback((companyId, { silent } = {}) => {
    if (!companyId) return;
    if (!silent) setLoadingCustomers(true);
    fetch(`/api/companies/${companyId}/customers`)
      .then((r) => r.json())
      .then((data) => setCustomers(data))
      .catch(() => setCustomers([]))
      .finally(() => setLoadingCustomers(false));
  }, []);

  // Fetch + poll whenever the active tenant changes
  useEffect(() => {
    if (!activeCompanyId) return;
    fetchCustomers(activeCompanyId);

    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(() => {
      fetchCustomers(activeCompanyId, { silent: true });
    }, POLL_INTERVAL_MS);

    return () => clearInterval(pollRef.current);
  }, [activeCompanyId, fetchCustomers]);

  const handleTriggerCampaign = async () => {
    if (!activeCompanyId) return;
    setTriggering(true);
    setTriggerMessage(null);
    try {
      const res = await fetch(`/api/campaigns/${activeCompanyId}/trigger`, {
        method: "POST",
      });
      const data = await res.json();
      setTriggerMessage(
        data.errors && data.errors.length > 0
          ? `Dispatched ${data.dispatched_count} call(s), ${data.errors.length} error(s).`
          : `Dispatched ${data.dispatched_count} call(s).`
      );
      fetchCustomers(activeCompanyId, { silent: true });
    } catch {
      setTriggerMessage("Campaign trigger failed. Check backend logs.");
    } finally {
      setTriggering(false);
    }
  };

  const activeCompany = companies.find((c) => c.id === activeCompanyId);

  return (
    <div className="min-h-screen bg-ink relative overflow-hidden">
      {/* Ambient gradient backdrop */}
      <div className="pointer-events-none fixed inset-0 -z-10">
        <div className="absolute -top-40 -left-40 w-[32rem] h-[32rem] bg-accent/10 rounded-full blur-[120px]" />
        <div className="absolute top-1/3 -right-40 w-[28rem] h-[28rem] bg-signal-qualified/10 rounded-full blur-[120px]" />
      </div>

      <header className="border-b border-line/60">
        <div className="max-w-6xl mx-auto px-6 py-5 flex items-center justify-between">
          <div>
            <p className="text-xs font-mono uppercase tracking-[0.2em] text-zinc-500">
              Campaign Console
            </p>
            <h1 className="font-display text-xl font-semibold text-zinc-50">
              Voice Orchestrator
            </h1>
          </div>
          <TenantSelector
            companies={companies}
            activeCompanyId={activeCompanyId}
            onChange={setActiveCompanyId}
          />
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-6 py-8">
        <Dashboard
          company={activeCompany}
          customers={customers}
          loading={loadingCustomers}
          onTriggerCampaign={handleTriggerCampaign}
          triggering={triggering}
          triggerMessage={triggerMessage}
        />
      </main>
    </div>
  );
}
