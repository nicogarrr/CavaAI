'use client';

import { useEffect, useRef } from 'react';

/**
 * Panel that collapses on mobile but stays expanded on desktop.
 *
 * A plain <details> is closed by default on EVERY viewport, which hid
 * content on desktop where the "tocar para expandir" hint is also
 * hidden (sm:hidden) - desktop users could not tell the panel expands.
 * This client component opens the details when the viewport is sm+
 * (>=640px) and lets the user toggle freely afterwards.
 */
export default function CollapsiblePanel({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  const ref = useRef<HTMLDetailsElement>(null);

  useEffect(() => {
    const media = window.matchMedia('(min-width: 640px)');
    const apply = () => {
      if (ref.current) {
        ref.current.open = media.matches;
      }
    };
    apply();
    media.addEventListener('change', apply);
    return () => media.removeEventListener('change', apply);
  }, []);

  return (
    <details
      ref={ref}
      className="rounded-xl border border-gray-800 bg-[#101010] p-4 sm:p-5"
    >
      <summary className="cursor-pointer list-none text-lg font-semibold text-gray-100 [&::-webkit-details-marker]:hidden">
        <span className="flex min-h-[44px] items-center justify-between gap-2">
          {title}
          <span className="text-xs font-normal text-gray-500 sm:hidden">
            tocar para expandir
          </span>
        </span>
      </summary>
      <div className="mt-4">{children}</div>
    </details>
  );
}
