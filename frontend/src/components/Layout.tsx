import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

export function Logo({ className = "" }: { className?: string }) {
  return (
    <span className={`inline-flex items-center gap-2 text-[19px] font-bold tracking-tight ${className}`}>
      <svg width="22" height="22" viewBox="0 0 24 24" aria-hidden="true">
        <path d="M2 13h4l2-6 3 12 3-9 2 3h6" fill="none" stroke="#0E6B6B" strokeWidth="2.2" strokeLinecap="round"
          strokeLinejoin="round" />
      </svg>
      MediMind
    </span>
  );
}

/** Bandeau permanent exigé par les garde-fous (docs/PLAN.md §4). */
export function DecisionSupportBanner() {
  return (
    <div role="note" className="sticky top-0 z-30 flex flex-wrap gap-x-3 gap-y-1 bg-ink px-4 py-1.5 text-[13px] text-[#f1f5f4] sm:px-5">
      <strong>Aide à la décision.</strong>
      <span>Les résultats de l'IA ne constituent pas un diagnostic. Démonstrateur de recherche, données fictives.</span>
    </div>
  );
}

const navClass = ({ isActive }: { isActive: boolean }) =>
  `rounded px-2.5 py-1.5 ${isActive ? "bg-paper font-semibold text-ink" : "text-ink-2 hover:text-ink"}`;

export function Layout() {
  const { user, signOut } = useAuth();
  return (
    <div className="min-h-screen">
      <DecisionSupportBanner />
      <header className="flex items-center gap-6 border-b border-grid bg-surface px-4 py-3 sm:px-5">
        <Logo />
        <nav className="flex gap-1" aria-label="Navigation principale">
          {user?.role === "doctor" && <NavLink to="/patients" className={navClass}>Patients</NavLink>}
          {user?.role === "admin" && <NavLink to="/admin/comptes" className={navClass}>Comptes</NavLink>}
        </nav>
        <div className="ml-auto flex items-center gap-3 text-sm text-ink-2">
          <span className="hidden sm:inline">{user?.name}</span>
          <button type="button" className="btn" onClick={() => void signOut()}>
            Se déconnecter
          </button>
        </div>
      </header>
      <main className="px-4 sm:px-6">
        <Outlet />
      </main>
    </div>
  );
}
