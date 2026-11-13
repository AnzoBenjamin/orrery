import { type ReactNode, useId } from "react";
import { Switch as AriaSwitch, type SwitchProps as AriaSwitchProps } from "react-aria-components";
import { useHydrated } from "../use-hydrated.ts";

/**
 * An on/off setting drawn as a lever in a ruled slot: the lever sits left when off and right, in
 * solid ink, when on. The label states the setting; the description, announced separately, says
 * what it changes.
 */
export function Switch({
  children,
  description,
  isDisabled,
  className,
  ...props
}: Omit<AriaSwitchProps, "children" | "className"> & {
  children: ReactNode;
  description?: string | undefined;
  className?: string | undefined;
}) {
  const hydrated = useHydrated();
  const descriptionId = useId();
  return (
    <div className={`flex flex-col gap-1 ${className ?? ""}`}>
      <AriaSwitch
        {...props}
        {...(description ? { "aria-describedby": descriptionId } : {})}
        isDisabled={!hydrated || (isDisabled ?? false)}
        className="o-switch group flex cursor-pointer items-center gap-4"
      >
        <span aria-hidden="true" className="o-switch-slot">
          <span className="o-switch-lever" />
        </span>
        <span className="o-label">{children}</span>
      </AriaSwitch>
      {description ? (
        <p id={descriptionId} className="o-description pl-[3.75rem]">
          {description}
        </p>
      ) : null}
    </div>
  );
}
