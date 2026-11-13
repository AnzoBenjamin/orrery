import { Banner, Button, Dialog, DialogTrigger } from "@orrery/ui";
import { createFileRoute, Link, useRouter } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { FootageUploader } from "../../../components/footage-uploader.tsx";
import { ShareButton } from "../../../components/share-dialog.tsx";
import { deleteFootageFn, listFootageFn, playbackUrlFn } from "../../../functions/footage.ts";
import { getSpecimenFn } from "../../../functions/specimens.ts";
import { footageRoles } from "../../../lib/footage-roles.ts";
import { formatBytes, formatDuration, formatFps } from "../../../lib/format.ts";
import { failureMessage } from "../../../lib/result.ts";
import type { FootageView } from "../../../server/operations/footage.ts";

export const Route = createFileRoute("/_app/specimens/$specimenId")({
  loader: async ({ params }) => {
    const [specimen, footage] = await Promise.all([
      getSpecimenFn({ data: { specimenId: params.specimenId } }),
      listFootageFn({ data: { specimenId: params.specimenId } }),
    ]);
    return { specimen, footage };
  },
  head: ({ loaderData }) => ({
    meta: [
      {
        title: loaderData?.specimen.ok
          ? `${loaderData.specimen.value.title} · Orrery`
          : "Specimen · Orrery",
      },
    ],
  }),
  pendingComponent: SpecimenSkeleton,
  component: SpecimenPage,
});

/** While footage is being inspected, its status is refreshed this often. */
const INSPECTION_REFRESH_MS = 3000;

function SpecimenPage() {
  const { specimen, footage } = Route.useLoaderData();
  const router = useRouter();
  const refresh = () => router.invalidate();
  const inspecting = footage.ok && footage.value.some((f) => f.status === "probing");

  // Until specimen events stream over SSE (platform-foundation task 7.4), poll while the engine
  // inspects footage.
  useEffect(() => {
    if (!inspecting) return;
    const timer = setInterval(() => void router.invalidate(), INSPECTION_REFRESH_MS);
    return () => clearInterval(timer);
  }, [inspecting, router]);

  if (!specimen.ok) {
    return (
      <main id="main" className="mx-auto w-full max-w-5xl px-4 py-12 sm:px-10">
        <Banner
          tone="error"
          title={failureMessage(specimen) ?? "This specimen could not be opened."}
        >
          <Link to="/cabinet" className="o-link">
            Return to the cabinet
          </Link>
        </Banner>
      </main>
    );
  }
  const s = specimen.value;

  return (
    <main id="main" className="mx-auto w-full max-w-5xl px-4 py-10 sm:px-10">
      <nav aria-label="Breadcrumb" className="mb-6">
        <Link to="/cabinet" className="o-link font-display text-parchment italic">
          ← Cabinet of specimens
        </Link>
      </nav>
      <header className="mb-10 flex flex-wrap items-end justify-between gap-6 border-umber border-b pb-6">
        <div>
          <p className="font-display-sc text-parchment text-sm tracking-[0.22em]">Specimen</p>
          <h1 className="mt-1 font-display text-5xl text-bone">{s.title}</h1>
          {s.description ? (
            <p className="mt-3 max-w-2xl whitespace-pre-line font-display text-lg text-parchment italic">
              {s.description}
            </p>
          ) : null}
        </div>
        {s.isOwner ? <ShareButton specimenId={s.id} title={s.title} /> : null}
      </header>

      <div className="grid gap-12 lg:grid-cols-[1fr_22rem]">
        <section aria-labelledby="footage-title">
          <h2 id="footage-title" className="mb-5 font-display text-2xl text-bone">
            Footage
          </h2>
          {!footage.ok ? (
            <Banner
              tone="error"
              title={failureMessage(footage) ?? "The footage could not be listed."}
            >
              Reload the page to try again.
            </Banner>
          ) : footage.value.length === 0 ? (
            <div className="border border-umber border-dashed px-6 py-10 text-center">
              <p className="font-display text-bone text-xl">No footage yet</p>
              <p className="mx-auto mt-2 max-w-md text-parchment">
                Film the machine running, or failing, for a few full cycles with the camera held
                still. Add the clip here and it is checked straight away.
              </p>
            </div>
          ) : (
            <ul aria-label="Footage" className="flex flex-col gap-4">
              {footage.value.map((f) => (
                <FootageItem key={f.id} footage={f} onChanged={refresh} />
              ))}
            </ul>
          )}
        </section>
        <FootageUploader specimenId={s.id} onChanged={refresh} />
      </div>
    </main>
  );
}

const statusText: Record<FootageView["status"], string> = {
  uploading: "Uploading",
  probing: "Being inspected",
  ready: "Ready",
  rejected: "Rejected",
};

function FootageItem(props: { footage: FootageView; onChanged: () => Promise<void> }) {
  const f = props.footage;
  const [playing, setPlaying] = useState<string | null>(null);
  const [playError, setPlayError] = useState<string | null>(null);
  const [loadingPlay, setLoadingPlay] = useState(false);

  async function play() {
    setLoadingPlay(true);
    setPlayError(null);
    const result = await playbackUrlFn({ data: { footageId: f.id } });
    setLoadingPlay(false);
    if (!result.ok) {
      setPlayError(failureMessage(result));
      return;
    }
    setPlaying(result.value.url);
  }

  const details =
    f.status === "ready" && f.durationS !== null
      ? [
          formatDuration(f.durationS),
          f.width && f.height ? `${f.width} × ${f.height}` : null,
          f.fpsNominal ? formatFps(f.fpsNominal) : null,
          f.codec ? f.codec.toUpperCase() : null,
          f.isVfr ? "variable frame rate" : null,
          f.rotationQuarterTurns ? `rotated ${f.rotationQuarterTurns * 90}°` : null,
        ].filter(Boolean)
      : [];

  return (
    <li aria-label={f.filename} className="border border-umber bg-soot px-5 py-4">
      <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-2">
        <div className="min-w-0">
          <p className="break-all font-instrument text-bone">{f.filename}</p>
          <p className="mt-1 text-parchment text-sm">
            <span className="font-display-sc tracking-[0.1em]">{footageRoles[f.role].label}</span>
            {" · "}
            {formatBytes(f.byteSize)}
          </p>
        </div>
        <p className="flex items-center gap-2 font-display-sc text-bone text-sm tracking-[0.12em]">
          <span
            aria-hidden="true"
            className={`size-2.5 ${
              f.status === "ready"
                ? "bg-verdigris"
                : f.status === "rejected"
                  ? "bg-oxblood ring-1 ring-bone/40"
                  : "bg-brass motion-safe:animate-pulse"
            }`}
          />
          {statusText[f.status]}
          {f.status === "probing" ? (
            <span className="sr-only">, check back in a moment</span>
          ) : null}
        </p>
      </div>
      {details.length > 0 ? (
        <p className="mt-2 font-instrument text-parchment text-sm">{details.join(" · ")}</p>
      ) : null}
      {f.status === "rejected" && f.rejectionReason ? (
        <p className="mt-3 border-oxblood border-l-2 pl-3 text-bone">{f.rejectionReason}</p>
      ) : null}
      {f.status === "uploading" ? (
        <p className="mt-2 text-parchment text-sm italic">
          Waiting for its upload to finish. If you closed the page mid-upload, choose the same file
          again to continue.
        </p>
      ) : null}
      {playing ? <PlaybackVideo url={playing} footage={f} /> : null}
      {playError ? (
        <div className="mt-3">
          <Banner tone="error" title={playError} />
        </div>
      ) : null}
      <div className="mt-3 flex gap-5">
        {f.status === "ready" && !playing ? (
          <Button
            variant="quiet"
            aria-label={`Play ${f.filename}`}
            onPress={play}
            isPending={loadingPlay}
          >
            Play
          </Button>
        ) : null}
        <RemoveFootage footage={f} onChanged={props.onChanged} />
      </div>
    </li>
  );
}

function PlaybackVideo(props: { url: string; footage: FootageView }) {
  const [unplayable, setUnplayable] = useState(false);
  if (unplayable) {
    return (
      <p className="mt-3 text-parchment text-sm">
        This browser cannot play {props.footage.codec?.toUpperCase() ?? "this"} video. The footage
        is stored and is analysed the same way.
      </p>
    );
  }
  return (
    // biome-ignore lint/a11y/useMediaCaption: footage of a machine has no speech to caption.
    <video
      src={props.url}
      controls
      preload="metadata"
      onError={() => setUnplayable(true)}
      className="mt-3 max-h-96 w-full bg-lampblack"
      aria-label={`Playback of ${props.footage.filename}`}
    />
  );
}

function RemoveFootage(props: { footage: FootageView; onChanged: () => Promise<void> }) {
  const [open, setOpen] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function remove(close: () => void) {
    setPending(true);
    setError(null);
    const result = await deleteFootageFn({ data: { footageId: props.footage.id } });
    setPending(false);
    if (!result.ok) {
      setError(failureMessage(result));
      return;
    }
    close();
    await props.onChanged();
  }
  return (
    <DialogTrigger isOpen={open} onOpenChange={setOpen}>
      <Button variant="quiet" aria-label={`Remove ${props.footage.filename}`}>
        Remove
      </Button>
      <Dialog title="Remove this footage?" caption={props.footage.filename} role="alertdialog">
        {(close) => (
          <div className="flex flex-col gap-5">
            {error ? <Banner tone="error" title={error} /> : null}
            <p className="text-lampblack">
              The file and anything measured from it will be deleted. This cannot be undone.
            </p>
            <div className="flex items-center gap-4">
              <Button onPress={() => remove(close)} isPending={pending}>
                Remove footage
              </Button>
              <Button variant="quiet" onPress={close}>
                Keep it
              </Button>
            </div>
          </div>
        )}
      </Dialog>
    </DialogTrigger>
  );
}

function SpecimenSkeleton() {
  return (
    <main id="main" className="mx-auto w-full max-w-5xl px-4 py-10 sm:px-10">
      <section
        aria-busy="true"
        aria-label="Loading specimen"
        className="h-96 border border-umber bg-soot motion-safe:animate-pulse"
      />
    </main>
  );
}
