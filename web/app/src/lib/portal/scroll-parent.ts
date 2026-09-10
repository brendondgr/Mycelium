/**
 * The nearest ancestor that actually scrolls `el`.
 *
 * The workspace scrolls inside `<main>`, not the window, and that matters to
 * every `IntersectionObserver` in the feeds. `rootMargin` adjusts the *root*'s
 * box, but clipping by intermediate ancestors is applied regardless of it — so
 * an observer left on the default viewport root has its margin measured against
 * the viewport while `main`'s own box does the real clipping. The margin is then
 * inert: the observer fires when the element reaches the panel edge, not the
 * lead distance ahead of it that the margin asked for.
 *
 * Returns null when nothing between `el` and the document scrolls, which is the
 * case on the public site — there the caller should use the default viewport
 * root, where a margin behaves as written.
 */
export function scrollParent(el: Element): Element | null {
  let node: Element | null = el.parentElement;
  while (node) {
    const overflowY = getComputedStyle(node).overflowY;
    // Identified by its overflow alone, deliberately: whether it happens to be
    // overflowing *right now* is not the question. A feed mounts its skeletons
    // first, so `main` is not yet taller than its box, and a check for that
    // would send the first batch of cards to a viewport-rooted observer that
    // can never see past `main`'s clip — leaving them invisible.
    if (overflowY === "auto" || overflowY === "scroll" || overflowY === "overlay") {
      return node;
    }
    node = node.parentElement;
  }
  return null;
}
