import { useState } from 'react';
import { useDataset } from '../context/DatasetContext';

export default function AIRuleBuilder() {
  const { selectedDataset } = useDataset();
  const [prompt, setPrompt] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  
  const [generatedResult, setGeneratedResult] = useState(null);
  const [dryRunResult, setDryRunResult] = useState(null);
  const [saveStatus, setSaveStatus] = useState(null);
  
  const [editedSql, setEditedSql] = useState('');

  const handleGenerate = async () => {
    if (!prompt.trim() || !selectedDataset) return;
    setLoading(true);
    setError(null);
    setGeneratedResult(null);
    setDryRunResult(null);
    setSaveStatus(null);
    
    try {
      const parts = selectedDataset.id.split('.');
      const schemaName = parts.length === 2 ? parts[0] : 'business_data';
      const tableName = parts.length === 2 ? parts[1] : parts[0];

      const res = await fetch('http://localhost:8000/ai-rules/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          prompt,
          schema_name: schemaName,
          table_name: tableName
        })
      });
      
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || 'Failed to generate rule');
      }
      
      const data = await res.json();
      setGeneratedResult(data);
      setEditedSql(data.sql);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleDryRun = async () => {
    if (!editedSql) return;
    setLoading(true);
    setError(null);
    
    try {
      const res = await fetch('http://localhost:8000/ai-rules/dry-run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sql: editedSql })
      });
      
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || 'Dry run failed');
      }
      
      const data = await res.json();
      setDryRunResult(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    if (!generatedResult || !editedSql) return;
    setLoading(true);
    setError(null);
    
    try {
      const res = await fetch('http://localhost:8000/ai-rules/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          generation_id: generatedResult.id,
          reviewed_sql: editedSql
        })
      });
      
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || 'Save failed');
      }
      
      setSaveStatus('success');
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div className="glass-panel p-6">
        <h2 className="text-xl font-semibold text-white">AI Rule Builder</h2>
        <p className="mt-2 text-sm text-slate-400">
          Describe the data quality rule in plain English. The AI will generate a SQL query to check for violations.
          <br />
          <strong className="text-amber-400">AI-generated SQL must be reviewed before activation.</strong>
        </p>

        <div className="mt-6">
          <label className="block text-sm font-medium text-slate-300">Rule Description</label>
          <textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            className="mt-2 w-full rounded-lg border border-slate-700 bg-slate-900/50 p-4 text-white placeholder-slate-500 focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500"
            rows="3"
            placeholder="e.g., No active employee should have negative salary"
            disabled={loading}
          />
        </div>

        <div className="mt-4 flex gap-3">
          <button
            onClick={handleGenerate}
            disabled={loading || !prompt || !selectedDataset}
            className="rounded-lg bg-cyan-600 px-4 py-2 text-sm font-semibold text-white hover:bg-cyan-500 disabled:opacity-50"
          >
            {loading && !generatedResult ? 'Generating...' : 'Generate SQL'}
          </button>
        </div>
        
        {error && (
          <div className="mt-4 rounded-lg bg-red-500/10 p-4 border border-red-500/20">
            <p className="text-sm text-red-400">{error}</p>
          </div>
        )}
      </div>

      {generatedResult && (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          {/* Left Column: SQL and actions */}
          <div className="glass-panel p-6 flex flex-col">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-white">Generated SQL</h3>
              <span className="rounded bg-amber-500/20 px-2 py-1 text-xs font-semibold text-amber-400 border border-amber-500/30">
                AI Generated - Needs Review
              </span>
            </div>
            
            <textarea
              value={editedSql}
              onChange={(e) => setEditedSql(e.target.value)}
              className="w-full flex-1 rounded-lg border border-slate-700 bg-slate-950 p-4 text-sm font-mono text-cyan-300 focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 min-h-[200px]"
            />
            
            <div className="mt-4 flex gap-3">
              <button
                onClick={handleDryRun}
                disabled={loading}
                className="rounded-lg border border-cyan-600 bg-transparent px-4 py-2 text-sm font-semibold text-cyan-400 hover:bg-cyan-600/10 disabled:opacity-50"
              >
                {loading && !dryRunResult ? 'Running...' : 'Dry Run'}
              </button>
              
              <button
                onClick={handleSave}
                disabled={loading || !dryRunResult?.success || saveStatus === 'success'}
                className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-500 disabled:opacity-50"
                title={!dryRunResult?.success ? 'Must dry run successfully before saving' : ''}
              >
                {saveStatus === 'success' ? 'Saved' : 'Approve & Save Rule'}
              </button>
            </div>
          </div>

          {/* Right Column: Explanations and Results */}
          <div className="space-y-6">
            <div className="glass-panel p-6">
              <h3 className="text-lg font-semibold text-white mb-4">AI Analysis</h3>
              
              <div className="space-y-4 text-sm">
                <div>
                  <strong className="text-slate-300 block mb-1">Explanation</strong>
                  <p className="text-slate-400">{generatedResult.explanation}</p>
                </div>
                
                <div>
                  <strong className="text-slate-300 block mb-1">Assumptions</strong>
                  <ul className="list-disc pl-5 text-slate-400">
                    {generatedResult.assumptions?.map((a, i) => <li key={i}>{a}</li>)}
                  </ul>
                </div>
                
                <div>
                  <strong className="text-amber-300 block mb-1">Possible Edge Cases</strong>
                  <ul className="list-disc pl-5 text-amber-400/80">
                    {generatedResult.possible_edge_cases?.map((e, i) => <li key={i}>{e}</li>)}
                  </ul>
                </div>
                
                <div>
                  <strong className="text-slate-300 block mb-1">Confidence: <span className="uppercase text-cyan-400">{generatedResult.confidence}</span></strong>
                  <p className="text-slate-400">{generatedResult.confidence_reasoning}</p>
                </div>
              </div>
            </div>

            {dryRunResult && (
              <div className={`glass-panel p-6 border ${dryRunResult.success ? 'border-emerald-500/30' : 'border-red-500/30'}`}>
                <h3 className="text-lg font-semibold text-white mb-4">Dry Run Results</h3>
                {dryRunResult.success ? (
                  <div>
                    <p className="text-sm text-emerald-400 mb-2">Success! Latency: {dryRunResult.latency_ms}ms</p>
                    {dryRunResult.estimated_cost && (
                      <p className="text-xs text-slate-400 mb-4">Estimated Cost: {dryRunResult.estimated_cost}</p>
                    )}
                    <div className="overflow-x-auto">
                      <pre className="text-xs text-slate-300 bg-slate-900 p-3 rounded">
                        {JSON.stringify(dryRunResult.sample_output, null, 2)}
                      </pre>
                    </div>
                  </div>
                ) : (
                  <div>
                    <p className="text-sm text-red-400 mb-2">Dry Run Failed</p>
                    <pre className="text-xs text-red-300/80 bg-red-950/50 p-3 rounded overflow-x-auto">
                      {dryRunResult.error}
                    </pre>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
