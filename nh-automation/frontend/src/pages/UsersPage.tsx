import {
  ActionIcon,
  Badge,
  Button,
  Group,
  Menu,
  Modal,
  PasswordInput,
  Select,
  Stack,
  Table,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconDots, IconPlus } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { ApiError } from "../api/client";
import { usersApi } from "../api/users";
import type { Role, User } from "../api/types";
import { strings } from "../i18n/strings";
import { formatDateTime } from "../utils/datetime";

const ROLE_OPTIONS: { value: Role; label: string }[] = [
  { value: "master_admin", label: strings.users.roles.master_admin },
  { value: "admin", label: strings.users.roles.admin },
  { value: "supervisor", label: strings.users.roles.supervisor },
  { value: "operator", label: strings.users.roles.operator },
];

export function UsersPage() {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const [editUser, setEditUser] = useState<User | null>(null);
  const [resetUser, setResetUser] = useState<User | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["users", search],
    queryFn: () => usersApi.list(search || undefined),
  });

  function invalidate() {
    queryClient.invalidateQueries({ queryKey: ["users"] });
  }

  const deactivateMutation = useMutation({
    mutationFn: (id: number) => usersApi.deactivate(id),
    onSuccess: () => {
      notifications.show({ message: strings.users.desactivado, color: "green" });
      invalidate();
    },
    onError: (err) => notifyError(err),
  });

  const activateMutation = useMutation({
    mutationFn: (id: number) => usersApi.activate(id),
    onSuccess: () => {
      notifications.show({ message: strings.users.activado, color: "green" });
      invalidate();
    },
    onError: (err) => notifyError(err),
  });

  function notifyError(err: unknown) {
    notifications.show({
      message: err instanceof ApiError ? err.message : strings.common.errorGenerico,
      color: "red",
    });
  }

  return (
    <Stack>
      <Group justify="space-between">
        <Title order={2}>{strings.users.title}</Title>
        <Button leftSection={<IconPlus size={16} />} onClick={() => setCreateOpen(true)}>
          {strings.users.nuevo}
        </Button>
      </Group>

      <TextInput
        placeholder={strings.users.buscar}
        value={search}
        onChange={(e) => setSearch(e.currentTarget.value)}
        maw={360}
      />

      <Table striped highlightOnHover>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>{strings.users.columnas.usuario}</Table.Th>
            <Table.Th>{strings.users.columnas.nombre}</Table.Th>
            <Table.Th>{strings.users.columnas.rol}</Table.Th>
            <Table.Th>{strings.users.columnas.estado}</Table.Th>
            <Table.Th>{strings.users.columnas.ultimoAcceso}</Table.Th>
            <Table.Th>{strings.users.columnas.acciones}</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {!isLoading && data?.items.length === 0 && (
            <Table.Tr>
              <Table.Td colSpan={6}>
                <Text c="dimmed">{strings.common.sinDatos}</Text>
              </Table.Td>
            </Table.Tr>
          )}
          {data?.items.map((u) => (
            <Table.Tr key={u.id}>
              <Table.Td>{u.username}</Table.Td>
              <Table.Td>{u.full_name}</Table.Td>
              <Table.Td>{strings.users.roles[u.role]}</Table.Td>
              <Table.Td>
                <Badge color={u.is_active ? "green" : "gray"}>
                  {u.is_active ? strings.users.estado.activo : strings.users.estado.inactivo}
                </Badge>
              </Table.Td>
              <Table.Td>{formatDateTime(u.last_login_at)}</Table.Td>
              <Table.Td>
                <Menu shadow="md" position="bottom-end">
                  <Menu.Target>
                    <ActionIcon variant="subtle">
                      <IconDots size={16} />
                    </ActionIcon>
                  </Menu.Target>
                  <Menu.Dropdown>
                    <Menu.Item onClick={() => setEditUser(u)}>
                      {strings.users.acciones.editar}
                    </Menu.Item>
                    <Menu.Item onClick={() => setResetUser(u)}>
                      {strings.users.acciones.restablecer}
                    </Menu.Item>
                    {u.is_active ? (
                      <Menu.Item color="red" onClick={() => deactivateMutation.mutate(u.id)}>
                        {strings.users.acciones.desactivar}
                      </Menu.Item>
                    ) : (
                      <Menu.Item color="green" onClick={() => activateMutation.mutate(u.id)}>
                        {strings.users.acciones.activar}
                      </Menu.Item>
                    )}
                  </Menu.Dropdown>
                </Menu>
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>

      <CreateUserModal
        opened={createOpen}
        onClose={() => setCreateOpen(false)}
        onDone={invalidate}
      />
      <EditUserModal
        key={editUser?.id ?? "none"}
        user={editUser}
        onClose={() => setEditUser(null)}
        onDone={invalidate}
      />
      <ResetCredentialsModal
        key={resetUser?.id ?? "none"}
        user={resetUser}
        onClose={() => setResetUser(null)}
        onDone={invalidate}
      />
    </Stack>
  );
}

function CreateUserModal({
  opened,
  onClose,
  onDone,
}: {
  opened: boolean;
  onClose: () => void;
  onDone: () => void;
}) {
  const [username, setUsername] = useState("");
  const [fullName, setFullName] = useState("");
  const [role, setRole] = useState<Role>("admin");
  const [password, setPassword] = useState("");
  const [pin, setPin] = useState("");
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () =>
      usersApi.create({
        username,
        full_name: fullName,
        role,
        password,
        pin: pin || undefined,
      }),
    onSuccess: () => {
      notifications.show({ message: strings.users.creado, color: "green" });
      setUsername("");
      setFullName("");
      setRole("admin");
      setPassword("");
      setPin("");
      onDone();
      onClose();
    },
    onError: (err) =>
      setError(err instanceof ApiError ? err.message : strings.common.errorGenerico),
  });

  return (
    <Modal opened={opened} onClose={onClose} title={strings.users.nuevo}>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          setError(null);
          mutation.mutate();
        }}
      >
        <Stack gap="sm">
          <TextInput
            label={strings.users.form.usuario}
            value={username}
            onChange={(e) => setUsername(e.currentTarget.value)}
            required
          />
          <TextInput
            label={strings.users.form.nombre}
            value={fullName}
            onChange={(e) => setFullName(e.currentTarget.value)}
            required
          />
          <Select
            label={strings.users.form.rol}
            data={ROLE_OPTIONS}
            value={role}
            onChange={(v) => setRole((v ?? "admin") as Role)}
            required
          />
          <PasswordInput
            label={strings.users.form.contrasena}
            value={password}
            onChange={(e) => setPassword(e.currentTarget.value)}
            required
          />
          <TextInput
            label={strings.users.form.pin}
            value={pin}
            onChange={(e) => setPin(e.currentTarget.value.replace(/\D/g, ""))}
            maxLength={6}
          />
          {error && <Text c="red">{error}</Text>}
          <Group justify="end" mt="sm">
            <Button variant="default" onClick={onClose}>
              {strings.users.form.cancelar}
            </Button>
            <Button type="submit" loading={mutation.isPending}>
              {strings.users.form.guardar}
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  );
}

function EditUserModal({
  user,
  onClose,
  onDone,
}: {
  user: User | null;
  onClose: () => void;
  onDone: () => void;
}) {
  // Keyed by user.id in the parent, so this remounts (and re-initializes
  // state) whenever a different row is opened for editing.
  const [fullName, setFullName] = useState(user?.full_name ?? "");
  const [role, setRole] = useState<Role>(user?.role ?? "admin");
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () => usersApi.update(user!.id, { full_name: fullName, role }),
    onSuccess: () => {
      notifications.show({ message: strings.users.actualizado, color: "green" });
      onDone();
      onClose();
    },
    onError: (err) =>
      setError(err instanceof ApiError ? err.message : strings.common.errorGenerico),
  });

  return (
    <Modal
      opened={Boolean(user)}
      onClose={onClose}
      title={strings.users.acciones.editar}
      onExitTransitionEnd={() => setError(null)}
    >
      {user && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            setError(null);
            mutation.mutate();
          }}
        >
          <Stack gap="sm">
            <TextInput label={strings.users.form.usuario} value={user.username} disabled />
            <TextInput
              label={strings.users.form.nombre}
              value={fullName}
              onChange={(e) => setFullName(e.currentTarget.value)}
              required
            />
            <Select
              label={strings.users.form.rol}
              data={ROLE_OPTIONS}
              value={role}
              onChange={(v) => setRole((v ?? user.role) as Role)}
              required
            />
            {error && <Text c="red">{error}</Text>}
            <Group justify="end" mt="sm">
              <Button variant="default" onClick={onClose}>
                {strings.users.form.cancelar}
              </Button>
              <Button type="submit" loading={mutation.isPending}>
                {strings.users.form.guardar}
              </Button>
            </Group>
          </Stack>
        </form>
      )}
    </Modal>
  );
}

function ResetCredentialsModal({
  user,
  onClose,
  onDone,
}: {
  user: User | null;
  onClose: () => void;
  onDone: () => void;
}) {
  const [password, setPassword] = useState("");
  const [pin, setPin] = useState("");
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () =>
      usersApi.resetCredentials(user!.id, {
        password: password || undefined,
        pin: pin || undefined,
      }),
    onSuccess: () => {
      notifications.show({ message: strings.users.credencialesRestablecidas, color: "green" });
      setPassword("");
      setPin("");
      onDone();
      onClose();
    },
    onError: (err) =>
      setError(err instanceof ApiError ? err.message : strings.common.errorGenerico),
  });

  return (
    <Modal opened={Boolean(user)} onClose={onClose} title={strings.users.reset.title}>
      {user && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            setError(null);
            mutation.mutate();
          }}
        >
          <Stack gap="sm">
            <Text size="sm" c="dimmed">
              {user.username}
            </Text>
            <PasswordInput
              label={strings.users.reset.nuevaContrasena}
              value={password}
              onChange={(e) => setPassword(e.currentTarget.value)}
            />
            <TextInput
              label={strings.users.reset.nuevoPin}
              value={pin}
              onChange={(e) => setPin(e.currentTarget.value.replace(/\D/g, ""))}
              maxLength={6}
            />
            {error && <Text c="red">{error}</Text>}
            <Group justify="end" mt="sm">
              <Button variant="default" onClick={onClose}>
                {strings.users.form.cancelar}
              </Button>
              <Button type="submit" loading={mutation.isPending}>
                {strings.users.form.guardar}
              </Button>
            </Group>
          </Stack>
        </form>
      )}
    </Modal>
  );
}
