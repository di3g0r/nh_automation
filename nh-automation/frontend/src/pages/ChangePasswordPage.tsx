import { Alert, Button, Paper, PasswordInput, Stack, TextInput, Title } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconAlertCircle } from "@tabler/icons-react";
import { useState } from "react";

import { authApi } from "../api/auth";
import { ApiError } from "../api/client";
import { strings } from "../i18n/strings";

export function ChangePasswordPage() {
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newPin, setNewPin] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await authApi.changePassword({
        current_password: currentPassword,
        new_password: newPassword || undefined,
        new_pin: newPin || undefined,
      });
      notifications.show({ message: strings.changePassword.exito, color: "green" });
      setCurrentPassword("");
      setNewPassword("");
      setNewPin("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : strings.common.errorGenerico);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Paper withBorder shadow="sm" p="xl" radius="md" maw={420}>
      <Stack gap="md">
        <Title order={2}>{strings.changePassword.title}</Title>
        <form onSubmit={handleSubmit}>
          <Stack gap="sm">
            <PasswordInput
              label={strings.changePassword.actual}
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.currentTarget.value)}
              required
            />
            <PasswordInput
              label={strings.changePassword.nueva}
              value={newPassword}
              onChange={(e) => setNewPassword(e.currentTarget.value)}
            />
            <TextInput
              label={strings.changePassword.nuevoPin}
              value={newPin}
              onChange={(e) => setNewPin(e.currentTarget.value.replace(/\D/g, ""))}
              maxLength={6}
            />
            {error && (
              <Alert color="red" icon={<IconAlertCircle size={18} />}>
                {error}
              </Alert>
            )}
            <Button type="submit" loading={submitting} mt="sm">
              {strings.changePassword.guardar}
            </Button>
          </Stack>
        </form>
      </Stack>
    </Paper>
  );
}
