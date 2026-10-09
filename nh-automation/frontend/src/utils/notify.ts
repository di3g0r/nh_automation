import { notifications } from "@mantine/notifications";

import { ApiError } from "../api/client";
import { strings } from "../i18n/strings";

export function notifyError(err: unknown) {
  notifications.show({
    message: err instanceof ApiError ? err.message : strings.common.errorGenerico,
    color: "red",
  });
}
