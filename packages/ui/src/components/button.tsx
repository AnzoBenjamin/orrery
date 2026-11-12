import type { PressEvent } from "react-aria-components";
import { Button as AriaButton, type ButtonProps as AriaButtonProps } from "react-aria-components";
import { useHydrated } from "../use-hydrated.ts";

export type ButtonVariant = "primary" | "secondary" | "quiet";

const variants: Record<ButtonVariant, string> = {
  primary:
    "bg-brass text-lampblack hover:bg-brass-bright pressed:bg-brass-bright disabled:bg-umber disabled:text-parchment",
  secondary:
    "border border-brass text-bone hover:border-brass-bright hover:text-brass-bright disabled:border-umber disabled:text-parchment",
  quiet:
    "text-brass-bright underline decoration-brass/50 underline-offset-4 hover:decoration-brass-bright",
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
  const base =
    variant === "quiet"
      ? "inline-flex items-center gap-2 font-interface text-base"
      : "inline-flex min-h-11 items-center justify-center gap-2 px-5 font-interface font-semibold text-base tracking-wide transition-colors duration-150";
  return (
    <AriaButton
      {...props}
      isDisabled={!hydrated || (isDisabled ?? false)}
      // A pending submit button must not submit its form again.
      type={isPending && type === "submit" ? "button" : (type ?? "button")}
      onPress={(event: PressEvent) => {
        if (!isPending) onPress?.(event);
      }}
      className={`${base} ${variants[variant]} ${isPending ? "cursor-wait" : ""} ${className ?? ""}`}
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
