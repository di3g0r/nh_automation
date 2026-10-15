import { notifications } from "@mantine/notifications";

import { ApiError } from "../api/client";
import { strings } from "../i18n/strings";

/** The API's Spanish message, or a generic one for network/unknown errors. */
export function errorMessage(err: unknown): string {
  return err instanceof ApiError ? err.message : strings.common.errorGenerico;
}

export function notifyError(err: unknown) {
  notifications.show({ message: errorMessage(err), color: "red" });
}
