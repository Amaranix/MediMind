import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState, type PointerEvent, type WheelEvent } from "react";
import { Link, useParams } from "react-router-dom";
import { api, fetchBlobUrl, patch, type ImagingItem, type ImagingList } from "../api/client";
import { DEFAULT_SCORE, fmtDate, PATHOLOGIES, QUALITY } from "../labels";
import { usePatient } from "./PatientPage";
import { AnnotationEditor, AnnotationLayer, ComparisonQualification } from "./RadioDoctorTools";

/*
 * Radiographies (F-C1 à F-C4) : liste chronologique, visionneuse comparative (côte à côte ou superposition,
 * zoom et déplacement synchronisés), zone d'attention du modèle (Grad-CAM), scores ± incertitude et leur
 * variation entre les deux clichés. La lecture et la conclusion appartiennent au médecin.
 */

function useBlob(path: string | null) {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    if (!path) return setUrl(null);
    let alive = true;
    let made: string | null = null;
    fetchBlobUrl(path).then((u) => { made = u; if (alive) setUrl(u); else URL.revokeObjectURL(u); }).catch(() => alive && setUrl(null));
    return () => { alive = false; if (made) URL.revokeObjectURL(made); };
  }, [path]);
  return url;
}

function Thumb({ item, slot, index, onPick }: { item: ImagingItem; slot: "L" | "R" | null; index: number; onPick: (shift: boolean) => void }) {
  const url = useBlob(`/documents/${item.document_id}/pages/0?width=300`);
  const ring = slot === "L" ? "border-[#7FC8C2]" : slot === "R" ? "border-[#E8B84A]" : "border-transparent";
  return (
    <button type="button" onClick={(e) => onPick(e.shiftKey)} aria-pressed={!!slot}
      aria-label={`Radiographie R${index + 1} du ${fmtDate(item.date)}${slot ? `, affichée à ${slot === "L" ? "gauche" : "droite"}` : ""}`}
      className={`w-[118px] flex-none rounded-lg border-2 ${ring} bg-lightbox p-1 text-left text-[#E6ECEE]`}>
      <div className="aspect-square overflow-hidden rounded-sm bg-black">
        {url && <img src={url} alt="" className="h-full w-full object-cover" />}
      </div>
      <div className="flex justify-between px-0.5 pt-1 text-xs">
        <b>R{index + 1}</b>
        <span>{fmtDate(item.date)}</span>
      </div>
      {item.view === "profil" && <div className="px-0.5 text-[11px] text-[#E8B84A]">Profil</div>}
    </button>
  );
}

type View = { zoom: number; x: number; y: number };

function Pane({ item, other, mode, opacity, view, cam, tag, slot }: {
  item: ImagingItem; other?: ImagingItem; mode: "side" | "overlay"; opacity: number; view: View; cam: string | null; tag: string; slot: "L" | "R";
}) {
  const base = useBlob(`/documents/${item.document_id}/pages/0?width=1400`);
  const top = useBlob(mode === "overlay" && other ? `/documents/${other.document_id}/pages/0?width=1400` : null);
  const camBase = useBlob(cam ? `/documents/${item.document_id}/gradcam?pathology=${encodeURIComponent(cam)}` : null);
  const camTop = useBlob(cam && mode === "overlay" && other ? `/documents/${other.document_id}/gradcam?pathology=${encodeURIComponent(cam)}` : null);
  const style = { transform: `translate(${view.x}px, ${view.y}px) scale(${view.zoom})`, transformOrigin: "0 0" };
  return (
    <div className="relative h-[min(520px,70vw)] overflow-hidden rounded-sm bg-black">
      <div className="absolute inset-0" style={style}>
        {base && <img src={base} alt={`Radiographie du ${fmtDate(item.date)}`} className="absolute inset-0 h-full w-full object-contain" draggable={false} />}
        {camBase && <img src={camBase} alt="" className="absolute inset-0 h-full w-full object-contain" draggable={false} />}
        {top && <img src={top} alt="" className="absolute inset-0 h-full w-full object-contain" style={{ opacity }} draggable={false} />}
        {camTop && <img src={camTop} alt="" className="absolute inset-0 h-full w-full object-contain" style={{ opacity }} draggable={false} />}
      </div>
      {mode === "side" && item.annotations.length > 0 && <FittedNotes item={item} view={view} />}
      <span className="absolute top-2 left-2 rounded bg-black/60 px-2 py-0.5 text-[13px] text-[#E6ECEE]"
        style={{ boxShadow: `inset 3px 0 0 ${slot === "L" ? "#7FC8C2" : "#E8B84A"}` }}>{tag}</span>
    </div>
  );
}

/** Annotations du médecin posées sur l'image affichée en « object-contain » (boîte calculée à partir des proportions). */
function FittedNotes({ item, view }: { item: ImagingItem; view: View }) {
  const ref = useRef<HTMLDivElement>(null);
  const [box, setBox] = useState<{ l: number; t: number; w: number; h: number } | null>(null);
  const src = useBlob(`/documents/${item.document_id}/pages/0?width=300`);
  useEffect(() => {
    if (!src || !ref.current) return;
    const img = new Image();
    img.onload = () => {
      const pane = ref.current!.getBoundingClientRect();
      const k = Math.min(pane.width / img.width, pane.height / img.height);
      const w = img.width * k, h = img.height * k;
      setBox({ l: (pane.width - w) / 2, t: (pane.height - h) / 2, w, h });
    };
    img.src = src;
  }, [src]);
  return (
    <div ref={ref} className="pointer-events-none absolute inset-0" style={{ transform: `translate(${view.x}px, ${view.y}px) scale(${view.zoom})`, transformOrigin: "0 0" }}>
      {box && <div className="absolute" style={{ left: box.l, top: box.t, width: box.w, height: box.h }}><AnnotationLayer notes={item.annotations} /></div>}
    </div>
  );
}

function fmt(v: number | undefined) {
  return v == null ? "–" : v.toLocaleString("fr-FR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function Assessment({ item, patientId }: { item: ImagingItem; patientId: string }) {
  const qc = useQueryClient();
  const [text, setText] = useState(item.doctor_assessment ?? "");
  const save = useMutation({
    mutationFn: (body: { view?: string; doctor_assessment?: string }) => patch(`/documents/${item.document_id}/imaging`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["imaging", patientId] }),
  });
  return (
    <div className="panel p-4">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h4 className="font-bold">Radiographie du {fmtDate(item.date)}</h4>
        <label className="flex items-center gap-2 text-sm">
          Vue
          <select className="field w-auto py-1" value={item.view ?? "face"} onChange={(e) => save.mutate({ view: e.target.value })}>
            <option value="face">Face</option>
            <option value="profil">Profil (exclue des comparaisons)</option>
          </select>
        </label>
      </div>
      {item.quality_flags.map((f) => <p key={f} className="text-[13px] text-warn">{QUALITY[f] ?? f}</p>)}
      <label htmlFor={`assess-${item.document_id}`} className="label mt-2">Lecture du médecin</label>
      <textarea id={`assess-${item.document_id}`} className="field min-h-16" value={text} onChange={(e) => setText(e.target.value)}
        placeholder="Votre interprétation (facultatif)" />
      <button type="button" className="btn mt-2" disabled={save.isPending || text === (item.doctor_assessment ?? "")}
        onClick={() => save.mutate({ doctor_assessment: text })}>Enregistrer la lecture</button>
      <details className="mt-3">
        <summary className="cursor-pointer text-sm font-semibold text-teal-ink">Annoter la radiographie ({item.annotations.length})</summary>
        <AnnotationEditor key={JSON.stringify(item.annotations)} item={item} patientId={patientId} />
      </details>
    </div>
  );
}

export function ImagingTab() {
  const { patientId = "" } = useParams();
  const { data: patient } = usePatient(patientId);
  const { data } = useQuery({ queryKey: ["imaging", patientId], queryFn: () => api<ImagingList>(`/patients/${patientId}/imaging`) });
  const items = useMemo(() => (data?.items ?? []).filter((i) => i.analyzed), [data]);
  const faces = items.filter((i) => i.view !== "profil");
  const [pick, setPick] = useState<{ L: string | null; R: string | null }>({ L: null, R: null });
  const [mode, setMode] = useState<"side" | "overlay">("side");
  const [opacity, setOpacity] = useState(0.5);
  const [view, setView] = useState<View>({ zoom: 1, x: 0, y: 0 });
  const defaultCam = DEFAULT_SCORE[patient?.conditions?.[0] ?? ""] ?? "Consolidation";
  const [camOn, setCamOn] = useState(false);
  const [camPath, setCamPath] = useState<string | null>(null);
  const drag = useRef<{ x: number; y: number } | null>(null);

  const L = items.find((i) => i.document_id === pick.L) ?? faces[faces.length - 2] ?? faces[0];
  const R = items.find((i) => i.document_id === pick.R) ?? faces[faces.length - 1];
  const [left, right] = L && R && (L.date ?? "") > (R.date ?? "") ? [R, L] : [L, R];
  const cam = camOn ? camPath ?? defaultCam : null;

  function onWheel(e: WheelEvent<HTMLDivElement>) {
    const rect = (e.target as HTMLElement).closest("[data-pane]")?.getBoundingClientRect();
    if (!rect) return;
    const z = Math.min(Math.max(view.zoom * (e.deltaY < 0 ? 1.12 : 1 / 1.12), 1), 6);
    const mx = e.clientX - rect.left, my = e.clientY - rect.top;
    setView(z === 1 ? { zoom: 1, x: 0, y: 0 } : { zoom: z, x: mx - ((mx - view.x) * z) / view.zoom, y: my - ((my - view.y) * z) / view.zoom });
  }
  function onDown(e: PointerEvent<HTMLDivElement>) {
    drag.current = { x: e.clientX - view.x, y: e.clientY - view.y };
    e.currentTarget.setPointerCapture(e.pointerId);
  }
  function onMoveDrag(e: PointerEvent<HTMLDivElement>) {
    if (drag.current && view.zoom > 1) setView({ ...view, x: e.clientX - drag.current.x, y: e.clientY - drag.current.y });
  }

  if (!data) return <p className="text-ink-2">Chargement des radiographies…</p>;
  if (items.length === 0)
    return <p className="panel p-6 text-ink-2">Aucune radiographie analysée. Déposez les clichés du patient depuis l'onglet Documents.</p>;

  const paths = data.pathologies;
  return (
    <>
      <p className="mb-2 text-sm text-ink-3">Cliquez une vignette pour l'afficher à gauche, Maj + clic pour l'afficher à droite.</p>
      <div className="mb-3.5 flex gap-2.5 overflow-x-auto pb-1">
        {items.map((it, i) => (
          <Thumb key={it.document_id} item={it} index={i} slot={it === left ? "L" : it === right ? "R" : null}
            onPick={(shift) => setPick(shift ? { L: left?.document_id ?? null, R: it.document_id } : { L: it.document_id, R: right?.document_id ?? null })} />
        ))}
      </div>

      {left && right && (
        <div className="rounded-lg bg-lightbox p-3 text-[#E6ECEE]">
          <div className="mb-2.5 flex flex-wrap items-center gap-2.5">
            <div className="inline-flex overflow-hidden rounded-lg border border-[#3A444A] bg-[#1F2529]" role="group" aria-label="Mode de comparaison">
              {(["side", "overlay"] as const).map((m, i) => (
                <button key={m} type="button" aria-pressed={mode === m} onClick={() => setMode(m)}
                  className={`px-3 py-1.5 ${i ? "border-l border-[#3A444A]" : ""} ${mode === m ? "bg-[#2E7F7A] text-white" : "text-[#C9D3D6]"}`}>
                  {m === "side" ? "Côte à côte" : "Superposition"}
                </button>
              ))}
            </div>
            {mode === "overlay" && (
              <label className="flex items-center gap-2 text-[13.5px]">
                Opacité de la plus récente
                <input type="range" min={0} max={100} value={Math.round(opacity * 100)} onChange={(e) => setOpacity(Number(e.target.value) / 100)} />
              </label>
            )}
            <button type="button" className="rounded border border-[#3A444A] bg-[#1F2529] px-3 py-1.5" onClick={() => setView({ ...view, zoom: Math.min(view.zoom * 1.25, 6) })}>Zoom +</button>
            <button type="button" className="rounded border border-[#3A444A] bg-[#1F2529] px-3 py-1.5"
              onClick={() => setView(view.zoom / 1.25 <= 1 ? { zoom: 1, x: 0, y: 0 } : { ...view, zoom: view.zoom / 1.25 })}>Zoom −</button>
            <button type="button" className="rounded border border-[#3A444A] bg-[#1F2529] px-3 py-1.5" onClick={() => setView({ zoom: 1, x: 0, y: 0 })}>Recentrer</button>
            <label className="flex items-center gap-1.5 text-[13.5px]">
              <input type="checkbox" checked={camOn} onChange={(e) => setCamOn(e.target.checked)} /> Zone d'attention du modèle
            </label>
            <select aria-label="Pathologie de la carte" className="rounded border border-[#3A444A] bg-[#1F2529] px-1.5 py-1"
              value={camPath ?? defaultCam} onChange={(e) => { setCamPath(e.target.value); setCamOn(true); }}>
              {paths.map((p) => <option key={p} value={p}>{PATHOLOGIES[p] ?? p}</option>)}
            </select>
          </div>
          <div className={`grid gap-2.5 ${mode === "side" ? "md:grid-cols-2" : ""} cursor-grab touch-none`}
            onWheel={onWheel} onPointerDown={onDown} onPointerMove={onMoveDrag} onPointerUp={() => (drag.current = null)}>
            <div data-pane>
              <Pane item={left} other={right} mode={mode} opacity={opacity} view={view} cam={cam} slot="L"
                tag={mode === "overlay" ? `${fmtDate(left.date)} sous ${fmtDate(right.date)} (${Math.round(opacity * 100)} %)` : fmtDate(left.date)} />
            </div>
            {mode === "side" && <div data-pane><Pane item={right} mode="side" opacity={1} view={view} cam={cam} tag={fmtDate(right.date)} slot="R" /></div>}
          </div>
          <p className="mt-2 text-[12.5px] text-[#AEB9BD]">
            Zoom et déplacement synchronisés (molette et glisser). La zone colorée montre où le modèle a porté son attention pour la
            pathologie choisie : ce n'est pas une localisation de lésion.
          </p>
        </div>
      )}

      {left && right && (
        <div className="panel mt-4 overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-paper text-ink-2">
              <tr>
                <th className="px-3 py-2 font-semibold">Pathologie</th>
                <th className="px-3 py-2 text-right font-semibold">{fmtDate(left.date)}</th>
                <th className="px-3 py-2 text-right font-semibold">{fmtDate(right.date)}</th>
                <th className="px-3 py-2 text-right font-semibold">Variation</th>
                <th className="px-3 py-2 font-semibold">Lecture du modèle</th>
              </tr>
            </thead>
            <tbody>
              {paths.map((p) => {
                const a = left.scores?.[p], b = right.scores?.[p];
                const ua = left.uncertainty?.[p] ?? 0, ub = right.uncertainty?.[p] ?? 0;
                const d = a != null && b != null ? b - a : null;
                const margin = 2 * Math.hypot(ua, ub) + 0.02;
                const within = d == null || Math.abs(d) <= margin;
                return (
                  <tr key={p} className="border-t border-grid">
                    <td className="px-3 py-2">{PATHOLOGIES[p] ?? p}</td>
                    <td className="px-3 py-2 text-right">{fmt(a)} ± {fmt(ua)}</td>
                    <td className="px-3 py-2 text-right">
                      <span className="mr-1.5 inline-block h-2 rounded bg-teal align-middle" style={{ width: `${(b ?? 0) * 60}px` }} />
                      {fmt(b)} ± {fmt(ub)}
                    </td>
                    <td className={`px-3 py-2 text-right font-semibold ${within ? "text-ink-2" : d! > 0 ? "text-alert" : "text-ok"}`}>
                      {d == null ? "–" : `${d > 0 ? "+" : ""}${fmt(d)}`}
                    </td>
                    <td className="px-3 py-2 text-ink-2">{within ? "Variation dans la marge d'incertitude" : d! > 0 ? "Score en hausse" : "Score en baisse"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      <p className="mt-2.5 max-w-[80ch] text-[13px] text-ink-2">
        Probabilités estimées par un modèle de recherche ({right?.model_name}, {right?.model_version}), ± écart-type sur 7 variantes de
        l'image ; 0,50 correspond au seuil de fonctionnement du modèle. La variation est indicative : l'interprétation de l'évolution
        revient au médecin.
      </p>
      {left && right && left !== right && <ComparisonQualification key={left.document_id + right.document_id} patientId={patientId} a={left} b={right} />}
      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        {[left, right].filter(Boolean).map((it) => <Assessment key={it!.document_id + (it!.doctor_assessment ?? "")} item={it!} patientId={patientId} />)}
      </div>
    </>
  );
}

function Mini({ item, label }: { item: ImagingItem; label: string }) {
  const url = useBlob(`/documents/${item.document_id}/pages/0?width=300`);
  return (
    <figure className="w-[104px] flex-none">
      <div className="aspect-square overflow-hidden rounded bg-black">
        {url && <img src={url} alt={`Radiographie ${label} du ${fmtDate(item.date)}`} className="h-full w-full object-cover" />}
      </div>
      <figcaption className="mt-0.5 text-xs text-ink-2"><b>{label}</b> {fmtDate(item.date)}</figcaption>
    </figure>
  );
}

/** Tableau de bord : les deux dernières radiographies de face et la variation du score suivi (T28, T29). */
export function RadiosSummary({ patientId }: { patientId: string }) {
  const { data: patient } = usePatient(patientId);
  const { data } = useQuery({ queryKey: ["imaging", patientId], queryFn: () => api<ImagingList>(`/patients/${patientId}/imaging`) });
  const faces = (data?.items ?? []).filter((i) => i.analyzed && i.view !== "profil");
  const paths = [...new Set((patient?.conditions ?? []).map((c) => DEFAULT_SCORE[c]).filter(Boolean))];
  if (!paths.length) paths.push("Consolidation");
  const [a, b] = faces.slice(-2);
  return (
    <section className="panel p-4" aria-label="Radiographies comparées">
      <div className="mb-2 flex items-baseline justify-between gap-3">
        <h2 className="text-[15px] font-bold">Radiographies comparées</h2>
        <Link to={`/patients/${patientId}/radiographies`} className="text-[13px] text-teal-ink underline">Ouvrir la visionneuse</Link>
      </div>
      {faces.length < 2 ? (
        <p className="text-sm text-ink-2">{faces.length ? "Une seule radiographie de face analysée." : "Aucune radiographie analysée."}</p>
      ) : (
        <div className="flex flex-wrap gap-4">
          <div className="flex gap-2">
            <Mini item={a} label={`R${faces.length - 1}`} />
            <Mini item={b} label={`R${faces.length}`} />
          </div>
          <ul className="min-w-[200px] flex-1 space-y-1.5 text-sm">
            {paths.map((p) => {
              const sa = a.scores?.[p], sb = b.scores?.[p];
              const ua = a.uncertainty?.[p] ?? 0, ub = b.uncertainty?.[p] ?? 0;
              if (sa == null || sb == null) return null;
              const d = sb - sa;
              const within = Math.abs(d) <= 2 * Math.hypot(ua, ub) + 0.02;
              return (
                <li key={p}>
                  Score {PATHOLOGIES[p] ?? p} : {fmt(sa)} ± {fmt(ua)} puis <b>{fmt(sb)}</b> ± {fmt(ub)}
                  <div className="text-[13px] text-ink-2">
                    {within ? "Variation dans la marge d'incertitude" : `Variation ${d > 0 ? "+" : ""}${fmt(d)}, au-delà de la marge`}
                  </div>
                </li>
              );
            })}
            <li className="text-[12.5px] text-ink-3">Scores indicatifs d'un modèle de recherche, non diagnostiques.</li>
          </ul>
        </div>
      )}
    </section>
  );
}
