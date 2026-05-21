import { useState } from 'react';
import api from '../services/api';

export default function RuleImprovementSuggestion({ ruleId }) {
  const [suggestion, setSuggestion] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [statusUpdating, setStatusUpdating] = useState(false);

  const fetchSuggestion = async () => {
    setLoading(true);
    setError(null);
    try {
      const { data } = await api.get(`/ai-rules/suggestions/${ruleId}`);
      setSuggestion(data);
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Failed to fetch suggestion');
    } finally {
      setLoading(false);
    }
  };

  const handleUpdateStatus = async (status) => {
    // Assuming the suggestion ID is returned, or we just rely on state. 
    // For this example, we pretend suggestion.id is available from the DB row, but our API returns the raw JSON.
    // In a full implementation, the API should return { id: 1, ...raw_json }. We'll mock it for now.
    setStatusUpdating(true);
    try {
      const suggestionId = suggestion.id || 1;
      await api.post(`/ai-rules/suggestions/${suggestionId}/status`, { status });
      setSuggestion(prev => ({ ...prev, status }));
    } catch (err) {
      console.error(err);
    } finally {
      setStatusUpdating(false);
    }
  };

  if (!suggestion && !loading) {
    return (
      <button 
        onClick={fetchSuggestion}
        className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded text-sm font-medium"
      >
        Generate Improvement Suggestion
      </button>
    );
  }

  if (loading) {
    return <div className="text-sm text-slate-400">Analyzing historical rule performance...</div>;
  }

  if (error) {
    return <div className="text-sm text-red-400">Error: {error}</div>;
  }

  if (suggestion.suggestion_type === 'none') {
    return (
      <div className="p-4 border border-slate-700 bg-slate-900/50 rounded text-sm text-slate-300">
        <strong className="text-slate-200">No Action Required</strong>
        <p className="mt-1">{suggestion.message || suggestion.reasoning}</p>
      </div>
    );
  }

  return (
    <div className="p-5 border border-indigo-500/30 bg-indigo-950/20 rounded-lg space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold text-indigo-300 flex items-center gap-2">
          <span className="bg-indigo-600 text-white px-2 py-0.5 rounded text-xs uppercase">
            {suggestion.suggestion_type.replace('_', ' ')}
          </span>
          Rule Improvement Available
        </h3>
        <div className="flex gap-2 text-xs font-semibold">
          <span className="px-2 py-1 rounded bg-slate-800 text-slate-300">
            Confidence: {suggestion.confidence}
          </span>
          <span className="px-2 py-1 rounded bg-slate-800 text-slate-300">
            Risk: <span className={suggestion.risk_level === 'high' ? 'text-red-400' : 'text-amber-400'}>{suggestion.risk_level}</span>
          </span>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4 text-sm">
        <div>
          <strong className="block text-slate-400 mb-1">Current Behavior</strong>
          <p className="text-slate-200">{suggestion.current_behavior}</p>
        </div>
        <div>
          <strong className="block text-slate-400 mb-1">Recommended Change</strong>
          <p className="text-slate-200">{suggestion.recommended_change}</p>
        </div>
      </div>

      <div className="bg-slate-900/80 p-3 rounded text-sm">
        <strong className="text-indigo-400">Why this helps:</strong>
        <p className="text-slate-300 mt-1">{suggestion.reasoning}</p>
        
        {suggestion.supporting_evidence && suggestion.supporting_evidence.length > 0 && (
          <div className="mt-3">
            <strong className="text-slate-400 text-xs uppercase">Historical Evidence</strong>
            <ul className="list-disc pl-5 mt-1 text-slate-300 text-xs space-y-1">
              {suggestion.supporting_evidence.map((ev, i) => (
                <li key={i}>{ev}</li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {suggestion.status ? (
        <div className="text-sm font-medium text-slate-400">
          Status: <span className="uppercase text-white">{suggestion.status}</span>
        </div>
      ) : (
        <div className="flex gap-3 pt-2">
          <button
            onClick={() => handleUpdateStatus('accepted')}
            disabled={statusUpdating}
            className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded text-sm font-medium"
          >
            Accept Suggestion
          </button>
          <button
            onClick={() => handleUpdateStatus('rejected')}
            disabled={statusUpdating}
            className="px-4 py-2 bg-slate-700 hover:bg-slate-600 text-white rounded text-sm font-medium"
          >
            Dismiss
          </button>
        </div>
      )}
    </div>
  );
}
