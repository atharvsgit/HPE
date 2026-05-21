import { useEffect, useState, useCallback } from 'react';
import { fetchViolations, fetchViolationBatches } from '../services/alertsApi';
import IncidentCorrelationPanel from '../components/IncidentCorrelationPanel';

const SEVERITY_CONFIG = {
  critical: { color: 'text-red-400', bg: 'bg-red-500/10 border-red-500/30', dot: 'bg-red-400', label: 'Critical' },
  high:     { color: 'text-orange-400', bg: 'bg-orange-500/10 border-orange-500/30', dot: 'bg-orange-400', label: 'High' },
  medium:   { color: 'text-yellow-400', bg: 'bg-yellow-500/10 border-yellow-500/30', dot: 'bg-yellow-400', label: 'Medium' },
  low:      { color: 'text-cyan-400', bg: 'bg-cyan-500/10 border-cyan-500/30', dot: 'bg-cyan-400', label: 'Low' },
};

const STATUS_CONFIG = {
  open:        { color: 'text-yellow-300', bg: 'bg-yellow-500/10 border-yellow-500/30' },
  dispatched:  { color: 'text-green-300',  bg: 'bg-green-500/10 border-green-500/30' },
  resolved:    { color: 'text-slate-400',  bg: 'bg-slate-500/10 border-slate-500/30' },
  failed:      { color: 'text-red-400',    bg: 'bg-red-500/10 border-red-500/30' },
  dispatching: { color: 'text-blue-300',   bg: 'bg-blue-500/10 border-blue-500/30' },
};

function SeverityBadge({ severity }) {
  const cfg = SEVERITY_CONFIG[severity] || SEVERITY_CONFIG.medium;
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-semibold ${cfg.bg} ${cfg.color}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${cfg.dot}`} />
      {cfg.label}
    </span>
  );
}

function StatusBadge({ status }) {
  const cfg = STATUS_CONFIG[status] || STATUS_CONFIG.open;
  return (
    <span className={`rounded-full border px-2.5 py-0.5 text-xs font-medium ${cfg.bg} ${cfg.color}`}>
      {status}
    </span>
  );
}

function MetricCard({ label, value, sub, accent }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-5 backdrop-blur">
      <p className="text-xs uppercase tracking-widest text-slate-500">{label}</p>
      <p className={`mt-2 text-3xl font-bold ${accent || 'text-white'}`}>{value}</p>
      {sub && <p className="mt-1 text-xs text-slate-500">{sub}</p>}
    </div>
  );
}

export default function IntelligentAlertsDashboard() {
  const [violations, setViolations] = useState([]);
  const [batches, setBatches] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filterSeverity, setFilterSeverity] = useState('all');

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const [v, b] = await Promise.all([fetchViolations({ limit: 100 }), fetchViolationBatches({ limit: 100 })]);
      setViolations(v);
      setBatches(b);
      setError(null);
    } catch (e) {
      setError('Failed to load violations. Is the API running?');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  // Derived metrics
  const totalViolations = violations.length;
  const suppressed = violations.filter(v => v.status === 'open' && batches.some(b => b.rule_id === v.rule_id && b.total_occurrences > 1)).length;
  const criticalOpen = batches.filter(b => b.severity === 'critical' && b.status === 'open').length;
  const openBatches  = batches.filter(b => b.status === 'open').length;

  const displayedViolations = filterSeverity === 'all'
    ? violations
    : violations.filter(v => v.severity === filterSeverity);

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="rounded-2xl border border-white/10 bg-gradient-to-br from-slate-900 to-slate-950 p-6 sm:p-8">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-xs uppercase tracking-widest text-cyan-400/70">Intelligent Alerts</p>
            <h1 className="mt-2 text-2xl font-bold text-white">Violation Dashboard</h1>
            <p className="mt-1 text-sm text-slate-400">
              Real-time view of aggregated violation events, deduplication status, and batch dispatch.
            </p>
          </div>
          <button
            onClick={load}
            className="shrink-0 rounded-xl border border-white/10 bg-white/[0.04] px-4 py-2 text-xs font-medium text-slate-300 transition hover:bg-white/10"
          >
            ↻ Refresh
          </button>
        </div>
      </div>

      {/* Metric Cards */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <MetricCard label="Total Events"       value={totalViolations}  sub="All violation events" />
        <MetricCard label="Open Batches"       value={openBatches}      sub="Awaiting dispatch"       accent="text-yellow-300" />
        <MetricCard label="Critical Open"      value={criticalOpen}     sub="Need attention"          accent="text-red-400" />
        <MetricCard label="Duplicates Seen"    value={suppressed}       sub="Suppressed by dedup"     accent="text-cyan-300" />
      </div>

      {error && (
        <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-300">{error}</div>
      )}

      {/* Violation Events Table */}
      <div className="rounded-2xl border border-white/10 bg-white/[0.02] backdrop-blur">
        <div className="flex items-center justify-between border-b border-white/10 px-6 py-4">
          <h2 className="text-sm font-semibold text-white">Violation Events</h2>
          <div className="flex gap-2">
            {['all', 'critical', 'high', 'medium', 'low'].map(s => (
              <button
                key={s}
                onClick={() => setFilterSeverity(s)}
                className={`rounded-lg px-3 py-1 text-xs font-medium transition ${
                  filterSeverity === s
                    ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40'
                    : 'text-slate-400 hover:text-white border border-transparent'
                }`}
              >
                {s === 'all' ? 'All' : SEVERITY_CONFIG[s].label}
              </button>
            ))}
          </div>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-16">
            <div className="h-6 w-6 animate-spin rounded-full border-2 border-cyan-400 border-t-transparent" />
          </div>
        ) : displayedViolations.length === 0 ? (
          <div className="py-16 text-center text-sm text-slate-500">
            No violation events recorded yet. Run a failing rule to generate one.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-white/5 text-left text-xs uppercase tracking-wider text-slate-500">
                  <th className="px-6 py-3">ID</th>
                  <th className="px-6 py-3">Rule ID</th>
                  <th className="px-6 py-3">Severity</th>
                  <th className="px-6 py-3">Violations</th>
                  <th className="px-6 py-3">Status</th>
                  <th className="px-6 py-3">Fingerprint</th>
                  <th className="px-6 py-3">Created</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {displayedViolations.map(v => (
                  <tr key={v.id} className="transition hover:bg-white/[0.02]">
                    <td className="px-6 py-3 font-mono text-xs text-slate-400">#{v.id}</td>
                    <td className="px-6 py-3 text-slate-300">Rule {v.rule_id}</td>
                    <td className="px-6 py-3"><SeverityBadge severity={v.severity} /></td>
                    <td className="px-6 py-3 font-semibold text-white">{v.violation_count ?? '—'}</td>
                    <td className="px-6 py-3"><StatusBadge status={v.status} /></td>
                    <td className="px-6 py-3 font-mono text-xs text-slate-500" title={v.fingerprint}>
                      {v.fingerprint?.slice(0, 12)}…
                    </td>
                    <td className="px-6 py-3 text-xs text-slate-500">
                      {new Date(v.created_at).toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Aggregation Batches summary */}
      <div className="rounded-2xl border border-white/10 bg-white/[0.02] backdrop-blur">
        <div className="border-b border-white/10 px-6 py-4">
          <h2 className="text-sm font-semibold text-white">Aggregation Batches</h2>
        </div>
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <div className="h-6 w-6 animate-spin rounded-full border-2 border-cyan-400 border-t-transparent" />
          </div>
        ) : batches.length === 0 ? (
          <div className="py-12 text-center text-sm text-slate-500">No aggregation batches yet.</div>
        ) : (
          <div className="grid gap-3 p-6 sm:grid-cols-2 xl:grid-cols-3">
            {batches.map(b => {
              const cfg = SEVERITY_CONFIG[b.severity] || SEVERITY_CONFIG.medium;
              return (
                <div key={b.id} className={`rounded-xl border p-4 ${cfg.bg}`}>
                  <div className="flex items-start justify-between">
                    <div className="flex items-center gap-2">
                      <SeverityBadge severity={b.severity} />
                      {b.ai_enrichment && (
                        <span 
                          className={`rounded-full border px-2 py-0.5 text-[10px] font-bold ${
                            b.ai_enrichment.confidence_score === 'high' ? 'bg-green-500/10 border-green-500/30 text-green-400' :
                            b.ai_enrichment.confidence_score === 'medium' ? 'bg-yellow-500/10 border-yellow-500/30 text-yellow-400' :
                            b.ai_enrichment.confidence_score === 'low' ? 'bg-orange-500/10 border-orange-500/30 text-orange-400' :
                            'bg-indigo-500/10 border-indigo-500/30 text-indigo-300'
                          }`} 
                          title={`AI Summary Available (${b.ai_enrichment.confidence_score || 'unknown'} confidence)`}
                        >
                          ✨ AI
                        </span>
                      )}
                    </div>
                    <StatusBadge status={b.status} />
                  </div>
                  <p className="mt-3 text-xs text-slate-400">Rule {b.rule_id}</p>
                  <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
                    <div>
                      <p className="text-slate-500">Occurrences</p>
                      <p className="font-bold text-white">{b.total_occurrences}</p>
                    </div>
                    <div>
                      <p className="text-slate-500">Total Violations</p>
                      <p className="font-bold text-white">{b.total_violation_count ?? '—'}</p>
                    </div>
                  </div>
                  <p className="mt-3 text-[10px] text-slate-500">
                    First: {new Date(b.first_seen).toLocaleString()}<br/>
                    Last: {new Date(b.last_seen).toLocaleString()}
                  </p>
                  
                  <div className="mt-4 pt-4 border-t border-white/10">
                    <IncidentCorrelationPanel batchId={b.id} />
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
