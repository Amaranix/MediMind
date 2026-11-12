import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Link, NavLink, Outlet, useNavigate, useParams } from "react-router-dom";
import { api, post, type AlertItem, type MedDocument, type Patient, type Referential } from "../api/client";
import { fmtDate } from "../labels";

export function useReferential() {
  return useQuery({ queryKey: ["referential"], queryFn: () => api<Referential>("/referential"), staleTime: Infinity });
}

export function usePatient(id: string) {
  return useQuery({ queryKey: ["patient", id], queryFn: () => api<Patient>(`/patients/${id}`) });
}

export function usePending(id: string) {
  return useQuery({
    queryKey: ["pending", id],
    queryFn: () => api<{ measurements: number; documents: number }>(`/patients/${id}/pending-count`),
  });
}

const DEPENDENT = ["imaging", "facts", "series", "trends", "timeline", "alerts", "pending", "periods"];
const reading = (d: MedDocument) => d.status === "uploaded" || d.status === "processing";

/**
 * Suit la lecture des documents déposés (toutes les 2 s tant qu'il y en a) et, dès qu'un document est lu,
 * rafraîchit ce qui en dépend : sans cela, une radiographie ou des valeurs nouvelles n'apparaissaient qu'au
 * rechargement de la page (données gardées 15 s en cache, puis plus de nouvelle demande).
 */
function useReadingWatcher(patientId: string) {
  const qc = useQueryClient();
  const { data } = useQuery({
    queryKey: ["documents", patientId],
    queryFn: () => api<MedDocument[]>(`/patients/${patientId}/documents`),
    refetchInterval: (q) => (q.state.data?.some(reading) ? 2000 : false),
  });
  const busy = data?.filter(reading).length ?? 0;
  const previous = useRef(busy);
  useEffect(() => {
    if (busy < previous.current) DEPENDENT.forEach((k) => qc.invalidateQueries({ queryKey: [k, patientId] }));
    previous.current = busy;
  }, [busy, patientId, qc]);
}

/** Alertes actuelles non acquittées : règle, source, valeurs déclenchantes (F-B5). */
function AlertsPanel({ patientId }: { patientId: string }) {
  const qc = useQueryClient();
  const [showHistory, setShowHistory] = useState(false);
  const { data: open } = useQuery({
    queryKey: ["alerts", patientId, "open"],
    queryFn: () => api<AlertItem[]>(`/patients/${patientId}/alerts?scope=open`),
  });
  const { data: all } = useQuery({
    queryKey: ["alerts", patientId, "all"],
    queryFn: () => api<AlertItem[]>(`/patients/${patientId}/alerts?scope=all`),
    enabled: showHistory,
  });
  const ack = useMutation({
    mutationFn: (id: string) => post(`/alerts/${id}/acknowledge`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["alerts", patientId] }),
  });
  return (
    <section aria-label="Alertes" className="mt-5">
      <h2 className="mb-2 text-[15px] font-bold">Alertes ouvertes</h2>
      {open && open.length === 0 && <p className="text-sm text-ink-2">Aucune alerte ouverte.</p>}
      {open?.map((a) => (
        <div key={a.id}
          className={`mb-2 rounded-r border-l-[3px] px-2.5 py-2 text-sm ${a.severity === "warning" ? "border-alert bg-alert-soft" : "border-info bg-info-soft"}`}>
          <div className="font-semibold">{a.label}</div>
          <div className="mt-0.5">{a.message}</div>
          {a.note && <div className="mt-0.5 text-[12.5px] text-ink-2">{a.note}</div>}
          <div className="mt-0.5 text-[12px] text-ink-2">Règle {a.rule_id}. Source : {a.source}</div>
          <div className="mt-1 flex flex-wrap gap-x-3 text-[12.5px]">
            {a.values.filter((v) => v.document_id).slice(-2).map((v) => (
              <Link key={v.date + v.value} className="text-teal-ink underline" to={`/patients/${patientId}/documents/${v.document_id}`}>
                Source du {fmtDate(v.date)}
              </Link>
            ))}
          </div>
          <button type="button" className="mt-1.5 rounded border border-current px-2 py-0.5 text-[13px] text-ink-2"
            onClick={() => ack.mutate(a.id)} disabled={ack.isPending}>Acquitter</button>
        </div>
      ))}
      <button type="button" className="text-[13px] text-teal-ink underline" onClick={() => setShowHistory(!showHistory)}>
        {showHistory ? "Masquer l'historique" : "Voir l'historique des alertes"}
      </button>
      {showHistory && (
        <ul className="mt-2 space-y-1 text-[12.5px] text-ink-2">
          {all?.filter((a) => !a.current || a.state === "acknowledged").map((a) => (
            <li key={a.id}>{fmtDate(a.date)} : {a.label}{a.state === "acknowledged" ? " (acquittée)" : ""}</li>
          ))}
        </ul>
      )}
    </section>
  );
}

/** Suppression définitive du dossier : le médecin retape le nom du patient pour confirmer. */
function DeletePatient({ p }: { p: Patient }) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [typed, setTyped] = useState("");
  const del = useMutation({
    mutationFn: () => api(`/patients/${p.id}`, { method: "DELETE" }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["patients"] }); navigate("/patients"); },
  });
  if (!open)
    return <button type="button" className="mt-6 text-[13px] text-alert underline" onClick={() => setOpen(true)}>Supprimer le dossier</button>;
  return (
    <div className="mt-6 rounded border border-alert bg-alert-soft p-3 text-sm">
      <p className="mb-2">Suppression définitive : documents, mesures, radiographies, fiches et conversations de ce patient.
        Tapez <b>{p.last_name.toUpperCase()}</b> pour confirmer.</p>
      <label htmlFor="confirm-delete" className="sr-only">Nom du patient</label>
      <input id="confirm-delete" className="field" value={typed} onChange={(e) => setTyped(e.target.value)} autoComplete="off" />
      <div className="mt-2 flex gap-2">
        <button type="button" className="btn border-alert text-alert" disabled={typed.trim().toUpperCase() !== p.last_name.toUpperCase() || del.isPending}
          onClick={() => del.mutate()}>Supprimer définitivement</button>
        <button type="button" className="btn" onClick={() => { setOpen(false); setTyped(""); }}>Annuler</button>
      </div>
      {del.error && <p role="alert" className="mt-1 text-alert">{del.error.message}</p>}
    </div>
  );
}

function PatientRail({ p }: { p: Patient }) {
  const { data: ref } = useReferential();
  const rows: [string, string][] = [
    ["Suivi", p.conditions.map((c) => ref?.conditions[c] ?? c).join(", ") || "Non précisé"],
    ["Naissance", fmtDate(p.birth_date)],
    ["Taille", p.height_cm ? `${p.height_cm} cm` : "Non renseignée"],
    ["Tabac", p.pack_years != null ? `${p.pack_years} paquets-années` : "Non renseigné"],
    ["Allergies", p.allergies || "Aucune connue"],
  ];
  return (
    <aside className="border-b border-grid bg-surface p-5 lg:border-r lg:border-b-0" aria-label="Résumé du patient">
      <h1 className="text-[22px] leading-tight font-bold">{p.last_name.toUpperCase()} {p.first_name}</h1>
      <p className="mb-4 text-ink-2">{p.age} ans, {p.sex === "M" ? "homme" : "femme"}</p>
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
        {rows.map(([k, v]) => (
          <div key={k} className="contents">
            <dt className="text-ink-3">{k}</dt>
            <dd>{v}</dd>
          </div>
        ))}
      </dl>
      <AlertsPanel patientId={p.id} />
      <DeletePatient p={p} />
    </aside>
  );
}

const tab = ({ isActive }: { isActive: boolean }) =>
  `-mb-px whitespace-nowrap border-b-2 px-3.5 py-3 ${isActive ? "border-teal font-semibold text-ink" : "border-transparent text-ink-2 hover:text-ink"}`;

export function PatientPage() {
  const { patientId = "" } = useParams();
  const { data: p, error } = usePatient(patientId);
  const { data: pending } = usePending(patientId);
  useReadingWatcher(patientId);
  if (error) return <p role="alert" className="mt-6 text-alert">{error.message}</p>;
  if (!p) return <p className="mt-6 text-ink-2">Chargement du dossier…</p>;
  return (
    <div className="-mx-4 grid min-h-[calc(100vh-92px)] sm:-mx-6 lg:grid-cols-[272px_minmax(0,1fr)]">
      <PatientRail p={p} />
      <div className="min-w-0 px-4 pb-10 sm:px-6">
        <nav className="sticky top-8 z-20 -mx-4 mb-5 flex gap-1 overflow-x-auto border-b border-grid bg-surface px-4 sm:-mx-6 sm:px-6"
          aria-label="Sections du dossier">
          <NavLink end to={`/patients/${patientId}`} className={tab}>Évolution</NavLink>
          <NavLink to={`/patients/${patientId}/radiographies`} className={tab}>Radiographies</NavLink>
          <NavLink to={`/patients/${patientId}/documents`} className={tab}>Documents</NavLink>
          <NavLink to={`/patients/${patientId}/a-valider`} className={tab}>
            À valider
            {!!pending?.measurements && (
              <span className="ml-1.5 rounded-full bg-warn-soft px-1.5 text-[12.5px] font-bold text-warn">{pending.measurements}</span>
            )}
          </NavLink>
          <NavLink to={`/patients/${patientId}/fiche`} className={tab}>Fiche</NavLink>
          <NavLink to={`/patients/${patientId}/assistant`} className={tab}>Assistant</NavLink>
        </nav>
        <Outlet />
      </div>
    </div>
  );
}
