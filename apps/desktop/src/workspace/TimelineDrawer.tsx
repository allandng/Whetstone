import { useEffect } from "react";
import Timeline from "../components/Timeline";
import { I } from "./icons";

type Props = {
  open: boolean;
  onClose: () => void;
  /** Live session id; "" renders the Timeline's own empty hint. */
  sessionId: string;
};

export function TimelineDrawer({ open, onClose, sessionId }: Props) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="absolute inset-0 z-50" role="dialog" aria-modal="true" aria-label="Session timeline">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} aria-hidden />
      <div className="absolute bottom-0 left-0 right-0 bg-zinc-950 border-t border-zinc-800 drawer-in h-[45%] flex flex-col">
        <div className="h-9 px-4 border-b border-zinc-900 flex items-center justify-between bg-zinc-900/20 shrink-0">
          <div className="text-[11px] font-medium text-zinc-200 flex items-center gap-2">
            <I.Clock size={12} className="text-zinc-500" />
            <span>Session timeline</span>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close timeline"
            className="text-zinc-400 hover:text-zinc-200 transition-colors duration-150"
          >
            <I.X size={13} />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto">
          {sessionId ? (
            <Timeline sessionId={sessionId} />
          ) : (
            <p className="p-4 text-[12px] text-zinc-500">
              The timeline is unavailable while the backend is offline — start it to record and view session events.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
