import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { Link, useParams } from "react-router-dom";
import {
  api,
  ApiError,
  fetchPageUrl,
  patch,
  post,
  type Measurement,
  type MedDocument,
} from "../api/client";
import { DATE_SOURCE, DOC_STATUS, DOC_TYPES, FLAGS, fmtNum } from "../labels";
import { useReferential } from "./PatientPage";

const STATUS_LABEL: Record<string, { label: string; tone: string }> = {
  validated: { label: "Validée", tone: "text-ok" },
  corrected: { label: "Corrigée", tone: "text-info" },
  rejected: { label: "Rejetée", tone: "text-alert" },
};

function confTone(c: number | null) {
  if (c == null) return "bg-paper text-ink-2";
  if (c >= 0.95) return "bg-ok-soft text-ok";
  if (c >= 0.8) return "bg-paper text-ink-2";
  return "bg-warn-soft text-warn";
}

/** Aperçu d'une page avec les zones des valeurs extraites superposées (coordonnées normalisées). */
function PageView({ docId, page, ms, active, onPick }: {
  docId: string; page: number; ms: Measurement[]; active: string | null; onPick: (id: string) => void;
}) {
  const [url, setUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let revoked: string | null = null;
    fetchPageUrl(docId, page, 1100).then((u) => { revoked = u; setUrl(u); }).catch(() => setFailed(true));
    return () => { if (revoked) URL.revokeObjectURL(revoked); };
  }, [docId, page]);
  if (failed) return <p className="p-4 text-sm text-alert">Aperçu de la page {page + 1} indisponible.</p>;
  if (!url) return <div className="aspect-[1/1.414] animate-pulse bg-paper" aria-label="Chargement de la page" />;
  return (
    <div className="relative">
      <img src={url} alt={`Page ${page + 1} du document`} className="block w-full" />
      {ms.filter((m) => m.bbox?.page === page).map((m) => {
        const b = m.bbox!;
        const on = m.id === active;
        return (
          <button key={m.id} type="button" tabIndex={-1} aria-hidden="true" onClick={() => onPick(m.id)}
            className={`absolute rounded-sm ${on ? "z-10 bg-teal/15 outline-[2.5px] outline-teal outline-solid" : "bg-warn/10 hover:bg-teal/10"}`}
            style={{ left: `${b.x0 * 100 - 0.4}%`, top: `${b.y0 * 100 - 0.3}%`, width: `${(b.x1 - b.x0) * 100 + 0.8}%`,
              height: `${(b.y1 - b.y0) * 100 + 0.6}%` }} />
        );
      })}
    </div>
  );
}

function Row({ m, name, contexts, active, onFocus, onAct }: {
  m: Measurement; name: string; contexts: Record<string, string>; active: boolean;
  onFocus: () => void; onAct: (body: { action: string; value?: number; context?: string[] }) => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(String(m.value).replace(".", ","));
  const [ctx, setCtx] = useState<string[]>(m.context);
  const [error, setError] = useState<string | null>(null);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => { if (active) ref.current?.scrollIntoView({ block: "nearest" }); }, [active]);
  const decided = STATUS_LABEL[m.validation_status];
  const printedDiffers = m.printed_unit && (m.printed_unit !== m.unit || m.printed_value !== m.value);

  async function save() {
    const v = Number(value.replace(",", "."));
    if (!Number.isFinite(v)) return setError("Saisissez un nombre.");
    try {
      await onAct({ action: "correct", value: v, context: ctx });
      setEditing(false);
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Enregistrement impossible.");
    }
  }
  function keys(e: KeyboardEvent) {
    if (editing || e.target !== ref.current) return;
    if (e.key === "Enter") { e.preventDefault(); void onAct({ action: "validate" }); }
    if (e.key.toLowerCase() === "e") { e.preventDefault(); setEditing(true); }
    if (e.key.toLowerCase() === "r") { e.preventDefault(); void onAct({ action: "reject" }); }
  }

  return (
    <div ref={ref} tabIndex={0} data-mid={m.id} onFocus={onFocus} onMouseEnter={onFocus} onKeyDown={keys}
      className={`grid grid-cols-[1fr_auto] gap-x-3 gap-y-1 border-b border-grid px-4 py-3 outline-none ${active ? "bg-teal-soft/60" : ""}`}>
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-semibold">{name}</span>
          <span className={`rounded px-1.5 text-xs font-semibold ${confTone(m.confidence)}`}>
            confiance {m.confidence != null ? Math.round(m.confidence * 100) : "?"} %
          </span>
          {m.context.map((c) => <span key={c} className="rounded bg-info-soft px-1.5 text-xs text-info">{contexts[c] ?? c}</span>)}
        </div>
        <div className="text-lg font-bold">{fmtNum(m.value, m.unit)}</div>
        {printedDiffers && (
          <div className="text-[12.5px] text-ink-3">Lu sur le document : {fmtNum(m.printed_value!, m.printed_unit!)}</div>
        )}
        {m.flags.filter((f) => f !== "ocr").map((f) => (
          <div key={f} className={`text-[12.5px] ${f === "implausible" ? "font-semibold text-alert" : "text-warn"}`}>{FLAGS[f] ?? f}</div>
        ))}
        {m.source_text && <div className="mt-0.5 truncate text-[12.5px] text-ink-3" title={m.source_text}>« {m.source_text} »</div>}
        {editing && (
          <div className="mt-2 space-y-2">
            <div className="flex items-center gap-2">
              <label className="sr-only" htmlFor={`v-${m.id}`}>Valeur corrigée en {m.unit}</label>
              <input id={`v-${m.id}`} autoFocus className="field w-28" inputMode="decimal" value={value}
                onChange={(e) => setValue(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") void save(); if (e.key === "Escape") setEditing(false); }} />
              <span className="text-sm text-ink-2">{m.unit}</span>
            </div>
            <fieldset className="flex flex-wrap gap-3 text-sm">
              <legend className="sr-only">Contexte de la mesure</legend>
              {Object.entries(contexts).map(([k, label]) => (
                <label key={k} className="flex items-center gap-1">
                  <input type="checkbox" checked={ctx.includes(k)}
                    onChange={(e) => setCtx(e.target.checked ? [...ctx, k] : ctx.filter((x) => x !== k))} />
                  {label}
                </label>
              ))}
            </fieldset>
            {error && <p role="alert" className="text-sm text-alert">{error}</p>}
          </div>
        )}
      </div>
      <div className="flex flex-col items-end gap-1.5">
        {decided && !editing ? (
          <>
            <span className={`text-sm font-semibold ${decided.tone}`}>{decided.label}</span>
            <button type="button" className="btn px-2 py-0.5 text-[13px]" onClick={() => void onAct({ action: "reset" })}>Annuler</button>
          </>
        ) : editing ? (
          <>
            <button type="button" className="btn btn-primary px-2 py-0.5 text-[13px]" onClick={() => void save()}>Enregistrer</button>
            <button type="button" className="btn px-2 py-0.5 text-[13px]" onClick={() => setEditing(false)}>Annuler</button>
          </>
        ) : (
          <div className="flex gap-1.5">
            <button type="button" className="btn border-ok px-2 py-0.5 text-[13px] text-ok" onClick={() => void onAct({ action: "validate" })}>Valider</button>
            <button type="button" className="btn px-2 py-0.5 text-[13px]" onClick={() => setEditing(true)}>Corriger</button>
            <button type="button" className="btn px-2 py-0.5 text-[13px]" onClick={() => void onAct({ action: "reject" })}>Rejeter</button>
          </div>
        )}
      </div>
    </div>
  );
}

export function ValidationPage() {
  const { patientId = "", docId = "" } = useParams();
  const qc = useQueryClient();
  const { data: ref } = useReferential();
  const docQ = useQuery({
    queryKey: ["document", docId],
    queryFn: () => api<MedDocument>(`/documents/${docId}`),
    refetchInterval: (q) => (q.state.data && ["uploaded", "processing"].includes(q.state.data.status) ? 2000 : false),
  });
  const msQ = useQuery({ queryKey: ["measurements", docId], queryFn: () => api<Measurement[]>(`/documents/${docId}/measurements`) });
  const [active, setActive] = useState<string | null>(null);
  const names = useMemo(() => Object.fromEntries((ref?.parameters ?? []).map((p) => [p.code, p.name])), [ref]);
  const doc = docQ.data;
  const ms = msQ.data ?? [];

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["measurements", docId] });
    qc.invalidateQueries({ queryKey: ["document", docId] });
    qc.invalidateQueries({ queryKey: ["documents", patientId] });
    qc.invalidateQueries({ queryKey: ["pending", patientId] });
  };
  const updateDoc = useMutation({
    mutationFn: (body: { type?: string; exam_date?: string }) => patch<MedDocument>(`/documents/${docId}`, body),
    onSuccess: refresh,
  });
  const bulk = useMutation({ mutationFn: () => post<MedDocument>(`/documents/${docId}/validate-confident`), onSuccess: refresh });

  async function act(id: string, body: { action: string; value?: number; context?: string[] }) {
    await patch<Measurement>(`/measurements/${id}`, body);
    refresh();
    // passer à la prochaine valeur en attente
    const next = ms.find((m) => m.id !== id && (m.validation_status === "pending" || m.validation_status === "suspect"));
    if (next && body.action !== "reset") {
      setActive(next.id);
      setTimeout(() => (document.querySelector(`[data-mid="${next.id}"]`) as HTMLElement | null)?.focus(), 0);
    }
  }

  if (docQ.error) return <p role="alert" className="text-alert">{docQ.error.message}</p>;
  if (!doc) return <p className="text-ink-2">Chargement du document…</p>;
  const sure = ms.filter((m) => m.validation_status === "pending" && (m.confidence ?? 0) >= 0.95 && m.flags.length === 0).length;
  const open = ms.filter((m) => m.validation_status === "pending" || m.validation_status === "suspect").length;
  const st = DOC_STATUS[doc.status];

  return (
    <>
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <Link to={`/patients/${patientId}`} className="text-sm text-teal-ink underline">Retour aux documents</Link>
          <h2 className="mt-1 text-xl font-bold break-all">{doc.original_name}</h2>
          <p className="text-sm text-ink-2">
            <span className={`mr-2 rounded px-2 py-0.5 text-[13px] font-semibold ${st.tone}`}>{st.label}</span>
            {doc.processing_seconds != null && `Lu en ${doc.processing_seconds.toLocaleString("fr-FR")} s`}
            {doc.confidence != null && doc.confidence < 1 && `, qualité de lecture ${Math.round(doc.confidence * 100)} %`}
          </p>
        </div>
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label htmlFor="d-type" className="label">Type</label>
            <select id="d-type" className="field" value={doc.type} onChange={(e) => updateDoc.mutate({ type: e.target.value })}>
              {Object.entries(DOC_TYPES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </div>
          <div>
            <label htmlFor="d-date" className="label">Date d'examen</label>
            <input id="d-date" type="date" className="field" value={doc.exam_date ?? ""} max={new Date().toISOString().slice(0, 10)}
              onChange={(e) => e.target.value && updateDoc.mutate({ exam_date: e.target.value })} />
            <span className="mt-0.5 block text-xs text-ink-3">{doc.date_source ? DATE_SOURCE[doc.date_source] : ""}</span>
          </div>
        </div>
      </div>

      {!!doc.warnings?.length && (
        <ul className="mb-4 space-y-1 rounded border-l-[3px] border-warn bg-warn-soft px-4 py-2 text-sm">
          {doc.warnings.map((w) => <li key={w}>{w}</li>)}
        </ul>
      )}

      <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
        <div className="panel overflow-hidden" aria-label="Document source">
          {Array.from({ length: doc.page_count ?? 1 }, (_, i) => (
            <div key={i} className={i > 0 ? "border-t border-grid" : ""}>
              <PageView docId={docId} page={i} ms={ms} active={active} onPick={(id) => {
                setActive(id);
                (document.querySelector(`[data-mid="${id}"]`) as HTMLElement | null)?.focus();
              }} />
            </div>
          ))}
        </div>

        <section className="panel xl:sticky xl:top-24" aria-label="Valeurs extraites">
          <header className="flex flex-wrap items-center justify-between gap-2 border-b border-grid px-4 py-3">
            <h3 className="font-bold">Valeurs extraites {ms.length > 0 && <span className="font-normal text-ink-2">({open} à décider)</span>}</h3>
            {sure > 0 && (
              <button type="button" className="btn btn-primary" onClick={() => bulk.mutate()} disabled={bulk.isPending}>
                Valider les {sure} valeurs sûres
              </button>
            )}
          </header>
          {ms.length === 0 && (
            <p className="px-4 py-6 text-ink-2">
              {doc.type === "ordonnance" ? "Les traitements des ordonnances seront extraits à l'étape suivante du projet."
                : doc.type === "radiographie" ? "Les radiographies sont analysées dans l'onglet dédié (module imagerie)."
                : "Aucune valeur reconnue. Vérifiez le type du document ci-dessus."}
            </p>
          )}
          <div className="max-h-[calc(100vh-240px)] overflow-y-auto">
            {ms.map((m) => (
              <Row key={m.id + m.validation_status + m.value} m={m} name={names[m.parameter_code] ?? m.parameter_code}
                contexts={ref?.contexts ?? {}} active={m.id === active} onFocus={() => setActive(m.id)}
                onAct={(body) => act(m.id, body)} />
            ))}
          </div>
          <p className="border-t border-grid px-4 py-2.5 text-[13px] text-ink-3">
            Clavier : Entrée valide, E corrige, R rejette. Seules les valeurs validées ou corrigées alimentent les courbes et les alertes.
            Les valeurs lues sur un scan se valident une par une.
          </p>
        </section>
      </div>
    </>
  );
}
