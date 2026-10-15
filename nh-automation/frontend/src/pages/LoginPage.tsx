import {
  Alert,
  Button,
  Center,
  Paper,
  PasswordInput,
  Stack,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { IconAlertCircle } from "@tabler/icons-react";
import { useState } from "react";
import { Navigate, useLocation } from "react-router-dom";

import { ApiError } from "../api/client";
import { useAuth } from "../context/AuthContext";
import { strings } from "../i18n/strings";
import { landingPath } from "../utils/landing";

/** Password login only: operators do not use the platform (v3.1). */
export function LoginPage() {
  const { user, loginWithPassword } = useAuth();
  const location = useLocation();

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  if (user) {
    const from = (location.state as { from?: string } | null)?.from ?? landingPath(user.role);
    return <Navigate to={from} replace />;
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await loginWithPassword(username, password);
      // The redirect above sends the user to their landing page once `user` is set.
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError(strings.common.errorGenerico);
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Center h="100vh" bg="gray.0">
      <Paper withBorder shadow="sm" p="xl" radius="md" w={380}>
        <Stack gap="md">
          <div>
            <Title order={2}>{strings.login.title}</Title>
            <Text c="dimmed" size="sm">
              {strings.login.subtitle}
            </Text>
          </div>

          <form onSubmit={handleSubmit}>
            <Stack gap="sm">
              <TextInput
                label={strings.login.usuario}
                value={username}
                onChange={(e) => setUsername(e.currentTarget.value)}
                required
                autoFocus
              />
              <PasswordInput
                label={strings.login.contrasena}
                value={password}
                onChange={(e) => setPassword(e.currentTarget.value)}
                required
              />

              {error && (
                <Alert color="red" icon={<IconAlertCircle size={18} />}>
                  {error}
                </Alert>
              )}

              <Button type="submit" loading={submitting} fullWidth mt="sm">
                {strings.login.entrar}
              </Button>
            </Stack>
          </form>
        </Stack>
      </Paper>
    </Center>
  );
}
