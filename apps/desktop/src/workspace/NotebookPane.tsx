import { I } from "./icons";

/** A single notebook cell as the UI renders it. `id` is the server Cell id;
 *  `output`/`status` mirror the last run (CellRead.last_output / status). */
export type NotebookCell = {
  id: string;
  language: string;
  content: string;
  /** Terminal text from the last run (CellRead.last_output), or null. */
  output: string | null;
  /** Backend cell status: ok | error | terminated | timeout | "" (never run). */
  status: string;
  running: boolean;
  /** Set when a run request was aborted client-side; the server job continues. */
  note: string | null;
};

type Props = {
  cells: NotebookCell[];
  online: boolean;
  /** True while an Add-cell request is in flight (disables the control). */
  adding: boolean;
  onChange: (cellId: string, content: string) => void;
  onRun: (cellId: string) => void;
  onCancel: (cellId: string) => void;
  onClear: (cellId: string) => void;
  onFocusCell: (cellId: string) => void;
  onAddCell: (language: string) => void;
};

const LINE_HEIGHT = 24; // leading-6

function statusTone(status: string): string {
  if (status === "ok") return "text-emerald-400";
  if (status === "error" || status === "terminated") return "text-red-400";
  if (status === "timeout") return "text-amber-400";
  return "text-zinc-400";
}

function cellLabel(index: number): string {
  return `Cell ${String(index + 1).padStart(2, "0")}`;
}

type CellCardProps = {
  cell: NotebookCell;
  label: string;
  onChange: (content: string) => void;
  onRun: () => void;
  onCancel: () => void;
  onClear: () => void;
  onFocus: () => void;
};

function CellCard({ cell, label, onChange, onRun, onCancel, onClear, onFocus }: CellCardProps) {
  const lineCount = Math.max(cell.content.split("\n").length, 1);
  const hasOutput = cell.output != null && cell.output.length > 0;

  return (
    <div className="rounded border border-zinc-900 bg-zinc-950 overflow-hidden">
      <div className="h-8 bg-zinc-900/40 border-b border-zinc-900 px-3 flex items-center justify-between">
        <span className="text-[10px] font-mono tracking-wider font-semibold uppercase text-zinc-400">
          {label} · {cell.language}
        </span>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={onRun}
            disabled={cell.running}
            aria-label="Run cell"
            className="h-5 px-2 rounded bg-zinc-900 hover:bg-zinc-800 border border-zinc-800 text-emerald-400 text-[11px] font-medium flex items-center gap-1 disabled:opacity-50 transition-colors duration-150"
          >
            <I.Play size={9} /> Run
          </button>
          <button
            type="button"
            onClick={onCancel}
            disabled={!cell.running}
            aria-label="Cancel run request"
            title="Cancels the client request; the server job continues to completion"
            className="h-5 px-2 rounded bg-zinc-900 hover:bg-zinc-800 border border-zinc-800 text-zinc-300 text-[11px] font-medium flex items-center gap-1 disabled:opacity-40 transition-colors duration-150"
          >
            <I.Stop size={9} /> Cancel
          </button>
          <button
            type="button"
            onClick={onClear}
            className="h-5 px-2 rounded bg-zinc-900 hover:bg-zinc-800 border border-zinc-800 text-zinc-400 text-[11px] font-medium transition-colors duration-150"
          >
            Clear
          </button>
        </div>
      </div>

      <div className="bg-zinc-950 px-1">
        <div className="flex py-3 font-mono text-[13px] leading-6">
          <div aria-hidden className="shrink-0 select-none">
            {Array.from({ length: lineCount }, (_, i) => (
              <div
                key={i}
                className="h-6 w-11 pr-4 text-right text-zinc-700 text-[11px] font-sans font-medium leading-6"
              >
                {i + 1}
              </div>
            ))}
          </div>
          <textarea
            value={cell.content}
            onChange={(e) => onChange(e.target.value)}
            onFocus={onFocus}
            spellCheck={false}
            wrap="off"
            aria-label={`${label} source`}
            className="flex-1 resize-none bg-transparent text-zinc-300 outline-none border-0 p-0 whitespace-pre overflow-hidden leading-6"
            style={{ height: lineCount * LINE_HEIGHT }}
          />
        </div>
      </div>

      <div
        className="border-t border-zinc-900 p-3 font-mono text-[12px] leading-relaxed min-h-[132px]"
        style={{ background: "var(--bg-inset)" }}
        role="log"
        aria-live="polite"
        aria-label="Cell output"
      >
        {cell.running && (
          <div className="text-zinc-400 flex items-center gap-2">
            <span className="w-1.5 h-1.5 rounded-full bg-amber-500 pulse-dot" aria-hidden />
            <span>Running on the local engine via loopback…</span>
          </div>
        )}

        {!cell.running && !hasOutput && (
          <div className="text-zinc-700 select-none">
            <span>$ ./engine_worker</span>
            <p className="text-[11px] mt-1 text-zinc-700 italic">No output recorded. Press Run.</p>
          </div>
        )}

        {!cell.running && hasOutput && (
          <>
            <div className={`mb-1.5 text-[10px] font-semibold uppercase tracking-wider ${statusTone(cell.status)}`}>
              Exited · {cell.status || "unknown"}
            </div>
            <pre className="whitespace-pre-wrap text-zinc-200 m-0">{cell.output}</pre>
          </>
        )}

        {cell.note && <p className="mt-2 text-[11px] text-amber-400/90 italic">{cell.note}</p>}
      </div>
    </div>
  );
}

export function NotebookPane({
  cells,
  online,
  adding,
  onChange,
  onRun,
  onCancel,
  onClear,
  onFocusCell,
  onAddCell,
}: Props) {
  const addDisabled = !online || adding;
  const addTitle = online
    ? "Add a runnable code cell"
    : "Start the backend to add cells";

  return (
    <main className="flex-1 min-w-0 flex flex-col" style={{ background: "var(--bg-canvas)" }} aria-label="Notebook">
      <div className="h-9 shrink-0 flex items-center border-b border-zinc-900 bg-zinc-950 px-3 justify-between">
        <div className="flex items-center gap-1.5 text-[11px] font-medium text-zinc-200">
          <I.File size={12} className="text-zinc-500" />
          <span>scratchpad</span>
        </div>
        <div className="text-[11px] font-mono text-zinc-500">
          {cells.length} {cells.length === 1 ? "cell" : "cells"} · loopback mode
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-4 max-w-4xl w-full mx-auto space-y-4">
        {cells.map((cell, index) => (
          <CellCard
            key={cell.id}
            cell={cell}
            label={cellLabel(index)}
            onChange={(content) => onChange(cell.id, content)}
            onRun={() => onRun(cell.id)}
            onCancel={() => onCancel(cell.id)}
            onClear={() => onClear(cell.id)}
            onFocus={() => onFocusCell(cell.id)}
          />
        ))}

        <div className="w-full rounded border border-dashed border-zinc-800 p-2 flex items-center justify-center gap-2">
          <span className="text-[11px] font-medium text-zinc-500 flex items-center gap-1">
            <I.Plus size={13} /> Add cell
          </span>
          <button
            type="button"
            onClick={() => onAddCell("python")}
            disabled={addDisabled}
            title={addTitle}
            className="h-6 px-2.5 rounded bg-zinc-900 hover:bg-zinc-800 border border-zinc-800 text-zinc-300 text-[11px] font-medium transition-colors duration-150 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            Python
          </button>
          <button
            type="button"
            onClick={() => onAddCell("cpp")}
            disabled={addDisabled}
            title={addTitle}
            className="h-6 px-2.5 rounded bg-zinc-900 hover:bg-zinc-800 border border-zinc-800 text-zinc-300 text-[11px] font-medium transition-colors duration-150 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            C++
          </button>
        </div>
      </div>
    </main>
  );
}
