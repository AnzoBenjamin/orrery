import { Banner, Button, Form, SubmitButton, TextField } from "@orrery/ui";
import { useState } from "react";
import { failureMessage, fieldErrors } from "../lib/result.ts";
import type { Result } from "../server/domain-errors.ts";

/** Title and description fields shared by the accession and edit dialogs. */
export function SpecimenForm(props: {
  initial?: { title: string; description: string };
  submitLabel: string;
  onSubmit: (values: { title: string; description: string }) => Promise<Result<unknown>>;
  onDone: () => void;
  onCancel: () => void;
}) {
  const [pending, setPending] = useState(false);
  const [result, setResult] = useState<Result<unknown> | null>(null);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setPending(true);
    const outcome = await props.onSubmit({
      title: String(form.get("title") ?? ""),
      description: String(form.get("description") ?? ""),
    });
    setPending(false);
    setResult(outcome);
    if (outcome.ok) props.onDone();
  }

  const failure = result ? failureMessage(result) : null;
  return (
    <Form onSubmit={submit} validationErrors={result ? fieldErrors(result) : {}}>
      {failure && !Object.keys(result ? fieldErrors(result) : {}).length ? (
        <Banner tone="error" title={failure} />
      ) : null}
      <TextField
        label="Name"
        name="title"
        isRequired
        maxLength={200}
        defaultValue={props.initial?.title ?? ""}
        description="What the machine is, as you would label it in a drawer."
      />
      <TextField
        label="Notes"
        name="description"
        maxLength={5000}
        defaultValue={props.initial?.description ?? ""}
        description="Maker, year, condition, what no longer moves. Optional."
      />
      <div className="flex items-center gap-4">
        <SubmitButton isPending={pending}>{props.submitLabel}</SubmitButton>
        <Button variant="quiet" onPress={props.onCancel}>
          Cancel
        </Button>
      </div>
    </Form>
  );
}
