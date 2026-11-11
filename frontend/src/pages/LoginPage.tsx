import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { DecisionSupportBanner, Logo } from "../components/Layout";

export function homeFor(role: string) {
  return role === "admin" ? "/admin/comptes" : "/patients";
}

export function LoginPage() {
  const { user, signIn } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (user) return <Navigate to={homeFor(user.role)} replace />;

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const me = await signIn(email, password);
      const from = (location.state as { from?: string } | null)?.from;
      navigate(from && me.role === "doctor" ? from : homeFor(me.role), { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Le serveur ne répond pas. Réessayez dans un instant.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen">
      <DecisionSupportBanner />
      <div
        className="grid min-h-[calc(100vh-32px)] place-items-center px-4"
        style={{
          backgroundImage:
            "linear-gradient(var(--color-grid) 1px, transparent 1px), linear-gradient(90deg, var(--color-grid) 1px, transparent 1px)",
          backgroundSize: "24px 24px",
        }}
      >
        <form onSubmit={submit} className="panel w-full max-w-sm p-7" noValidate>
          <Logo className="mb-4" />
          <h1 className="mb-1 text-2xl font-bold">Connexion</h1>
          <p className="mb-5 text-ink-2">Accès réservé aux médecins et à l'administrateur.</p>
          {error && (
            <p role="alert" className="mb-4 rounded border-l-[3px] border-alert bg-alert-soft px-3 py-2 text-sm">
              {error}
            </p>
          )}
          <label htmlFor="email" className="label">Adresse e-mail</label>
          <input id="email" type="email" className="field mb-3" autoComplete="username" required value={email}
            onChange={(e) => setEmail(e.target.value)} />
          <label htmlFor="password" className="label">Mot de passe</label>
          <input id="password" type="password" className="field" autoComplete="current-password" required
            value={password} onChange={(e) => setPassword(e.target.value)} />
          <button type="submit" className="btn btn-primary mt-5 w-full py-2" disabled={busy || !email || !password}>
            {busy ? "Connexion…" : "Se connecter"}
          </button>
        </form>
      </div>
    </div>
  );
}
