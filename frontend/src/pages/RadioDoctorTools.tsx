import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState, type PointerEvent } from "react";
import { api, fetchBlobUrl, patch, type Annotation, type ImagingItem, type RadioComparison } from "../api/client";
import { fmtDate } from "../labels";

/*
 * Outils du médecin sur les radiographies.
 * F-C7 : annotations (flèches, textes) en coordonnées normalisées 0..1 sur l'image, stockées en JSON.
 * F-C6 : qualification de l'évolution entre deux clichés, saisie par le médecin (l'IA n'en donne aucune, D5).
 */

const QUALIF = [
  ["amelioration", "Amélioration"], ["stable", "Stabilité"], ["aggravation", "Aggravation"], ["non_evaluable", "Non évaluable"],
] as const;

function useImage(path: string) {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    let made: string | null = null;
    fetchBlobUrl(path).then((u) => { made = u; if (alive) setUrl(u); else URL.revokeObjectURL(u); }).catch(() => setUrl(null));
    return () => { alive = false; if (made) URL.revokeObjectURL(made); };
  }, [path]);
  return url;
}

export function AnnotationLayer({ notes, draft }: { notes: Annotation[]; draft?: Annotation | null }) {
  return (
    <svg viewBox="0 0 1000 1000" preserveAspectRatio="none" className="pointer-events-none absolute inset-0 h-full w-full" aria-hidden="true">
      <defs>
        <marker id="arrowhead" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">
          <path d="M0,0 L8,4 L0,8 z" fill="#FFD447" />
        </marker>
      </defs>
      {[...notes, ...(draft ? [draft] : [])].map((n, i) =>
        n.type === "arrow" ? (
          <line key={i} x1={n.x1 * 1000} y1={n.y1 * 1000} x2={(n.x2 ?? n.x1) * 1000} y2={(n.y2 ?? n.y1) * 1000}
            stroke="#FFD447" strokeWidth="5" markerEnd="url(#arrowhead)" vectorEffect="non-scaling-stroke" />
        ) : (
          <text key={i} x={n.x1 * 1000} y={n.y1 * 1000} fill="#FFD447" fontSize="34" fontWeight="bold"
            stroke="#000" strokeWidth="1.5" paintOrder="stroke">{n.text}</text>
        ),
      )}
    </svg>
  );
}

export function AnnotationEditor({ item, patientId }: { item: ImagingItem; patientId: string }) {
  const qc = useQueryClient();
  const url = useImage(`/documents/${item.document_id}/pages/0?width=900`);
  const [notes, setNotes] = useState<Annotation[]>(item.annotations);
  const [tool, setTool] = useState<"arrow" | "text">("arrow");
  const [draft, setDraft] = useState<Annotation | null>(null);
  const box = useRef<HTMLDivElement>(null);
  const save = useMutation({
    mutationFn: () => patch(`/documents/${item.document_id}/imaging`, { annotations: notes }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["imaging", patientId] }),
  });
  const pos = (e: PointerEvent) => {
    const r = box.current!.getBoundingClientRect();
    const c = (v: number) => Math.min(1, Math.max(0, v));
    return { x: c((e.clientX - r.left) / r.width), y: c((e.clientY - r.top) / r.height) };
  };
  function down(e: PointerEvent<HTMLDivElement>) {
    const p = pos(e);
    if (tool === "text") {
      const text = window.prompt("Texte de l'annotation (200 caractères au plus)")?.trim().slice(0, 200);
      if (text) setNotes([...notes, { type: "text", x1: p.x, y1: p.y, text }]);
      return;
    }
    e.currentTarget.setPointerCapture(e.pointerId);
    setDraft({ type: "arrow", x1: p.x, y1: p.y, x2: p.x, y2: p.y });
  }
  function move(e: PointerEvent<HTMLDivElement>) {
    if (draft) { const p = pos(e); setDraft({ ...draft, x2: p.x, y2: p.y }); }
  }
  function up() {
    if (draft && Math.hypot((draft.x2 ?? 0) - draft.x1, (draft.y2 ?? 0) - draft.y1) > 0.02) setNotes([...notes, draft]);
    setDraft(null);
  }
  const dirty = JSON.stringify(notes) !== JSON.stringify(item.annotations);
  return (
    <div className="mt-3">
      <div className="mb-2 flex flex-wrap items-center gap-2 text-sm" role="toolbar" aria-label="Outils d'annotation">
        {(["arrow", "text"] as const).map((t) => (
          <button key={t} type="button" aria-pressed={tool === t} onClick={() => setTool(t)}
            className={`btn py-1 ${tool === t ? "border-teal bg-teal-soft font-semibold" : ""}`}>{t === "arrow" ? "Flèche" : "Texte"}</button>
        ))}
        <button type="button" className="btn py-1" disabled={!notes.length} onClick={() => setNotes(notes.slice(0, -1))}>Annuler la dernière</button>
        <button type="button" className="btn py-1" disabled={!notes.length} onClick={() => setNotes([])}>Tout effacer</button>
        <button type="button" className="btn btn-primary py-1" disabled={!dirty || save.isPending} onClick={() => save.mutate()}>Enregistrer</button>
      </div>
      <div ref={box} className="relative inline-block w-full max-w-[520px] cursor-crosshair touch-none select-none bg-black"
        onPointerDown={down} onPointerMove={move} onPointerUp={up}>
        {url ? <img src={url} alt={`Radiographie du ${fmtDate(item.date)}`} className="block w-full" draggable={false} />
          : <div className="aspect-square" />}
        <AnnotationLayer notes={notes} draft={draft} />
      </div>
      <p className="mt-1 text-[12.5px] text-ink-3">
        {tool === "arrow" ? "Cliquez-glissez pour tracer une flèche." : "Cliquez à l'endroit du texte."} {notes.length} annotation(s).
        {save.isError && <span className="text-alert"> Enregistrement impossible.</span>}
      </p>
    </div>
  );
}

export function ComparisonQualification({ patientId, a, b }: { patientId: string; a: ImagingItem; b: ImagingItem }) {
  const qc = useQueryClient();
  const { data } = useQuery({
    queryKey: ["radio-comparisons", patientId],
    queryFn: () => api<RadioComparison[]>(`/patients/${patientId}/radiograph-comparisons`),
  });
  const saved = data?.find((c) => c.document_a_id === a.document_id && c.document_b_id === b.document_id);
  const [q, setQ] = useState<string>("");
  const [comment, setComment] = useState<string | null>(null);
  const save = useMutation({
    mutationFn: () => api("/radiograph-comparisons", { method: "PUT", body: JSON.stringify({
      document_a_id: a.document_id, document_b_id: b.document_id, qualification: q || saved?.qualification, comment: comment ?? saved?.comment ?? null,
    }) }),
    onSuccess: () => { setQ(""); setComment(null); qc.invalidateQueries({ queryKey: ["radio-comparisons", patientId] }); qc.invalidateQueries({ queryKey: ["facts", patientId] }); },
  });
  const value = q || saved?.qualification || "";
  return (
    <div className="panel mt-4 p-4">
      <h3 className="font-bold">Évolution entre le {fmtDate(a.date)} et le {fmtDate(b.date)} : votre jugement</h3>
      <p className="mb-2 text-[13px] text-ink-2">Le modèle ne donne aucun verdict d'évolution ; cette qualification est la vôtre et figure sur la fiche.</p>
      <div className="flex flex-wrap gap-1.5" role="radiogroup" aria-label="Qualification de l'évolution">
        {QUALIF.map(([k, label]) => (
          <button key={k} type="button" role="radio" aria-checked={value === k} onClick={() => setQ(k)}
            className={`btn py-1 ${value === k ? "border-teal bg-teal-soft font-semibold" : ""}`}>{label}</button>
        ))}
      </div>
      <label htmlFor="cmp-comment" className="label mt-2">Commentaire (facultatif)</label>
      <textarea id="cmp-comment" className="field min-h-12" value={comment ?? saved?.comment ?? ""} onChange={(e) => setComment(e.target.value)} />
      <div className="mt-2 flex items-center gap-3">
        <button type="button" className="btn btn-primary" disabled={!value || save.isPending || (q === "" && comment === null)}
          onClick={() => save.mutate()}>Enregistrer le jugement</button>
        {saved && <span className="text-[13px] text-ink-3">Enregistré le {new Date(saved.updated_at).toLocaleDateString("fr-FR")}</span>}
      </div>
    </div>
  );
}
