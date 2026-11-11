import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useLayoutEffect, useMemo, useRef, useState, type FormEvent, type PointerEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, ApiError, post, type Series, type SeriesPoint, type Timeline, type Trend } from "../api/client";
import { DEFAULT_PARAMS, EVENT_TYPES, fmtDate, fmtValue, TREND, unitLabel } from "../labels";
import { usePatient } from "./PatientPage";

/*
 * Écran d'évolution (F-B1 à F-B4, F-D2) : toutes les courbes, la frise des traitements et les radiographies
 * partagent un seul axe du temps. Un curseur unique les traverse ; chaque paramètre affiche alors sa
 * dernière valeur validée à cette date. Seules les valeurs validées sont reliées ; les valeurs en attente
 * de validation sont dessinées en pointillé, sans être reliées ni prises en compte dans les tendances.
 */

const DAY = 86_400_000;
const PAD = { l: 14, r: 18, t: 12, b: 12 };
const ROW_H = 92;
const PERIODS = [
  { months: 3, label: "3 mois" },
  { months: 6, label: "6 mois" },
  { months: 12, label: "1 an" },
  { months: 0, label: "Tout" },
];
const C = { ink: "#1D2A31", ink3: "#7A8A91", grid: "#DCE6E3", band: "#EAF3F0", alert: "#A8233F", teal: "#0E6B6B", info: "#3B5B8C" };
const BAR_COLORS: Record<string, string> = {
  antibiotic: "#9A6400", systemic_steroid: "#7A4E8C", lama: "#0E6B6B", "laba+ics": "#3B5B8C", laba: "#3B5B8C",
  ics: "#3B5B8C", saba: "#5F7A84", antifibrotic: "#2C6E45",
};

const toDate = (iso: string) => new Date(iso.slice(0, 10) + "T00:00:00");
const iso = (d: Date) => d.toISOString().slice(0, 10);
const shortMonth = (d: Date) => d.toLocaleDateString("fr-FR", { month: "short", year: "2-digit" });

/** Largeur de la colonne des tracés. Référence de rappel : l'élément n'existe qu'une fois les données chargées. */
function useWidth<T extends HTMLElement>() {
  const ref = useRef<T | null>(null);
  const [el, setEl] = useState<T | null>(null);
  const [w, setW] = useState(600);
  useLayoutEffect(() => {
    if (!el) return;
    setW(Math.max(280, Math.floor(el.getBoundingClientRect().width)));
    const ro = new ResizeObserver(([e]) => setW(Math.max(280, Math.floor(e.contentRect.width))));
    ro.observe(el);
    return () => ro.disconnect();
  }, [el]);
  const callback = useCallback((node: T | null) => {
    ref.current = node;
    setEl(node);
  }, []);
  return [callback, w, ref] as const;
}

type Scale = { x: (d: Date) => number; inv: (px: number) => Date; start: Date; end: Date; w: number };

function makeScale(start: Date, end: Date, w: number): Scale {
  const span = Math.max(end.getTime() - start.getTime(), DAY);
  const inner = w - PAD.l - PAD.r;
  return {
    start, end, w,
    x: (d) => PAD.l + ((d.getTime() - start.getTime()) / span) * inner,
    inv: (px) => new Date(start.getTime() + ((px - PAD.l) / inner) * span),
  };
}

function MonthGrid({ s, h }: { s: Scale; h: number }) {
  const lines = [];
  const d = new Date(s.start.getFullYear(), s.start.getMonth() + 1, 1);
  while (d <= s.end) {
    lines.push(<line key={d.getTime()} x1={s.x(d)} x2={s.x(d)} y1={0} y2={h} stroke={C.grid} />);
    d.setMonth(d.getMonth() + 1);
  }
  return <>{lines}</>;
}

function EventLines({ s, h, tl }: { s: Scale; h: number; tl: Timeline }) {
  const inRange = (iso: string) => toDate(iso) >= s.start && toDate(iso) <= s.end;
  return (
    <>
      {tl.events.filter((e) => e.type === "hospitalisation" && inRange(e.date)).map((e) => (
        <rect key={e.id} x={s.x(toDate(e.date))} y={0} height={h} fill={C.alert} opacity={0.06}
          width={Math.max(3, s.x(toDate(e.end_date ?? e.date)) - s.x(toDate(e.date)))} />
      ))}
      {tl.events.filter((e) => e.type !== "hospitalisation" && inRange(e.date)).map((e) => (
        <line key={e.id} x1={s.x(toDate(e.date))} x2={s.x(toDate(e.date))} y1={0} y2={h} stroke={C.alert} strokeDasharray="3 3" />
      ))}
      {tl.treatment_changes.filter((c) => inRange(c.date)).map((c) => (
        <line key={c.date} x1={s.x(toDate(c.date))} x2={s.x(toDate(c.date))} y1={0} y2={h} stroke={C.teal} strokeDasharray="5 3" />
      ))}
    </>
  );
}

function Chart({ series, s, tl, onOpen }: { series: Series; s: Scale; tl: Timeline; onOpen: (p: SeriesPoint) => void }) {
  const inWin = (p: SeriesPoint) => toDate(p.date) >= s.start && toDate(p.date) <= s.end;
  const pts = series.points.filter(inWin);
  const pending = series.pending.filter(inWin);
  const ref = series.reference;
  const values = [...pts, ...pending].map((p) => p.value);
  let lo = Math.min(...values), hi = Math.max(...values);
  // La zone de référence est incluse si elle est proche des données (sinon elle écraserait la courbe)
  const span0 = hi - lo || Math.abs(hi) * 0.2 || 1;
  if (ref?.low != null && ref.low >= lo - span0) lo = Math.min(lo, ref.low);
  if (ref?.high != null && ref.high <= hi + span0) hi = Math.max(hi, ref.high);
  const span = hi - lo || 1;
  lo -= span * 0.12;
  hi += span * 0.12;
  const y = (v: number) => PAD.t + (1 - (v - lo) / (hi - lo)) * (ROW_H - PAD.t - PAD.b);
  const out = (v: number) => (ref?.low != null && v < ref.low) || (ref?.high != null && v > ref.high);
  const bandTop = ref?.high != null ? y(Math.min(ref.high, hi)) : PAD.t;
  const bandBottom = ref?.low != null ? y(Math.max(ref.low, lo)) : ROW_H - PAD.b;
  const threshold = series.code === "FEV1_FVC" ? 0.7 : null;
  return (
    <svg width={s.w} height={ROW_H} role="img" aria-label={`Courbe ${series.name}`} className="block">
      <MonthGrid s={s} h={ROW_H} />
      {ref && (ref.low != null || ref.high != null) && bandBottom > bandTop && (
        <rect x={PAD.l} width={s.w - PAD.l - PAD.r} y={bandTop} height={bandBottom - bandTop} fill={C.band} />
      )}
      {threshold != null && threshold > lo && threshold < hi && (
        <>
          <line x1={PAD.l} x2={s.w - PAD.r} y1={y(threshold)} y2={y(threshold)} stroke={C.teal} strokeDasharray="5 4" />
          <text x={s.w - PAD.r - 4} y={y(threshold) - 4} textAnchor="end" fontSize={11} fill={C.teal}>seuil 0,70</text>
        </>
      )}
      <EventLines s={s} h={ROW_H} tl={tl} />
      {pts.length > 1 && (
        <polyline fill="none" stroke={C.ink} strokeWidth={2}
          points={pts.map((p) => `${s.x(toDate(p.date))},${y(p.value)}`).join(" ")} />
      )}
      {pending.map((p) => (
        <circle key={p.id} cx={s.x(toDate(p.date))} cy={y(p.value)} r={4.5} fill="#fff" stroke={C.ink3} strokeWidth={1.5}
          strokeDasharray="2 2"><title>{`${series.name} ${fmtValue(p.value, series.unit)} ${unitLabel(series.unit)}, ${fmtDate(p.date)} : à valider`}</title></circle>
      ))}
      {pts.map((p) => {
        const o = out(p.value);
        return (
          <circle key={p.id} cx={s.x(toDate(p.date))} cy={y(p.value)} r={o ? 4.5 : 3.5} fill={o ? "#fff" : C.ink}
            stroke={o ? C.alert : C.ink} strokeWidth={2} className="cursor-pointer" onClick={() => onOpen(p)}>
            <title>{`${series.name} ${fmtValue(p.value, series.unit)} ${unitLabel(series.unit)}, ${fmtDate(p.date)}. Cliquer pour ouvrir le document source.`}</title>
          </circle>
        );
      })}
    </svg>
  );
}

function Frise({ s, tl, onOpenDoc }: { s: Scale; tl: Timeline; onOpenDoc: (id: string) => void }) {
  const bars = tl.treatments.filter((b) => toDate(b.start) <= s.end && (!b.end || toDate(b.end) >= s.start));
  const rowH = 16;
  const yEvents = PAD.t + bars.length * rowH + 4;
  const yRadio = yEvents + 20;
  const h = yRadio + 22;
  const clamp = (d: Date) => new Date(Math.min(Math.max(d.getTime(), s.start.getTime()), s.end.getTime()));
  return (
    <svg width={s.w} height={h} role="img" aria-label="Frise des traitements, événements et radiographies" className="block">
      <MonthGrid s={s} h={h} />
      <EventLines s={s} h={h} tl={tl} />
      {bars.map((b, i) => {
        const x1 = s.x(clamp(toDate(b.start)));
        const x2 = s.x(clamp(b.end ? toDate(b.end) : s.end));
        const yy = PAD.t + i * rowH;
        const color = BAR_COLORS[b.drug_class ?? ""] ?? C.ink3;
        const label = b.molecule.charAt(0).toUpperCase() + b.molecule.slice(1);
        return (
          <g key={`${b.molecule}-${b.start}`}>
            <rect x={x1} y={yy} width={Math.max(3, x2 - x1)} height={10} rx={2} fill={color} opacity={0.85}>
              <title>{`${label} ${b.dosage ?? ""} : ${fmtDate(b.start)}${b.end ? ` au ${fmtDate(b.end)}` : ", en cours"}`}</title>
            </rect>
            <text x={x2 - x1 > 150 ? x1 + 6 : x2 + 5} y={yy + 8.5} fontSize={10.5} fill={x2 - x1 > 150 ? "#fff" : "#4A5A62"}>{label}</text>
          </g>
        );
      })}
      {tl.events.filter((e) => toDate(e.date) >= s.start && toDate(e.date) <= s.end).map((e) => (
        <g key={e.id}>
          <rect x={s.x(toDate(e.date)) - 4} y={yEvents} width={8} height={8} fill={C.alert} transform={`rotate(45 ${s.x(toDate(e.date))} ${yEvents + 4})`}>
            <title>{`${EVENT_TYPES[e.type] ?? e.type} le ${fmtDate(e.date)}${e.end_date ? ` au ${fmtDate(e.end_date)}` : ""}`}</title>
          </rect>
        </g>
      ))}
      {tl.radiographs.filter((r) => toDate(r.date) >= s.start && toDate(r.date) <= s.end).map((r, i) => {
        const x = s.x(toDate(r.date));
        return (
          <g key={r.document_id} className="cursor-pointer" onClick={() => onOpenDoc(r.document_id)}>
            <rect x={x - 5} y={yRadio} width={10} height={10} fill={C.ink} transform={`rotate(45 ${x} ${yRadio + 5})`}>
              <title>{`Radiographie du ${fmtDate(r.date)}`}</title>
            </rect>
            <text x={x + 9} y={yRadio + 9} fontSize={10.5} fontWeight={700} fill={C.ink}>R{i + 1}</text>
          </g>
        );
      })}
    </svg>
  );
}

function Axis({ s }: { s: Scale }) {
  const months = (s.end.getTime() - s.start.getTime()) / (30 * DAY);
  const step = months <= 7 ? 1 : months <= 14 ? 2 : 3;
  const ticks = [];
  const d = new Date(s.start.getFullYear(), s.start.getMonth() + 1, 1);
  let i = 0;
  while (d <= s.end) {
    if (i++ % step === 0) ticks.push(<text key={d.getTime()} x={s.x(d)} y={17} fontSize={11.5} textAnchor="middle" fill="#4A5A62">{shortMonth(d)}</text>);
    d.setMonth(d.getMonth() + 1);
  }
  return <svg width={s.w} height={26} aria-hidden="true" className="block">{ticks}</svg>;
}

function lastAt(series: Series, at: Date | null): SeriesPoint | null {
  const pts = series.points.filter((p) => !at || toDate(p.date) <= at);
  return pts.length ? pts[pts.length - 1] : null;
}

function EventForm({ patientId, onDone }: { patientId: string; onDone: () => void }) {
  const qc = useQueryClient();
  const [form, setForm] = useState({ type: "exacerbation", date: "", end_date: "", note: "" });
  const [error, setError] = useState<string | null>(null);
  const add = useMutation({
    mutationFn: () => post(`/patients/${patientId}/events`, { ...form, end_date: form.end_date || null, note: form.note || null }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["timeline", patientId] }); onDone(); },
    onError: (e) => setError(e instanceof ApiError ? e.message : "Enregistrement impossible."),
  });
  function submit(e: FormEvent) { e.preventDefault(); setError(null); add.mutate(); }
  return (
    <form onSubmit={submit} className="panel mt-4 grid gap-3 p-4 sm:grid-cols-[180px_160px_160px_1fr_auto] sm:items-end" aria-label="Ajouter un événement">
      <div>
        <label className="label" htmlFor="ev-type">Événement</label>
        <select id="ev-type" className="field" value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })}>
          {Object.entries(EVENT_TYPES).filter(([k]) => k !== "treatment_change").map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
      </div>
      <div>
        <label className="label" htmlFor="ev-date">Date</label>
        <input id="ev-date" type="date" required className="field" value={form.date} max={iso(new Date())}
          onChange={(e) => setForm({ ...form, date: e.target.value })} />
      </div>
      <div>
        <label className="label" htmlFor="ev-end">Fin (facultatif)</label>
        <input id="ev-end" type="date" className="field" value={form.end_date} onChange={(e) => setForm({ ...form, end_date: e.target.value })} />
      </div>
      <div>
        <label className="label" htmlFor="ev-note">Note</label>
        <input id="ev-note" className="field" value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} />
      </div>
      <div className="flex gap-2">
        <button type="submit" className="btn btn-primary" disabled={!form.date || add.isPending}>Ajouter</button>
        <button type="button" className="btn" onClick={onDone}>Annuler</button>
      </div>
      {error && <p role="alert" className="text-sm text-alert sm:col-span-5">{error}</p>}
    </form>
  );
}

export function EvolutionTab() {
  const { patientId = "" } = useParams();
  const navigate = useNavigate();
  const { data: patient } = usePatient(patientId);
  const seriesQ = useQuery({ queryKey: ["series", patientId], queryFn: () => api<Record<string, Series>>(`/patients/${patientId}/series`) });
  const tlQ = useQuery({ queryKey: ["timeline", patientId], queryFn: () => api<Timeline>(`/patients/${patientId}/timeline`) });
  const [months, setMonths] = useState(12);
  const [chosen, setChosen] = useState<string[] | null>(null);
  const [cursor, setCursor] = useState<{ x: number; date: Date } | null>(null);
  const [adding, setAdding] = useState(false);
  const [plotRef, plotW, plotEl] = useWidth<HTMLDivElement>();
  const all = useMemo(() => seriesQ.data ?? {}, [seriesQ.data]);
  const tl = tlQ.data;

  const lastDate = useMemo(() => {
    const dates = Object.values(all).flatMap((s) => [...s.points, ...s.pending].map((p) => p.date));
    return dates.length ? toDate(dates.sort().at(-1)!) : new Date();
  }, [all]);
  const firstDate = useMemo(() => {
    const dates = Object.values(all).flatMap((s) => s.points.map((p) => p.date));
    return dates.length ? toDate(dates.sort()[0]) : new Date(lastDate.getTime() - 365 * DAY);
  }, [all, lastDate]);
  const end = new Date(lastDate.getTime() + 10 * DAY);
  const start = months ? new Date(end.getFullYear(), end.getMonth() - months, end.getDate()) : new Date(firstDate.getTime() - 15 * DAY);
  const scale = makeScale(start, end, plotW);

  const trendsQ = useQuery({
    queryKey: ["trends", patientId, iso(start)],
    queryFn: () => api<Trend[]>(`/patients/${patientId}/trends?from=${iso(start)}`),
  });
  const trendBy = Object.fromEntries((trendsQ.data ?? []).map((t) => [t.param, t]));

  const available = Object.keys(all);
  const defaults = (patient?.conditions ?? []).flatMap((c) => DEFAULT_PARAMS[c] ?? []);
  const shown = (chosen ?? (defaults.length ? defaults : available.slice(0, 5))).filter((c) => all[c]);

  function onMove(e: PointerEvent<HTMLDivElement>) {
    const plot = plotEl.current?.getBoundingClientRect();
    if (!plot) return;
    const x = e.clientX - plot.left;
    if (x < PAD.l || x > plot.width - PAD.r) return setCursor(null);
    // position du trait relative au panneau, date relative à la colonne des tracés
    setCursor({ x: plot.left - e.currentTarget.getBoundingClientRect().left + x, date: scale.inv(x) });
  }
  const openPoint = (p: SeriesPoint) => p.document_id && navigate(`/patients/${patientId}/documents/${p.document_id}`);

  if (seriesQ.isLoading || !tl) return <p className="text-ink-2">Chargement de l'évolution…</p>;
  if (available.length === 0)
    return <p className="panel p-6 text-ink-2">Aucune valeur validée pour l'instant. Déposez et validez des documents pour voir l'évolution du patient.</p>;

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center gap-4">
        <div className="inline-flex overflow-hidden rounded-lg border border-grid-strong bg-surface" role="group" aria-label="Période">
          {PERIODS.map((p, i) => (
            <button key={p.months} type="button" aria-pressed={months === p.months} onClick={() => setMonths(p.months)}
              className={`px-3 py-1.5 ${i ? "border-l border-grid" : ""} ${months === p.months ? "bg-teal font-semibold text-white" : "text-ink-2"}`}>
              {p.label}
            </button>
          ))}
        </div>
        <div className="flex flex-wrap gap-1.5" aria-label="Paramètres affichés">
          {available.map((code) => {
            const on = shown.includes(code);
            return (
              <button key={code} type="button" aria-pressed={on}
                onClick={() => setChosen(on ? shown.filter((c) => c !== code) : available.filter((c) => shown.includes(c) || c === code))}
                className={`rounded-full border px-2.5 py-0.5 text-[13.5px] ${on ? "border-teal bg-teal-soft font-semibold text-teal-ink" : "border-grid-strong bg-surface text-ink-2"}`}>
                {all[code].name}
              </button>
            );
          })}
        </div>
      </div>

      <div className="panel relative overflow-hidden" onPointerMove={onMove} onPointerLeave={() => setCursor(null)}>
        {shown.map((code) => {
          const s = all[code];
          const lv = lastAt(s, cursor?.date ?? null);
          const t = trendBy[code];
          const tr = TREND[t?.qualification ?? "insufficient"];
          const pend = s.pending.length;
          return (
            <div key={code} className="grid grid-cols-[132px_minmax(0,1fr)] border-b border-grid sm:grid-cols-[208px_minmax(0,1fr)]">
              <div className="border-r border-grid px-3.5 py-3">
                <div className="font-semibold">{s.name}</div>
                <div className="text-[26px] leading-tight font-bold">
                  {lv ? fmtValue(lv.value, s.unit) : "–"}
                  <small className="ml-1 text-[13px] font-medium text-ink-2">{unitLabel(s.unit)}</small>
                </div>
                <div className="text-[12.5px] text-ink-3">
                  {lv ? `${cursor ? "Valeur au" : "Dernière valeur,"} ${fmtDate(lv.date)}` : "Aucune valeur avant cette date"}
                </div>
                <span className={`mt-1.5 inline-block rounded px-1.5 text-[12.5px] font-semibold ${tr.tone}`}
                  title={t?.slope_per_year != null ? `Pente ${fmtValue(t.slope_per_year, s.unit)} ${unitLabel(s.unit)} par an (Theil-Sen, ${t.n} mesures)` : undefined}>
                  {tr.label}
                </span>
                {pend > 0 && <div className="mt-1 text-[12px] text-warn">{pend} valeur(s) à valider</div>}
              </div>
              <div ref={code === shown[0] ? plotRef : undefined} className="min-w-0">
                <Chart series={s} s={scale} tl={tl} onOpen={openPoint} />
              </div>
            </div>
          );
        })}
        {shown.length === 0 && <div ref={plotRef} className="p-4 text-ink-2">Choisissez au moins un paramètre.</div>}
        <div className="grid grid-cols-[132px_minmax(0,1fr)] border-b border-grid sm:grid-cols-[208px_minmax(0,1fr)]">
          <div className="border-r border-grid px-3.5 py-3">
            <div className="font-semibold">Traitements et événements</div>
            <div className="text-[12.5px] text-ink-3">Exacerbations, hospitalisations, radiographies</div>
            <button type="button" className="mt-2 text-[13px] text-teal-ink underline" onClick={() => setAdding(true)}>Ajouter un événement</button>
          </div>
          <div className="min-w-0"><Frise s={scale} tl={tl} onOpenDoc={(id) => navigate(`/patients/${patientId}/documents/${id}`)} /></div>
        </div>
        <div className="grid grid-cols-[132px_minmax(0,1fr)] sm:grid-cols-[208px_minmax(0,1fr)]">
          <div className="border-r border-grid" />
          <div className="min-w-0"><Axis s={scale} /></div>
        </div>
        {/* Curseur commun : simple trait, ne capte aucun clic (les points restent cliquables) */}
        {cursor && (
          <div className="pointer-events-none absolute inset-y-0 border-l-[1.5px] border-ink" style={{ left: cursor.x }}>
            <span className="absolute top-1 -translate-x-1/2 rounded bg-ink px-1.5 py-0.5 text-xs whitespace-nowrap text-white">
              {cursor.date.toLocaleDateString("fr-FR")}
            </span>
          </div>
        )}
      </div>

      <div className="mt-2.5 flex flex-wrap gap-4 text-[13px] text-ink-2">
        <span className="inline-flex items-center gap-1.5"><i className="inline-block h-2.5 w-3.5 rounded-sm bg-[#EAF3F0]" />Zone de référence</span>
        <span className="inline-flex items-center gap-1.5"><svg width="12" height="12"><circle cx="6" cy="6" r="4.5" fill="#fff" stroke={C.alert} strokeWidth="2" /></svg>Hors zone</span>
        <span className="inline-flex items-center gap-1.5"><svg width="12" height="12"><circle cx="6" cy="6" r="4" fill="none" stroke={C.ink3} strokeWidth="1.5" strokeDasharray="2 2" /></svg>À valider (non prise en compte)</span>
        <span className="inline-flex items-center gap-1.5"><svg width="14" height="12"><line x1="7" y1="0" x2="7" y2="12" stroke={C.alert} strokeDasharray="3 2" /></svg>Exacerbation</span>
        <span className="inline-flex items-center gap-1.5"><svg width="14" height="12"><line x1="7" y1="0" x2="7" y2="12" stroke={C.teal} strokeDasharray="4 2" /></svg>Changement de traitement</span>
        <span className="inline-flex items-center gap-1.5"><svg width="14" height="12"><rect x="3" y="2" width="8" height="8" fill={C.ink} transform="rotate(45 7 6)" /></svg>Radiographie</span>
      </div>
      {adding && <EventForm patientId={patientId} onDone={() => setAdding(false)} />}
    </>
  );
}
