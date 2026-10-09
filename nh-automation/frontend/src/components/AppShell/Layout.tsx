import {
  ActionIcon,
  Indicator,
  AppShell as MantineAppShell,
  Burger,
  Group,
  Menu,
  Tooltip,
  NavLink as MantineNavLink,
  Text,
  Title,
} from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import {
  IconAlertTriangle,
  IconBooks,
  IconChevronDown,
  IconClipboardList,
  IconHome,
  IconKey,
  IconLogout,
  IconNotebook,
  IconPackage,
  IconSettings,
  IconUsers,
} from "@tabler/icons-react";
import { Outlet, useLocation, useNavigate } from "react-router-dom";

import { useAuth } from "../../context/AuthContext";
import { strings } from "../../i18n/strings";
import { useStockAlerts } from "../inventory/useStockAlerts";

interface NavItem {
  label: string;
  to: string;
  icon: typeof IconHome;
  permission?: string;
  children?: { label: string; to: string }[];
}

const NAV_ITEMS: NavItem[] = [
  { label: strings.nav.inicio, to: "/", icon: IconHome },
  {
    label: strings.nav.ordenes,
    to: "/ordenes",
    icon: IconClipboardList,
    permission: "orders.view",
  },
  {
    label: strings.nav.inventario,
    to: "/inventario",
    icon: IconPackage,
    permission: "inventory.view",
  },
  {
    label: strings.nav.catalogos,
    to: "/catalogos",
    icon: IconBooks,
    permission: "catalogs.manage",
    children: [
      { label: strings.nav.productos, to: "/catalogos/productos" },
      { label: strings.nav.materiales, to: "/catalogos/materiales" },
      { label: strings.nav.clientes, to: "/catalogos/clientes" },
      { label: strings.nav.sitios, to: "/catalogos/sitios" },
      { label: strings.nav.maquinas, to: "/catalogos/maquinas" },
    ],
  },
  { label: strings.nav.usuarios, to: "/usuarios", icon: IconUsers, permission: "users.manage" },
  { label: strings.nav.bitacora, to: "/bitacora", icon: IconNotebook, permission: "audit.view" },
  {
    label: strings.nav.configuracion,
    to: "/configuracion",
    icon: IconSettings,
    permission: "settings.manage",
  },
];

export function Layout() {
  const [opened, { toggle }] = useDisclosure();
  const { user, hasPermission, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const visibleItems = NAV_ITEMS.filter(
    (item) => !item.permission || hasPermission(item.permission),
  );

  const roleLabel = user ? strings.users.roles[user.role] : "";

  return (
    <MantineAppShell
      header={{ height: 60 }}
      navbar={{ width: 260, breakpoint: "sm", collapsed: { mobile: !opened } }}
      padding="md"
    >
      <MantineAppShell.Header>
        <Group h="100%" px="md" justify="space-between">
          <Group>
            <Burger opened={opened} onClick={toggle} hiddenFrom="sm" size="sm" />
            <Title order={4}>{strings.app.title}</Title>
            <Text c="dimmed" size="sm" visibleFrom="sm">
              {strings.app.site}
            </Text>
          </Group>
          <Group gap="md">
            <StockAlertsIndicator />
            <Menu shadow="md" width={220} position="bottom-end">
              <Menu.Target>
                <Group gap={6} style={{ cursor: "pointer" }}>
                  <Text fw={500}>{user?.full_name}</Text>
                  <Text c="dimmed" size="sm">
                    ({roleLabel})
                  </Text>
                  <IconChevronDown size={16} />
                </Group>
              </Menu.Target>
              <Menu.Dropdown>
                <Menu.Item
                  leftSection={<IconKey size={16} />}
                  onClick={() => navigate("/cambiar-contrasena")}
                >
                  {strings.topbar.cambiarContrasena}
                </Menu.Item>
                <Menu.Item
                  color="red"
                  leftSection={<IconLogout size={16} />}
                  onClick={() => logout().then(() => navigate("/login"))}
                >
                  {strings.topbar.cerrarSesion}
                </Menu.Item>
              </Menu.Dropdown>
            </Menu>
          </Group>
        </Group>
      </MantineAppShell.Header>

      <MantineAppShell.Navbar p="md">
        {visibleItems.map((item) =>
          item.children ? (
            <MantineNavLink
              key={item.to}
              label={item.label}
              leftSection={<item.icon size={18} />}
              defaultOpened={location.pathname.startsWith(item.to)}
              childrenOffset={28}
            >
              {item.children.map((child) => (
                <MantineNavLink
                  key={child.to}
                  label={child.label}
                  active={location.pathname === child.to}
                  onClick={() => navigate(child.to)}
                />
              ))}
            </MantineNavLink>
          ) : (
            <MantineNavLink
              key={item.to}
              label={item.label}
              leftSection={<item.icon size={18} />}
              active={location.pathname === item.to}
              onClick={() => navigate(item.to)}
            />
          ),
        )}
      </MantineAppShell.Navbar>

      <MantineAppShell.Main>
        <Outlet />
      </MantineAppShell.Main>
    </MantineAppShell>
  );
}

/** Top bar: count of stock alerts (FR-INV-10/11), links to Inventario. */
function StockAlertsIndicator() {
  const { hasPermission } = useAuth();
  const navigate = useNavigate();
  const { data } = useStockAlerts();
  if (!hasPermission("inventory.view")) return null;
  const count = data?.count ?? 0;
  return (
    <Tooltip label={`${strings.alerts.topbar}: ${count}`}>
      <Indicator label={count} size={16} color="orange" disabled={count === 0}>
        <ActionIcon
          variant="subtle"
          color={count ? "orange" : "gray"}
          aria-label={strings.alerts.topbar}
          onClick={() => navigate("/inventario?tab=materiales&alertas=1")}
        >
          <IconAlertTriangle size={20} />
        </ActionIcon>
      </Indicator>
    </Tooltip>
  );
}
