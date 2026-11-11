import { useQuery } from "@tanstack/react-query";
import { NavLink, Outlet, useParams } from "react-router-dom";
import { api, type Patient, type Referential } from "../api/client";
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

function PatientRail({ p }: { p: Patient }) {
  const rows: [string, string][] = [
    ["Naissance", fmtDate(p.birth_date)],
    ["Taille", p.height_cm ? `${p.height_cm} cm` : "Non renseignée"],
    ["Tabac", p.pack_years != null ? `${p.pack_years} paquets-années` : "Non renseigné"],
    ["Allergies", p.allergies || "Aucune connue"],
    ["Traitement de fond", p.base_treatments || "Non renseigné"],
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
      {p.antecedents && (
        <>
          <h2 className="mt-5 mb-1 text-[15px] font-bold">Antécédents</h2>
          <p className="text-sm whitespace-pre-line">{p.antecedents}</p>
        </>
      )}
    </aside>
  );
}

const tab = ({ isActive }: { isActive: boolean }) =>
  `-mb-px whitespace-nowrap border-b-2 px-3.5 py-3 ${isActive ? "border-teal font-semibold text-ink" : "border-transparent text-ink-2 hover:text-ink"}`;

export function PatientPage() {
  const { patientId = "" } = useParams();
  const { data: p, error } = usePatient(patientId);
  const { data: pending } = usePending(patientId);
  if (error) return <p role="alert" className="mt-6 text-alert">{error.message}</p>;
  if (!p) return <p className="mt-6 text-ink-2">Chargement du dossier…</p>;
  return (
    <div className="-mx-4 grid min-h-[calc(100vh-92px)] sm:-mx-6 lg:grid-cols-[272px_minmax(0,1fr)]">
      <PatientRail p={p} />
      <div className="min-w-0 px-4 pb-10 sm:px-6">
        <nav className="sticky top-8 z-20 -mx-4 mb-5 flex gap-1 overflow-x-auto border-b border-grid bg-surface px-4 sm:-mx-6 sm:px-6"
          aria-label="Sections du dossier">
          <NavLink end to={`/patients/${patientId}`} className={tab}>Documents</NavLink>
          <NavLink to={`/patients/${patientId}/a-valider`} className={tab}>
            À valider
            {!!pending?.measurements && (
              <span className="ml-1.5 rounded-full bg-warn-soft px-1.5 text-[12.5px] font-bold text-warn">{pending.measurements}</span>
            )}
          </NavLink>
        </nav>
        <Outlet />
      </div>
    </div>
  );
}
