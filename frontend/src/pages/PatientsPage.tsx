import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { api, ApiError, post, type Patient } from "../api/client";

const EMPTY = {
  first_name: "",
  last_name: "",
  birth_date: "",
  sex: "M",
  height_cm: "",
  pack_years: "",
  antecedents: "",
  allergies: "",
  base_treatments: "",
};

function fmtDate(iso: string) {
  return new Date(iso + "T00:00:00").toLocaleDateString("fr-FR");
}

function PatientForm({ onDone }: { onDone: () => void }) {
  const qc = useQueryClient();
  const [form, setForm] = useState(EMPTY);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const set = (k: keyof typeof EMPTY) => (e: { target: { value: string } }) => setForm({ ...form, [k]: e.target.value });

  const create = useMutation({
    mutationFn: () =>
      post<Patient>("/patients", {
        ...form,
        height_cm: form.height_cm ? Number(form.height_cm) : null,
        pack_years: form.pack_years ? Number(form.pack_years.replace(",", ".")) : null,
        antecedents: form.antecedents || null,
        allergies: form.allergies || null,
        base_treatments: form.base_treatments || null,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["patients"] });
      onDone();
    },
    onError: (err) => {
      if (err instanceof ApiError && err.errors.length) {
        setErrors(Object.fromEntries(err.errors.map((e) => [e.field, e.message])));
      } else setErrors({ _: err instanceof Error ? err.message : "Erreur inconnue" });
    },
  });

  function submit(e: FormEvent) {
    e.preventDefault();
    setErrors({});
    create.mutate();
  }

  const field = (k: keyof typeof EMPTY, label: string, props: Record<string, unknown> = {}) => (
    <div>
      <label htmlFor={k} className="label">{label}</label>
      <input id={k} className="field" value={form[k]} onChange={set(k)} aria-invalid={!!errors[k]}
        aria-describedby={errors[k] ? `${k}-err` : undefined} {...props} />
      {errors[k] && <p id={`${k}-err`} className="mt-1 text-sm text-alert">{errors[k]}</p>}
    </div>
  );

  return (
    <form onSubmit={submit} className="panel mb-6 p-5" aria-label="Nouveau patient">
      <h2 className="mb-4 text-lg font-bold">Nouveau patient</h2>
      {errors._ && <p role="alert" className="mb-3 text-sm text-alert">{errors._}</p>}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {field("last_name", "Nom", { required: true, autoComplete: "off" })}
        {field("first_name", "Prénom", { required: true, autoComplete: "off" })}
        {field("birth_date", "Date de naissance", { type: "date", required: true })}
        <div>
          <label htmlFor="sex" className="label">Sexe</label>
          <select id="sex" className="field" value={form.sex} onChange={set("sex")}>
            <option value="M">Homme</option>
            <option value="F">Femme</option>
          </select>
        </div>
        {field("height_cm", "Taille (cm)", { inputMode: "numeric" })}
        {field("pack_years", "Tabac (paquets-années)", { inputMode: "decimal" })}
        {field("allergies", "Allergies")}
        {field("base_treatments", "Traitements de fond")}
      </div>
      <div className="mt-4">
        <label htmlFor="antecedents" className="label">Antécédents</label>
        <textarea id="antecedents" className="field min-h-20" value={form.antecedents} onChange={set("antecedents")} />
      </div>
      <p className="mt-3 text-sm text-ink-3">Réservé aux patients adultes (18 ans ou plus).</p>
      <div className="mt-4 flex gap-2">
        <button type="submit" className="btn btn-primary" disabled={create.isPending}>
          {create.isPending ? "Enregistrement…" : "Créer le patient"}
        </button>
        <button type="button" className="btn" onClick={onDone}>Annuler</button>
      </div>
    </form>
  );
}

export function PatientsPage() {
  const [adding, setAdding] = useState(false);
  const navigate = useNavigate();
  const { data, isLoading, error } = useQuery({ queryKey: ["patients"], queryFn: () => api<Patient[]>("/patients") });

  return (
    <div className="mx-auto max-w-6xl pb-10">
      <div className="mt-6 mb-4 flex flex-wrap items-end justify-between gap-4">
        <h1 className="text-[26px] font-bold">Mes patients</h1>
        {!adding && (
          <button type="button" className="btn btn-primary" onClick={() => setAdding(true)}>
            Ajouter un patient
          </button>
        )}
      </div>
      {adding && <PatientForm onDone={() => setAdding(false)} />}
      {isLoading && <p className="text-ink-2">Chargement des patients…</p>}
      {error && <p role="alert" className="text-alert">Impossible de charger les patients : {error.message}</p>}
      {data && data.length === 0 && !adding && (
        <div className="panel p-8 text-center">
          <p className="mb-1 text-lg font-semibold">Aucun patient pour l'instant</p>
          <p className="mb-4 text-ink-2">Créez la fiche d'un patient pour déposer ses documents et suivre son évolution.</p>
          <button type="button" className="btn btn-primary" onClick={() => setAdding(true)}>Ajouter un patient</button>
        </div>
      )}
      {data && data.length > 0 && (
        <div className="panel overflow-x-auto">
          <table className="w-full text-left">
            <thead className="bg-paper text-sm text-ink-2">
              <tr>
                <th className="px-4 py-3 font-semibold">Patient</th>
                <th className="px-4 py-3 font-semibold">Naissance</th>
                <th className="px-4 py-3 font-semibold">Tabac</th>
                <th className="px-4 py-3 font-semibold">Traitements de fond</th>
              </tr>
            </thead>
            <tbody>
              {data.map((p) => (
                <tr key={p.id} className="cursor-pointer border-t border-grid hover:bg-teal-soft"
                  onClick={() => navigate(`/patients/${p.id}`)}>
                  <td className="px-4 py-3">
                    <a href={`/patients/${p.id}`} className="font-bold hover:underline"
                      onClick={(e) => { e.preventDefault(); navigate(`/patients/${p.id}`); }}>
                      {p.last_name.toUpperCase()} {p.first_name}
                    </a>
                    <div className="text-sm text-ink-3">{p.age} ans, {p.sex === "M" ? "homme" : "femme"}</div>
                  </td>
                  <td className="px-4 py-3">{fmtDate(p.birth_date)}</td>
                  <td className="px-4 py-3">{p.pack_years != null ? `${p.pack_years} PA` : "Non renseigné"}</td>
                  <td className="px-4 py-3 text-ink-2">{p.base_treatments || "Non renseigné"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
