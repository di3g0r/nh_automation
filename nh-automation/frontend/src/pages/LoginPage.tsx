import {
  Alert,
  Button,
  Center,
  Paper,
  PasswordInput,
  SegmentedControl,
  Stack,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { IconAlertCircle } from "@tabler/icons-react";
import { useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";

import { ApiError } from "../api/client";
import { useAuth } from "../context/AuthContext";
import { strings } from "../i18n/strings";

type Mode = "password" | "pin";

export function LoginPage() {
  const { user, loginWithPassword, loginWithPin } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const [mode, setMode] = useState<Mode>("password");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [pin, setPin] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  if (user) {
    const from = (location.state as { from?: string } | null)?.from ?? "/";
    return <Navigate to={from} replace />;
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      if (mode === "password") {
        await loginWithPassword(username, password);
      } else {
        await loginWithPin(username, pin);
      }
      navigate("/", { replace: true });
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

          <SegmentedControl
            fullWidth
            value={mode}
            onChange={(v) => setMode(v as Mode)}
            data={[
              { label: strings.login.modoContrasena, value: "password" },
              { label: strings.login.modoPin, value: "pin" },
            ]}
          />

          <form onSubmit={handleSubmit}>
            <Stack gap="sm">
              <TextInput
                label={strings.login.usuario}
                value={username}
                onChange={(e) => setUsername(e.currentTarget.value)}
                required
                autoFocus
              />
              {mode === "password" ? (
                <PasswordInput
                  label={strings.login.contrasena}
                  value={password}
                  onChange={(e) => setPassword(e.currentTarget.value)}
                  required
                />
              ) : (
                <TextInput
                  label={strings.login.pin}
                  value={pin}
                  onChange={(e) => setPin(e.currentTarget.value.replace(/\D/g, ""))}
                  inputMode="numeric"
                  maxLength={6}
                  required
                />
              )}

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
