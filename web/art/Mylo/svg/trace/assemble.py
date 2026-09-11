"""Assemble the traced parts + pivots into the rigged mylo.svg."""
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__))
_REPO = _os.path.abspath(_os.path.join(_HERE, '..', '..', '..', '..', '..'))
SRC = _os.path.join(_REPO, 'docs', 'Resources', 'myloCharacterCard.png')
BUILD = _os.path.join(_HERE, 'build')          # scratch: pbm layers, json hand-offs (git-ignored)
_os.makedirs(BUILD, exist_ok=True); _os.chdir(BUILD)
import json, os
P = json.load(open('parts.json')); V = json.load(open('pivots.json'))
def px(k): x,y = V[k]; return f'{x:.1f}px {y:.1f}px'
bx0,by0,bx1,by1 = V['bounds']
cx = (bx0+bx1)/2
css = f"""
  /* Mylo rig — traced from the character sheet. States are attributes on the root svg element:
       data-anim   idle | walk | wave | think | search | write | cheer | nod | shake | alert | none
       data-prop   none | magnifier | notebook
       data-facing front | left | right
     Speed per instance: style="--m-speed: 1.4"  */
  .mylo {{ --m-speed: 1; }}
  .mylo * {{ transform-box: view-box; }}
  .mylo .m-flip   {{ transform-origin: {cx:.1f}px {(by0+by1)/2:.1f}px; }}
  .mylo .m-figure {{ transform-origin: {px('figure')}; }}
  .mylo .m-torso  {{ transform-origin: {px('torso')}; }}
  .mylo .m-head   {{ transform-origin: {px('head')}; }}
  .mylo .m-arm-l  {{ transform-origin: {px('arm-l')}; }}
  .mylo .m-arm-r  {{ transform-origin: {px('arm-r')}; }}
  .mylo .m-hand-l {{ transform-origin: {px('hand-l')}; }}
  .mylo .m-hand-r {{ transform-origin: {px('hand-r')}; }}
  .mylo .m-leg-l  {{ transform-origin: {px('boot-l')}; }}
  .mylo .m-leg-r  {{ transform-origin: {px('boot-r')}; }}
  .mylo .m-eye-l  {{ transform-origin: {px('eye-l')}; }}
  .mylo .m-eye-r  {{ transform-origin: {px('eye-r')}; }}
  .mylo .m-shadow {{ transform-origin: {cx:.1f}px {by1+2:.1f}px; }}

  .mylo[data-facing="left"]  .m-flip {{ transform: scaleX(-1) rotate(-3deg); }}
  .mylo[data-facing="right"] .m-flip {{ transform: rotate(3deg); }}

  .mylo .m-prop {{ display: none; }}
  .mylo[data-prop="magnifier"] .m-prop-magnifier,
  .mylo[data-prop="notebook"]  .m-prop-notebook {{ display: inline; }}
  .mylo .m-fx {{ display: none; }}
  .mylo[data-anim="think"] .m-fx-thought,
  .mylo[data-anim="cheer"] .m-fx-spark,
  .mylo[data-anim="alert"] .m-fx-spark {{ display: inline; }}

  /* blinking runs in every state */
  .mylo .m-eye-l, .mylo .m-eye-r {{ animation: m-blink 6.4s calc(1s / var(--m-speed)) infinite; }}
  .mylo .m-eye-r {{ animation-delay: calc(1.03s / var(--m-speed)); }}
  @keyframes m-blink {{ 0%, 91%, 100% {{ transform: scaleY(1); }} 93.5% {{ transform: scaleY(.06); }} 96% {{ transform: scaleY(1); }} }}

  /* idle */
  .mylo[data-anim="idle"] .m-figure {{ animation: m-breathe calc(4.2s / var(--m-speed)) ease-in-out infinite; }}
  .mylo[data-anim="idle"] .m-head   {{ animation: m-head-float calc(4.2s / var(--m-speed)) ease-in-out infinite; }}
  .mylo[data-anim="idle"] .m-arm-l  {{ animation: m-sway-l calc(4.2s / var(--m-speed)) ease-in-out infinite; }}
  .mylo[data-anim="idle"] .m-arm-r  {{ animation: m-sway-r calc(4.2s / var(--m-speed)) ease-in-out infinite; }}
  @keyframes m-breathe    {{ 0%,100% {{ transform: translateY(0) scaleY(1); }} 50% {{ transform: translateY(-1.2px) scaleY(1.012); }} }}
  @keyframes m-head-float {{ 0%,100% {{ transform: translateY(0) rotate(-1deg); }} 50% {{ transform: translateY(-1px) rotate(1.2deg); }} }}
  @keyframes m-sway-l     {{ 0%,100% {{ transform: rotate(2deg); }}  50% {{ transform: rotate(-3deg); }} }}
  @keyframes m-sway-r     {{ 0%,100% {{ transform: rotate(-2deg); }} 50% {{ transform: rotate(3deg); }} }}

  /* walk: a front-facing march */
  .mylo[data-anim="walk"] .m-leg-l  {{ animation: m-step calc(.72s / var(--m-speed)) ease-in-out infinite; }}
  .mylo[data-anim="walk"] .m-leg-r  {{ animation: m-step calc(.72s / var(--m-speed)) ease-in-out infinite; animation-delay: calc(-.36s / var(--m-speed)); }}
  .mylo[data-anim="walk"] .m-figure {{ animation: m-bob calc(.36s / var(--m-speed)) ease-in-out infinite; }}
  .mylo[data-anim="walk"] .m-torso  {{ animation: m-waddle calc(.72s / var(--m-speed)) ease-in-out infinite; }}
  .mylo[data-anim="walk"] .m-head   {{ animation: m-head-lag calc(.72s / var(--m-speed)) ease-in-out infinite; }}
  .mylo[data-anim="walk"] .m-arm-l  {{ animation: m-swing calc(.72s / var(--m-speed)) ease-in-out infinite; }}
  .mylo[data-anim="walk"] .m-arm-r  {{ animation: m-swing calc(.72s / var(--m-speed)) ease-in-out infinite; animation-delay: calc(-.36s / var(--m-speed)); }}
  .mylo[data-anim="walk"] .m-shadow {{ animation: m-shadow-pulse calc(.36s / var(--m-speed)) ease-in-out infinite; }}
  @keyframes m-step   {{ 0%,100% {{ transform: translateY(0) rotate(6deg); }} 25% {{ transform: translateY(-9px) rotate(-8deg); }} 50% {{ transform: translateY(0) rotate(-5deg); }} }}
  @keyframes m-bob    {{ 0%,100% {{ transform: translateY(0); }} 50% {{ transform: translateY(-3.5px); }} }}
  @keyframes m-waddle {{ 0%,100% {{ transform: rotate(1.6deg); }} 50% {{ transform: rotate(-1.6deg); }} }}
  @keyframes m-head-lag {{ 0%,100% {{ transform: rotate(-2.2deg); }} 50% {{ transform: rotate(2.2deg); }} }}
  @keyframes m-swing  {{ 0%,100% {{ transform: rotate(-16deg); }} 50% {{ transform: rotate(18deg); }} }}
  @keyframes m-shadow-pulse {{ 0%,100% {{ transform: scale(1); opacity: .45; }} 50% {{ transform: scale(.9); opacity: .3; }} }}

  /* wave */
  .mylo[data-anim="wave"] .m-arm-r  {{ animation: m-wave calc(2.6s / var(--m-speed)) ease-in-out infinite; }}
  .mylo[data-anim="wave"] .m-figure {{ animation: m-breathe calc(2.6s / var(--m-speed)) ease-in-out infinite; }}
  .mylo[data-anim="wave"] .m-head   {{ animation: m-tilt-r calc(2.6s / var(--m-speed)) ease-in-out infinite; }}
  @keyframes m-wave {{ 0% {{ transform: rotate(0); }} 10% {{ transform: rotate(-132deg); }} 22% {{ transform: rotate(-104deg); }} 34% {{ transform: rotate(-136deg); }}
                      46% {{ transform: rotate(-104deg); }} 58% {{ transform: rotate(-136deg); }} 72% {{ transform: rotate(-112deg); }} 88%,100% {{ transform: rotate(0); }} }}
  @keyframes m-tilt-r {{ 0%,100% {{ transform: rotate(0); }} 20%,70% {{ transform: rotate(5deg); }} }}

  /* think: hand up under the chin */
  .mylo[data-anim="think"] .m-arm-r  {{ animation: m-chin calc(4s / var(--m-speed)) ease-in-out infinite; }}
  .mylo[data-anim="think"] .m-head   {{ animation: m-ponder calc(4s / var(--m-speed)) ease-in-out infinite; }}
  .mylo[data-anim="think"] .m-figure {{ animation: m-breathe calc(4s / var(--m-speed)) ease-in-out infinite; }}
  .mylo[data-anim="think"] .m-dot-1  {{ animation: m-dot calc(2.4s / var(--m-speed)) ease-out infinite; }}
  .mylo[data-anim="think"] .m-dot-2  {{ animation: m-dot calc(2.4s / var(--m-speed)) ease-out infinite; animation-delay: calc(.28s / var(--m-speed)); }}
  .mylo[data-anim="think"] .m-dot-3  {{ animation: m-dot calc(2.4s / var(--m-speed)) ease-out infinite; animation-delay: calc(.56s / var(--m-speed)); }}
  @keyframes m-chin   {{ 0%,100% {{ transform: rotate(98deg); }} 50% {{ transform: rotate(103deg); }} }}
  @keyframes m-ponder {{ 0%,100% {{ transform: rotate(-5deg) translateY(0); }} 50% {{ transform: rotate(-8deg) translateY(-1.5px); }} }}
  @keyframes m-dot    {{ 0% {{ opacity: 0; transform: translateY(4px) scale(.6); }} 30% {{ opacity: 1; transform: translateY(0) scale(1); }} 70% {{ opacity: 1; }} 100% {{ opacity: 0; transform: translateY(-6px) scale(.9); }} }}

  /* search: glass held up and swept */
  .mylo[data-anim="search"] .m-arm-r  {{ animation: m-lift-glass calc(3.4s / var(--m-speed)) ease-in-out infinite; }}
  .mylo[data-anim="search"] .m-hand-r {{ animation: m-glass-turn calc(3.4s / var(--m-speed)) ease-in-out infinite; }}
  .mylo[data-anim="search"] .m-head   {{ animation: m-scan calc(3.4s / var(--m-speed)) ease-in-out infinite; }}
  .mylo[data-anim="search"] .m-figure {{ animation: m-lean calc(3.4s / var(--m-speed)) ease-in-out infinite; }}
  @keyframes m-lift-glass {{ 0%,100% {{ transform: rotate(-126deg); }} 50% {{ transform: rotate(-134deg); }} }}
  @keyframes m-glass-turn {{ 0%,100% {{ transform: rotate(12deg); }} 50% {{ transform: rotate(-10deg); }} }}
  @keyframes m-scan   {{ 0%,100% {{ transform: rotate(4deg); }} 50% {{ transform: rotate(-4deg); }} }}
  @keyframes m-lean   {{ 0%,100% {{ transform: translateY(-1px) rotate(1deg); }} 50% {{ transform: translateY(-2px) rotate(-1deg); }} }}

  /* write: notebook held up, other hand jotting */
  .mylo[data-anim="write"] .m-arm-l  {{ animation: m-hold-book calc(3s / var(--m-speed)) ease-in-out infinite; }}
  .mylo[data-anim="write"] .m-hand-l {{ animation: m-book-settle calc(3s / var(--m-speed)) ease-in-out infinite; }}
  .mylo[data-anim="write"] .m-arm-r  {{ animation: m-jot calc(.9s / var(--m-speed)) ease-in-out infinite; }}
  .mylo[data-anim="write"] .m-head   {{ animation: m-read-down calc(3s / var(--m-speed)) ease-in-out infinite; }}
  .mylo[data-anim="write"] .m-figure {{ animation: m-breathe calc(3s / var(--m-speed)) ease-in-out infinite; }}
  @keyframes m-hold-book  {{ 0%,100% {{ transform: rotate(-62deg); }} 50% {{ transform: rotate(-65deg); }} }}
  @keyframes m-book-settle{{ 0%,100% {{ transform: rotate(30deg); }} 50% {{ transform: rotate(34deg); }} }}
  @keyframes m-jot        {{ 0%,100% {{ transform: rotate(58deg) translateY(0); }} 50% {{ transform: rotate(52deg) translateY(-2.5px); }} }}
  @keyframes m-read-down  {{ 0%,100% {{ transform: rotate(-3deg) translateY(.5px); }} 50% {{ transform: rotate(-6deg) translateY(1.5px); }} }}

  /* cheer */
  .mylo[data-anim="cheer"] .m-figure {{ animation: m-hop calc(1.1s / var(--m-speed)) cubic-bezier(.3,.7,.4,1) infinite; }}
  .mylo[data-anim="cheer"] .m-arm-l  {{ animation: m-arm-up-l calc(1.1s / var(--m-speed)) ease-in-out infinite; }}
  .mylo[data-anim="cheer"] .m-arm-r  {{ animation: m-arm-up-r calc(1.1s / var(--m-speed)) ease-in-out infinite; }}
  .mylo[data-anim="cheer"] .m-head   {{ animation: m-head-hop calc(1.1s / var(--m-speed)) ease-in-out infinite; }}
  .mylo[data-anim="cheer"] .m-shadow {{ animation: m-shadow-hop calc(1.1s / var(--m-speed)) cubic-bezier(.3,.7,.4,1) infinite; }}
  @keyframes m-hop      {{ 0%,100% {{ transform: translateY(0) scaleY(.97) scaleX(1.03); }} 20% {{ transform: translateY(-15px) scaleY(1.04) scaleX(.97); }} 55% {{ transform: translateY(-3px) scaleY(1); }} }}
  @keyframes m-arm-up-l {{ 0%,100% {{ transform: rotate(115deg); }} 25% {{ transform: rotate(148deg); }} }}
  @keyframes m-arm-up-r {{ 0%,100% {{ transform: rotate(-115deg); }} 25% {{ transform: rotate(-148deg); }} }}
  @keyframes m-head-hop {{ 0%,100% {{ transform: translateY(1.5px) rotate(0); }} 25% {{ transform: translateY(-2px) rotate(2deg); }} }}
  @keyframes m-shadow-hop {{ 0%,100% {{ transform: scale(1); opacity: .45; }} 25% {{ transform: scale(.78); opacity: .25; }} }}
  .mylo[data-anim="cheer"] .m-spark-1, .mylo[data-anim="alert"] .m-spark-1 {{ animation: m-spark calc(1.2s / var(--m-speed)) ease-out infinite; }}
  .mylo[data-anim="cheer"] .m-spark-2, .mylo[data-anim="alert"] .m-spark-2 {{ animation: m-spark calc(1.2s / var(--m-speed)) ease-out infinite; animation-delay: calc(.18s / var(--m-speed)); }}
  .mylo[data-anim="cheer"] .m-spark-3, .mylo[data-anim="alert"] .m-spark-3 {{ animation: m-spark calc(1.2s / var(--m-speed)) ease-out infinite; animation-delay: calc(.36s / var(--m-speed)); }}
  @keyframes m-spark {{ 0% {{ opacity: 0; transform: scale(.4); }} 25% {{ opacity: 1; transform: scale(1.15); }} 60% {{ opacity: .9; transform: scale(1); }} 100% {{ opacity: 0; transform: scale(.5); }} }}

  /* nod / shake / alert */
  .mylo[data-anim="nod"] .m-head {{ animation: m-nod calc(1.5s / var(--m-speed)) ease-in-out infinite; }}
  .mylo[data-anim="nod"] .m-figure {{ animation: m-breathe calc(3s / var(--m-speed)) ease-in-out infinite; }}
  @keyframes m-nod {{ 0%,100% {{ transform: translateY(0) rotate(0); }} 20% {{ transform: translateY(3px) rotate(-2deg); }} 40% {{ transform: translateY(-.5px); }} 60% {{ transform: translateY(3px) rotate(-2deg); }} 80% {{ transform: translateY(0); }} }}
  .mylo[data-anim="shake"] .m-head {{ animation: m-shake calc(1.4s / var(--m-speed)) ease-in-out infinite; }}
  .mylo[data-anim="shake"] .m-figure {{ animation: m-breathe calc(2.8s / var(--m-speed)) ease-in-out infinite; }}
  @keyframes m-shake {{ 0%,100% {{ transform: rotate(0); }} 15% {{ transform: rotate(-7deg); }} 35% {{ transform: rotate(7deg); }} 55% {{ transform: rotate(-6deg); }} 75% {{ transform: rotate(4deg); }} }}
  .mylo[data-anim="alert"] .m-figure {{ animation: m-pop calc(1.6s / var(--m-speed)) ease-out infinite; }}
  .mylo[data-anim="alert"] .m-head   {{ animation: m-pop-head calc(1.6s / var(--m-speed)) ease-out infinite; }}
  .mylo[data-anim="alert"] .m-arm-r  {{ animation: m-point calc(1.6s / var(--m-speed)) ease-out infinite; }}
  @keyframes m-pop      {{ 0%,100% {{ transform: translateY(0) scale(1); }} 12% {{ transform: translateY(-5px) scale(1.03); }} 30% {{ transform: translateY(0) scale(1); }} }}
  @keyframes m-pop-head {{ 0%,100% {{ transform: translateY(0) rotate(0); }} 12% {{ transform: translateY(-2.5px) rotate(-3deg); }} 30% {{ transform: translateY(0) rotate(0); }} }}
  @keyframes m-point    {{ 0%,100% {{ transform: rotate(-124deg); }} 12% {{ transform: rotate(-138deg); }} 40% {{ transform: rotate(-124deg); }} }}

  @media (prefers-reduced-motion: reduce) {{ .mylo * {{ animation: none !important; }} }}
"""
props = json.load(open('props.json')) if os.path.exists('props.json') else {'magnifier':'', 'notebook':''}
hl = V['hand-l']; hr = V['hand-r']
def group(cls, inner): return f'<g class="{cls}">\n{inner}\n</g>'
figure = '\n'.join([
  group('m-legs', group('m-leg-l', P['boot-l']) + '\n' + group('m-leg-r', P['boot-r'])),
  group('m-head', P['head'] + '\n' + group('m-eye-l', P['eye-l']) + '\n' + group('m-eye-r', P['eye-r'])),
  group('m-torso', P['torso']),
  group('m-arm-l', P['arm-l'] + '\n' + group('m-hand-l', group('m-prop m-prop-notebook', props['notebook']))),
  group('m-arm-r', P['arm-r'] + '\n' + group('m-hand-r', group('m-prop m-prop-magnifier', props['magnifier']))),
  f'''<g class="m-fx m-fx-thought" fill="#ABC38A" stroke="#4E6B3C" stroke-width="1.6">
  <circle class="m-dot-1" cx="{bx1-12:.0f}" cy="{by0+92:.0f}" r="3.6"/><circle class="m-dot-2" cx="{bx1+2:.0f}" cy="{by0+74:.0f}" r="5.4"/><circle class="m-dot-3" cx="{bx1+16:.0f}" cy="{by0+52:.0f}" r="7.2"/>
</g>
<g class="m-fx m-fx-spark" fill="#D9A93F">
  <path class="m-spark-1" d="M17 82c1.2 5.4 2.4 6.6 7.8 7.8-5.4 1.2-6.6 2.4-7.8 7.8-1.2-5.4-2.4-6.6-7.8-7.8 5.4-1.2 6.6-2.4 7.8-7.8Z" style="transform-origin:17px 89.8px"/>
  <path class="m-spark-2" d="M188 44c1.5 6.6 3 8 9.6 9.6-6.6 1.5-8 3-9.6 9.6-1.5-6.6-3-8-9.6-9.6 6.6-1.5 8-3 9.6-9.6Z" style="transform-origin:188px 53.6px"/>
  <path class="m-spark-3" d="M30 30c1 4.4 2 5.4 6.4 6.4-4.4 1-5.4 2-6.4 6.4-1-4.4-2-5.4-6.4-6.4 4.4-1 5.4-2 6.4-6.4Z" style="transform-origin:30px 36.4px"/>
</g>''',
])
svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="-30 -6 265 332" width="265" height="332"
     class="mylo" data-anim="idle" data-prop="none" data-facing="front"
     role="img" aria-labelledby="mylo-title mylo-desc">
  <title id="mylo-title">Mylo, the Mycelium mushroom scout</title>
  <desc id="mylo-desc">Mylo, traced from the front view of his character sheet: a small mushroom scout with a green spotted cap, round glasses, a green neckerchief with a leaf badge, a satchel and green boots.</desc>
  <style>{css}  </style>
  <g class="m-flip">
    <ellipse class="m-shadow" cx="{cx:.1f}" cy="{by1+2:.1f}" rx="{(bx1-bx0)*0.44:.1f}" ry="6" fill="#D6C69C" opacity=".45"/>
    <g class="m-figure">
{figure}
    </g>
  </g>
</svg>
'''
out = _os.path.join(_HERE, '..', 'mylo.svg')
open(out,'w').write(svg)
print('wrote', out, os.path.getsize(out), 'bytes')
