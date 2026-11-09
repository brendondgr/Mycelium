"use client";

import { useQuery } from "@tanstack/react-query";
import * as React from "react";
import { ArrowUp, Square, X } from "lucide-react";

import { searchRefs } from "@/lib/portal/agent/client";
import type { RefSearchResult } from "@/lib/portal/agent/types";

import { splitItemTitle } from "./open-ref";

type Mention = { ref: string; title: string };

/** The `@word` being typed at the caret, if any. */
export function mentionQuery(text: string, caret: number): { start: number; q: string } | null {
  const before = text.slice(0, caret);
  const at = before.lastIndexOf("@");
  if (at < 0) return null;
  if (at > 0 && !/\s/.test(before[at - 1])) return null;
  const q = before.slice(at + 1);
  if (q.length > 40 || /\n/.test(q) || /^\s/.test(q)) return null;
  return { start: at, q };
}

/**
 * The composer. Enter sends, Shift+Enter makes a new line. While Mylo works,
 * Stop replaces Send and a new message waits its turn (shown as queued). When
 * Mylo has asked a question, what is typed here is the answer. `@` searches
 * for an item or project to attach — only things the person can already see.
 */
export function Composer({
  inputRef,
  threadId,
  working,
  waiting,
  disabled,
  placeholder,
  footer,
  onSend,
  onAnswer,
  onStop,
}: {
  inputRef: React.RefObject<HTMLTextAreaElement | null>;
  threadId: string | null;
  working: boolean;
  waiting: boolean;
  disabled?: boolean;
  placeholder: string;
  footer?: React.ReactNode;
  onSend: (text: string, mentions: string[]) => void;
  onAnswer: (text: string) => void;
  onStop: () => void;
}) {
  const [text, setText] = React.useState("");
  const [mentions, setMentions] = React.useState<Mention[]>([]);
  const [picker, setPicker] = React.useState<{ start: number; q: string } | null>(null);
  const [active, setActive] = React.useState(0);
  const listId = React.useId();
  const hintId = React.useId();

  const q = picker?.q.trim() ?? "";
  const results = useQuery({
    queryKey: ["agent", "refs", q, threadId],
    queryFn: () => searchRefs(q, threadId),
    enabled: q.length >= 2,
    staleTime: 30_000,
  });
  const options: RefSearchResult[] = picker && q.length >= 2 ? (results.data ?? []).slice(0, 8) : [];

  const track = (value: string, caret: number) => {
    setText(value);
    setPicker(mentionQuery(value, caret));
    setActive(0);
  };

  const choose = (option: RefSearchResult) => {
    if (!picker) return;
    const caret = picker.start + 1 + picker.q.length;
    const next = `${text.slice(0, picker.start)}${text.slice(caret)}`.replace(/\s{2,}/g, " ");
    setText(next);
    setPicker(null);
    setMentions((m) =>
      m.some((x) => x.ref === option.ref)
        ? m
        : [...m, { ref: option.ref, title: splitItemTitle(option.title).title }],
    );
    requestAnimationFrame(() => inputRef.current?.focus());
  };

  const submit = () => {
    const clean = text.trim();
    if (!clean || disabled) return;
    if (waiting) onAnswer(clean);
    else onSend(clean, mentions.map((m) => m.ref));
    setText("");
    setMentions([]);
    setPicker(null);
  };

  const onKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.nativeEvent.isComposing) return;
    if (options.length) {
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        const d = event.key === "ArrowDown" ? 1 : -1;
        setActive((a) => (a + d + options.length) % options.length);
        return;
      }
      if (event.key === "Enter" || event.key === "Tab") {
        event.preventDefault();
        choose(options[active]);
        return;
      }
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        setPicker(null);
        return;
      }
    }
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  };

  // grow with the text, up to a few lines
  React.useLayoutEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, [text, inputRef]);

  return (
    <div className="ws-mylo-composer">
      {options.length ? (
        <ul id={listId} role="listbox" className="ws-mylo-picker" aria-label="Attach something">
          {options.map((option, i) => {
            const { kind, title } = splitItemTitle(option.title);
            return (
              <li
                key={option.ref}
                id={`${listId}-${i}`}
                role="option"
                aria-selected={i === active}
                onMouseDown={(e) => {
                  e.preventDefault();
                  choose(option);
                }}
              >
                <span className="ws-mylo-picker-kind">{kind ?? option.kind}</span>
                <span className="ws-mylo-picker-title">{title}</span>
              </li>
            );
          })}
        </ul>
      ) : null}
      {mentions.length ? (
        <ul className="ws-mylo-mentions" aria-label="Attached">
          {mentions.map((m) => (
            <li key={m.ref}>
              <span>{m.title}</span>
              <button
                type="button"
                aria-label={`Remove ${m.title}`}
                onClick={() => setMentions((all) => all.filter((x) => x.ref !== m.ref))}
              >
                <X size={11} aria-hidden="true" />
              </button>
            </li>
          ))}
        </ul>
      ) : null}
      <div className="ws-mylo-input">
        <label htmlFor={`${hintId}-input`} className="ws-sr">
          {waiting ? "Your answer to Mylo" : "Message Mylo"}
        </label>
        <textarea
          id={`${hintId}-input`}
          ref={inputRef}
          rows={1}
          value={text}
          placeholder={placeholder}
          disabled={disabled}
          aria-describedby={hintId}
          role="combobox"
          aria-expanded={options.length > 0}
          aria-controls={options.length ? listId : undefined}
          aria-autocomplete="list"
          aria-activedescendant={options.length ? `${listId}-${active}` : undefined}
          onChange={(e) => track(e.target.value, e.target.selectionStart ?? e.target.value.length)}
          onKeyDown={onKeyDown}
          onBlur={() => setPicker(null)}
        />
        {working && !waiting ? (
          <button type="button" className="ws-mylo-send" data-stop onClick={onStop} aria-label="Stop Mylo">
            <Square size={12} aria-hidden="true" fill="currentColor" />
          </button>
        ) : (
          <button
            type="button"
            className="ws-mylo-send"
            onClick={submit}
            disabled={!text.trim() || disabled}
            aria-label={waiting ? "Send answer" : "Send"}
          >
            <ArrowUp size={15} aria-hidden="true" />
          </button>
        )}
      </div>
      <p id={hintId} className="ws-mylo-foot">
        {footer}
        <span className="ws-sr"> Enter sends, Shift+Enter makes a new line, @ attaches an item or project.</span>
      </p>
    </div>
  );
}
