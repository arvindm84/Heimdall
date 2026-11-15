import { useEffect, useState, type ReactNode } from "react";
import { Check, ChevronRight } from "lucide-react";
import { ApiError, api, type Folder, type FolderLabels, type Label } from "../lib/api";

const COLUMNS: { label: Label; name: string; hint: string }[] = [
  { label: "public", name: "Public", hint: "Fine to share" },
  { label: "private", name: "Private", hint: "Personal" },
  { label: "confidential", name: "Confidential", hint: "Most sensitive" },
];

// Least to most strict, the order COLUMNS lists them in.
const rank = (label: Label) => COLUMNS.findIndex((c) => c.label === label);
const nameOf = (label: Label) => COLUMNS[rank(label)].name;

// The folder inside `path` that makes it shared under a stricter label than its own, or null.
// Same rule as _granted in backend/services/folder_service.py: the firewall has one label per
// shared folder, so a folder is shared under the strictest label marked anywhere inside it.
function stricterInside(path: string, own: Label, labels: FolderLabels): { path: string; label: Label } | null {
  let found: { path: string; label: Label } | null = null;
  for (const [inside, label] of Object.entries(labels)) {
    if (inside.startsWith(path + "/") && rank(label) > rank(found?.label ?? own)) found = { path: inside, label };
  }
  return found;
}

// Folder name, then one column per label.
const ROW = "grid grid-cols-[1fr_6rem_6rem_7rem] items-center";

type Props = {
  agentName: string;
  initial: FolderLabels; // {} the first time
  saveText: string; // "Save and start" or "Save"
  onSave: (labels: FolderLabels) => Promise<void>;
  onCancel: () => void;
};

// The popup before an agent's first start: a folder tree with one label per folder.
// Only folders the user clicks go into `labels`, and only those are shared with the agent
// (backend/services/folder_service.py, granted_folders). Any other folder shows its parent's
// label (dimmed), or Confidential at the top level, so changing a parent changes every
// subfolder the user hasn't set.
export default function FolderAccessDialog({ agentName, initial, saveText, onSave, onCancel }: Props) {
  const [labels, setLabels] = useState<FolderLabels>(initial);
  const [home, setHome] = useState<string | null>(null);
  const [children, setChildren] = useState<Record<string, Folder[]>>({}); // folder path -> subfolders, once loaded
  const [open, setOpen] = useState<Set<string>>(new Set());
  const [errors, setErrors] = useState<Record<string, string>>({}); // folder path -> why it wouldn't open
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const message = (e: unknown) => (e instanceof ApiError ? e.message : String(e));

  // Load the folders in home to start the tree.
  useEffect(() => {
    api
      .folders()
      .then((res) => {
        setHome(res.path);
        setChildren({ [res.path]: res.folders });
      })
      .catch((e) => setSaveError(message(e)));
  }, []);

  // Esc closes, like any dialog.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onCancel();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onCancel]);

  // Open or close a folder. Its subfolders load the first time it opens.
  const toggle = async (path: string) => {
    const next = new Set(open);
    if (next.has(path)) next.delete(path);
    else next.add(path);
    setOpen(next);
    if (children[path] || !next.has(path)) return;
    try {
      const res = await api.folders(path);
      setChildren((all) => ({ ...all, [path]: res.folders }));
    } catch (e) {
      setErrors((all) => ({ ...all, [path]: message(e) }));
    }
  };

  const save = async () => {
    setSaving(true);
    setSaveError(null);
    try {
      await onSave(labels);
    } catch (e) {
      setSaveError(message(e));
      setSaving(false);
    }
  };

  // One row per folder, then its subfolders if open. `inherited`: the parent's label.
  const rows = (parent: string, depth: number, inherited: Label): ReactNode =>
    children[parent]?.map((folder) => {
      const chosen = labels[folder.path];
      const label = chosen ?? inherited;
      const isOpen = open.has(folder.path);
      const stricter = chosen ? stricterInside(folder.path, chosen, labels) : null;
      return (
        <div key={folder.path}>
          <div className={`${ROW} border-b border-rule/60 py-1.5 hover:bg-ground/40`}>
            <button
              onClick={() => toggle(folder.path)}
              className="flex min-w-0 items-center gap-1.5 text-left"
              style={{ paddingLeft: `${depth * 1.25}rem` }}
            >
              <ChevronRight className={`size-4 shrink-0 text-lichen transition-transform ${isOpen ? "rotate-90" : ""}`} />
              <span className="truncate font-mono text-[13px]">{folder.name}</span>
            </button>
            {COLUMNS.map((c) => (
              <LabelBox
                key={c.label}
                name={folder.path}
                checked={label === c.label}
                inherited={!chosen}
                title={chosen === c.label ? `${folder.name}: click again to stop sharing it` : `${folder.name}: ${c.name}`}
                // Click a label to mark the folder (share it). Click the marked one again to un-mark it.
                onPick={() =>
                  setLabels((all) => {
                    if (all[folder.path] !== c.label) return { ...all, [folder.path]: c.label };
                    const { [folder.path]: _removed, ...rest } = all;
                    return rest;
                  })
                }
              />
            ))}
          </div>
          {/* The truth about how it's shared, when that differs from the mark on the row */}
          {stricter && (
            <p className="pb-1.5 text-xs text-waiting" style={{ paddingLeft: `${depth * 1.25 + 1.375}rem` }}>
              Shared as {nameOf(stricter.label)}, because {stricter.path.slice(folder.path.length + 1)} inside it is{" "}
              {nameOf(stricter.label)}.
            </p>
          )}
          {isOpen && (
            <>
              {errors[folder.path] && (
                <p className="py-1.5 text-sm text-blocked" style={{ paddingLeft: `${(depth + 1) * 1.25 + 1.375}rem` }}>
                  {errors[folder.path]}
                </p>
              )}
              {children[folder.path]?.length === 0 && (
                <p className="py-1.5 text-sm text-lichen" style={{ paddingLeft: `${(depth + 1) * 1.25 + 1.375}rem` }}>
                  No subfolders
                </p>
              )}
              {rows(folder.path, depth + 1, label)}
            </>
          )}
        </div>
      );
    });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-6" role="dialog" aria-modal="true">
      <div className="flex max-h-[85vh] w-[46rem] max-w-full flex-col rounded-md border border-rule bg-raised shadow-2xl">
        <div className="px-6 pt-5 pb-4">
          <h2 className="text-xl font-bold">Folder access for {agentName}</h2>
          <p className="mt-1 max-w-[60ch] text-sm text-lichen">
            Only folders you mark are shared with {agentName}. Everything else starts as Confidential and stays hidden
            from it. Subfolders follow their parent unless you change them, so to share one subfolder only, mark just
            that subfolder. Click a mark again to remove it. Change this later from Folder access; it applies the next time the agent starts.
          </p>
        </div>

        {/* Column names, pinned above the scrolling tree */}
        <div className={`${ROW} border-y border-rule px-6 py-2 text-sm`}>
          <span className="text-lichen">Folder</span>
          {COLUMNS.map((c) => (
            <span key={c.label} className="text-center">
              <span className="block font-bold">{c.name}</span>
              <span className="block text-xs text-lichen">{c.hint}</span>
            </span>
          ))}
        </div>

        <div className="min-h-40 flex-1 overflow-y-auto px-6">
          {home ? rows(home, 0, "confidential") : !saveError && <p className="py-4 text-sm text-lichen">Loading folders…</p>}
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-rule px-6 py-4">
          {saveError && <p className="mr-auto text-sm text-blocked">{saveError}</p>}
          <button
            onClick={onCancel}
            className="rounded border border-rule px-4 py-2 text-sm text-lichen transition-colors hover:border-lichen hover:text-paper"
          >
            Cancel
          </button>
          <button
            onClick={save}
            disabled={saving}
            className="rounded bg-paper px-4 py-2 text-sm font-bold text-ground hover:opacity-90 disabled:opacity-50"
          >
            {saving ? "Saving…" : saveText}
          </button>
        </div>
      </div>
    </div>
  );
}

// A square box that works like a radio button: one per folder can be checked.
// Dimmed when the folder hasn't been set and is only following its parent.
function LabelBox(props: { name: string; checked: boolean; inherited: boolean; title: string; onPick: () => void }) {
  return (
    <label className="flex cursor-pointer justify-center py-1" title={props.title}>
      {/* onClick, not onChange: a radio that is already checked fires no change, and we need that click to un-mark. */}
      <input type="radio" name={props.name} checked={props.checked} onChange={() => {}} onClick={props.onPick} className="peer sr-only" />
      <span
        className={`flex size-[18px] items-center justify-center rounded-[3px] border transition-colors peer-focus-visible:ring-2 peer-focus-visible:ring-paper/60 ${
          props.checked
            ? props.inherited
              ? "border-lichen/60 bg-lichen/30 text-paper"
              : "border-paper bg-paper text-ground"
            : "border-rule hover:border-lichen"
        }`}
      >
        {props.checked && <Check className="size-3.5" strokeWidth={3} />}
      </span>
    </label>
  );
}
