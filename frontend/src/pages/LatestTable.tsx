import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, type Facts } from "../api/client";
import { fmtDate, fmtValue, TREND, unitLabel } from "../labels";

/** F-B6 : dernière valeur, précédente et variation de chaque paramètre (données validées), avec renvoi au document. */
export function LatestTable({ patientId }: { patientId: string }) {
  const { data } = useQuery({ queryKey: ["facts", patientId], queryFn: () => api<Facts>(`/patients/${patientId}/facts`) });
  if (!data?.latest_values.length) return null;
  const trends = Object.fromEntries(data.trends.map((t) => [t.param, t]));
  const src = (doc: string | null, label: string, color = "text-teal-ink") =>
    doc ? <Link className={`${color} underline decoration-dotted`} to={`/patients/${patientId}/documents/${doc}`}>{label}</Link> : label;
  return (
    <section className="panel overflow-x-auto" aria-label="Dernières valeurs">
      <h2 className="px-4 pt-3 text-[15px] font-bold">Dernière valeur, précédente et variation</h2>
      <table className="mt-2 w-full text-left text-sm">
        <thead className="bg-paper text-ink-2">
          <tr>
            <th className="px-3 py-2 font-semibold">Paramètre</th>
            <th className="px-3 py-2 text-right font-semibold">Précédente</th>
            <th className="px-3 py-2 text-right font-semibold">Dernière</th>
            <th className="px-3 py-2 text-right font-semibold">Variation</th>
            <th className="px-3 py-2 font-semibold">Tendance sur 12 mois</th>
          </tr>
        </thead>
        <tbody>
          {data.latest_values.map((v) => {
            const u = unitLabel(v.unit);
            const t = trends[v.param];
            const d = v.previous?.delta;
            return (
              <tr key={v.param} className="border-t border-grid">
                <td className="px-3 py-1.5">{v.name}{v.days_old > 183 && <span className="ml-1.5 text-[12px] text-warn">ancienne</span>}</td>
                <td className="px-3 py-1.5 text-right text-ink-2">
                  {v.previous ? src(v.previous.document_id, `${fmtValue(v.previous.value, v.unit)} ${u} · ${fmtDate(v.previous.date)}`) : "–"}
                </td>
                <td className={`px-3 py-1.5 text-right ${v.out_of_range ? "font-bold text-alert" : ""}`}>
                  {src(v.document_id, `${fmtValue(v.value, v.unit)} ${u} · ${fmtDate(v.date)}`, v.out_of_range ? "text-alert" : undefined)}
                </td>
                <td className="px-3 py-1.5 text-right">
                  {d == null ? "–" : `${d > 0 ? "+" : d < 0 ? "−" : ""}${fmtValue(Math.abs(d), v.unit)} ${v.unit === "%" ? "pts" : u}`}
                </td>
                <td className="px-3 py-1.5">
                  <span className={`rounded px-1.5 text-[12.5px] font-semibold ${TREND[t?.qualification ?? "insufficient"].tone}`}>
                    {TREND[t?.qualification ?? "insufficient"].label}
                  </span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="px-4 py-2 text-[12.5px] text-ink-3">En rouge : hors de la zone de référence. Cliquez une valeur pour ouvrir son document source.</p>
    </section>
  );
}
