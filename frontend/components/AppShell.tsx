"use client";
import { useEffect } from "react";
import { X } from "lucide-react";

/**
 * Two-pane on desktop, drawer on mobile.
 *
 * The app used to be a single 672px column at every width, so ~65% of a depot
 * desktop was empty background and there was no navigation at all. The rail is
 * permanent from `lg` up and slides over below it — not a shrunken copy of the
 * desktop layout, but the same content reached differently.
 */
export default function AppShell({
  rail,
  railOpen,
  onCloseRail,
  children,
}: {
  rail: React.ReactNode;
  railOpen: boolean;
  onCloseRail: () => void;
  children: React.ReactNode;
}) {
  // Escape closes the drawer, and body scroll is locked while it is open so a
  // swipe moves the drawer rather than the conversation behind it.
  useEffect(() => {
    if (!railOpen) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onCloseRail();
    }
    window.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [railOpen, onCloseRail]);

  return (
    <div className="flex h-[100dvh] w-full overflow-hidden">
      {/* Permanent rail — desktop only */}
      <aside className="hidden w-[264px] shrink-0 border-r border-line/12 bg-bg-panel/60 lg:block">
        {rail}
      </aside>

      {/* Drawer — below lg */}
      <div
        className={`fixed inset-0 z-40 lg:hidden ${
          railOpen ? "" : "pointer-events-none"
        }`}
        aria-hidden={!railOpen}
      >
        <div
          onClick={onCloseRail}
          className={`absolute inset-0 bg-bg-base/70 backdrop-blur-sm transition-opacity duration-200 ${
            railOpen ? "opacity-100" : "opacity-0"
          }`}
        />
        <div
          role="dialog"
          aria-modal={railOpen}
          aria-label="Navigation"
          className={`absolute inset-y-0 left-0 flex w-[min(84vw,300px)] flex-col border-r border-line/12 bg-bg-panel shadow-rail transition-transform duration-200 ease-out ${
            railOpen ? "translate-x-0" : "-translate-x-full"
          }`}
        >
          <div className="flex items-center justify-between px-3 pb-1 pt-[calc(env(safe-area-inset-top,0px)+0.6rem)]">
            <span className="text-[0.7rem] font-bold uppercase tracking-[0.12em] text-ink-faint">
              Menu
            </span>
            <button
              type="button"
              onClick={onCloseRail}
              aria-label="Close navigation"
              className="grid h-10 w-10 place-items-center rounded-lg text-ink-dim transition hover:text-accent active:scale-95"
            >
              <X size={18} aria-hidden />
            </button>
          </div>
          <div className="min-h-0 flex-1">{rail}</div>
        </div>
      </div>

      <div className="flex min-w-0 flex-1 flex-col">{children}</div>
    </div>
  );
}
