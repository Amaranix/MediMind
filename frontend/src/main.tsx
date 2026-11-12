import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Link, Navigate, Route, Routes, useLocation } from "react-router-dom";
import type { Role } from "./api/client";
import { AuthProvider, useAuth } from "./auth/AuthContext";
import { Layout } from "./components/Layout";
import "./index.css";
import { homeFor, LoginPage } from "./pages/LoginPage";
import { DocumentsTab } from "./pages/DocumentsTab";
import { EvolutionTab } from "./pages/EvolutionTab";
import { ImagingTab } from "./pages/ImagingTab";
import { PatientPage } from "./pages/PatientPage";
import { PatientsPage } from "./pages/PatientsPage";
import { PendingTab } from "./pages/PendingTab";
import { SheetTab } from "./pages/SheetTab";
import { AssistantTab } from "./pages/AssistantTab";
import { ValidationPage } from "./pages/ValidationPage";
import { UsersPage } from "./pages/UsersPage";

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: 1, staleTime: 15_000 } } });

function RequireRole({ role, children }: { role: Role; children: ReactNode }) {
  const { user, ready } = useAuth();
  const location = useLocation();
  if (!ready) return <p className="p-6 text-ink-2">Chargement…</p>;
  if (!user) return <Navigate to="/connexion" replace state={{ from: location.pathname }} />;
  if (user.role !== role) return <Navigate to={homeFor(user.role)} replace />;
  return <>{children}</>;
}

function Home() {
  const { user, ready } = useAuth();
  if (!ready) return <p className="p-6 text-ink-2">Chargement…</p>;
  return <Navigate to={user ? homeFor(user.role) : "/connexion"} replace />;
}

function NotFound() {
  return (
    <div className="mt-10">
      <h1 className="mb-2 text-2xl font-bold">Page introuvable</h1>
      <p className="mb-4 text-ink-2">Cette adresse ne correspond à aucune page de MediMind.</p>
      <Link to="/" className="btn">Revenir à l'accueil</Link>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <Routes>
            <Route path="/connexion" element={<LoginPage />} />
            <Route path="/" element={<Home />} />
            <Route element={<Layout />}>
              <Route path="/patients" element={<RequireRole role="doctor"><PatientsPage /></RequireRole>} />
              <Route path="/patients/:patientId" element={<RequireRole role="doctor"><PatientPage /></RequireRole>}>
                <Route index element={<EvolutionTab />} />
                <Route path="radiographies" element={<ImagingTab />} />
                <Route path="documents" element={<DocumentsTab />} />
                <Route path="a-valider" element={<PendingTab />} />
                <Route path="fiche" element={<SheetTab />} />
                <Route path="assistant" element={<AssistantTab />} />
                <Route path="documents/:docId" element={<ValidationPage />} />
              </Route>
              <Route path="/admin/comptes" element={<RequireRole role="admin"><UsersPage /></RequireRole>} />
              <Route path="*" element={<NotFound />} />
            </Route>
          </Routes>
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
