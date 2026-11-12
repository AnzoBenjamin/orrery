const MAILPIT = process.env.E2E_MAILPIT_URL ?? "http://localhost:58025";

interface Summary {
  ID: string;
  Subject: string;
  Created: string;
}

/**
 * Reads mail the stack actually sent, through Mailpit's API, so tests follow real verification
 * and reset links instead of bypassing them (requirement 13.3).
 */
export async function waitForEmail(
  to: string,
  options: { subject?: string; after?: Date; timeoutMs?: number } = {},
): Promise<{ subject: string; text: string; html: string }> {
  const deadline = Date.now() + (options.timeoutMs ?? 20_000);
  while (Date.now() < deadline) {
    const res = await fetch(`${MAILPIT}/api/v1/search?query=${encodeURIComponent(`to:"${to}"`)}`);
    if (!res.ok) throw new Error(`Mailpit search failed: ${res.status}`);
    const { messages } = (await res.json()) as { messages: Summary[] };
    const match = messages.find(
      (m) =>
        (!options.subject || m.Subject === options.subject) &&
        (!options.after || new Date(m.Created) >= options.after),
    );
    if (match) {
      const full = (await (await fetch(`${MAILPIT}/api/v1/message/${match.ID}`)).json()) as {
        Text: string;
        HTML: string;
      };
      return { subject: match.Subject, text: full.Text, html: full.HTML };
    }
    await new Promise((r) => setTimeout(r, 300));
  }
  throw new Error(
    `no email to ${to}${options.subject ? ` with subject "${options.subject}"` : ""}`,
  );
}

/** The first link in a message's plain-text part that contains `fragment`. */
export function linkIn(text: string, fragment: string): string {
  const link = text.match(/https?:\/\/\S+/g)?.find((l) => l.includes(fragment));
  if (!link) throw new Error(`no link containing ${fragment} in email`);
  return link;
}
