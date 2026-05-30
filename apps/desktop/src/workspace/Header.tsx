import { I } from "./icons";

/** Voice dictation lifecycle: idle → recording → transcribing → idle. */
export type VoiceState = "idle" | "recording" | "transcribing";

type Props = {
  voiceState: VoiceState;
  onToggleRecording: () => void;
  /** Returns to the legacy Home view; the brand and the cog both use it. */
  onNavigateHome: () => void;
  /** Online indicator — reflects whether the backend bootstrap succeeded. */
  online: boolean;
  breadcrumb: { project: string; file: string };
};

export function Header({ voiceState, onToggleRecording, onNavigateHome, online, breadcrumb }: Props) {
  const recording = voiceState === "recording";
  const transcribing = voiceState === "transcribing";
  return (
    <header className="h-11 shrink-0 border-b border-zinc-900 bg-zinc-950 flex items-center justify-between px-4 select-none">
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={onNavigateHome}
          aria-label="Whetstone — back to home"
          className="w-5 h-5 bg-zinc-100 flex items-center justify-center rounded-[3px]"
        >
          <span className="w-2 h-2 bg-zinc-950 rotate-45" aria-hidden />
        </button>
        <span className="font-semibold text-zinc-100 text-sm tracking-tight">Whetstone</span>
        <span className="w-px h-3 bg-zinc-800" aria-hidden />
        <nav aria-label="Breadcrumb" className="flex items-center gap-1.5 font-mono text-[11px] text-zinc-400">
          <span>{breadcrumb.project}</span>
          <span className="text-zinc-700" aria-hidden>
            /
          </span>
          <span className="text-zinc-200">{breadcrumb.file}</span>
        </nav>
      </div>

      <div className="flex items-center gap-4">
        <div
          className="flex items-center gap-1.5 text-[11px] font-medium text-zinc-300"
          title={online ? "Backend reachable on loopback" : "Backend unreachable — running on local UI state"}
        >
          <span
            className={`w-1.5 h-1.5 rounded-full ${online ? "bg-emerald-500 pulse-dot" : "bg-zinc-600"}`}
            aria-hidden
          />
          <span>{online ? "Local engine · online" : "Local engine · offline"}</span>
        </div>

        <button
          type="button"
          onClick={onToggleRecording}
          aria-pressed={recording}
          disabled={transcribing}
          aria-label={recording ? "Stop dictation and transcribe" : "Start voice dictation"}
          title={
            online
              ? "Dictate into the co-pilot prompt — on-device transcription"
              : "Backend offline — voice needs the local engine"
          }
          className={`h-7 px-2.5 rounded flex items-center gap-2 border font-medium text-[11px] transition-all duration-200 disabled:cursor-not-allowed ${
            recording
              ? "bg-red-950/30 border-red-800 text-red-300"
              : transcribing
                ? "bg-sky-950/30 border-sky-800 text-sky-300"
                : "bg-zinc-900 border-zinc-800 text-zinc-300 hover:text-zinc-100 hover:border-zinc-700"
          }`}
        >
          <I.Mic size={12} className={recording ? "text-red-400" : transcribing ? "text-sky-400" : ""} />
          {recording ? (
            <span className="flex items-center gap-2">
              <span className="flex items-end gap-[2px] h-3" aria-hidden>
                {[0, 1, 2, 3].map((n) => (
                  <span
                    key={n}
                    className="wbar w-[2px] bg-red-400 rounded-full"
                    style={{ height: "100%", animationDelay: `${n * 0.12}s` }}
                  />
                ))}
              </span>
              <span>Recording</span>
            </span>
          ) : transcribing ? (
            <span className="flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-sky-400 pulse-dot" aria-hidden />
              <span>Transcribing…</span>
            </span>
          ) : (
            <span>Dictate</span>
          )}
        </button>

        <button
          type="button"
          onClick={onNavigateHome}
          aria-label="Settings (returns to home)"
          className="text-zinc-400 hover:text-zinc-200 transition-colors duration-150"
        >
          <I.Cog size={14} />
        </button>
      </div>
    </header>
  );
}
