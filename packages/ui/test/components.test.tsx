// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { Banner, Button, Plate, TextField } from "../src/index.ts";

afterEach(cleanup);

describe("components", () => {
  it("labels a plate by its title and shows the plate number in Roman form", () => {
    render(
      <Plate number={14} title="Sign in">
        <p>body</p>
      </Plate>,
    );
    expect(screen.getByRole("region", { name: "Sign in" })).toBeTruthy();
    expect(screen.getByText("Plate XIV")).toBeTruthy();
  });

  it("associates a text field's label and description with the input", () => {
    render(<TextField label="Email" description="We send a confirmation link." type="email" />);
    const input = screen.getByLabelText("Email");
    expect(input.getAttribute("type")).toBe("email");
    const describedBy = input.getAttribute("aria-describedby") ?? "";
    expect(document.getElementById(describedBy.split(" ")[0] ?? "")?.textContent).toBe(
      "We send a confirmation link.",
    );
  });

  it("announces errors assertively and other banners politely", () => {
    render(
      <>
        <Banner tone="error" title="That password is incorrect." />
        <Banner tone="success" title="Password changed." />
      </>,
    );
    expect(screen.getByRole("alert").textContent).toContain("That password is incorrect.");
    expect(screen.getByRole("status").textContent).toContain("Password changed.");
  });

  it("marks a pending button busy", () => {
    render(<Button isPending>Sign in</Button>);
    const button = screen.getByRole("button", { name: /Sign in/ });
    expect(button.getAttribute("aria-disabled")).toBe("true");
  });
});
