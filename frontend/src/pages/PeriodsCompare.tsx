import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, type PeriodRow } from "../api/client";
import { fmtValue, TREND, unitLabel } from "../labels";

/** F-B8 : comparaison de deux périodes (mesures validées), écart des moyennes qualifié par le référentiel. */
const iso = (d: Date) => d.toISOString().slice(0, 10);
const back = (months: number) => { const d = new Date(); d.setMonth(d.getMonth() - months); return iso(d); };

export function PeriodsCompare({ patientId }: { patientId: string }) {
  const [p, setP] = useState({ a_from: back(12), a_to: back(6), b_from: back(6), b_to: iso(new Date()) });
  const valid = p.a_from <= p.a_to && p.b_from <= p.b_to;
  const { data, isFetching } = useQuery({
    queryKey: ["periods", patientId, p],
    queryFn: () => api<PeriodRow[]>(`/patients/${patientId}/periods?${new URLSearchParams(p)}`),
    enabled: valid,
  });
  const field = (k: keyof typeof p, label: string) => (
    <label className="flex items-center gap-1.5 text-sm">
      {label}
      <input type="date" className="field w-auto py-1" value={p[k]} onChange={(e) => setP({ ...p, [k]: e.target.value })} />
    </label>
  );
  const cell = (s: PeriodRow["a"], unit: string) =>
    s ? <>{fmtValue(s.mean, unit)} {unitLabel(unit)} <span className="text-ink-3">({s.n} mes., {fmtValue(s.min, unit)}–{fmtValue(s.max, unit)})</span></> : <span className="text-ink-3">aucune mesure</span>;
  return (
    <section className="panel p-4" aria-label="Comparaison de deux périodes">
      <h2 className="mb-2 text-[15px] font-bold">Comparer deux périodes</h2>
      <div className="flex flex-wrap gap-x-5 gap-y-2">
        <fieldset className="flex flex-wrap gap-2"><legend className="sr-only">Période A</legend><b className="text-sm">A</b>{field("a_from", "du")}{field("a_to", "au")}</fieldset>
        <fieldset className="flex flex-wrap gap-2"><legend className="sr-only">Période B</legend><b className="text-sm">B</b>{field("b_from", "du")}{field("b_to", "au")}</fieldset>
      </div>
      {!valid && <p role="alert" className="mt-2 text-sm text-alert">Chaque période doit commencer avant de finir.</p>}
      {valid && data && (
        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-paper text-ink-2">
              <tr>
                <th className="px-3 py-2 font-semibold">Paramètre</th>
                <th className="px-3 py-2 font-semibold">A : moyenne</th>
                <th className="px-3 py-2 font-semibold">B : moyenne</th>
                <th className="px-3 py-2 text-right font-semibold">Écart B − A</th>
                <th className="px-3 py-2 font-semibold">Qualification</th>
              </tr>
            </thead>
            <tbody>
              {data.map((r) => (
                <tr key={r.param} className="border-t border-grid">
                  <td className="px-3 py-1.5">{r.name}</td>
                  <td className="px-3 py-1.5">{cell(r.a, r.unit)}</td>
                  <td className="px-3 py-1.5">{cell(r.b, r.unit)}</td>
                  <td className="px-3 py-1.5 text-right">{r.diff == null ? "–" : `${r.diff > 0 ? "+" : r.diff < 0 ? "−" : ""}${fmtValue(Math.abs(r.diff), r.unit)} ${r.unit === "%" ? "pts" : unitLabel(r.unit)}`}</td>
                  <td className="px-3 py-1.5">
                    <span className={`rounded px-1.5 text-[12.5px] font-semibold ${TREND[r.qualification].tone}`}>
                      {r.qualification === "insufficient" ? "Données insuffisantes" : TREND[r.qualification].label}
                    </span>
                  </td>
                </tr>
              ))}
              {data.length === 0 && <tr><td colSpan={5} className="px-3 py-2 text-ink-2">Aucune mesure validée sur ces périodes.</td></tr>}
            </tbody>
          </table>
          <p className="mt-1.5 text-[12.5px] text-ink-3">
            Écart « stable » s'il reste sous le seuil cliniquement significatif du référentiel.{isFetching ? " Mise à jour…" : ""}
          </p>
        </div>
      )}
    </section>
  );
}
