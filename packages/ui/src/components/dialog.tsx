import type { ReactNode } from "react";
import {
  Dialog as AriaDialog,
  DialogTrigger,
  Heading,
  Modal,
  ModalOverlay,
} from "react-aria-components";

export { DialogTrigger };

/**
 * A modal plate: bone paper laid over the dimmed desk. Focus is trapped and restored, Escape
 * closes it, and the title labels the dialog (React Aria).
 */
export function Dialog(props: {
  title: string;
  caption?: string | undefined;
  role?: "dialog" | "alertdialog";
  children: (close: () => void) => ReactNode;
  isOpen?: boolean;
  onOpenChange?: (open: boolean) => void;
}) {
  return (
    <ModalOverlay
      isDismissable={props.role !== "alertdialog"}
      {...(props.isOpen === undefined ? {} : { isOpen: props.isOpen })}
      {...(props.onOpenChange ? { onOpenChange: props.onOpenChange } : {})}
      className="fixed inset-0 z-50 flex items-center justify-center bg-lampblack/80 p-4 motion-safe:entering:animate-[fade-in_160ms_ease-out] motion-safe:exiting:animate-[fade-in_120ms_ease-in_reverse]"
    >
      <Modal className="paper w-full max-w-lg p-2.5">
        <AriaDialog role={props.role ?? "dialog"} className="outline-none">
          {({ close }) => (
            <div className="border-[1.5px] border-lampblack/80 p-1">
              <div className="border border-lampblack/40 px-6 pt-6 pb-7 sm:px-8">
                <Heading slot="title" className="font-display text-3xl text-lampblack">
                  {props.title}
                </Heading>
                {props.caption ? (
                  <p className="mt-1 font-display text-umber italic">{props.caption}</p>
                ) : null}
                <div className="mt-5">{props.children(close)}</div>
              </div>
            </div>
          )}
        </AriaDialog>
      </Modal>
    </ModalOverlay>
  );
}
