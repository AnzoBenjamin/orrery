import { GenericContainer, type StartedTestContainer, Wait } from "testcontainers";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { createMailer } from "../src/index.ts";

/** Same image as infra/compose.yaml. */
const MAILPIT_IMAGE =
  "axllent/mailpit:v1.33.1@sha256:aef2aacc11f075ec0fb6874275ee4a421e688e11a96ebb296134d1735c7761ce";

let mailpit: StartedTestContainer;
let api: string;

beforeAll(async () => {
  mailpit = await new GenericContainer(MAILPIT_IMAGE)
    .withExposedPorts(1025, 8025)
    .withWaitStrategy(Wait.forHttp("/readyz", 8025))
    .start();
  api = `http://${mailpit.getHost()}:${mailpit.getMappedPort(8025)}/api/v1`;
}, 120_000);

afterAll(async () => {
  await mailpit?.stop();
});

describe("mailer", () => {
  it("delivers a rendered message over SMTP with both parts", async () => {
    const mailer = createMailer({
      host: mailpit.getHost(),
      port: mailpit.getMappedPort(1025),
      secure: false,
      from: "Orrery <mail@orrery.test>",
    });
    try {
      await mailer.verify();
      await mailer.send({
        template: "reset-password",
        to: "grace@orrery.test",
        name: "Grace",
        url: "https://orrery.test/reset?token=abc",
      });
    } finally {
      mailer.close();
    }

    const list = (await (await fetch(`${api}/messages`)).json()) as {
      messages: { ID: string; Subject: string; To: { Address: string; Name: string }[] }[];
    };
    const sent = list.messages.find((m) => m.To[0]?.Address === "grace@orrery.test");
    expect(sent?.Subject).toBe("Reset your Orrery password");
    expect(sent?.To[0]?.Name).toBe("Grace");

    const full = (await (await fetch(`${api}/message/${sent?.ID}`)).json()) as {
      HTML: string;
      Text: string;
      From: { Address: string };
    };
    expect(full.From.Address).toBe("mail@orrery.test");
    expect(full.HTML).toContain("https://orrery.test/reset?token=abc");
    expect(full.Text).toContain("https://orrery.test/reset?token=abc");
  });
});
