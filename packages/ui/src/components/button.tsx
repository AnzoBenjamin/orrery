import { Button as AriaButton, type ButtonProps as AriaButtonProps } from "react-aria-components";

export type ButtonVariant = "primary" | "secondary" | "quiet";

const variants: Record<ButtonVariant, string> = {
  primary:
    "bg-brass text-lampblack hover:bg-brass-bright pressed:bg-brass-bright disabled:bg-umber disabled:text-parchment",
  secondary:
    "border border-brass text-bone hover:border-brass-bright hover:text-brass-bright disabled:border-umber disabled:text-parchment",
  quiet:
    "text-brass-bright underline decoration-brass/50 underline-offset-4 hover:decoration-brass-bright",
};

/** Buttons on React Aria. `isPending` keeps the button focusable and announces progress. */
export function Button({
  variant = "primary",
  className,
  children,
  ...props
}: AriaButtonProps & { variant?: ButtonVariant; className?: string }) {
  const base =
    variant === "quiet"
      ? "inline-flex items-center gap-2 font-interface text-base"
      : "inline-flex min-h-11 items-center justify-center gap-2 px-5 font-interface font-semibold text-base tracking-wide transition-colors duration-150 pending:cursor-wait";
  return (
    <AriaButton {...props} className={`${base} ${variants[variant]} ${className ?? ""}`}>
      {(renderProps) => (
        <>
          {typeof children === "function" ? children(renderProps) : children}
          {renderProps.isPending ? (
            <span aria-hidden="true" className="font-instrument text-sm">
              ···
            </span>
          ) : null}
        </>
      )}
    </AriaButton>
  );
}
