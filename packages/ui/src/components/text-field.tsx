import {
  TextField as AriaTextField,
  type TextFieldProps as AriaTextFieldProps,
  FieldError,
  Input,
  Label,
  Text,
} from "react-aria-components";

/**
 * A labelled entry on a ledger line. Styled by surface (see .o-* in styles.css), so it reads as ink
 * on a paper plate and as bone on the dark workbench.
 */
export function TextField({
  label,
  description,
  className,
  placeholder,
  ...props
}: AriaTextFieldProps & {
  label: string;
  description?: string | undefined;
  placeholder?: string | undefined;
  className?: string;
}) {
  return (
    <AriaTextField {...props} className={`flex flex-col gap-1 ${className ?? ""}`}>
      <Label className="o-label">{label}</Label>
      <Input {...(placeholder === undefined ? {} : { placeholder })} className="o-input" />
      {description ? (
        <Text slot="description" className="o-description">
          {description}
        </Text>
      ) : null}
      <FieldError className="o-error text-sm" />
    </AriaTextField>
  );
}
