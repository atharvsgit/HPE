import { useEffect, useState, useCallback } from 'react';
import { fetchViolationBatches, sendBatchNow, reEnrichBatch, submitFeedback, fetchFeedback } from '../services/alertsApi';

// ─── Config ────────────────────────────────────────────────────────────────

const SEVERITY_CONFIG = {
  critical: { color: 'text-red-400',    bg: 'bg-red-500/10 border-red-500/30',    dot: 'bg-red-400',    label: 'Critical', window: 'Immediate' },
  high:     { color: 'text-orange-400', bg: 'bg-orange-500/10 border-orange-500/30', dot: 'bg-orange-400', label: 'High',     window: '15 min' },
  medium:   { color: 'text-yellow-400', bg: 'bg-yellow-500/10 border-yellow-500/30', dot: 'bg-yellow-400', label: 'Medium',   window: '1 hour' },
  low:      { color: 'text-cyan-400',   bg: 'bg-cyan-500/10 border-cyan-500/30',   dot: 'bg-cyan-400',   label: 'Low',      window: '6 hours' },
};

const STATUS_CONFIG = {
  open:        { color: 'text-yellow-300', bg: 'bg-yellow-500/10 border-yellow-500/30' },
  dispatched:  { color: 'text-green-300',  bg: 'bg-green-500/10  border-green-500/30' },
  resolved:    { color: 'text-slate-400',  bg: 'bg-slate-500/10  border-slate-500/30' },
  failed:      { color: 'text-red-400',    bg: 'bg-red-500/10    border-red-500/30' },
  dispatching: { color: 'text-blue-300',   bg: 'bg-blue-500/10   border-blue-500/30' },
  enriched:    { color: 'text-indigo-300', bg: 'bg-indigo-500/10 border-indigo-500/30' },
};

// ─── Helpers ───────────────────────────────────────────────────────────────

function timeAgo(dateStr) {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

function windowExpiry(batch) {
  const windowMins = { critical: 0, high: 15, medium: 60, low: 360 }[batch.severity] ?? 60;
  const expiry = new Date(new Date(batch.first_seen).getTime() + windowMins * 60000);
  return { expired: expiry <= new Date(), expiry, windowMins };
}

function ConfidenceBadge({ level }) {
  if (!level) return null;
  const styles = {
    high:   'bg-green-500/10 border-green-500/30 text-green-400',
    medium: 'bg-yellow-500/10 border-yellow-500/30 text-yellow-400',
    low:    'bg-orange-500/10 border-orange-500/30 text-orange-400',
  };
  return (
    <span className={`px-2 py-0.5 rounded-full text-[9px] font-bold uppercase border ${styles[level] || styles.low}`}>
      {level} conf.
    </span>
  );
}

// ─── Audit History ─────────────────────────────────────────────────────────

function AuditHistory({ feedbackList }) {
  const [open, setOpen] = useState(false);
  if (!feedbackList || feedbackList.length === 0) return null;

  return (
    <div className="mt-3 border-t border-white/10 pt-3">
      <button
        onClick={() => setOpen(o => !o)}
        className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-wider text-slate-500 hover:text-slate-300 transition"
      >
        <span>{open ? '▾' : '▸'}</span>
        Governance Audit Log ({feedbackList.length})
      </button>

      {open && (
        <div className="mt-3 space-y-3">
          {feedbackList.map((fb, idx) => (
            <div key={fb.id} className="rounded-xl border border-white/10 bg-black/20 p-3 text-xs space-y-2">
              {/* Header */}
              <div className="flex items-center justify-between gap-2 flex-wrap">
                <div className="flex items-center gap-2">
                  <span className={`px-2 py-0.5 rounded-full font-bold uppercase text-[9px] border ${
                    fb.feedback_type === 'accept'   ? 'bg-green-500/15 border-green-500/30 text-green-400' :
                    fb.feedback_type === 'reject'   ? 'bg-red-500/15 border-red-500/30 text-red-400' :
                    fb.feedback_type === 'edit'     ? 'bg-blue-500/15 border-blue-500/30 text-blue-400' :
                    'bg-slate-500/15 border-slate-500/30 text-slate-400'
                  }`}>
                    {fb.feedback_type}
                  </span>
                  <span className="text-slate-500">#{idx + 1}</span>
                </div>
                <div className="text-[9px] text-slate-500 text-right">
                  <span className="text-slate-400">{fb.user_id}</span>
                  {' · '}
                  {new Date(fb.created_at).toLocaleString()}
                  {' · '}
                  prompt {fb.prompt_version}
                  {' · '}
                  <ConfidenceBadge level={fb.confidence_level} />
                </div>
              </div>

              {/* Original AI output */}
              <div>
                <p className="text-[9px] uppercase tracking-wider text-slate-500 mb-1">Original AI Output</p>
                <p className="text-slate-400 leading-relaxed">{fb.original_summary}</p>
                {fb.original_fixes?.length > 0 && (
                  <ul className="mt-1 list-disc list-inside text-slate-500 space-y-0.5">
                    {fb.original_fixes.map((f, i) => <li key={i}>{f}</li>)}
                  </ul>
                )}
              </div>

              {/* Human corrections */}
              {(fb.edited_summary || fb.edited_fixes?.length > 0) && (
                <div className="border-t border-blue-500/20 pt-2">
                  <p className="text-[9px] uppercase tracking-wider text-blue-400 mb-1">Human Corrected Version</p>
                  {fb.edited_summary && (
                    <p className="text-blue-100/80 leading-relaxed">{fb.edited_summary}</p>
                  )}
                  {fb.edited_fixes?.length > 0 && (
                    <ul className="mt-1 list-disc list-inside text-blue-200/70 space-y-0.5">
                      {fb.edited_fixes.map((f, i) => <li key={i}>{f}</li>)}
                    </ul>
                  )}
                </div>
              )}

              {/* Notes */}
              {fb.feedback_notes && (
                <div className="border-t border-white/5 pt-2">
                  <p className="text-[9px] uppercase tracking-wider text-slate-500 mb-1">Reviewer Notes</p>
                  <p className="text-slate-400 italic">{fb.feedback_notes}</p>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ─── AI Enrichment Panel ───────────────────────────────────────────────────

function AIEnrichmentPanel({ batch, onSubmitFeedback, feedbackList }) {
  const { ai_enrichment: ai } = batch;
  const [mode, setMode] = useState('view'); // 'view' | 'editing' | 'submitting'
  const [editSummary, setEditSummary] = useState('');
  const [editFixes, setEditFixes] = useState('');
  const [notes, setNotes] = useState('');
  const [error, setError] = useState(null);

  // Derive the effective state from feedback list
  const latestFeedback = feedbackList?.length > 0 ? feedbackList[feedbackList.length - 1] : null;
  const isAccepted = latestFeedback?.feedback_type === 'accept';
  const isRejected = latestFeedback?.feedback_type === 'reject';
  const isEdited   = latestFeedback?.feedback_type === 'edit';

  // The version the user actually sees (human-corrected wins)
  const displaySummary  = isEdited && latestFeedback.edited_summary ? latestFeedback.edited_summary : ai?.ai_summary;
  const displayFixes    = isEdited && latestFeedback.edited_fixes?.length > 0 ? latestFeedback.edited_fixes : ai?.suggested_fixes;
  const showHumanBadge  = isAccepted || isEdited;

  async function handleAction(type) {
    setError(null);
    const payload = { feedback_type: type };
    if (type === 'edit') {
      payload.edited_summary = editSummary.trim();
      payload.edited_fixes   = editFixes.split('\n').map(l => l.trim()).filter(Boolean);
      payload.feedback_notes = notes.trim() || undefined;
    }
    try {
      setMode('submitting');
      await onSubmitFeedback(batch.id, payload);
      setMode('view');
    } catch {
      setError('Failed to submit feedback. Please try again.');
      setMode(type === 'edit' ? 'editing' : 'view');
    }
  }

  if (!ai) return null;

  return (
    <div className="mt-4 rounded-xl border border-indigo-500/30 bg-indigo-900/30 overflow-hidden relative">
      {/* Gradient wash */}
      <div className="absolute inset-0 bg-gradient-to-br from-indigo-500/5 to-transparent pointer-events-none" />

      <div className="relative p-4 space-y-3">

        {/* ── Header row ── */}
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <div className="flex items-center gap-2">
            <span className="text-[11px] font-bold uppercase tracking-wider text-indigo-300">✨ AI Analysis</span>
            {/* AI advisory disclaimer */}
            <span className="text-[9px] text-indigo-400/60 italic">advisory only</span>
          </div>
          <div className="flex items-center gap-2">
            <ConfidenceBadge level={ai.confidence_score} />
            {showHumanBadge && (
              <span className={`px-2 py-0.5 rounded-full text-[9px] font-bold uppercase border ${
                isAccepted || isEdited
                  ? 'bg-green-500/15 border-green-500/30 text-green-400'
                  : ''
              }`}>
                ✓ Human Validated
              </span>
            )}
            {isRejected && (
              <span className="px-2 py-0.5 rounded-full text-[9px] font-bold uppercase border bg-red-500/15 border-red-500/30 text-red-400">
                ✗ AI Interpretation Rejected
              </span>
            )}
          </div>
        </div>

        {/* ── Parsing failure ── */}
        {ai.parsing_failure ? (
          <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-300 text-xs flex items-start gap-2">
            <span>⚠️</span><span>{ai.ai_summary}</span>
          </div>
        ) : (
          <>
            {/* ── Rejected state ── */}
            {isRejected && (
              <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-xs text-red-300">
                This AI interpretation has been marked invalid by a reviewer.
                {latestFeedback.feedback_notes && (
                  <p className="mt-1 italic text-red-300/70">Reason: {latestFeedback.feedback_notes}</p>
                )}
              </div>
            )}

            {/* ── Edit form ── */}
            {mode === 'editing' ? (
              <div className="space-y-3">
                <div>
                  <label className="text-[10px] uppercase tracking-wider text-blue-300 font-semibold block mb-1">
                    Corrected Summary
                  </label>
                  <textarea
                    rows={4}
                    value={editSummary}
                    onChange={e => setEditSummary(e.target.value)}
                    placeholder={displaySummary || 'Enter corrected summary…'}
                    className="w-full rounded-lg bg-black/40 border border-blue-500/30 text-blue-100 text-xs p-2.5 placeholder-slate-600 focus:outline-none focus:border-blue-500/60 resize-none"
                  />
                </div>
                <div>
                  <label className="text-[10px] uppercase tracking-wider text-blue-300 font-semibold block mb-1">
                    Corrected Fixes <span className="text-slate-500">(one per line)</span>
                  </label>
                  <textarea
                    rows={4}
                    value={editFixes}
                    onChange={e => setEditFixes(e.target.value)}
                    placeholder={(displayFixes || []).join('\n') || 'Enter fixes, one per line…'}
                    className="w-full rounded-lg bg-black/40 border border-blue-500/30 text-blue-100 text-xs p-2.5 placeholder-slate-600 focus:outline-none focus:border-blue-500/60 resize-none font-mono"
                  />
                </div>
                <div>
                  <label className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold block mb-1">
                    Reviewer Notes <span className="text-slate-600">(optional)</span>
                  </label>
                  <textarea
                    rows={2}
                    value={notes}
                    onChange={e => setNotes(e.target.value)}
                    placeholder="Reason for edit…"
                    className="w-full rounded-lg bg-black/40 border border-white/10 text-slate-300 text-xs p-2.5 placeholder-slate-600 focus:outline-none focus:border-white/20 resize-none"
                  />
                </div>
                {error && <p className="text-xs text-red-400">{error}</p>}
                <div className="flex gap-2">
                  <button
                    onClick={() => handleAction('edit')}
                    disabled={mode === 'submitting'}
                    className="flex-1 py-2 rounded-lg bg-blue-500/20 border border-blue-500/40 text-blue-300 text-xs font-semibold hover:bg-blue-500/30 transition disabled:opacity-50"
                  >
                    {mode === 'submitting' ? 'Saving…' : '✓ Save Correction'}
                  </button>
                  <button
                    onClick={() => { setMode('view'); setError(null); }}
                    className="px-4 py-2 rounded-lg bg-white/5 border border-white/10 text-slate-400 text-xs hover:text-white transition"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <>
                {/* ── AI/Human content display ── */}
                {!isRejected && (
                  <div className="space-y-3">
                    {/* If human corrected version exists, show it first prominently */}
                    {isEdited && (
                      <div className="rounded-lg bg-blue-500/10 border border-blue-500/25 p-3">
                        <p className="text-[9px] font-bold uppercase tracking-wider text-blue-400 mb-1.5">Human Corrected Version</p>
                        <p className="text-sm text-blue-100/95 leading-relaxed font-medium">{latestFeedback.edited_summary || displaySummary}</p>
                        {(latestFeedback.edited_fixes?.length > 0) && (
                          <ul className="mt-2 list-disc list-inside text-xs text-blue-200/85 space-y-1">
                            {latestFeedback.edited_fixes.map((f, i) => <li key={i}>{f}</li>)}
                          </ul>
                        )}
                      </div>
                    )}

                    {/* Original AI output (secondary if edited) */}
                    <div className={isEdited ? 'opacity-60' : ''}>
                      {isEdited && (
                        <p className="text-[9px] font-bold uppercase tracking-wider text-indigo-400/70 mb-1.5">Original AI Output</p>
                      )}
                      <p className={`text-sm leading-relaxed ${isEdited ? 'text-indigo-200/70' : 'text-indigo-100/90 font-medium'}`}>
                        {ai.ai_summary}
                      </p>

                      {ai.root_causes?.length > 0 && (
                        <div className="mt-2">
                          <p className="text-[10px] font-semibold uppercase tracking-wider text-indigo-300/80 mb-1">
                            {isEdited ? 'AI Root Causes' : 'Potential Root Causes'}
                          </p>
                          <ul className="list-disc list-inside text-xs text-indigo-200/80 space-y-0.5">
                            {ai.root_causes.map((rc, i) => <li key={i}>{rc}</li>)}
                          </ul>
                        </div>
                      )}

                      {!isEdited && ai.suggested_fixes?.length > 0 && (
                        <div className="mt-2">
                          <p className="text-[10px] font-semibold uppercase tracking-wider text-indigo-300/80 mb-1">Suggested Fixes</p>
                          <ul className="list-disc list-inside text-xs text-indigo-200/80 space-y-0.5">
                            {ai.suggested_fixes.map((sf, i) => <li key={i}>{sf}</li>)}
                          </ul>
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* Low confidence warning */}
                {ai.confidence_score === 'low' && !isAccepted && (
                  <div className="p-2.5 rounded-lg bg-orange-500/10 border border-orange-500/20 text-orange-300 text-[11px] flex items-start gap-2">
                    <span>⚠️</span>
                    <span>Low confidence result. Verify manually before acting on this advisory information.</span>
                  </div>
                )}
              </>
            )}
          </>
        )}

        {/* ── Action bar ── */}
        {mode !== 'editing' && !ai.parsing_failure && (
          <div className="flex items-center justify-between border-t border-indigo-500/20 pt-3 gap-2 flex-wrap">
            <div className="text-[9px] text-indigo-300/40 uppercase tracking-widest">
              {ai.provider_name}{ai.model_name ? ` · ${ai.model_name}` : ''}
            </div>
            <div className="flex items-center gap-2">
              {/* Accept */}
              {!isAccepted && !isEdited && (
                <button
                  onClick={() => handleAction('accept')}
                  disabled={mode === 'submitting'}
                  className="px-3 py-1.5 rounded-lg border border-green-500/30 bg-green-500/10 text-[10px] font-bold text-green-400 hover:bg-green-500/20 transition disabled:opacity-40 flex items-center gap-1"
                >
                  ✓ Accept
                </button>
              )}
              {/* Reject */}
              {!isRejected && (
                <button
                  onClick={() => handleAction('reject')}
                  disabled={mode === 'submitting'}
                  className="px-3 py-1.5 rounded-lg border border-red-500/30 bg-red-500/10 text-[10px] font-bold text-red-400 hover:bg-red-500/20 transition disabled:opacity-40 flex items-center gap-1"
                >
                  ✗ Reject
                </button>
              )}
              {/* Edit */}
              <button
                onClick={() => {
                  setEditSummary(displaySummary || '');
                  setEditFixes((displayFixes || []).join('\n'));
                  setMode('editing');
                }}
                disabled={mode === 'submitting'}
                className="px-3 py-1.5 rounded-lg border border-blue-500/30 bg-blue-500/10 text-[10px] font-bold text-blue-300 hover:bg-blue-500/20 transition disabled:opacity-40 flex items-center gap-1"
              >
                ✎ Edit
              </button>
              {/* Re-enrich */}
              <button
                onClick={() => batch._onReEnrich(batch.id)}
                disabled={mode === 'submitting'}
                className="px-3 py-1.5 rounded-lg border border-indigo-500/30 bg-indigo-500/10 text-[10px] font-bold text-indigo-300 hover:bg-indigo-500/20 transition disabled:opacity-40"
              >
                ↻
              </button>
            </div>
          </div>
        )}

        {error && mode !== 'editing' && (
          <p className="text-xs text-red-400 pt-1">{error}</p>
        )}

        {/* Audit history */}
        <AuditHistory feedbackList={feedbackList} />
      </div>
    </div>
  );
}

// ─── Batch Card ────────────────────────────────────────────────────────────

function BatchCard({ batch, onSendNow, onReEnrich, onSubmitFeedback }) {
  const cfg  = SEVERITY_CONFIG[batch.severity] || SEVERITY_CONFIG.medium;
  const stCfg = STATUS_CONFIG[batch.status] || STATUS_CONFIG.open;
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);
  const [feedbackList, setFeedbackList] = useState([]);
  const { expired, expiry, windowMins } = windowExpiry(batch);

  // Load feedback on mount and after any submission
  const loadFeedback = useCallback(async () => {
    if (!batch.ai_enrichment) return;
    try {
      const data = await fetchFeedback(batch.id);
      setFeedbackList(data);
    } catch {
      // Non-critical — silently ignore, feedback history just won't show
    }
  }, [batch.id, batch.ai_enrichment]);

  useEffect(() => { loadFeedback(); }, [loadFeedback]);

  const handleSend = async () => {
    setSending(true);
    try { await onSendNow(batch.id); setSent(true); }
    finally { setSending(false); }
  };

  const handleFeedback = async (batchId, payload) => {
    await onSubmitFeedback(batchId, payload);
    await loadFeedback(); // Refresh after submission
  };

  // Attach re-enrich callback via batch obj to avoid prop-drilling into deep component
  const batchWithCallback = { ...batch, _onReEnrich: onReEnrich };

  return (
    <div className={`relative rounded-2xl border p-5 ${cfg.bg} transition`}>
      {/* Severity stripe */}
      <div className={`absolute left-0 top-4 bottom-4 w-0.5 rounded-full ${cfg.dot}`} />

      <div className="ml-3">
        {/* ── Header ── */}
        <div className="flex items-start justify-between gap-3">
          <div>
            <span className={`text-xs font-bold uppercase tracking-widest ${cfg.color}`}>{cfg.label}</span>
            <p className="mt-0.5 text-xs text-slate-500">
              Rule ID: <span className="font-semibold text-slate-300">#{batch.rule_id}</span>
            </p>
          </div>
          <span className={`rounded-full border px-2.5 py-0.5 text-xs font-medium ${stCfg.bg} ${stCfg.color}`}>
            {batch.status}
          </span>
        </div>

        {/* ── Stats ── */}
        <div className="mt-4 grid grid-cols-3 gap-3 text-center">
          {[
            ['Occurrences', batch.total_occurrences, 'text-white'],
            ['Violations', batch.total_violation_count ?? '—', 'text-white'],
            ['Window', windowMins === 0 ? 'Instant' : cfg.window, cfg.color],
          ].map(([label, value, cls]) => (
            <div key={label} className="rounded-xl bg-black/20 p-2">
              <p className="text-[10px] text-slate-500">{label}</p>
              <p className={`mt-0.5 text-lg font-bold ${cls}`}>{value}</p>
            </div>
          ))}
        </div>

        {/* ── Timeline ── */}
        <div className="mt-4 space-y-1 text-xs text-slate-500">
          {[['First seen', batch.first_seen], ['Last seen', batch.last_seen]].map(([lbl, d]) => (
            <div key={lbl} className="flex justify-between">
              <span>{lbl}</span>
              <span className="text-slate-300">{timeAgo(d)} · {new Date(d).toLocaleTimeString()}</span>
            </div>
          ))}
          {windowMins > 0 && (
            <div className="flex justify-between">
              <span>Dispatch window</span>
              <span className={expired ? 'text-red-400 font-semibold' : 'text-slate-300'}>
                {expired ? '⚡ Expired' : `Expires ${expiry.toLocaleTimeString()}`}
              </span>
            </div>
          )}
        </div>

        {/* ── AI Enrichment panel ── */}
        <AIEnrichmentPanel
          batch={batchWithCallback}
          onSubmitFeedback={handleFeedback}
          feedbackList={feedbackList}
        />

        {/* ── Send Now ── */}
        {batch.status === 'open' && (
          <button
            onClick={handleSend}
            disabled={sending || sent}
            className={`mt-4 w-full rounded-xl py-2 text-xs font-semibold transition ${
              sent
                ? 'bg-green-500/20 text-green-300 border border-green-500/30 cursor-default'
                : 'bg-white/5 border border-white/10 text-slate-300 hover:bg-white/10 active:scale-95'
            }`}
          >
            {sending ? 'Dispatching…' : sent ? '✓ Sent' : '⚡ Send Now'}
          </button>
        )}
      </div>
    </div>
  );
}

// ─── Main Page ─────────────────────────────────────────────────────────────

export default function ViolationBatchTimeline() {
  const [batches, setBatches] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filterStatus, setFilterStatus] = useState('all');

  const load = useCallback(async () => {
    try {
      setLoading(true);
      setBatches(await fetchViolationBatches({ limit: 100 }));
      setError(null);
    } catch {
      setError('Failed to load batches.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleSendNow = async (batchId) => { await sendBatchNow(batchId); await load(); };
  const handleReEnrich = async (batchId) => { await reEnrichBatch(batchId); };
  const handleFeedback = async (batchId, payload) => { await submitFeedback(batchId, payload); };

  const displayed = filterStatus === 'all' ? batches : batches.filter(b => b.status === filterStatus);
  const statusCounts = batches.reduce((acc, b) => { acc[b.status] = (acc[b.status] || 0) + 1; return acc; }, {});

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="rounded-2xl border border-white/10 bg-gradient-to-br from-slate-900 to-slate-950 p-6 sm:p-8">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-xs uppercase tracking-widest text-cyan-400/70">Governance Layer</p>
            <h1 className="mt-2 text-2xl font-bold text-white">Batch Dispatch & AI Review</h1>
            <p className="mt-1 text-sm text-slate-400">
              Accept, reject, or correct AI-generated interpretations. Human decisions are authoritative and preserved for audit.
            </p>
          </div>
          <button
            onClick={load}
            className="shrink-0 rounded-xl border border-white/10 bg-white/[0.04] px-4 py-2 text-xs font-medium text-slate-300 transition hover:bg-white/10"
          >
            ↻ Refresh
          </button>
        </div>
        {/* Legend */}
        <div className="mt-6 flex flex-wrap gap-3">
          {Object.entries(SEVERITY_CONFIG).map(([key, cfg]) => (
            <div key={key} className={`flex items-center gap-2 rounded-xl border px-3 py-1.5 text-xs ${cfg.bg}`}>
              <span className={`h-2 w-2 rounded-full ${cfg.dot}`} />
              <span className={cfg.color}>{cfg.label}</span>
              <span className="text-slate-500">→ {cfg.window}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Status filter */}
      <div className="flex gap-2 overflow-x-auto pb-1">
        {['all', 'open', 'enriched', 'dispatched', 'failed', 'resolved'].map(s => {
          const count = s === 'all' ? batches.length : (statusCounts[s] || 0);
          return (
            <button
              key={s}
              onClick={() => setFilterStatus(s)}
              className={`flex shrink-0 items-center gap-1.5 rounded-xl border px-4 py-2 text-xs font-medium transition ${
                filterStatus === s
                  ? 'bg-cyan-500/20 border-cyan-500/40 text-cyan-300'
                  : 'border-white/10 text-slate-400 hover:text-white'
              }`}
            >
              {s.charAt(0).toUpperCase() + s.slice(1)}
              <span className="rounded-full bg-white/10 px-1.5 py-0.5 text-[10px]">{count}</span>
            </button>
          );
        })}
      </div>

      {error && (
        <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-300">{error}</div>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-24">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-cyan-400 border-t-transparent" />
        </div>
      ) : displayed.length === 0 ? (
        <div className="flex flex-col items-center justify-center gap-3 py-24 text-center">
          <div className="text-4xl">📭</div>
          <p className="text-sm font-medium text-slate-400">No batches found</p>
          <p className="text-xs text-slate-600">
            {filterStatus !== 'all' ? 'Try switching to "All".' : 'Execute a failing rule to generate your first violation batch.'}
          </p>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {displayed.map(b => (
            <BatchCard
              key={b.id}
              batch={b}
              onSendNow={handleSendNow}
              onReEnrich={handleReEnrich}
              onSubmitFeedback={handleFeedback}
            />
          ))}
        </div>
      )}
    </div>
  );
}
