import { Center, Loader } from "@mantine/core";
import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";

import { useAuth } from "../context/AuthContext";

/** Redirects to /login when unauthenticated; to /operador when the route
 * requires a permission the current role lacks (route guards by permission,
 * per phase 0 scope -- the UI hides nav items too, but this is the real
 * gate since the backend is the source of truth). */
export function RouteGuard({ children, permission }: { children: ReactNode; permission?: string }) {
  const { user, loading, hasPermission } = useAuth();

  if (loading) {
    return (
      <Center h="100vh">
        <Loader />
      </Center>
    );
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  if (permission && !hasPermission(permission)) {
    return <Navigate to={user.role === "operator" ? "/operador" : "/"} replace />;
  }

  return <>{children}</>;
}
