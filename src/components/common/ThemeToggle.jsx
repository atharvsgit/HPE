import { useEffect, useState } from 'react';

const STORAGE_KEY = 'data-validity-checker-theme';

function MoonIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor">
      <path
        d="M20 15.5A8.5 8.5 0 0 1 8.5 4a8.5 8.5 0 1 0 11.5 11.5Z"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function SunIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor">
      <circle cx="12" cy="12" r="4" strokeWidth="1.8" />
      <path
        d="M12 2.5v2.2M12 19.3v2.2M4.7 4.7l1.6 1.6M17.7 17.7l1.6 1.6M2.5 12h2.2M19.3 12h2.2M4.7 19.3l1.6-1.6M17.7 6.3l1.6-1.6"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
    </svg>
  );
}

function SparkIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor">
      <path
        d="M12 2.5 13.8 8l5.7 1.9-5.7 1.9L12 17.5l-1.8-5.7L4.5 9.9 10.2 8 12 2.5Z"
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
      <path
        d="m18.5 15.5.9 2.5 2.6.9-2.6.9-.9 2.6-.9-2.6-2.5-.9 2.5-.9.9-2.5ZM5.5 14l.6 1.6 1.7.6-1.7.6-.6 1.7-.6-1.7-1.6-.6 1.6-.6.6-1.6Z"
        strokeWidth="1.6"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export default function ThemeToggle() {
  const [theme, setTheme] = useState(() => {
    if (typeof window === 'undefined') {
      return 'dark';
    }

    return window.localStorage.getItem(STORAGE_KEY) || 'dark';
  });

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    window.localStorage.setItem(STORAGE_KEY, theme);
  }, [theme]);

  const isPrism = theme === 'prism';

  return (
    <button
      type="button"
      onClick={() => setTheme(isPrism ? 'dark' : 'prism')}
      className="group inline-flex items-center gap-3 rounded-full border border-white/10 bg-white/[0.06] px-4 py-2 text-sm font-medium text-slate-200 shadow-lg shadow-black/25 backdrop-blur-xl transition duration-300 hover:-translate-y-0.5 hover:border-cyan-300/35 hover:bg-white/[0.1]"
      title="Toggle ambience"
    >
      <span
        className={`inline-flex h-9 w-9 items-center justify-center rounded-full border transition duration-300 ${
          isPrism
            ? 'border-fuchsia-300/30 bg-fuchsia-300/15 text-fuchsia-100'
            : 'border-cyan-300/30 bg-cyan-300/10 text-cyan-100'
        }`}
      >
        {isPrism ? <SparkIcon /> : <MoonIcon />}
      </span>
      <span className="text-left">
        <span className="block text-xs uppercase tracking-[0.24em] text-slate-500">
          Ambience
        </span>
        <span className="block text-sm text-white">
          {isPrism ? 'Prism Mode' : 'Night Mode'}
        </span>
      </span>
    </button>
  );
}
