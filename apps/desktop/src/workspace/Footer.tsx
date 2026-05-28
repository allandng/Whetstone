import { I } from "./icons";

type Props = {
  online: boolean;
  /** Short summary of the most recent in-session activity, or null. */
  lastActivity: string | null;
  apiHost: string;
  onOpenTimeline: () => void;
};

export function Footer({ online, lastActivity, apiHost, onOpenTimeline }: Props) {
  return (
    <footer className="h-7 shrink-0 border-t border-zinc-900 bg-zinc-950 flex items-center justify-between px-3 text-[11px] font-mono text-zinc-500 select-none">
      <div className="flex items-center gap-2 min-w-0">
        <span className={`w-1.5 h-1.5 rounded-full ${online ? "bg-emerald-500" : "bg-zinc-600"}`} aria-hidden />
        <span className="text-zinc-300 font-medium font-sans">{online ? "Sandbox active" : "Sandbox offline"}</span>
        <span className="text-zinc-800" aria-hidden>
          |
        </span>
        <span className="truncate">{lastActivity ?? "No activity yet"}</span>
      </div>
      <div className="flex items-center gap-3 shrink-0">
        <button
          type="button"
          onClick={onOpenTimeline}
          className="hover:text-zinc-300 text-[10.5px] transition-colors duration-150 flex items-center gap-1 font-sans font-medium"
        >
          <I.Clock size={11} /> View full timeline
        </button>
        <span className="text-zinc-800" aria-hidden>
          //
        </span>
        <span className="text-[10.5px]">{online ? "ONLINE" : "OFFLINE"} · llama.cpp · {apiHost}</span>
      </div>
    </footer>
  );
}
