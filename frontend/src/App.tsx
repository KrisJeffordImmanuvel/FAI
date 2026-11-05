import { lazy, Suspense, type ReactNode } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { ThemeProvider } from "./context/ThemeContext";
import { AgentProvider } from "./context/AgentContext";
import { ToastProvider } from "./components/toast";
import Layout from "./components/Layout";
import { Spinner } from "./components/ui";
import { canAccess } from "./lib/roles";
import LoginPage from "./pages/Login";

const Dashboard = lazy(() => import("./pages/Dashboard"));
const Catalog = lazy(() => import("./pages/Catalog"));
const Members = lazy(() => import("./pages/Members"));
const MemberDetailPage = lazy(() => import("./pages/MemberDetail"));
const Circulation = lazy(() => import("./pages/Circulation"));
const MyLoans = lazy(() => import("./pages/MyLoans"));
const Reservations = lazy(() => import("./pages/Reservations"));
const Fines = lazy(() => import("./pages/Fines"));
const Approvals = lazy(() => import("./pages/Approvals"));
const Notifications = lazy(() => import("./pages/Notifications"));
const AgentControl = lazy(() => import("./pages/AgentControl"));
const Explainability = lazy(() => import("./pages/Explainability"));
const KnowledgeBase = lazy(() => import("./pages/KnowledgeBase"));
const MLInsights = lazy(() => import("./pages/MLInsights"));
const Analytics = lazy(() => import("./pages/Analytics"));
const About = lazy(() => import("./pages/About"));
const Admin = lazy(() => import("./pages/Admin"));
const Audit = lazy(() => import("./pages/Audit"));

function Guard({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const location = useLocation();
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  if (!canAccess(user.role, location.pathname)) {
    return (
      <Layout>
        <div className="card mx-auto max-w-lg p-6 text-center">
          <h1 className="text-2xl font-semibold">Not available for your role</h1>
          <p className="mt-2 text-sm text-ink2">This page needs a different role. Use the navigation to continue.</p>
        </div>
      </Layout>
    );
  }
  return <Layout><Suspense fallback={<Spinner />}>{children}</Suspense></Layout>;
}

function AppRoutes() {
  const { user, loading } = useAuth();
  if (loading) return <Spinner label="Starting…" />;
  return (
    <Routes>
      <Route path="/login" element={user ? <Navigate to="/" replace /> : <LoginPage />} />
      <Route path="/" element={<Guard><Dashboard /></Guard>} />
      <Route path="/catalog" element={<Guard><Catalog /></Guard>} />
      <Route path="/members" element={<Guard><Members /></Guard>} />
      <Route path="/members/:id" element={<Guard><MemberDetailPage /></Guard>} />
      <Route path="/circulation" element={<Guard><Circulation /></Guard>} />
      <Route path="/my-loans" element={<Guard><MyLoans /></Guard>} />
      <Route path="/reservations" element={<Guard><Reservations /></Guard>} />
      <Route path="/fines" element={<Guard><Fines /></Guard>} />
      <Route path="/approvals" element={<Guard><Approvals /></Guard>} />
      <Route path="/notifications" element={<Guard><Notifications /></Guard>} />
      <Route path="/agent" element={<Guard><AgentControl /></Guard>} />
      <Route path="/explain" element={<Guard><Explainability /></Guard>} />
      <Route path="/knowledge-base" element={<Guard><KnowledgeBase /></Guard>} />
      <Route path="/ml" element={<Guard><MLInsights /></Guard>} />
      <Route path="/analytics" element={<Guard><Analytics /></Guard>} />
      <Route path="/about" element={<Guard><About /></Guard>} />
      <Route path="/admin" element={<Guard><Admin /></Guard>} />
      <Route path="/audit" element={<Guard><Audit /></Guard>} />
      <Route path="*" element={<Guard><div className="card p-6"><h1 className="text-2xl font-semibold">Page not found</h1><p className="mt-1 text-sm text-ink2">The page you asked for does not exist.</p></div></Guard>} />
    </Routes>
  );
}

export default function App() {
  return (
    <ThemeProvider>
      <ToastProvider>
        <AuthProvider>
          <AgentProvider>
            <AppRoutes />
          </AgentProvider>
        </AuthProvider>
      </ToastProvider>
    </ThemeProvider>
  );
}
