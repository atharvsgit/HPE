import { useState, useEffect } from 'react';
import StatusBadge from './common/StatusBadge';
import Loader from './common/Loader';
import api from '../services/api';

const statusTone = (status) => {
  const normalized = String(status || '').toUpperCase();
  if (['PASS', 'COMPLETED', 'ACTIVE', 'RESOLVED'].includes(normalized)) return 'success';
  if (['FAIL', 'ERROR', 'FAILED'].includes(normalized)) return 'error';
  return 'pending';
};

const formatDateTime = (value) =>
  new Intl.DateTimeFormat('en-US', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value));

export default function IncidentCorrelationPanel({ batchId }) {
  const [correlations, setCorrelations] = useState([]);
  const [message, setMessage] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let mounted = true;
    
    const fetchCorrelations = async () => {
      setLoading(true);
      try {
        const { data } = await api.get(`/ai-rules/correlations/${batchId}`);

        if (mounted) {
          setCorrelations(data.correlations || []);
          setMessage(data.message || '');
        }
      } catch (err) {
        if (mounted) setError(err.response?.data?.detail || err.message || 'Failed to fetch correlations');
      } finally {
        if (mounted) setLoading(false);
      }
    };

    if (batchId) {
      fetchCorrelations();
    }
    
    return () => { mounted = false; };
  }, [batchId]);

  if (loading) {
    return (
      <div className="p-4 border border-slate-700 bg-slate-900/50 rounded-lg flex items-center gap-3">
        <Loader compact />
        <span className="text-sm text-slate-400">Analyzing semantic correlations...</span>
      </div>
    );
  }

  if (error) {
    return <div className="text-sm text-red-400">Correlation Error: {error}</div>;
  }

  if (correlations.length === 0) {
    return (
      <div className="p-4 border border-slate-700 bg-slate-900/50 rounded-lg">
        <p className="text-sm text-slate-400">{message || "No meaningful historical correlations found."}</p>
      </div>
    );
  }

  return (
    <div className="border border-indigo-500/30 bg-indigo-950/10 rounded-lg overflow-hidden">
      <div className="px-4 py-3 border-b border-indigo-500/20 bg-indigo-950/40">
        <h3 className="text-sm font-semibold text-indigo-300 flex items-center gap-2">
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
          </svg>
          Similar Historical Incidents
        </h3>
      </div>
      
      <div className="divide-y divide-slate-800">
        {correlations.map((c, i) => (
          <div key={i} className="p-4 hover:bg-slate-800/30 transition-colors">
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-3">
                <span className={`px-2 py-0.5 rounded text-xs font-bold ${c.similarity_score >= 75 ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30' : 'bg-amber-500/20 text-amber-400 border border-amber-500/30'}`}>
                  {c.similarity_score}% Match
                </span>
                <span className="text-xs text-slate-400 border-l border-slate-700 pl-3">
                  {formatDateTime(c.created_at)}
                </span>
                <StatusBadge tone={statusTone(c.historical_resolution)}>
                  {c.historical_resolution}
                </StatusBadge>
              </div>
              
              <div className="flex gap-2">
                <button title="Mark as Useful" className="text-slate-500 hover:text-emerald-400 transition-colors">
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 10h4.764a2 2 0 011.789 2.894l-3.5 7A2 2 0 0115.263 21h-4.017c-.163 0-.326-.02-.485-.06L7 20m7-10V5a2 2 0 00-2-2h-.095c-.5 0-.905.405-.905.905 0 .714-.211 1.412-.608 2.006L7 11v9m7-10h-2M7 20H5a2 2 0 01-2-2v-6a2 2 0 012-2h2.5" /></svg>
                </button>
                <button title="Dismiss Correlation" className="text-slate-500 hover:text-rose-400 transition-colors">
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
                </button>
              </div>
            </div>
            
            <div className="mt-3">
              <p className="text-xs text-indigo-200">{c.rationale}</p>
              
              <div className="mt-2 flex flex-wrap gap-1.5">
                <span className="text-xs text-slate-500 mr-1">Shared concepts:</span>
                {c.matched_keywords.map((kw, idx) => (
                  <span key={idx} className="px-1.5 py-0.5 rounded bg-slate-800 text-slate-300 text-[10px] uppercase">
                    {kw}
                  </span>
                ))}
              </div>
            </div>

            {c.human_validated_interpretation && (
              <div className="mt-3 p-2 bg-indigo-900/30 border border-indigo-500/20 rounded text-sm">
                <strong className="text-indigo-300 text-xs uppercase block mb-1">Prior Human Interpretation</strong>
                <p className="text-slate-300">{c.human_validated_interpretation}</p>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
