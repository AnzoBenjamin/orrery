import type { ReactNode } from "react";
import { Form as AriaForm, type FormProps as AriaFormProps } from "react-aria-components";
import { useHydrated } from "../use-hydrated.ts";
import { Button, type ButtonVariant } from "./button.tsx";

/**
 * A form handled in JavaScript. Its fields are disabled until the page hydrates, because text
 * typed into the server-rendered inputs before then would be erased by hydration. It declares method="post" so no submission can put values such as passwords in the
 * URL.
 */
export function Form({
  children,
  ...props
}: Omit<AriaFormProps, "method"> & { children: ReactNode }) {
  const hydrated = useHydrated();
  return (
    <AriaForm {...props} method="post">
      <fieldset disabled={!hydrated} className="flex flex-col gap-5">
        {children}
      </fieldset>
    </AriaForm>
  );
}

export function SubmitButton(props: {
  children: ReactNode;
  isPending?: boolean;
  isDisabled?: boolean;
  variant?: ButtonVariant;
}) {
  return (
    <Button
      type="submit"
      variant={props.variant ?? "primary"}
      isPending={props.isPending ?? false}
      isDisabled={props.isDisabled ?? false}
    >
      {props.children}
    </Button>
  );
}
