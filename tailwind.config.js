/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        midnight: '#020817',
        'midnight-soft': '#0f172a',
        cyan: {
          450: '#38bdf8',
          550: '#0891b2',
        },
        emerald: {
          450: '#34d399',
        },
        rose: {
          450: '#fb7185',
        },
      },
      fontFamily: {
        sans: ['IBM Plex Sans', 'Segoe UI', 'sans-serif'],
        display: ['Sora', 'IBM Plex Sans', 'sans-serif'],
      },
      boxShadow: {
        glow: '0 0 0 1px rgba(56, 189, 248, 0.15), 0 22px 70px rgba(8, 145, 178, 0.18)',
      },
      backgroundImage: {
        mesh: 'radial-gradient(circle at 15% 20%, rgba(34, 211, 238, 0.18), transparent 28%), radial-gradient(circle at 85% 0%, rgba(251, 113, 133, 0.14), transparent 24%), linear-gradient(140deg, rgba(15, 23, 42, 0.94), rgba(2, 6, 23, 1))',
      },
      keyframes: {
        float: {
          '0%, 100%': { transform: 'translateY(0px)' },
          '50%': { transform: 'translateY(-6px)' },
        },
        pulseGrid: {
          '0%, 100%': { opacity: '0.4' },
          '50%': { opacity: '0.85' },
        },
        slideUp: {
          '0%': { opacity: '0', transform: 'translateY(12px)' },
          '100%': { opacity: '1', transform: 'translateY(0px)' },
        },
      },
      animation: {
        float: 'float 7s ease-in-out infinite',
        'pulse-grid': 'pulseGrid 4.4s ease-in-out infinite',
        'slide-up': 'slideUp 0.45s ease-out',
      },
    },
  },
  plugins: [],
};
