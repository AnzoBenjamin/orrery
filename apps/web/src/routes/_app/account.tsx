import { Plate } from "@orrery/ui";
import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/_app/account")({
  head: () => ({ meta: [{ title: "Account · Orrery" }] }),
  component: Account,
});

function Account() {
  const { session } = Route.useRouteContext();
  return (
    <main id="main" className="mx-auto w-full max-w-2xl px-4 py-12">
      <Plate number={5} title="Account" caption={session.user.name}>
        <dl className="grid grid-cols-[max-content_1fr] gap-x-8 gap-y-3">
          <dt className="font-display-sc text-umber tracking-[0.08em]">Name</dt>
          <dd className="text-lampblack">{session.user.name}</dd>
          <dt className="font-display-sc text-umber tracking-[0.08em]">Email</dt>
          <dd className="font-instrument text-lampblack">{session.user.email}</dd>
          <dt className="font-display-sc text-umber tracking-[0.08em]">Status</dt>
          <dd className="text-lampblack">
            {session.user.emailVerified ? "Email confirmed" : "Email not yet confirmed"}
          </dd>
        </dl>
      </Plate>
    </main>
  );
}
