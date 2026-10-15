import { Navigate, Route, Routes } from "react-router-dom";

import { Layout } from "./components/AppShell/Layout";
import { RouteGuard } from "./components/RouteGuard";
import { AuditLogPage } from "./pages/AuditLogPage";
import { ChangePasswordPage } from "./pages/ChangePasswordPage";
import {
  ClientsPage,
  MachinesPage,
  PackagingPage,
  ProductsPage,
  RazonesSocialesPage,
  SitesPage,
} from "./pages/catalogs/CatalogPages";
import { HomePage } from "./pages/HomePage";
import { InventoryPage } from "./pages/InventoryPage";
import { LoginPage } from "./pages/LoginPage";
import { MachinesBoardPage } from "./pages/MachinesBoardPage";
import { OrderDetailPage } from "./pages/orders/OrderDetailPage";
import { OrderFormPage } from "./pages/orders/OrderFormPage";
import { OrderPrintPage } from "./pages/orders/OrderPrintPage";
import { OrdersListPage } from "./pages/orders/OrdersListPage";
import { ProductionPage } from "./pages/ProductionPage";
import { SettingsPage } from "./pages/SettingsPage";
import { UsersPage } from "./pages/UsersPage";

const CATALOG_ROUTES = [
  { path: "/catalogos/productos", element: <ProductsPage /> },
  { path: "/catalogos/materiales", element: <PackagingPage /> },
  { path: "/catalogos/razones-sociales", element: <RazonesSocialesPage /> },
  { path: "/catalogos/clientes", element: <ClientsPage /> },
  { path: "/catalogos/sitios", element: <SitesPage /> },
  { path: "/catalogos/maquinas", element: <MachinesPage /> },
];

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      {/* Print view renders without the app shell so only the form prints. */}
      <Route
        path="/ordenes/:id/imprimir"
        element={
          <RouteGuard permission="orders.view">
            <OrderPrintPage />
          </RouteGuard>
        }
      />

      <Route
        element={
          <RouteGuard>
            <Layout />
          </RouteGuard>
        }
      >
        <Route index path="/" element={<HomePage />} />
        <Route
          path="/produccion"
          element={
            <RouteGuard permission="orders.assign">
              <ProductionPage />
            </RouteGuard>
          }
        />
        <Route
          path="/maquinas"
          element={
            <RouteGuard permission="machines.board">
              <MachinesBoardPage />
            </RouteGuard>
          }
        />
        <Route
          path="/ordenes"
          element={
            <RouteGuard permission="orders.view">
              <OrdersListPage />
            </RouteGuard>
          }
        />
        <Route
          path="/ordenes/nueva"
          element={
            <RouteGuard permission="orders.edit">
              <OrderFormPage />
            </RouteGuard>
          }
        />
        <Route
          path="/ordenes/:id"
          element={
            <RouteGuard permission="orders.view">
              <OrderDetailPage />
            </RouteGuard>
          }
        />
        <Route
          path="/ordenes/:id/editar"
          element={
            <RouteGuard permission="orders.edit">
              <OrderFormPage />
            </RouteGuard>
          }
        />
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
