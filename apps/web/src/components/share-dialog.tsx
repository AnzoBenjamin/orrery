import { Banner, Button, Dialog, DialogTrigger, Radio, RadioGroup } from "@orrery/ui";
import { useEffect, useState } from "react";
import { createShareFn, listSharesFn, revokeShareFn } from "../functions/shares.ts";
import { failureMessage } from "../lib/result.ts";
import type { ShareLinkView } from "../server/operations/shares.ts";

const dateFormat = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  year: "numeric",
  timeZone: "UTC",
});
const day = (iso: string) => dateFormat.format(new Date(iso));

const expiryChoices = { never: undefined, week: 7, month: 30 } as const;
type Expiry = keyof typeof expiryChoices;

/** Create, copy, and revoke read-only links to a specimen (workbench requirement 12.1). */
export function ShareButton(props: { specimenId: string; title: string }) {
  const [open, setOpen] = useState(false);
  return (
    <DialogTrigger isOpen={open} onOpenChange={setOpen}>
      <Button variant="secondary">Share</Button>
      <Dialog title="Share this specimen" caption={props.title}>
        {() => <ShareManager specimenId={props.specimenId} />}
      </Dialog>
    </DialogTrigger>
  );
}

function ShareManager(props: { specimenId: string }) {
  const [links, setLinks] = useState<ShareLinkView[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [expiry, setExpiry] = useState<Expiry>("month");
  const [created, setCreated] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    const result = await listSharesFn({ data: { specimenId: props.specimenId } });
    if (!result.ok) {
      setLoadError(failureMessage(result));
      return;
    }
    setLoadError(null);
    setLinks(result.value);
  }
  // biome-ignore lint/correctness/useExhaustiveDependencies: load once when the dialog opens.
  useEffect(() => {
    void load();
  }, []);

  async function create() {
    setPending("create");
    setError(null);
    setCopied(false);
    const days = expiryChoices[expiry];
    const result = await createShareFn({
      data: days
        ? { specimenId: props.specimenId, expiresInDays: days }
        : { specimenId: props.specimenId },
    });
    setPending(null);
    if (!result.ok) {
      setError(failureMessage(result));
      return;
    }
    setCreated(`${window.location.origin}/s/${result.value.token}`);
    await load();
  }

  async function revoke(id: string) {
    setPending(id);
    setError(null);
    const result = await revokeShareFn({ data: { shareLinkId: id } });
    setPending(null);
    if (!result.ok) {
      setError(failureMessage(result));
      return;
    }
    await load();
  }

  async function copy() {
    if (!created) return;
    await navigator.clipboard.writeText(created);
    setCopied(true);
  }

  return (
    <div className="flex flex-col gap-5">
      <p className="text-lampblack">
        Anyone with a link can view this specimen and play its checked footage without signing in.
        They cannot change anything.
      </p>
      {error ? <Banner tone="error" title={error} /> : null}
      <RadioGroup label="The link works" value={expiry} onChange={(v) => setExpiry(v as Expiry)}>
        <Radio value="week">For 7 days</Radio>
        <Radio value="month">For 30 days</Radio>
        <Radio value="never">Until revoked</Radio>
      </RadioGroup>
      <div>
        <Button onPress={create} isPending={pending === "create"}>
          Create link
        </Button>
      </div>
      {created ? (
        <div className="flex flex-col gap-2 border-lampblack/40 border-y py-3">
          <label htmlFor="new-share-link" className="o-label">
            New link
          </label>
          <input
            id="new-share-link"
            readOnly
            value={created}
            onFocus={(e) => e.currentTarget.select()}
            className="o-input text-sm"
          />
          <div className="flex items-center gap-4">
            <Button variant="secondary" onPress={copy}>
              Copy link
            </Button>
            <p role="status" className="o-description">
              {copied ? "Copied." : "Copy it now: it is shown only once."}
            </p>
          </div>
        </div>
      ) : null}
      <div>
        <h3 className="font-display text-lampblack text-xl">Links</h3>
        {loadError ? (
          <Banner tone="error" title={loadError} />
        ) : links === null ? (
          <p className="text-umber" aria-busy="true">
            Loading links…
          </p>
        ) : links.length === 0 ? (
          <p className="text-umber">No links yet.</p>
        ) : (
          <ul aria-label="Share links" className="mt-2">
            {links.map((l) => (
              <li
                key={l.id}
                aria-label={`Link created ${day(l.createdAt)}`}
                className="flex flex-wrap items-center justify-between gap-3 border-lampblack/20 border-b py-2 last:border-b-0"
              >
                <div className="text-sm">
                  <p className="text-lampblack">
                    Created {day(l.createdAt)}
                    {l.revokedAt
                      ? ` · revoked ${day(l.revokedAt)}`
                      : !l.active && l.expiresAt
                        ? ` · expired ${day(l.expiresAt)}`
                        : l.expiresAt
                          ? ` · works until ${day(l.expiresAt)}`
                          : " · works until revoked"}
                  </p>
                  <p className="text-umber">
                    {l.lastUsedAt ? `Last opened ${day(l.lastUsedAt)}` : "Not opened yet"}
                  </p>
                </div>
                {l.active ? (
                  <Button
                    variant="quiet"
                    aria-label={`Revoke link created ${day(l.createdAt)}`}
                    onPress={() => revoke(l.id)}
                    isPending={pending === l.id}
                  >
                    Revoke
                  </Button>
                ) : (
                  <span className="font-display-sc text-sm text-umber tracking-[0.1em]">
                    Inactive
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
