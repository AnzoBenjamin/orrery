import type { JobSummary } from "@orrery/jobs";
import { Banner, Button } from "@orrery/ui";
import { createFileRoute, useRouter } from "@tanstack/react-router";
import { useState } from "react";
import { adminOverviewFn, cancelJobFn, retryJobFn } from "../../functions/admin.ts";
import { failureMessage } from "../../lib/result.ts";

export const Route = createFileRoute("/_app/admin")({
  head: () => ({ meta: [{ title: "Operator · Orrery" }] }),
  loader: () => adminOverviewFn({ data: {} }),
  component: Operator,
});

const timeFormat = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  timeZone: "UTC",
  timeZoneName: "short",
});
const at = (iso: string | null) => (iso ? timeFormat.format(new Date(iso)) : "—");

/** The operator page (requirement 7.4): queue depth, running jobs, recent failures. */
function Operator() {
  const overview = Route.useLoaderData();
  const router = useRouter();

  if (!overview.ok) {
    return (
      <main id="main" className="mx-auto w-full max-w-5xl px-4 py-12 sm:px-10">
        <Banner tone="error" title={failureMessage(overview) ?? "This page could not be opened."} />
      </main>
    );
  }
  const { queues, running, failed } = overview.value;

  return (
    <main id="main" className="mx-auto w-full max-w-6xl px-4 py-10 sm:px-10">
      <div className="mb-8 flex flex-wrap items-end justify-between gap-6 border-umber border-b pb-6">
        <div>
          <p className="font-display-sc text-parchment text-sm tracking-[0.22em]">
            The engine room
          </p>
          <h1 className="mt-1 font-display text-5xl text-bone">Operator</h1>
        </div>
        <Button variant="secondary" onPress={() => router.invalidate()}>
          Refresh
        </Button>
      </div>

      <section aria-labelledby="queues-title">
        <h2 id="queues-title" className="mb-3 font-display text-2xl text-bone">
          Queues
        </h2>
        <table className="w-full border-collapse font-instrument text-sm">
          <thead>
            <tr className="border-umber border-b text-left text-parchment">
              <th scope="col" className="py-2 pr-4 font-normal">
                Queue
              </th>
              <th scope="col" className="py-2 pr-4 text-right font-normal">
                Waiting
              </th>
              <th scope="col" className="py-2 pr-4 text-right font-normal">
                Scheduled
              </th>
              <th scope="col" className="py-2 pr-4 text-right font-normal">
                Running
              </th>
              <th scope="col" className="py-2 text-right font-normal">
                Failed
              </th>
            </tr>
          </thead>
          <tbody>
            {queues.map((q) => (
              <tr key={q.name} className="border-umber/60 border-b text-bone">
                <th scope="row" className="py-2 pr-4 text-left font-normal">
                  {q.name}
                </th>
                <td className="py-2 pr-4 text-right">{q.queued}</td>
                <td className="py-2 pr-4 text-right">{q.deferred}</td>
                <td className="py-2 pr-4 text-right">{q.active}</td>
                <td className={`py-2 text-right ${q.failed > 0 ? "text-brass-bright" : ""}`}>
                  {q.failed}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <JobTable
        id="running"
        title="Running"
        empty="Nothing is running."
        jobs={running}
        action="cancel"
      />
      <JobTable
        id="failed"
        title="Recent failures"
        empty="No failed jobs are retained."
        jobs={failed}
        action="retry"
      />
    </main>
  );
}

function JobTable(props: {
  id: string;
  title: string;
  empty: string;
  jobs: JobSummary[];
  action: "retry" | "cancel";
}) {
  const router = useRouter();
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function act(job: JobSummary) {
    setPending(job.id);
    setError(null);
    const fn = props.action === "retry" ? retryJobFn : cancelJobFn;
    const result = await fn({ data: { queue: job.queue, jobId: job.id } });
    setPending(null);
    if (!result.ok) {
      setError(failureMessage(result));
      return;
    }
    await router.invalidate();
  }

  return (
    <section aria-labelledby={`${props.id}-title`} className="mt-10">
      <h2 id={`${props.id}-title`} className="mb-3 font-display text-2xl text-bone">
        {props.title}
      </h2>
      {error ? (
        <div className="mb-3">
          <Banner tone="error" title={error} />
        </div>
      ) : null}
      {props.jobs.length === 0 ? (
        <p className="text-parchment">{props.empty}</p>
      ) : (
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-umber border-b text-left text-parchment">
              <th scope="col" className="py-2 pr-4 font-normal">
                Job
              </th>
              <th scope="col" className="py-2 pr-4 font-normal">
                Attempts
              </th>
              <th scope="col" className="py-2 pr-4 font-normal">
                {props.action === "retry" ? "Failed at" : "Started at"}
              </th>
              <th scope="col" className="py-2 pr-4 font-normal">
                Error
              </th>
              <th scope="col" className="py-2 font-normal">
                <span className="sr-only">Action</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {props.jobs.map((job) => (
              <tr key={job.id} className="border-umber/60 border-b align-top text-bone">
                <th scope="row" className="py-2 pr-4 text-left font-normal">
                  <span className="block font-instrument">{job.queue}</span>
                  <span className="block font-instrument text-parchment text-xs">{job.id}</span>
                </th>
                <td className="py-2 pr-4 font-instrument">
                  {job.attempts} / {job.retryLimit + 1}
                </td>
                <td className="py-2 pr-4 font-instrument">
                  {at(props.action === "retry" ? job.finishedAt : job.startedAt)}
                </td>
                <td className="max-w-md break-words py-2 pr-4">{job.error ?? "—"}</td>
                <td className="py-2 text-right">
                  <Button
                    variant="quiet"
                    aria-label={`${props.action === "retry" ? "Retry" : "Cancel"} ${job.queue} job ${job.id}`}
                    onPress={() => act(job)}
                    isPending={pending === job.id}
                  >
                    {props.action === "retry" ? "Retry" : "Cancel"}
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
