import {
  TextField as AriaTextField,
  type TextFieldProps as AriaTextFieldProps,
  FieldError,
  Input,
  Label,
  Text,
} from "react-aria-components";

/**
 * Labelled text input. Errors come from native constraint validation or from the server through
 * React Aria's form `validationErrors`, and are announced with the field.
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
    <AriaTextField {...props} className={`flex flex-col gap-1.5 ${className ?? ""}`}>
      <Label className="font-interface font-medium text-bone text-sm tracking-wide">{label}</Label>
      <Input
        {...(placeholder === undefined ? {} : { placeholder })}
        className="min-h-11 border border-brass/70 bg-lampblack px-3 font-interface text-base text-bone placeholder:text-parchment/70 hover:border-brass focus:border-brass-bright data-invalid:border-bone data-invalid:border-dashed"
      />
      {description ? (
        <Text slot="description" className="font-interface text-parchment text-sm">
          {description}
        </Text>
      ) : null}
      <FieldError className="font-interface text-bone text-sm before:mr-1.5 before:font-instrument before:text-brass-bright before:content-['✕']" />
    </AriaTextField>
  );
}
