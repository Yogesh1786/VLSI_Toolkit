// "Feedback" button in the top bar: a small dialog that sends a message (and optional rating,
// name and e-mail) to /api/feedback, where it is stored in the database.
import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { useLocation } from "react-router-dom";
import { CircleCheck, MessageSquareText, Send, Star, X } from "lucide-react";
import { postJSON } from "../lib/api";
import { Alert, Button, Field, TextInput } from "./ui";
import { cx } from "../lib/format";

export function FeedbackButton() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="flex items-center gap-2 rounded-lg border border-line bg-surface px-3 py-1.5 text-[13px] font-medium text-muted shadow-card hover:border-line-strong hover:text-fg"
        title="Send feedback"
      >
        <MessageSquareText className="size-4" />
        <span className="hidden md:inline">Feedback</span>
      </button>
      {/* rendered on <body>: the blurred sticky header would otherwise trap the fixed overlay */}
      {open && createPortal(<FeedbackDialog onClose={() => setOpen(false)} />, document.body)}
    </>
  );
}

function FeedbackDialog({ onClose }: { onClose: () => void }) {
  const { pathname } = useLocation();
  const [message, setMessage] = useState("");
  const [rating, setRating] = useState<number | null>(null);
  const [hover, setHover] = useState<number | null>(null);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState(false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const send = async () => {
    setSending(true);
    setError(null);
    try {
      await postJSON("/api/feedback", { message, rating, name, email, page: pathname });
      setSent(true);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSending(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/40 p-4 pt-[10vh] backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-label="Send feedback"
        className="w-full max-w-md overflow-hidden rounded-xl border border-line bg-surface shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-line px-5 py-3.5">
          <div className="flex items-center gap-2 font-semibold">
            <MessageSquareText className="size-4.5 text-brand" /> Send feedback
          </div>
          <button onClick={onClose} className="rounded-md p-1 text-faint hover:bg-surface-2 hover:text-fg" aria-label="Close">
            <X className="size-4.5" />
          </button>
        </div>

        {sent ? (
          <div className="flex flex-col items-center gap-3 px-6 py-10 text-center">
            <CircleCheck className="size-10 text-good" />
            <div className="text-[15px] font-semibold">Thank you!</div>
            <p className="text-[13px] text-muted">Your feedback was saved. It helps decide what to build next.</p>
            <Button onClick={onClose} className="mt-2">Close</Button>
          </div>
        ) : (
          <div className="space-y-4 px-5 py-5">
            <Field label="How useful is the toolkit?">
              <div className="flex gap-1" onMouseLeave={() => setHover(null)}>
                {[1, 2, 3, 4, 5].map((n) => (
                  <button
                    key={n}
                    onClick={() => setRating(rating === n ? null : n)}
                    onMouseEnter={() => setHover(n)}
                    aria-label={`${n} star${n > 1 ? "s" : ""}`}
                    className="rounded p-0.5"
                  >
                    <Star
                      className={cx(
                        "size-6 transition-colors",
                        (hover ?? rating ?? 0) >= n ? "fill-amber-400 text-amber-400" : "text-line-strong",
                      )}
                    />
                  </button>
                ))}
              </div>
            </Field>
            <Field label="Message" hint="What works, what's missing, which check you'd like next">
              <textarea
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                rows={4}
                maxLength={2000}
                autoFocus
                placeholder="e.g. The SDC checker found a typo in our constraints. Could it also check set_max_transition?"
                className="w-full resize-y rounded-lg border border-line bg-surface px-3 py-2 text-[13.5px] outline-none placeholder:text-faint focus:border-brand focus:ring-2 focus:ring-brand/20"
              />
            </Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Name (optional)">
                <TextInput value={name} onChange={setName} placeholder="Your name" />
              </Field>
              <Field label="E-mail (optional)">
                <TextInput value={email} onChange={setEmail} placeholder="for a reply" />
              </Field>
            </div>
            {error && <Alert tone="bad">{error}</Alert>}
            <div className="flex items-center justify-between gap-3 pt-1">
              <span className="text-[11.5px] text-faint">Only what you type here is stored.</span>
              <Button variant="primary" icon={Send} onClick={send} disabled={sending || message.trim().length < 3}>
                {sending ? "Sending…" : "Send"}
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
