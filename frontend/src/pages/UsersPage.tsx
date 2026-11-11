import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { api, ApiError, patch, post, type Health, type User } from "../api/client";

function HealthPanel() {
  const { data } = useQuery({ queryKey: ["health"], queryFn: () => api<Health>("/health"), refetchInterval: 30_000 });
  if (!data) return null;
  const rows: [string, string][] = [
    ["Base de données", data.database],
    [`LLM local (${data.ollama_model})`, data.ollama],
    ["Modèle d'imagerie", data.imaging_model],
    ["Référentiel clinique", `version ${data.referential_version}`],
  ];
  return (
    <section className="panel mb-6 p-5" aria-label="État du service">
      <h2 className="mb-3 text-lg font-bold">État du service</h2>
      <dl className="grid gap-x-6 gap-y-2 sm:grid-cols-[auto_1fr]">
        {rows.map(([k, v]) => (
          <div key={k} className="contents">
            <dt className="text-ink-2">{k}</dt>
            <dd className={v === "ok" || v.startsWith("version") ? "text-ok" : "text-warn"}>{v === "ok" ? "Opérationnel" : v}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

export function UsersPage() {
  const qc = useQueryClient();
  const { data: users } = useQuery({ queryKey: ["users"], queryFn: () => api<User[]>("/users") });
  const [form, setForm] = useState({ name: "", email: "", password: "" });
  const [error, setError] = useState<string | null>(null);

  const create = useMutation({
    mutationFn: () => post<User>("/users", { ...form, role: "doctor" }),
    onSuccess: () => {
      setForm({ name: "", email: "", password: "" });
      qc.invalidateQueries({ queryKey: ["users"] });
    },
    onError: (err) =>
      setError(err instanceof ApiError && err.errors.length ? err.errors.map((e) => e.message).join(" ") : (err as Error).message),
  });
  const toggle = useMutation({
    mutationFn: (u: User) => patch<User>(`/users/${u.id}`, { is_active: !u.is_active }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["users"] }),
  });

  function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    create.mutate();
  }

  return (
    <div className="mx-auto max-w-6xl pb-10">
      <h1 className="mt-6 mb-4 text-[26px] font-bold">Comptes et service</h1>
      <HealthPanel />
      <form onSubmit={submit} className="panel mb-6 p-5" aria-label="Nouveau compte médecin">
        <h2 className="mb-4 text-lg font-bold">Créer un compte médecin</h2>
        {error && <p role="alert" className="mb-3 text-sm text-alert">{error}</p>}
        <div className="grid gap-4 sm:grid-cols-3">
          <div>
            <label htmlFor="u-name" className="label">Nom affiché</label>
            <input id="u-name" className="field" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </div>
          <div>
            <label htmlFor="u-email" className="label">Adresse e-mail</label>
            <input id="u-email" type="email" className="field" value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })} />
          </div>
          <div>
            <label htmlFor="u-pw" className="label">Mot de passe initial (10 caractères minimum)</label>
            <input id="u-pw" type="password" className="field" autoComplete="new-password" value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })} />
          </div>
        </div>
        <button type="submit" className="btn btn-primary mt-4" disabled={create.isPending}>Créer le compte</button>
        <p className="mt-3 text-sm text-ink-3">L'administrateur gère les comptes mais n'a aucun accès aux dossiers des patients.</p>
      </form>
      <div className="panel overflow-x-auto">
        <table className="w-full text-left">
          <thead className="bg-paper text-sm text-ink-2">
            <tr>
              <th className="px-4 py-3 font-semibold">Nom</th>
              <th className="px-4 py-3 font-semibold">E-mail</th>
              <th className="px-4 py-3 font-semibold">Rôle</th>
              <th className="px-4 py-3 font-semibold">Statut</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody>
            {users?.map((u) => (
              <tr key={u.id} className="border-t border-grid">
                <td className="px-4 py-3 font-semibold">{u.name}</td>
                <td className="px-4 py-3">{u.email}</td>
                <td className="px-4 py-3">{u.role === "admin" ? "Administrateur" : "Médecin"}</td>
                <td className={`px-4 py-3 ${u.is_active ? "text-ok" : "text-ink-3"}`}>{u.is_active ? "Actif" : "Désactivé"}</td>
                <td className="px-4 py-3 text-right">
                  {u.role === "doctor" && (
                    <button type="button" className="btn" onClick={() => toggle.mutate(u)}>
                      {u.is_active ? "Désactiver" : "Réactiver"}
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
