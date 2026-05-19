export default function Skeleton({ className = 'h-4 w-full' }) {
  return (
    <div
      className={`skeleton-shimmer animate-pulse rounded-2xl bg-gradient-to-r from-white/[0.05] via-white/[0.12] to-white/[0.05] ${className}`}
    />
  );
}
