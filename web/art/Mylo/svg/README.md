# Mylo — animation rig (SVG)

`mylo.svg` is the front view of Mylo from his character sheet
(`docs/Resources/myloCharacterCard.png`), traced into vector paths and cut into
parts that can move. It is not a redraw: every shape in the file was produced
from the pixels of that painting, so the cap, the gills under it, the glasses,
the smile, the neckerchief and badge, the satchel straps, the shoulder sprout
and the boots are the sheet's own, colour for colour.

It is one self-contained file: the paths, the layer names and the animation CSS
all live inside it, so it works as a plain `<img src>`, as an `<object>`, or
pasted inline into a component.

    web/art/Mylo/svg/
      mylo.svg        the rig — traced art + animation CSS in one file (~250 KB)
      rig-demo.html   a harness for exercising every state
      trace/          the pipeline that produced mylo.svg (run.sh regenerates it)
      README.md

## Driving it

Everything is an attribute on the root `<svg>`.

| Attribute | Values | Default |
|---|---|---|
| `data-anim` | `idle` `walk` `wave` `think` `search` `write` `cheer` `nod` `shake` `alert` `none` | `idle` |
| `data-prop` | `none` `magnifier` `notebook` — both traced from the sheet's props panel | `none` |
| `data-facing` | `front` `left` `right` | `front` |
| `--m-speed` | any number — `2` runs every cycle twice as fast | `1` |

```js
mylo.setAttribute("data-anim", "search");
mylo.setAttribute("data-prop", "magnifier");
mylo.style.setProperty("--m-speed", "1.4");
```

Blinking runs in every state, including `none`. `prefers-reduced-motion: reduce`
stops every animation inside the file and leaves the painting at rest.

There is no `data-expr`. The sheet's other expressions are separate drawings
(the Expressions row), not variants of this one, so swapping a mouth here would
mean inventing strokes the painting does not have. Tracing that row into
swappable faces is the natural next step if expressions are wanted.

## The rig

The figure is a shallow tree. Each group has a pivot declared in the stylesheet
(in viewBox units, `transform-box: view-box`) and rotations compose down the
tree, so a head tilt on top of a body bob needs no arithmetic.

    .m-flip                whole-figure mirror + facing lean
      .m-shadow            ground contact (the one element not from the sheet)
      .m-figure            bob, hop, lean — the root-motion handle
        .m-legs
          .m-leg-l/.m-leg-r    each boot, pivot at its top
        .m-head            cap, gills, face, glasses, mouth — pivot at the collar
          .m-eye-l/.m-eye-r  each eye, for blinks
        .m-torso           collar, badge, belly, straps, satchel, sprout
        .m-arm-l           shoulder pivot
          .m-hand-l          tip of the arm — carries the notebook
        .m-arm-r
          .m-hand-r          carries the magnifying glass
        .m-fx              thought dots, sparkles

Where a part sits on top of another in the painting, the part underneath was
extended under it before tracing (skin under the collar, belly under the arms,
boot under the belly, lens behind each eye), so small rotations reveal painted
surface rather than background. That covers minor motion; a raised arm still
swings past the belly's edge, so keep torso-crossing poses to what is here.

Adding a move is one CSS block; there is no other wiring:

```css
.mylo[data-anim="peek"] .m-head { animation: m-peek 2s ease-in-out infinite; }
@keyframes m-peek { 0%,100% { transform: rotate(0); } 50% { transform: rotate(-9deg); } }
```

## Views

This is the front view. `walk` is a march in place: alternating steps, a
two-beat bob, counter-swinging arms and a lagging cap. To cross a space,
translate the element itself (the demo's "travel across" does exactly that).
The sheet has Side, Back and 3/4 views; each would be a second run of the same
pipeline on a different crop.

## Regenerating

```bash
web/art/Mylo/svg/trace/run.sh
```

Needs `python3` with Pillow and numpy, plus `potrace` on `PATH`; about 20 s.
`build.py` crops the front view, upscales it 4×, floods the paper away, finds
the painted outlines, floods each named region from a seed point, assigns
regions to parts (arms win a shared outline over the torso, the torso over the
boots and the head), paints the under-extensions, quantises each part to a few
colours and traces each colour with potrace. `props.py` does the same for the
two props; `assemble.py` writes the pivots and the CSS. Seeds and part lists are
at the top of `build.py` — if the sheet is repainted, they are what to revisit.

## Using it in the app

Inline the markup (so the attributes are reachable) rather than pointing an
`<img>` at it. Two things to watch:

- The stylesheet inside the file is global once inlined. Every selector is
  scoped under `.mylo`, so keep that class on the root.
- Never put a `<` in the embedded `<style>`. Inline SVG is parsed as HTML, not
  as XML, so a tag-shaped token in a CSS comment silently voids the whole
  stylesheet and every animation with it.
