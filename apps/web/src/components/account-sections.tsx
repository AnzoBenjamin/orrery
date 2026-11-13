import {
  Banner,
  Button,
  Dialog,
  DialogTrigger,
  Form,
  SubmitButton,
  Switch,
  TextField,
} from "@orrery/ui";
import { useNavigate, useRouter } from "@tanstack/react-router";
import { type ReactNode, useState } from "react";
import { Meter } from "react-aria-components";
import {
  forgetDeviceFn,
  revokeOtherSessionsFn,
  revokeSessionFn,
  updatePreferencesFn,
} from "../functions/account.ts";
import { authClient, authErrorMessage } from "../lib/auth-client.ts";
import { formatBytes } from "../lib/format.ts";
import { failureMessage } from "../lib/result.ts";
import type { Result } from "../server/domain-errors.ts";
import type {
  AccountView,
  KnownDeviceView,
  PasskeyView,
  PreferencesView,
  SessionView,
} from "../server/operations/account.ts";

type Provider = "github" | "google";

const providerNames: Record<Provider, string> = { github: "GitHub", google: "Google" };

const isProvider = (id: string): id is Provider => id === "github" || id === "google";

// Times are shown in UTC so the server-rendered text matches what the browser hydrates.
const dateFormat = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "long",
  year: "numeric",
  timeZone: "UTC",
});
const dateTimeFormat = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  timeZone: "UTC",
  timeZoneName: "short",
});

function When(props: { iso: string; withTime?: boolean }) {
  const format = props.withTime ? dateTimeFormat : dateFormat;
  return <time dateTime={props.iso}>{format.format(new Date(props.iso))}</time>;
}

export function SectionHeading(props: { id: string; children: ReactNode }) {
  return (
    <h2
      id={props.id}
      className="mb-5 border-lampblack/40 border-b pb-2 font-display-sc text-2xl text-lampblack tracking-[0.08em]"
    >
      {props.children}
    </h2>
  );
}

function Row(props: { title: string; detail: ReactNode; action?: ReactNode; label?: string }) {
  return (
    <li
      aria-label={props.label ?? props.title}
      className="flex flex-wrap items-center justify-between gap-x-6 gap-y-2 border-lampblack/20 border-b py-3 last:border-b-0"
    >
      <div className="min-w-0">
        <p className="font-display text-lampblack text-lg">{props.title}</p>
        <div className="text-sm text-umber">{props.detail}</div>
      </div>
      {props.action ? <div className="flex items-center gap-5">{props.action}</div> : null}
    </li>
  );
}

/** Runs an action that reloads the page data on success and reports failures in one banner. */
function useAction() {
  const router = useRouter();
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  async function run(key: string, action: () => Promise<string | null>) {
    setPending(key);
    setError(null);
    const failure = await action();
    if (failure) {
      setPending(null);
      setError(failure);
      return false;
    }
    await router.invalidate();
    setPending(null);
    return true;
  }
  return { pending, error, run };
}

export function SignInMethodsSection(props: {
  account: AccountView;
  configured: Record<Provider, boolean>;
}) {
  const { account } = props;
  const { pending, error, run } = useAction();
  const linked = new Map(
    account.providers.filter((p) => isProvider(p.providerId)).map((p) => [p.providerId, p]),
  );
  const shown = (["github", "google"] as const).filter((p) => props.configured[p] || linked.has(p));
  // Better Auth refuses to unlink the last linked account; passkeys do not count toward it.
  const accountCount = account.providers.length + (account.hasPassword ? 1 : 0);

  async function link(provider: Provider) {
    await run(`link-${provider}`, async () => {
      const { error: failure } = await authClient.linkSocial({
        provider,
        callbackURL: "/account",
        errorCallbackURL: "/account",
      });
      return failure ? authErrorMessage(failure) : null;
    });
  }

  async function unlink(provider: Provider, accountId: string) {
    await run(`unlink-${provider}`, async () => {
      const { error: failure } = await authClient.unlinkAccount({ accountId });
      return failure ? authErrorMessage(failure) : null;
    });
  }

  return (
    <section aria-labelledby="methods-title">
      <SectionHeading id="methods-title">Ways to sign in</SectionHeading>
      <div className="flex flex-col gap-4">
        {error ? <Banner tone="error" title={error} /> : null}
        <ul aria-label="Sign-in methods">
          <Row
            title="Email and password"
            detail={
              account.hasPassword
                ? "Set. Change it with “Forgot your password?” on the sign-in page."
                : "Not set. Use “Forgot your password?” on the sign-in page to set one."
            }
          />
          {shown.map((provider) => {
            const record = linked.get(provider);
            const name = providerNames[provider];
            return (
              <Row
                key={provider}
                title={name}
                detail={
                  record ? (
                    <>
                      Linked <When iso={record.linkedAt} />
                    </>
                  ) : (
                    "Not linked"
                  )
                }
                action={
                  record ? (
                    <Button
                      variant="quiet"
                      aria-label={`Unlink ${name}`}
                      onPress={() => unlink(provider, record.id)}
                      isPending={pending === `unlink-${provider}`}
                      isDisabled={accountCount <= 1}
                    >
                      Unlink
                    </Button>
                  ) : (
                    <Button
                      variant="secondary"
                      aria-label={`Link ${name}`}
                      onPress={() => link(provider)}
                      isPending={pending === `link-${provider}`}
                    >
                      Link
                    </Button>
                  )
                }
              />
            );
          })}
        </ul>
        {accountCount <= 1 && linked.size > 0 ? (
          <p className="o-description">
            Your only linked account cannot be unlinked. Set a password or link another provider
            first.
          </p>
        ) : null}
        <Passkeys passkeys={account.passkeys} />
      </div>
    </section>
  );
}

function Passkeys(props: { passkeys: PasskeyView[] }) {
  const { pending, error, run } = useAction();
  const [adding, setAdding] = useState(false);

  async function remove(passkey: PasskeyView, close: () => void) {
    const ok = await run(`remove-${passkey.id}`, async () => {
      const { error: failure } = await authClient.passkey.deletePasskey({ id: passkey.id });
      return failure ? authErrorMessage(failure) : null;
    });
    if (ok) close();
  }

  return (
    <div className="mt-4 flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h3 className="font-display text-xl text-lampblack">Passkeys</h3>
        <DialogTrigger isOpen={adding} onOpenChange={setAdding}>
          <Button variant="secondary">Add a passkey</Button>
          <Dialog
            title="Add a passkey"
            caption="Sign in with this device's fingerprint, face, or screen lock."
          >
            {(close) => <AddPasskeyForm close={close} />}
          </Dialog>
        </DialogTrigger>
      </div>
      {error ? <Banner tone="error" title={error} /> : null}
      {props.passkeys.length === 0 ? (
        <p className="text-umber">
          No passkeys yet. A passkey lets you sign in with your device's screen lock instead of a
          password, and cannot be phished.
        </p>
      ) : (
        <ul aria-label="Passkeys">
          {props.passkeys.map((p, i) => {
            const name = p.name || `Passkey ${i + 1}`;
            return (
              <Row
                key={p.id}
                title={name}
                detail={
                  <>
                    {p.synced ? "Synced across your devices" : "Kept on one device"}
                    {p.createdAt ? (
                      <>
                        {" · added "}
                        <When iso={p.createdAt} />
                      </>
                    ) : null}
                  </>
                }
                action={
                  <DialogTrigger>
                    <Button variant="quiet" aria-label={`Remove ${name}`}>
                      Remove
                    </Button>
                    <Dialog title="Remove this passkey?" caption={name} role="alertdialog">
                      {(close) => (
                        <div className="flex flex-col gap-5">
                          <p className="text-lampblack">
                            You will no longer be able to sign in with it. The credential stays on
                            your device until you delete it there too.
                          </p>
                          <div className="flex items-center gap-4">
                            <Button
                              onPress={() => remove(p, close)}
                              isPending={pending === `remove-${p.id}`}
                            >
                              Remove passkey
                            </Button>
                            <Button variant="quiet" onPress={close}>
                              Keep it
                            </Button>
                          </div>
                        </div>
                      )}
                    </Dialog>
                  </DialogTrigger>
                }
              />
            );
          })}
        </ul>
      )}
    </div>
  );
}

function AddPasskeyForm(props: { close: () => void }) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const name = String(new FormData(event.currentTarget).get("name") ?? "").trim();
    setPending(true);
    setError(null);
    const result = await authClient.passkey.addPasskey(name ? { name } : {});
    if (result?.error) {
      setPending(false);
      setError(authErrorMessage(result.error));
      return;
    }
    await router.invalidate();
    setPending(false);
    props.close();
  }

  return (
    <Form onSubmit={onSubmit}>
      {error ? <Banner tone="error" title={error} /> : null}
      <TextField
        label="Name"
        name="name"
        maxLength={60}
        description="So you can tell your passkeys apart, such as “Workshop laptop”. Optional."
      />
      <div className="flex items-center gap-4">
        <SubmitButton isPending={pending}>Create passkey</SubmitButton>
        <Button variant="quiet" onPress={props.close}>
          Cancel
        </Button>
      </div>
    </Form>
  );
}

export function SessionsSection(props: { sessions: SessionView[] }) {
  const { pending, error, run } = useAction();
  const others = props.sessions.filter((s) => !s.current);

  return (
    <section aria-labelledby="sessions-title" id="sessions">
      <SectionHeading id="sessions-title">Where you are signed in</SectionHeading>
      <div className="flex flex-col gap-4">
        {error ? <Banner tone="error" title={error} /> : null}
        <ul aria-label="Sessions">
          {props.sessions.map((s) => {
            const device = s.device ?? "Unknown browser";
            return (
              <Row
                key={s.id}
                title={device}
                label={s.current ? `${device}, this device` : device}
                detail={
                  <>
                    {s.ipAddress ? <span className="font-instrument">{s.ipAddress} · </span> : null}
                    signed in <When iso={s.signedInAt} withTime />
                    {" · last active "}
                    <When iso={s.lastActiveAt} withTime />
                  </>
                }
                action={
                  s.current ? (
                    <span className="o-tag text-sm">This device</span>
                  ) : (
                    <Button
                      variant="quiet"
                      aria-label={`Sign out ${device}`}
                      isPending={pending === s.id}
                      onPress={() =>
                        run(s.id, async () => {
                          const result = await revokeSessionFn({ data: { sessionId: s.id } });
                          return failureMessage(result);
                        })
                      }
                    >
                      Sign out
                    </Button>
                  )
                }
              />
            );
          })}
        </ul>
        {others.length > 0 ? (
          <div>
            <Button
              variant="secondary"
              isPending={pending === "others"}
              onPress={() =>
                run("others", async () => failureMessage(await revokeOtherSessionsFn({ data: {} })))
              }
            >
              Sign out everywhere else
            </Button>
          </div>
        ) : (
          <p className="o-description">This is the only place you are signed in.</p>
        )}
      </div>
    </section>
  );
}

/**
 * Devices and networks the account has signed in from. A sign-in from anywhere else emails a
 * new sign-in alert; forgetting an entry makes the next sign-in from it alert again.
 */
export function KnownDevicesSection(props: { devices: KnownDeviceView[] }) {
  const { pending, error, run } = useAction();
  return (
    <section aria-labelledby="devices-title">
      <SectionHeading id="devices-title">Devices we recognize</SectionHeading>
      <div className="flex flex-col gap-4">
        <p className="o-description">
          When your account is used from a device or network not listed here, we email you. Forget
          an entry to be told the next time it signs in.
        </p>
        {error ? <Banner tone="error" title={error} /> : null}
        {props.devices.length > 0 ? (
          <ul aria-label="Recognized devices">
            {props.devices.map((d) => {
              const label = `${d.device}, network ${d.network}`;
              return (
                <Row
                  key={d.id}
                  title={d.device}
                  label={label}
                  detail={
                    <>
                      <span className="font-instrument">Network {d.network}</span>
                      {" · first seen "}
                      <When iso={d.firstSeenAt} withTime />
                      {" · last seen "}
                      <When iso={d.lastSeenAt} withTime />
                    </>
                  }
                  action={
                    <Button
                      variant="quiet"
                      aria-label={`Forget ${label}`}
                      isPending={pending === d.id}
                      onPress={() =>
                        run(d.id, async () =>
                          failureMessage(await forgetDeviceFn({ data: { deviceId: d.id } })),
                        )
                      }
                    >
                      Forget
                    </Button>
                  }
                />
              );
            })}
          </ul>
        ) : (
          <p className="text-lampblack">
            No devices yet. The next place you sign in from is remembered without an email.
          </p>
        )}
      </div>
    </section>
  );
}

export function StorageSection(props: {
  usage: Result<{ usedBytes: number; quotaBytes: number }>;
}) {
  const { usage } = props;
  return (
    <section aria-labelledby="storage-title">
      <SectionHeading id="storage-title">Storage</SectionHeading>
      {usage.ok ? (
        <div className="flex flex-col gap-2">
          <Meter
            aria-label="Footage storage used"
            value={usage.value.usedBytes}
            maxValue={usage.value.quotaBytes}
            className="flex flex-col gap-2"
          >
            {({ percentage }) => (
              <>
                <p className="text-lampblack">
                  <span className="font-instrument">{formatBytes(usage.value.usedBytes)}</span> of{" "}
                  <span className="font-instrument">{formatBytes(usage.value.quotaBytes)}</span>{" "}
                  used by footage
                </p>
                <div className="h-2 w-full shadow-[inset_0_0_0_1px_rgb(14_13_11/0.6)]">
                  <div className="h-full bg-lampblack" style={{ width: `${percentage}%` }} />
                </div>
              </>
            )}
          </Meter>
          <p className="o-description">
            Uploads that would pass the limit are refused. Removing footage frees its space.
          </p>
        </div>
      ) : (
        <Banner tone="error" title={failureMessage(usage) ?? "Storage use could not be read."} />
      )}
    </section>
  );
}

export function PreferencesSection(props: { preferences: PreferencesView }) {
  const [analysisEmail, setAnalysisEmail] = useState(props.preferences.analysisCompleteEmail);
  const [status, setStatus] = useState<{ tone: "saved" | "error"; text: string } | null>(null);
  const [saving, setSaving] = useState(false);

  async function change(next: boolean) {
    const previous = analysisEmail;
    setAnalysisEmail(next);
    setSaving(true);
    setStatus(null);
    const result = await updatePreferencesFn({ data: { analysisCompleteEmail: next } });
    setSaving(false);
    if (!result.ok) {
      setAnalysisEmail(previous);
      setStatus({ tone: "error", text: failureMessage(result) ?? "The change was not saved." });
      return;
    }
    setAnalysisEmail(result.value.analysisCompleteEmail);
    setStatus({ tone: "saved", text: "Saved." });
  }

  return (
    <section aria-labelledby="preferences-title">
      <SectionHeading id="preferences-title">Correspondence</SectionHeading>
      <div className="flex flex-col gap-4">
        <Switch
          isSelected={analysisEmail}
          onChange={change}
          isDisabled={saving}
          description="When the engine finishes reconstructing a specimen, we send a link to the result. Account and security emails are always sent."
        >
          Email me when an analysis finishes
        </Switch>
        {status?.tone === "error" ? <Banner tone="error" title={status.text} /> : null}
        <p role="status" className="o-description min-h-5">
          {status?.tone === "saved" ? status.text : ""}
        </p>
      </div>
    </section>
  );
}

export function DeleteAccountSection(props: { email: string; hasPassword: boolean }) {
  const [open, setOpen] = useState(false);
  return (
    <section aria-labelledby="delete-title">
      <SectionHeading id="delete-title">Delete account</SectionHeading>
      <p className="text-lampblack">
        Deleting your account destroys every specimen in your cabinet, all footage, and everything
        reconstructed from it. Shared links stop working. This cannot be undone.
      </p>
      <div className="mt-5">
        <DialogTrigger isOpen={open} onOpenChange={setOpen}>
          <Button variant="secondary">Delete account</Button>
          <Dialog title="Delete your account?" caption={props.email} role="alertdialog">
            {(close) => (
              <DeleteAccountForm
                email={props.email}
                hasPassword={props.hasPassword}
                close={close}
              />
            )}
          </Dialog>
        </DialogTrigger>
      </div>
    </section>
  );
}

function DeleteAccountForm(props: { email: string; hasPassword: boolean; close: () => void }) {
  const navigate = useNavigate();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setError(null);
    let password: string | undefined;
    if (props.hasPassword) {
      password = String(form.get("password") ?? "");
    } else if (
      String(form.get("confirmEmail") ?? "")
        .trim()
        .toLowerCase() !== props.email.toLowerCase()
    ) {
      setError("Type your email address exactly as shown to confirm.");
      return;
    }
    setPending(true);
    const { error: failure } = await authClient.deleteUser(password ? { password } : {});
    if (failure) {
      setPending(false);
      setError(authErrorMessage(failure));
      return;
    }
    await navigate({ to: "/sign-in", search: { deleted: "1" } });
  }

  return (
    <Form onSubmit={onSubmit}>
      {error ? <Banner tone="error" title={error} /> : null}
      <p className="text-lampblack">
        Every specimen, all footage, and every reconstruction will be destroyed.
      </p>
      {props.hasPassword ? (
        <TextField
          label="Password"
          name="password"
          type="password"
          autoComplete="current-password"
          isRequired
          description="Enter your password to confirm."
        />
      ) : (
        <TextField
          label="Your email address"
          name="confirmEmail"
          type="email"
          autoComplete="off"
          isRequired
          description="Type it to confirm."
        />
      )}
      <div className="flex items-center gap-4">
        <SubmitButton isPending={pending}>Delete everything</SubmitButton>
        <Button variant="quiet" onPress={props.close}>
          Keep my account
        </Button>
      </div>
    </Form>
  );
}
