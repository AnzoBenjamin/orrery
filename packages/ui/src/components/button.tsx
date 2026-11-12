import type { PressEvent } from "react-aria-components";
import { Button as AriaButton, type ButtonProps as AriaButtonProps } from "react-aria-components";
import { useHydrated } from "../use-hydrated.ts";

export type ButtonVariant = "primary" | "secondary" | "quiet";

const variants: Record<ButtonVariant, string> = {
  primary: "o-button o-button-primary",
  secondary: "o-button o-button-secondary",
  quiet: "o-button-quiet",
};

type Props = Omit<AriaButtonProps, "isPending" | "children"> & {
  variant?: ButtonVariant;
  className?: string;
  children: React.ReactNode;
  /**
   * While true the button keeps focus, ignores presses, and its name gains ", working". React Aria's own
   * pending state is not used: it inserts an unlabelled role="img" node that fails axe.
   */
  isPending?: boolean;
};

export function Button({
  variant = "primary",
  className,
  children,
  isPending = false,
  onPress,
  type,
  isDisabled,
  ...props
}: Props) {
  // Every button acts through JavaScript, so it stays disabled until the page has hydrated.
  const hydrated = useHydrated();
  return (
    <AriaButton
      {...props}
      isDisabled={!hydrated || (isDisabled ?? false)}
      // A pending submit button must not submit its form again.
      type={isPending && type === "submit" ? "button" : (type ?? "button")}
      onPress={(event: PressEvent) => {
        if (!isPending) onPress?.(event);
      }}
      className={`${variants[variant]} ${isPending ? "cursor-wait" : ""} ${className ?? ""}`}
    >
      {children}
      {isPending ? (
        <>
          <span aria-hidden="true" className="font-instrument text-sm">
            ···
          </span>
          <span className="sr-only">, working</span>
        </>
      ) : null}
    </AriaButton>
  );
}
