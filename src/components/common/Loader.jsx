export default function Loader({
  label = 'Loading',
  compact = false,
  className = '',
}) {
  if (compact) {
    return (
      <span className={`inline-flex items-center gap-2 text-sm font-medium text-slate-100 ${className}`}>
        <span className="relative inline-flex h-5 w-5 items-center justify-center">
          <span className="absolute inset-0 rounded-full border-2 border-cyan-400/15" />
          <span className="absolute inset-[2px] animate-spin rounded-full border-2 border-transparent border-t-cyan-300 border-r-sky-300" />
        </span>
        <span>{label}</span>
      </span>
    );
  }

  return (
    <div
      className={`flex min-h-[180px] flex-col items-center justify-center gap-4 rounded-2xl border border-white/10 bg-slate-950/35 p-6 ${className}`}
    >
      <span className="relative inline-flex h-14 w-14 items-center justify-center">
        <span className="absolute inset-0 rounded-full border-[3px] border-cyan-400/15" />
        <span className="absolute inset-[4px] animate-spin rounded-full border-[3px] border-transparent border-t-cyan-300 border-r-sky-300" />
        <span className="absolute inset-[14px] rounded-full bg-cyan-300/10 shadow-[0_0_24px_rgba(56,189,248,0.22)]" />
      </span>
      <p className="text-sm font-semibold tracking-[0.12em] text-slate-200">{label}</p>
    </div>
  );
}
