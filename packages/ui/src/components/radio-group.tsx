import type { ReactNode } from "react";
import {
  Radio as AriaRadio,
  RadioGroup as AriaRadioGroup,
  type RadioGroupProps as AriaRadioGroupProps,
  Label,
  Text,
} from "react-aria-components";
import { useHydrated } from "../use-hydrated.ts";

/** A labelled choice of one option, laid out as a row of ruled rings that fill with ink. */
export function RadioGroup({
  label,
  description,
  children,
  isDisabled,
  className,
  ...props
}: Omit<AriaRadioGroupProps, "children" | "className"> & {
  label: string;
  description?: string | undefined;
  children: ReactNode;
  className?: string | undefined;
}) {
  const hydrated = useHydrated();
  return (
    <AriaRadioGroup
      {...props}
      isDisabled={!hydrated || (isDisabled ?? false)}
      className={`flex flex-col gap-2 ${className ?? ""}`}
    >
      <Label className="o-label">{label}</Label>
      <div className="flex flex-wrap gap-x-8 gap-y-2">{children}</div>
      {description ? (
        <Text slot="description" className="o-description">
          {description}
        </Text>
      ) : null}
    </AriaRadioGroup>
  );
}

export function Radio(props: { value: string; children: ReactNode }) {
  return (
    <AriaRadio value={props.value} className="o-radio flex cursor-pointer items-center gap-2.5">
      <span aria-hidden="true" className="o-radio-ring" />
      <span>{props.children}</span>
    </AriaRadio>
  );
}
