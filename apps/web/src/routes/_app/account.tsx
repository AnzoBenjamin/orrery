import { Banner, Plate } from "@orrery/ui";
import { createFileRoute } from "@tanstack/react-router";
import {
  DeleteAccountSection,
  PreferencesSection,
  SectionHeading,
  SessionsSection,
  SignInMethodsSection,
  StorageSection,
} from "../../components/account-sections.tsx";
import { getAccountFn } from "../../functions/account.ts";
import { getStorageUsageFn } from "../../functions/footage.ts";
import { failureMessage } from "../../lib/result.ts";
import { getAuthMethods } from "../../server/auth-methods.ts";

export const Route = createFileRoute("/_app/account")({
  head: () => ({ meta: [{ title: "Account · Orrery" }] }),
  loader: async () => {
    const [account, methods, usage] = await Promise.all([
      getAccountFn({ data: {} }),
      getAuthMethods(),
      getStorageUsageFn({ data: {} }),
    ]);
    return { account, methods, usage };
  },
  pendingComponent: AccountSkeleton,
  component: Account,
});

function Account() {
  const { session } = Route.useRouteContext();
  const { account, methods, usage } = Route.useLoaderData();
  return (
    <main id="main" className="mx-auto w-full max-w-3xl px-4 py-12">
      <Plate number={5} title="Account" caption={session.user.name}>
        <div className="flex flex-col gap-12">
          <section aria-labelledby="particulars-title">
            <SectionHeading id="particulars-title">Particulars</SectionHeading>
            <dl className="grid grid-cols-[max-content_1fr] gap-x-8 gap-y-3">
              <dt className="font-display-sc text-umber tracking-[0.08em]">Name</dt>
              <dd className="text-lampblack">{session.user.name}</dd>
              <dt className="font-display-sc text-umber tracking-[0.08em]">Email</dt>
              <dd className="break-all font-instrument text-lampblack">{session.user.email}</dd>
              <dt className="font-display-sc text-umber tracking-[0.08em]">Status</dt>
              <dd className="text-lampblack">
                {session.user.emailVerified ? "Email confirmed" : "Email not yet confirmed"}
              </dd>
            </dl>
          </section>
          {account.ok ? (
            <>
              <SignInMethodsSection account={account.value} configured={methods} />
              <SessionsSection sessions={account.value.sessions} />
              <StorageSection usage={usage} />
              <PreferencesSection preferences={account.value.preferences} />
              <DeleteAccountSection
                email={session.user.email}
                hasPassword={account.value.hasPassword}
              />
            </>
          ) : (
            <Banner
              tone="error"
              title={failureMessage(account) ?? "Your account settings could not be loaded."}
            >
              Reload the page to try again.
            </Banner>
          )}
        </div>
      </Plate>
    </main>
  );
}

function AccountSkeleton() {
  return (
    <main id="main" className="mx-auto w-full max-w-3xl px-4 py-12">
      <section
        aria-busy="true"
        aria-label="Loading account settings"
        className="h-[40rem] border border-umber bg-soot motion-safe:animate-pulse"
      />
    </main>
  );
}
