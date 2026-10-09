import { Navigate, Route, Routes } from "react-router-dom";

import { Layout } from "./components/AppShell/Layout";
import { RouteGuard } from "./components/RouteGuard";
import { useAuth } from "./context/AuthContext";
import { AuditLogPage } from "./pages/AuditLogPage";
import { ChangePasswordPage } from "./pages/ChangePasswordPage";
import {
  ClientsPage,
  MachinesPage,
  PackagingPage,
  ProductsPage,
  SitesPage,
} from "./pages/catalogs/CatalogPages";
import { HomePage } from "./pages/HomePage";
import { InventoryPage } from "./pages/InventoryPage";
import { LoginPage } from "./pages/LoginPage";
import { OperatorStationPage } from "./pages/OperatorStationPage";
import { SettingsPage } from "./pages/SettingsPage";
import { UsersPage } from "./pages/UsersPage";

const CATALOG_ROUTES = [
  { path: "/catalogos/productos", element: <ProductsPage /> },
  { path: "/catalogos/materiales", element: <PackagingPage /> },
  { path: "/catalogos/clientes", element: <ClientsPage /> },
  { path: "/catalogos/sitios", element: <SitesPage /> },
  { path: "/catalogos/maquinas", element: <MachinesPage /> },
];

/** Operators have no "Inicio"; they land on the operator station instead. */
function IndexRoute() {
  const { user } = useAuth();
  if (user?.role === "operator") return <Navigate to="/operador" replace />;
  return <HomePage />;
}

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />

      <Route
        element={
          <RouteGuard>
            <Layout />
          </RouteGuard>
        }
      >
        <Route index path="/" element={<IndexRoute />} />
        <Route path="/operador" element={<OperatorStationPage />} />
        <Route path="/cambiar-contrasena" element={<ChangePasswordPage />} />
        <Route
          path="/inventario"
          element={
            <RouteGuard permission="inventory.view">
              <InventoryPage />
            </RouteGuard>
          }
        />
        <Route path="/catalogos" element={<Navigate to="/catalogos/productos" replace />} />
        {CATALOG_ROUTES.map(({ path, element }) => (
          <Route
            key={path}
            path={path}
            element={<RouteGuard permission="catalogs.manage">{element}</RouteGuard>}
          />
        ))}
        <Route
          path="/usuarios"
          element={
            <RouteGuard permission="users.manage">
              <UsersPage />
            </RouteGuard>
          }
        />
        <Route
          path="/bitacora"
          element={
            <RouteGuard permission="audit.view">
              <AuditLogPage />
            </RouteGuard>
          }
        />
        <Route
          path="/configuracion"
          element={
            <RouteGuard permission="settings.manage">
              <SettingsPage />
            </RouteGuard>
          }
        />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
