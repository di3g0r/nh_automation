import {
  AppShell as MantineAppShell,
  Burger,
  Group,
  Menu,
  NavLink as MantineNavLink,
  Text,
  Title,
} from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import {
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

interface NavItem {
  label: string;
  to: string;
  icon: typeof IconHome;
  permission?: string;
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
      </MantineAppShell.Header>

      <MantineAppShell.Navbar p="md">
        {visibleItems.map((item) => (
          <MantineNavLink
            key={item.to}
            label={item.label}
            leftSection={<item.icon size={18} />}
            active={location.pathname === item.to}
            onClick={() => navigate(item.to)}
          />
        ))}
      </MantineAppShell.Navbar>

      <MantineAppShell.Main>
        <Outlet />
      </MantineAppShell.Main>
    </MantineAppShell>
  );
}
