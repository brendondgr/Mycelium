# Mylo — animation rig (SVG)

`mylo.svg` is Mylo drawn as a small, clean SVG — about 70 plain shapes,
27 KB — and split into parts that can move. The shapes are hand-authored
(smooth curves through a few points, circles, ellipses, rounded rectangles),
but where each one sits was *measured* from the front view of his character
sheet (`docs/Resources/myloCharacterCard.png`): the cap's dome and brim, the
gills under it, each lens and eye, the mouth, the collar and badge, the straps,
the arms, the boots, the seven leaves of the shoulder sprout, the cap's spots.
Colours are the sheet's own, sampled from the same regions.

It is one self-contained file: shapes, layer names and animation CSS together,
so it works as a plain `<img src>`, as an `<object>`, or pasted inline.

    web/art/Mylo/svg/
      mylo.svg        the rig — art + animation CSS in one file
      rig-demo.html   a harness for exercising every state
      trace/          draw.py + rig.css regenerate mylo.svg (run.sh)
      README.md

## Driving it

Everything is an attribute on the root `<svg>`.

| Attribute | Values | Default |
|---|---|---|
| `data-anim` | `idle` `walk` `wave` `think` `search` `write` `cheer` `nod` `shake` `alert` `none` | `idle` |
| `data-prop` | `none` `magnifier` `notebook` | `none` |
| `data-facing` | `front` `left` `right` | `front` |
| `--m-speed` | any number — `2` runs every cycle twice as fast | `1` |

```js
mylo.setAttribute("data-anim", "search");
mylo.setAttribute("data-prop", "magnifier");
mylo.style.setProperty("--m-speed", "1.4");
```

Blinking runs in every state, including `none`. `prefers-reduced-motion: reduce`
stops every animation inside the file and leaves him at rest.

## The rig

A shallow tree. Each group has a pivot declared in the stylesheet (viewBox
units, `transform-box: view-box`) and rotations compose down the tree, so a
head tilt on top of a body bob needs no arithmetic.

    .m-flip                whole-figure mirror + facing lean
      .m-shadow            ground contact (the one element not from the sheet)
      .m-figure            bob, hop, lean — the root-motion handle
        .m-legs
          .m-leg-l/.m-leg-r    each boot, pivot at its top
        .m-torso-back      satchel, stem, ribs, straps      } both carry .m-torso
        .m-head            skin, gills, cap, spots, brows, glasses, mouth — pivot at the collar
          .m-eye-l/.m-eye-r  each eye, for blinks
        .m-arm-l           shoulder pivot
          .m-hand-l          tip of the arm — carries the notebook
        .m-arm-r
          .m-hand-r          carries the magnifying glass
        .m-torso-front     collar, badge, sprout             } both carry .m-torso
        .m-fx              thought dots, sparkles

The torso is two groups because the arms sit *behind* the collar but *in front
of* the belly, as they do in the painting. The head owns its own skin down to
under the collar, so a tilt carries the face with it and the seam stays hidden.

Adding a move is one CSS block in `trace/rig.css`; there is no other wiring:

```css
.mylo[data-anim="peek"] .m-head { animation: m-peek 2s ease-in-out infinite; }
@keyframes m-peek { 0%,100% { transform: rotate(0); } 50% { transform: rotate(-9deg); } }
```

Two limits worth knowing before you plan a pose. The arms are single stubs, so
reach comes from the shoulder alone — a hand gets to the chin or out to the
side, not to the far shoulder. And the cap is painted last, so a prop lifted
above head height ends up behind it; `search` is angled to keep the glass clear
of the brim.

There is no `data-expr`. The sheet's other expressions are separate drawings;
adding them means drawing alternate brows and mouths, not inventing them here.

## Views

This is the front view. `walk` is a march in place: alternating steps, a
two-beat bob, counter-swinging arms and a lagging cap. To cross a space,
translate the element itself (the demo's "travel across" does exactly that).
A side profile is a second drawing.

## Regenerating

```bash
web/art/Mylo/svg/trace/run.sh
```

`draw.py` (Pillow + numpy) crops the sheet's front view, floods each painted
region from a seed point, measures it, and writes the shapes; `rig.css` is the
animation stylesheet with `@PIVOT@` placeholders it fills in. Edit `draw.py` to
change a shape, `rig.css` to change a move, and run the script. If the sheet is
repainted, the seed points at the top of `draw.py` are what to revisit.

## Using it in the app

Inline the markup (so the attributes are reachable) rather than pointing an
`<img>` at it. Three things to watch:

- The stylesheet inside the file is global once inlined. Every selector is
  scoped under `.mylo`, so keep that class on the root.
- `mylo-cap` and `mylo-stem` are document-level ids (a gradient and a clip).
  Two inlined copies on one page need them suffixed.
- Never put a `<` in the embedded `<style>`. Inline SVG is parsed as HTML, not
  as XML, so a tag-shaped token in a CSS comment silently voids the whole
  stylesheet and every animation with it.
