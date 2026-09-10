# Mylo — animation rig (SVG)

`mylo.svg` is the vector, riggable Mylo: the front view from the character
sheet, traced feature for feature — the bell cap with its striated underside,
the glasses over big dark eyes, the open smile, the neckerchief with the leaf
badge, the satchel and its straps, the shoulder sprout, the boots — and split
into named, independently transformable parts.

It is one self-contained file. Geometry, layer names, animation CSS and the
default pose all live inside it, so it works as a plain `<img src>`, as an
`<object>`, or pasted inline into a component.

    web/art/Mylo/svg/
      mylo.svg        the rig — art + animation CSS in one file
      rig-demo.html   a harness for exercising every state
      README.md

## Driving it

Everything is an attribute on the root `<svg>`. Nothing else needs to change.

| Attribute | Values | Default |
|---|---|---|
| `data-anim` | `idle` `walk` `wave` `think` `search` `write` `cheer` `nod` `shake` `alert` `none` | `idle` |
| `data-expr` | `happy` `curious` `thinking` `excited` `determined` | `happy` |
| `data-prop` | `none` `magnifier` `notebook` | `none` |
| `data-facing` | `front` `left` `right` | `front` |
| `--m-speed` | any number — `2` runs every cycle twice as fast | `1` |

```js
mylo.setAttribute("data-anim", "search");
mylo.setAttribute("data-prop", "magnifier");
mylo.style.setProperty("--m-speed", "1.4");
```

Blinking runs in every state, including `none`. `prefers-reduced-motion: reduce`
stops every animation and leaves him in his rest pose — that is handled inside
the file, so no caller has to remember it.

## The rig

The figure is a shallow tree. Each group has a pivot declared in the stylesheet
and rotations compose down the tree, so a head tilt on top of a body bob needs
no arithmetic.

    .m-flip                whole-figure mirror + facing lean
      .m-shadow            ground contact
      .m-figure            bob, hop, lean — the "root motion" handle
        .m-sprout          shoulder sprout
        .m-legs
          .m-leg-l/.m-leg-r    hip pivots (120,380) / (194,380)
        .m-torso           body, striations, straps, scarf, badge
        .m-arm-l           shoulder pivot (84,272)
          .m-hand-l          tip pivot (74,346) — carries the notebook
        .m-arm-r           shoulder pivot (220,272)
          .m-hand-r          tip pivot (230,346) — carries the magnifier
        .m-head            cap, its underside, face — pivot (152,266)
          .m-eye-l/.m-eye-r  blink pivots
          .m-face            brows, eyes, glasses, mouths
          .m-cap
        .m-fx              thought dots, sparkles

Pivots use `transform-box: view-box`, so `transform-origin` is written in
viewBox units and reads straight off the drawing.

Limbs are drawn as two stacked strokes — a wide dark one for the outline, a
narrower light one for the fill — which is why they keep a clean silhouette at
any rotation. Keep that pairing if you redraw an arm.

## Adding a move

Add one block. There is no other wiring.

```css
.mylo[data-anim="peek"] .m-head { animation: m-peek 2s ease-in-out infinite; }
@keyframes m-peek { 0%,100% { transform: rotate(0); } 50% { transform: rotate(-9deg); } }
```

Two limits worth knowing before you plan a pose:

- **The arms are single stubs, not two-segment limbs.** Reach comes from the
  shoulder only. An arm covers ~78 units of the 340×480 viewBox, so a hand can
  get to the chin or out to the side, but not to the far shoulder.
- **The cap is painted last.** Anything a hand carries above head height ends up
  behind it. `search` is angled to keep the magnifying glass clear of the rim;
  a new overhead pose needs the same check.

## Views

This is the front view. It marches in place: `walk` is a full cycle of steps,
counter-swinging arms, a two-beat body bob and a lagging cap, but he does not
travel. To cross a space, translate the element itself — the demo's "travel
across" button does exactly that. A true side profile is a second drawing, not
an attribute on this one.

## Running the demo

```bash
python3 -m http.server 4399 --bind 127.0.0.1 -d web/art/Mylo/svg
```

Then open `http://127.0.0.1:4399/rig-demo.html`. It has to be served rather than
opened from disk because it fetches `mylo.svg`. There is also a `mylo-rig` entry
in `.claude/launch.json` that starts the same server.

## Using it in the app

Inline the markup (so the attributes are reachable) rather than pointing an
`<img>` at it. Two things to watch:

- The stylesheet inside the file is global once inlined. Every selector is
  scoped under `.mylo`, so keep that class on the root.
- `mylo-body-clip` is a document-level id. Two inlined copies on one page must
  have that id and its `clip-path` reference suffixed.
- Never put a `<` in the embedded `<style>`. Inline SVG is parsed as HTML, not
  as XML, so a tag-shaped token in a CSS comment silently voids the whole
  stylesheet and every animation with it.
