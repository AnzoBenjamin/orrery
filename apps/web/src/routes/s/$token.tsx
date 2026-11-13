import { Banner, Button, Plate } from "@orrery/ui";
import { createFileRoute, Link } from "@tanstack/react-router";
import { useState } from "react";
import { openShareFn, sharePlaybackFn } from "../../functions/shares.ts";
import { footageRoles } from "../../lib/footage-roles.ts";
import { formatDuration, formatFps } from "../../lib/format.ts";
import { failureMessage } from "../../lib/result.ts";
import type { FootageView } from "../../server/operations/footage.ts";

/**
 * A specimen opened through a read-only share link, without signing in (workbench requirement
 * 12.2). The read-only workbench replaces the footage list here once the workbench exists.
 */
export const Route = createFileRoute("/s/$token")({
  loader: ({ params }) => openShareFn({ data: { token: params.token } }),
  head: ({ loaderData }) => ({
    meta: [
      { title: loaderData?.ok ? `${loaderData.value.title} · Orrery` : "Shared specimen · Orrery" },
      // The token is the credential: never send it onward in a Referer header or to a crawler.
      { name: "referrer", content: "no-referrer" },
      { name: "robots", content: "noindex, nofollow" },
    ],
  }),
  component: SharedSpecimen,
});

function SharedSpecimen() {
  const shared = Route.useLoaderData();
  const { token } = Route.useParams();
  return (
    <div className="desk lamp-light flex min-h-dvh flex-col text-bone">
      <header className="flex items-center justify-between border-umber border-b px-6 py-4 sm:px-10">
        <Link
          to="/"
          className="font-display-sc text-bone text-xl tracking-[0.32em] hover:text-brass-bright"
        >
          Orrery
        </Link>
        <Link to="/sign-in" className="o-link font-display italic">
          Sign in
        </Link>
      </header>
      <main id="main" className="mx-auto w-full max-w-3xl px-4 py-12">
        {shared.ok ? (
          <Plate number={1} title={shared.value.title} caption="A shared specimen">
            <div className="flex flex-col gap-6">
              {shared.value.description ? (
                <p className="whitespace-pre-line font-display text-lg text-umber italic">
                  {shared.value.description}
                </p>
              ) : null}
              <section aria-labelledby="shared-footage-title">
                <h2
                  id="shared-footage-title"
                  className="mb-4 border-lampblack/40 border-b pb-2 font-display-sc text-2xl text-lampblack tracking-[0.08em]"
                >
                  Footage
                </h2>
                {shared.value.footage.length === 0 ? (
                  <p className="text-umber">No footage has been checked for this specimen yet.</p>
                ) : (
                  <ul aria-label="Footage" className="flex flex-col gap-4">
                    {shared.value.footage.map((f) => (
                      <SharedFootage key={f.id} footage={f} token={token} />
                    ))}
                  </ul>
                )}
              </section>
            </div>
          </Plate>
        ) : (
          <Plate number={1} title="Link unavailable">
            <div className="flex flex-col gap-4">
              <Banner
                tone="error"
                title={
                  shared.error.kind === "RateLimited"
                    ? shared.error.message
                    : "This link has expired, been revoked, or was copied incompletely."
                }
              />
              <p className="text-lampblack">Ask the person who shared it for a new link.</p>
            </div>
          </Plate>
        )}
      </main>
    </div>
  );
}

function SharedFootage(props: { footage: FootageView; token: string }) {
  const f = props.footage;
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [unplayable, setUnplayable] = useState(false);

  async function play() {
    setPending(true);
    setError(null);
    const result = await sharePlaybackFn({ data: { token: props.token, footageId: f.id } });
    setPending(false);
    if (!result.ok) {
      setError(failureMessage(result));
      return;
    }
    setUrl(result.value.url);
  }

  const details = [
    f.durationS !== null ? formatDuration(f.durationS) : null,
    f.width && f.height ? `${f.width} × ${f.height}` : null,
    f.fpsNominal ? formatFps(f.fpsNominal) : null,
  ].filter(Boolean);

  return (
    <li aria-label={f.filename} className="border border-lampblack/30 px-4 py-3">
      <p className="font-display text-lampblack text-lg">{footageRoles[f.role].label} footage</p>
      <p className="font-instrument text-sm text-umber">{details.join(" · ")}</p>
      {error ? (
        <div className="mt-2">
          <Banner tone="error" title={error} />
        </div>
      ) : null}
      {url ? (
        unplayable ? (
          <p className="mt-2 text-sm text-umber">
            This browser cannot play {f.codec?.toUpperCase() ?? "this"} video.
          </p>
        ) : (
          // biome-ignore lint/a11y/useMediaCaption: footage of a machine has no speech to caption.
          <video
            src={url}
            controls
            preload="metadata"
            onError={() => setUnplayable(true)}
            className="mt-3 max-h-96 w-full bg-lampblack"
            aria-label={`Playback of ${footageRoles[f.role].label.toLowerCase()} footage`}
          />
        )
      ) : (
        <div className="mt-2">
          <Button variant="quiet" onPress={play} isPending={pending}>
            Play
          </Button>
        </div>
      )}
    </li>
  );
}
