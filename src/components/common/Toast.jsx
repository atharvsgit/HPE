const toneClasses = {
  success: 'border-emerald-400/30 bg-emerald-400/10 text-emerald-100',
  error: 'border-rose-400/30 bg-rose-400/10 text-rose-100',
  info: 'border-cyan-400/30 bg-cyan-400/10 text-cyan-100',
};

export default function Toast({ toasts, onDismiss }) {
  if (!toasts.length) {
    return null;
  }

  return (
    <div className="pointer-events-none fixed right-4 top-4 z-50 flex w-full max-w-sm flex-col gap-3">
      {toasts.map((toast) => (
        <div
          key={toast.id}
          className={`pointer-events-auto animate-slide-up rounded-2xl border p-4 shadow-2xl shadow-black/35 backdrop-blur-xl transition-all duration-300 ${
            toneClasses[toast.tone] || toneClasses.info
          }`}
        >
          <div className="flex items-start justify-between gap-4">
            <div className="flex items-start gap-3">
              <span className="mt-0.5 inline-flex h-3 w-3 rounded-full bg-current opacity-80" />
              <div>
                <p className="text-sm font-semibold">{toast.title}</p>
                <p className="mt-1 text-sm leading-6 opacity-85">{toast.message}</p>
              </div>
            </div>
            <button
              type="button"
              onClick={() => onDismiss(toast.id)}
              className="rounded-full border border-current/20 px-3 py-1.5 text-[0.7rem] font-semibold uppercase tracking-[0.24em] transition-all duration-300 hover:bg-white/10"
            >
              Close
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
