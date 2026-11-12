// TSX files here declare the automatic JSX runtime with pragmas, so they compile the same in
// every consumer (Vite, esbuild, tsx) regardless of which tsconfig that consumer applies.
export { type RenderedEmail, renderEmail } from "./render.tsx";
export { createMailer, type Mailer, type MailerConfig } from "./send.ts";
