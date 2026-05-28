import type { RequirementItemRead, RequirementStatus } from "../types";
import { I } from "./icons";
import { StatusMenu } from "./StatusMenu";

type Props = {
  requirements: RequirementItemRead[];
  hasSpec: boolean;
  loading: boolean;
  online: boolean;
  onStatusChange: (id: string, status: RequirementStatus) => void;
};

// The backend stores only free text per requirement (no label column), so we
// synthesise a short tag: a leading code like "FR-SPEC-7" / "[NFR-SEC-3]" if the
// text carries one, otherwise a positional "R{n}".
function labelFor(text: string, index: number): { tag: string; body: string } {
  const m = text.match(/^\s*\[?([A-Z]{1,5}(?:[-\s][A-Z0-9]{1,6}){0,3})\]?\s*[:.\-—]\s*(.*)$/s);
  if (m && /\d/.test(m[1])) {
    return { tag: m[1].replace(/\s+/g, "-"), body: m[2].trim() || text.trim() };
  }
  return { tag: `R${index + 1}`, body: text.trim() };
}

// Heuristic for the prototype's amber advisory: surface it on requirements that
// talk about asymptotic/complexity bounds, where the co-pilot's complexity
// analysis is the natural follow-up.
function isComplexityRelated(text: string): boolean {
  return /\bO\(|complexity|time bound|asymptotic|big[-\s]?o/i.test(text);
}

export function RequirementsPane({ requirements, hasSpec, loading, online, onStatusChange }: Props) {
  const doneCount = requirements.filter((r) => r.status === "done").length;

  return (
    <aside
      className="w-[310px] shrink-0 border-r border-zinc-900 bg-zinc-950 flex flex-col"
      aria-label="Tracked requirements"
    >
      <div className="h-9 px-3 flex items-center justify-between border-b border-zinc-900">
        <span className="text-[11px] font-medium text-zinc-300 tracking-tight">Tracked Requirements</span>
        <span className="font-mono text-[10px] text-zinc-500">
          {doneCount}/{requirements.length}
        </span>
      </div>

      <ul className="flex-1 overflow-y-auto px-2 py-3 space-y-2 list-none m-0">
        {requirements.map((r, i) => {
          const { tag, body } = labelFor(r.text, i);
          return (
            <li
              key={r.id}
              className="p-2.5 rounded bg-zinc-900/40 border border-zinc-900 hover:border-zinc-800 transition-colors duration-150 flex flex-col gap-2"
            >
              <div className="flex items-center justify-between gap-2">
                <span className="font-mono text-[10px] uppercase font-semibold tracking-wider text-zinc-400">
                  {tag}
                </span>
                <StatusMenu
                  status={r.status}
                  label={tag}
                  onChange={(s) => onStatusChange(r.id, s)}
                  disabled={!online}
                />
              </div>
              <p className="text-[12px] text-zinc-300 leading-normal">{body}</p>
              {isComplexityRelated(r.text) && (
                <div className="mt-1 flex items-center gap-1.5 text-[10px] text-amber-400 font-medium">
                  <I.Alert size={11} />
                  <span>Advisory: ask the co-pilot to check this cell's complexity bound</span>
                </div>
              )}
            </li>
          );
        })}

        {!loading && requirements.length === 0 && (
          <li className="px-1 py-6 text-center list-none">
            <p className="text-[11.5px] text-zinc-500 leading-relaxed">
              {hasSpec
                ? online
                  ? "No requirements extracted yet. Extraction runs in the background after a spec import."
                  : "Requirements live in the backend — start it to load this session's checklist."
                : "No spec attached. Import an assignment spec to track its requirements here."}
            </p>
          </li>
        )}

        {loading && (
          <li className="px-1 py-6 text-center list-none">
            <p className="text-[11.5px] text-zinc-500">Loading requirements…</p>
          </li>
        )}

        {requirements.length > 0 && (
          <li className="pt-4 border-t border-zinc-900 mt-2 px-1 list-none">
            <div className="text-[10px] font-semibold text-zinc-500 uppercase tracking-wider mb-2">
              Automated extraction
            </div>
            <div className="p-2 rounded border border-dashed border-zinc-800 text-zinc-400 text-[11.5px] leading-relaxed">
              {requirements.length} requirement {requirements.length === 1 ? "item" : "items"} extracted from the
              attached spec. Edit status on any item — extraction is advisory.
            </div>
          </li>
        )}
      </ul>
    </aside>
  );
}
