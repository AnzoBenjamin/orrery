import { Banner, Button, Dialog, DialogTrigger, toRoman } from "@orrery/ui";
import { createFileRoute, Link, useRouter } from "@tanstack/react-router";
import { useState } from "react";
import { SpecimenForm } from "../../components/specimen-form.tsx";
import {
  createSpecimenFn,
  deleteSpecimenFn,
  listSpecimensFn,
  updateSpecimenFn,
} from "../../functions/specimens.ts";
import { failureMessage } from "../../lib/result.ts";
import type { SpecimenView } from "../../server/operations/specimens.ts";

export const Route = createFileRoute("/_app/cabinet")({
  head: () => ({ meta: [{ title: "Cabinet · Orrery" }] }),
  loader: () => listSpecimensFn({ data: { limit: 48 } }),
  pendingComponent: CabinetSkeleton,
  component: Cabinet,
});

const accessioned = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "long",
  year: "numeric",
});

function Cabinet() {
  const first = Route.useLoaderData();
  const router = useRouter();
  const [more, setMore] = useState<SpecimenView[]>([]);
  const [cursor, setCursor] = useState<string | undefined>(
    first.ok ? first.value.nextCursor : undefined,
  );
  const [loadingMore, setLoadingMore] = useState(false);
  const [moreError, setMoreError] = useState<string | null>(null);

  if (!first.ok) {
    return (
      <Page>
        <Banner tone="error" title={failureMessage(first) ?? "The cabinet could not be opened."}>
          Reload the page to try again.
        </Banner>
      </Page>
    );
  }

  const specimens = [...first.value.items, ...more];
  const refresh = async () => {
    setMore([]);
    await router.invalidate();
  };

  async function loadMore() {
    setLoadingMore(true);
    const page = await listSpecimensFn({ data: { limit: 48, before: cursor } });
    setLoadingMore(false);
    if (!page.ok) {
      setMoreError(failureMessage(page));
      return;
    }
    setMore((m) => [...m, ...page.value.items]);
    setCursor(page.value.nextCursor);
  }

  return (
    <Page action={<AccessionButton onDone={refresh} />}>
      {specimens.length === 0 ? (
        <EmptyCabinet onDone={refresh} />
      ) : (
        <>
          <ul className="grid gap-6 sm:grid-cols-2 xl:grid-cols-3" aria-label="Specimens">
            {specimens.map((s, i) => (
              <SpecimenDrawer
                key={s.id}
                specimen={s}
                number={specimens.length - i}
                onChanged={refresh}
              />
            ))}
          </ul>
          {moreError ? (
            <div className="mt-6">
              <Banner tone="error" title={moreError} />
            </div>
          ) : null}
          {cursor ? (
            <div className="mt-10 flex justify-center">
              <Button variant="secondary" onPress={loadMore} isPending={loadingMore}>
                Open the next drawer
              </Button>
            </div>
          ) : null}
        </>
      )}
    </Page>
  );
}

function Page(props: { children: React.ReactNode; action?: React.ReactNode }) {
  return (
    <main id="main" className="mx-auto w-full max-w-7xl px-4 py-10 sm:px-10">
      <div className="mb-9 flex flex-wrap items-end justify-between gap-6 border-umber border-b pb-6">
        <div>
          <p className="font-display-sc text-parchment text-sm tracking-[0.22em]">The collection</p>
          <h1 className="mt-1 font-display text-5xl text-bone">Cabinet of specimens</h1>
          <p className="mt-2 max-w-xl font-display text-lg text-parchment italic">
            Each drawer holds one machine: its footage, its reconstructed mechanism, and every
            repair proposed for it.
          </p>
        </div>
        {props.action}
      </div>
      {props.children}
    </main>
  );
}

function AccessionButton({
  onDone,
  label = "Accession a specimen",
}: {
  onDone: () => Promise<void>;
  label?: string;
}) {
  const [open, setOpen] = useState(false);
  return (
    <DialogTrigger isOpen={open} onOpenChange={setOpen}>
      <Button>{label}</Button>
      <Dialog title="Accession a specimen" caption="Enter it in the register. Footage comes next.">
        {(close) => (
          <SpecimenForm
            submitLabel="Enter in the register"
            onSubmit={(values) => createSpecimenFn({ data: values })}
            onDone={async () => {
              close();
              await onDone();
            }}
            onCancel={close}
          />
        )}
      </Dialog>
    </DialogTrigger>
  );
}

function EmptyCabinet({ onDone }: { onDone: () => Promise<void> }) {
  return (
    <section
      aria-labelledby="empty-title"
      className="mx-auto max-w-xl border border-umber border-dashed px-8 py-14 text-center"
    >
      <p aria-hidden="true" className="font-display text-6xl text-umber">
        ∅
      </p>
      <h2 id="empty-title" className="mt-4 font-display text-3xl text-bone">
        The cabinet is empty
      </h2>
      <p className="mx-auto mt-3 max-w-md text-parchment">
        Start with one machine you can film: a sewing machine, a clock, a toy, a typewriter. Name it
        here, then add footage of it moving, or failing to.
      </p>
      <div className="mt-8 flex justify-center">
        <AccessionButton onDone={onDone} label="Accession your first specimen" />
      </div>
    </section>
  );
}

function SpecimenDrawer(props: {
  specimen: SpecimenView;
  number: number;
  onChanged: () => Promise<void>;
}) {
  const s = props.specimen;
  const [editing, setEditing] = useState(false);
  const [deleting, setDeleting] = useState(false);
  return (
    <li className="paper flex flex-col p-2" aria-labelledby={`specimen-${s.id}`}>
      <div className="flex flex-1 flex-col border border-lampblack/40 px-6 pt-5 pb-5">
        <div className="flex items-start justify-between gap-4">
          <span className="o-tag text-sm">No. {toRoman(props.number)}</span>
          <span className="font-instrument text-umber text-xs">
            {accessioned.format(new Date(s.createdAt))}
          </span>
        </div>
        <h2
          id={`specimen-${s.id}`}
          className="mt-5 font-display text-2xl text-lampblack leading-tight"
        >
          <Link
            to="/specimens/$specimenId"
            params={{ specimenId: s.id }}
            className="hover:underline hover:decoration-oxblood hover:underline-offset-4"
          >
            {s.title}
          </Link>
        </h2>
        <p className="mt-2 line-clamp-3 flex-1 font-display text-umber italic">
          {s.description || "No notes yet."}
        </p>
        <div className="mt-5 flex gap-5 border-lampblack/25 border-t pt-4">
          <DialogTrigger isOpen={editing} onOpenChange={setEditing}>
            <Button variant="quiet" aria-label={`Edit ${s.title}`}>
              Edit
            </Button>
            <Dialog title="Edit specimen" caption={s.title}>
              {(close) => (
                <SpecimenForm
                  initial={{ title: s.title, description: s.description }}
                  submitLabel="Save changes"
                  onSubmit={(values) => updateSpecimenFn({ data: { specimenId: s.id, ...values } })}
                  onDone={async () => {
                    close();
                    await props.onChanged();
                  }}
                  onCancel={close}
                />
              )}
            </Dialog>
          </DialogTrigger>
          <DialogTrigger isOpen={deleting} onOpenChange={setDeleting}>
            <Button variant="quiet" aria-label={`Delete ${s.title}`}>
              Delete
            </Button>
            <Dialog title="Dispose of this specimen?" caption={s.title} role="alertdialog">
              {(close) => <DeleteConfirm specimen={s} close={close} onDone={props.onChanged} />}
            </Dialog>
          </DialogTrigger>
        </div>
      </div>
    </li>
  );
}

function DeleteConfirm(props: {
  specimen: SpecimenView;
  close: () => void;
  onDone: () => Promise<void>;
}) {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function confirm() {
    setPending(true);
    const result = await deleteSpecimenFn({ data: { specimenId: props.specimen.id } });
    setPending(false);
    if (!result.ok) {
      setError(failureMessage(result));
      return;
    }
    props.close();
    await props.onDone();
  }
  return (
    <div className="flex flex-col gap-5">
      {error ? <Banner tone="error" title={error} /> : null}
      <p className="text-lampblack">
        The specimen, all of its footage, and everything reconstructed from it will be destroyed.
        This cannot be undone.
      </p>
      <div className="flex items-center gap-4">
        <Button onPress={confirm} isPending={pending}>
          Destroy specimen
        </Button>
        <Button variant="quiet" onPress={props.close}>
          Keep it
        </Button>
      </div>
    </div>
  );
}

function CabinetSkeleton() {
  return (
    <Page>
      <ul
        className="grid gap-6 sm:grid-cols-2 xl:grid-cols-3"
        aria-busy="true"
        aria-label="Loading specimens"
      >
        {[0, 1, 2].map((i) => (
          <li key={i} className="h-56 border border-umber bg-soot motion-safe:animate-pulse" />
        ))}
      </ul>
    </Page>
  );
}
