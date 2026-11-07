"""Draw Mylo as a small, clean SVG whose shapes sit where the character sheet
has them.

The front view of web/art/Mylo/myloCharacterCard.png is segmented into
regions (cap, gills, face, lenses, eyes, mouth, collar, badge, belly, straps,
satchel, arms, boots, sprout). Each region is *measured* — a handful of outline
points, a centre, a radius, a median colour — and those numbers place plain
hand-authored shapes: smooth curves through a few points, circles, ellipses,
rounded rectangles. Nothing is traced pixel for pixel; the file stays a few
dozen readable elements.
"""
import os, sys, json, re
import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..', '..', '..', '..'))
SRC = os.path.join(REPO, 'web', 'art', 'Mylo', 'myloCharacterCard.png')
OUT = os.path.join(HERE, '..', 'mylo.svg')
UP = 4

# ---------------------------------------------------------------------------
# 1. segmentation (regions bounded by the painting's own outlines)
# ---------------------------------------------------------------------------
sheet = Image.open(SRC).convert('RGB')
front = sheet.crop((500, 235, 705, 552))
im = front.resize((front.width*UP, front.height*UP), Image.LANCZOS)
W, H = im.size
a = np.asarray(im).astype(np.int16)

def erode(m, k):
    for _ in range(k):
        n = m.copy(); n[1:,:] &= m[:-1,:]; n[:-1,:] &= m[1:,:]; n[:,1:] &= m[:,:-1]; n[:,:-1] &= m[:,1:]; m = n
    return m
def dilate(m, k):
    for _ in range(k):
        n = m.copy(); n[1:,:] |= m[:-1,:]; n[:-1,:] |= m[1:,:]; n[:,1:] |= m[:,:-1]; n[:,:-1] |= m[:,1:]; m = n
    return m
def flood(mask, xy):
    m = Image.fromarray((mask*255).astype(np.uint8)).copy()
    ImageDraw.floodfill(m, xy, 128)
    return np.asarray(m) == 128

bgim = im.copy()
for xy in [(2,2),(W-3,2),(2,H-3),(W-3,H-3),(W//2,2),(W//2,H-3),(2,H//2),(W-3,H//2)]:
    ImageDraw.floodfill(bgim, xy, (255,0,255), thresh=26)
fig = erode(~(np.asarray(bgim) == (255,0,255)).all(axis=2), 2)

R,G,B = a[...,0], a[...,1], a[...,2]
lum = 0.299*R + 0.587*G + 0.114*B
dark = (((lum < 150) & ((R - G) > -12)) | (lum < 75)) & fig
thick = dilate(erode(dark, 5), 6) & dark
ink = dark & ~thick
barrier = Image.new('L', (W,H), 0)
ImageDraw.Draw(barrier).line([(60,520),(110,488),(170,450),(260,424),(410,414),(560,424),(650,450),(710,488),(760,520)], fill=255, width=7)
wall = dilate(ink, 2) | thick | (np.asarray(barrier) > 0)
free = fig & ~wall

seeds = {
  'face':    ('free',  [(410,470),(230,640),(600,640),(410,600),(560,660)]),
  'cap':     ('free',  [(410,250),(300,180),(560,200)]),
  'gills':   ('free',  [(410,360),(250,400),(580,400)]),
  'lens-l':  ('free',  [(250,600),(300,505)]),
  'lens-r':  ('free',  [(480,600),(515,505)]),
  'eye-l':   ('thick', [(300,560)]),
  'eye-r':   ('thick', [(515,560)]),
  'mouth':   ('thick', [(410,640)]),
  'collar':  ('free',  [(300,730),(520,730),(240,760),(590,740)]),
  'badge':   ('free',  [(380,830),(430,850),(410,790)]),
  'belly':   ('free',  [(410,950),(300,1050),(520,1050)]),
  'strap-l': ('thick', [(245,830),(235,880)]),
  'strap-r': ('thick', [(560,840),(575,880)]),
  'pack':    ('thick', [(180,760)]),
  'arm-l':   ('free',  [(165,900),(150,980)]),
  'arm-r':   ('free',  [(650,900),(670,980)]),
  'boot-l':  ('free',  [(280,1170),(250,1190)]),
  'boot-r':  ('free',  [(540,1170),(570,1190)]),
}
lab = np.zeros((H,W), np.int32); idx = {}
for i,(name,(kind,pts)) in enumerate(seeds.items(), start=1):
    idx[name] = i; src = free if kind=='free' else thick
    for (x,y) in pts:
        if src[y,x] and not lab[y,x]:
            lab[flood(src & (lab==0), (x,y))] = i
poly = Image.new('L', (W,H), 0)
ImageDraw.Draw(poly).polygon([(100,600),(215,600),(230,690),(205,720),(180,830),(95,830)], fill=255)
idx['sprout'] = len(idx)+1
lab[(np.asarray(poly) > 0) & fig & (lab==0) & ~dark] = idx['sprout']
M = {n: lab==i for n,i in idx.items()}
M['cap'] |= dilate(M['cap'], 4) & fig & ~M['gills']      # the cap's own outline belongs to its silhouette

# ---------------------------------------------------------------------------
# 2. measuring helpers (all results in source pixels = x4 / 4)
# ---------------------------------------------------------------------------
def row_ext(m, y, pad=2):
    for p in (pad, pad+4, pad+10, pad+20):
        ys = slice(max(0,int(y*UP)-p), int(y*UP)+p+1); xs = np.nonzero(m[ys].any(axis=0))[0]
        if len(xs): return (xs.min()/UP, xs.max()/UP)
    return None
def col_ext(m, x, pad=2):
    for p in (pad, pad+4, pad+10, pad+20):
        xs = slice(max(0,int(x*UP)-p), int(x*UP)+p+1); ys = np.nonzero(m[:,xs].any(axis=1))[0]
        if len(ys): return (ys.min()/UP, ys.max()/UP)
    return None
def bbox(m):
    ys, xs = np.nonzero(m); return xs.min()/UP, ys.min()/UP, xs.max()/UP, ys.max()/UP
def centroid(m):
    ys, xs = np.nonzero(m); return xs.mean()/UP, ys.mean()/UP
def color(m):
    return '#%02X%02X%02X' % tuple(int(v) for v in np.median(a[m], axis=0))
def px(x, y):
    return a[int(y*UP), int(x*UP)]
def hexc(c): return '#%02X%02X%02X' % tuple(int(v) for v in c)
def f(v): return ('%.1f' % v).rstrip('0').rstrip('.')

def smooth(pts, closed=True):
    """Catmull-Rom through pts -> cubic Bézier path data."""
    n = len(pts); P = [np.array(p, float) for p in pts]
    d = ['M%s %s' % (f(P[0][0]), f(P[0][1]))]
    segs = range(n) if closed else range(n-1)
    for i in segs:
        p0 = P[(i-1) % n] if closed or i > 0 else P[0]
        p1, p2 = P[i], P[(i+1) % n]
        p3 = P[(i+2) % n] if closed or i+2 < n else P[-1]
        c1 = p1 + (p2 - p0) / 6; c2 = p2 - (p3 - p1) / 6
        d.append('C%s %s %s %s %s %s' % tuple(f(v) for v in (*c1, *c2, *p2)))
    return ''.join(d) + ('Z' if closed else '')

# ---------------------------------------------------------------------------
# 3. measurements
# ---------------------------------------------------------------------------
INK = color(ink)                                  # the painting's line colour
cap_c, gill_c, skin_c = color(M['cap']), color(M['gills']), color(M['face'])
belly_c, collar_c, badge_c = color(M['belly']), color(M['collar']), color(M['badge'])
boot_c, strap_c, pack_c = color(M['boot-l']|M['boot-r']), color(M['strap-l']|M['strap-r']), color(M['pack'])
eye_c, sprout_c = color(M['eye-l']|M['eye-r']), color(M['sprout'])
lens_c = color(M['lens-l']|M['lens-r'])

# cap: brim tips, dome, lower edge
cx0, cy0, cx1, cy1 = bbox(M['cap'])
tipL = (cx0, col_ext(M['cap'], cx0+1)[1]); tipR = (cx1, col_ext(M['cap'], cx1-1)[1])
dome = [tipL] + [(x, col_ext(M['cap'], x)[0]) for x in np.linspace(cx0+10, cx1-10, 7)] + [tipR]
under = [(x, col_ext(M['cap'], x)[1]) for x in np.linspace(cx1-16, cx0+16, 7)]       # right -> left
cap_path = smooth(dome + under, closed=True)
# gills band: from the cap's lower edge down to the band's bottom
BAND = [(x/UP, y/UP) for (x,y) in [(60,520),(110,488),(170,450),(260,424),(410,414),(560,424),(650,450),(710,488),(760,520)]]
gx0, gx1 = BAND[0][0], BAND[-1][0]
gt = [(x, col_ext(M['cap'], x)[1]) for x in np.linspace(gx1, gx0, 9)]
gill_path = smooth(BAND + gt, closed=True)
gy_bottom = lambda x: np.interp(x, [p[0] for p in BAND], [p[1] for p in BAND])
# stem silhouette (face + collar + belly ...), sampled outside the arm rows
stem = M['face']|M['collar']|M['belly']|M['strap-l']|M['strap-r']|M['badge']|M['mouth']|M['lens-l']|M['lens-r']|M['eye-l']|M['eye-r']
fx0, fy0, fx1, fy1 = bbox(M['face']); bx0, by0, bx1, by1 = bbox(M['belly'])
ax0, ay0, ax1, ay1 = bbox(M['arm-l']); rx0, ry0, rx1, ry1 = bbox(M['arm-r'])
ys_upper = list(np.linspace(fy0+4, ay0-4, 5)); ys_lower = list(np.linspace(ay1+6, by1-8, 4))
def side(k):
    up = [(row_ext(stem, y)[k], y) for y in ys_upper]; lo = [(row_ext(stem, y)[k], y) for y in ys_lower]
    mid = ((up[-1][0]*0.45 + lo[0][0]*0.55), (ay0+ay1)/2)
    return up + [mid] + lo
left, right = side(0), side(1)
bottom = [(x, col_ext(M['belly'], x)[1]) for x in np.linspace(bx0+14, bx1-14, 5)]
top_hidden = (fx0+fx1)/2, fy0-10
stem_pts = [top_hidden] + left + bottom + right[::-1]
stem_path = smooth(stem_pts, closed=True)
# the head's own skin: the same silhouette down to just under the collar
collar_x0, collar_y0, collar_x1, collar_y1 = bbox(M['collar'])
ys_head = list(np.linspace(fy0+4, collar_y0-7, 5))
hl_pts = [(row_ext(M['face'], y)[0], y) for y in ys_head]; hr_pts = [(row_ext(M['face'], y)[1], y) for y in ys_head]
hl_pts += [(row_ext(stem, collar_y0+5)[0], collar_y0+5), (row_ext(stem, collar_y1-4)[0]+1, collar_y1-4)]; hr_pts += [(row_ext(stem, collar_y0+5)[1], collar_y0+5), (row_ext(stem, collar_y1-4)[1]-1, collar_y1-4)]
head_skin = smooth([top_hidden] + hl_pts + [((fx0+fx1)/2, collar_y1+3)] + hr_pts[::-1], closed=True)
# arms
def arm_path(m):
    x0,y0,x1,y1 = bbox(m); ys = np.linspace(y0+9, y1-6, 4)
    L = [(row_ext(m,y)[0], y) for y in ys]; Rr = [(row_ext(m,y)[1], y) for y in ys]
    e = row_ext(m, y1-4); bot = ((e[0]+e[1])/2, y1)
    e = row_ext(m, y0+9); top = ((e[0]+e[1])/2, y0+1)
    return smooth([top] + L + [bot] + Rr[::-1], closed=True)
arm_l_path, arm_r_path = arm_path(M['arm-l']), arm_path(M['arm-r'])
shoulder_l = ((row_ext(M['arm-l'], ay0+3)[0]+row_ext(M['arm-l'], ay0+3)[1])/2, ay0+3)
shoulder_r = ((row_ext(M['arm-r'], ry0+3)[0]+row_ext(M['arm-r'], ry0+3)[1])/2, ry0+3)
hand_l = ((row_ext(M['arm-l'], ay1-4)[0]+row_ext(M['arm-l'], ay1-4)[1])/2, ay1-3)
hand_r = ((row_ext(M['arm-r'], ry1-4)[0]+row_ext(M['arm-r'], ry1-4)[1])/2, ry1-3)
# collar: top and bottom edges by column
cxs = np.linspace(collar_x0+3, collar_x1-3, 11)
collar_top = [(x, col_ext(M['collar']|M['badge'], x)[0]) for x in cxs]
collar_bot = [(x, col_ext(M['collar']|M['badge'], x)[1]) for x in cxs[::-1]]
collar_path = smooth(collar_top + collar_bot, closed=True)
# badge, glasses, eyes, mouth
bgx0, bgy0, bgx1, bgy1 = bbox(M['badge']); badge = ((bgx0+bgx1)/2, (bgy0+bgy1)/2, (bgx1-bgx0+bgy1-bgy0)/4 + 1.2)
def circle_of(m):
    x0,y0,x1,y1 = bbox(m); return ((x0+x1)/2, (y0+y1)/2, (x1-x0+y1-y0)/4)
lensL, lensR = circle_of(M['lens-l']|M['eye-l']), circle_of(M['lens-r']|M['eye-r'])
lensL = (lensL[0], lensL[1], lensL[2]+1.4); lensR = (lensR[0], lensR[1], lensR[2]+1.4)
def ellipse_of(m):
    x0,y0,x1,y1 = bbox(m); return ((x0+x1)/2, (y0+y1)/2, (x1-x0)/2, (y1-y0)/2)
eyeL, eyeR = ellipse_of(M['eye-l']), ellipse_of(M['eye-r'])
def highlight(eye):
    x0,y0,x1,y1 = bbox(eye); box = np.zeros_like(eye); box[int(y0*UP):int(y1*UP), int(x0*UP):int(x1*UP)] = True
    w = box & (lum > 190) & fig
    if not w.any(): return None
    cx, cy = centroid(w); return (cx, cy, max(1.4, np.sqrt(w.sum()/np.pi)/UP))
hlL, hlR = highlight(M['eye-l']), highlight(M['eye-r'])
mx0, my0, mx1, my1 = bbox(M['mouth'])
# brows: ink just above each lens
def brow(lens):
    cx, cy, r = lens; box = np.zeros_like(ink)
    box[int((cy-r-14)*UP):int((cy-r-1)*UP), int((cx-r+2)*UP):int((cx+r-2)*UP)] = True
    m = ink & box
    if not m.any(): return None
    x0,y0,x1,y1 = bbox(m); return (x0, y1-1, (x0+x1)/2, y0, x1, y1-1)
browL, browR = brow(lensL), brow(lensR)
# nose (a soft tan dot between the lenses), tongue, cheeks: sampled colours at known spots
nose = ((lensL[0]+lensR[0])/2, lensL[1]+4)
nose_c = hexc(px(*nose)); tongue_c = hexc(px((mx0+mx1)/2, my1-1.5)); blush_c = hexc(px(fx0+8, my0-2))
# boots
def boot_box(m):
    x0,y0,x1,y1 = bbox(m); return (x0, y0, x1-x0, y1-y0)
bootL, bootR = boot_box(M['boot-l']), boot_box(M['boot-r'])
# straps: a centre line each (top, mid, bottom)
def strap_line(m):
    x0,y0,x1,y1 = bbox(m); pts = []
    for y in (y0+2, (y0+y1)/2, y1-2):
        e = row_ext(m, y); pts.append(((e[0]+e[1])/2, y))
    e = row_ext(m, (y0+y1)/2); return pts, (e[1]-e[0])*0.85
strapL, strap_w = strap_line(M['strap-l']); strapR, _ = strap_line(M['strap-r'])
# satchel peeking out on the left
px0, py0, px1, py1 = bbox(M['pack'])
# sprout leaves: connected blobs of the sprout label
leaves = [(x/UP, y/UP, rx/UP, ry/UP, rot) for (x,y,rx,ry,rot) in
          [(154,632,17,10,-35),(190,660,17,10,30),(134,690,17,10,-25),(172,706,17,10,35),(128,746,16,10,-20),(160,770,16,10,40),(122,806,15,9,-15)]]
# cap spots: bright blobs inside the cap
spots = []; bright = M['cap'] & (lum > 200); bright = erode(dilate(bright, 1), 1)
while bright.any():
    ys, xs = np.nonzero(bright); comp = flood(bright, (int(xs[0]), int(ys[0])))
    if comp.sum() > 20*UP*UP:
        x0,y0,x1,y1 = bbox(comp); spots.append(((x0+x1)/2, (y0+y1)/2, (x1-x0)/2+0.6, (y1-y0)/2+0.6))
    bright &= ~comp
spot_c = hexc(np.median(a[M['cap'] & (lum > 200)], axis=0)) if (M['cap'] & (lum > 200)).any() else '#F1E6C6'
figx0, figy0, figx1, figy1 = bbox(fig)

# ---------------------------------------------------------------------------
# 4. the drawing
# ---------------------------------------------------------------------------
def E(x, y, rx, ry, **kw):
    attrs = ' '.join(f'{k.replace("_","-")}="{v}"' for k,v in kw.items())
    return f'<ellipse cx="{f(x)}" cy="{f(y)}" rx="{f(rx)}" ry="{f(ry)}" {attrs}/>'
def C(x, y, r, **kw):
    attrs = ' '.join(f'{k.replace("_","-")}="{v}"' for k,v in kw.items())
    return f'<circle cx="{f(x)}" cy="{f(y)}" r="{f(r)}" {attrs}/>'
LINE = f'stroke="{INK}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"'

gill_lines = ' '.join(f'M{f(x)} {f(col_ext(M["cap"], x)[1]+1)}V{f(gy_bottom(x)-1.5)}' for x in np.linspace(gx0+12, gx1-12, 15))
rib_lines = ' '.join(f'M{f(x)} {f(collar_y1+10)}V{f(by1-8)}' for x in np.linspace(bx0+22, bx1-22, 6))
spots_svg = '\n    '.join(E(*s, fill=spot_c) for s in spots)
leaves_svg = '\n    '.join(E(x, y, rx, ry, fill=sprout_c, stroke=INK, stroke_width="1.2", transform=f"rotate({rot} {f(x)} {f(y)})") for (x,y,rx,ry,rot) in leaves)
stem_line = f'M{f(leaves[-1][0]+6)} {f(leaves[-1][1]+2)}C{f(leaves[2][0]+4)} {f(leaves[3][1])} {f(leaves[0][0]-2)} {f(leaves[1][1])} {f(leaves[0][0]+4)} {f(leaves[0][1]-2)}'
def brow_svg(b):
    if not b: return ''
    x0,y0,xm,ym,x1,y1 = b; return f'<path d="M{f(x0)} {f(y0)}Q{f(xm)} {f(ym-2)} {f(x1)} {f(y1)}" fill="none" stroke="{INK}" stroke-width="2.4" stroke-linecap="round"/>'
mouth_svg = (f'<path d="M{f(mx0)} {f(my0+1)}Q{f((mx0+mx1)/2)} {f(my0-1)} {f(mx1)} {f(my0+1)}'
             f'Q{f(mx1)} {f(my1+1)} {f((mx0+mx1)/2)} {f(my1+1)}Q{f(mx0)} {f(my1+1)} {f(mx0)} {f(my0+1)}Z" fill="{eye_c}"/>'
             + E((mx0+mx1)/2, my1-2, (mx1-mx0)*0.28, (my1-my0)*0.22, fill=tongue_c))

def prop_magnifier():
    x, y = hand_r
    return f'''<g class="m-prop m-prop-magnifier">
      <path d="M{f(x)} {f(y+2)}l3 13" stroke="{INK}" stroke-width="7" stroke-linecap="round"/>
      <path d="M{f(x)} {f(y+2)}l3 13" stroke="{strap_c}" stroke-width="4" stroke-linecap="round"/>
      {C(x+6, y+26, 11, fill="#DCE5D4", fill_opacity=".55", stroke=INK, stroke_width="4.5")}
      <path d="M{f(x+0.5)} {f(y+23)}c.6-3 3-5.5 6-6" fill="none" stroke="#FFFFFF" stroke-width="2.2" stroke-linecap="round" opacity=".85"/>
    </g>'''
def prop_notebook():
    x, y = hand_l
    return f'''<g class="m-prop m-prop-notebook">
      <rect x="{f(x-18)}" y="{f(y+4)}" width="34" height="42" rx="4" fill="{gill_c}" stroke="{INK}" stroke-width="2.2"/>
      <path d="M{f(x-9)} {f(y+14)}h16M{f(x-9)} {f(y+22)}h16M{f(x-9)} {f(y+30)}h10" stroke="{sprout_c}" stroke-width="2.4" stroke-linecap="round" fill="none"/>
      <path d="M{f(x-15)} {f(y+9)}h5M{f(x-15)} {f(y+17)}h5M{f(x-15)} {f(y+25)}h5M{f(x-15)} {f(y+33)}h5M{f(x-15)} {f(y+41)}h5" stroke="{INK}" stroke-width="1.8" stroke-linecap="round"/>
      <rect x="{f(x+13)}" y="{f(y+16)}" width="5" height="9" rx="1.5" fill="#D9853B" stroke="{INK}" stroke-width="1.4"/>
    </g>'''

def pv(p): return f'{f(p[0])}px {f(p[1])}px'
midx = (figx0+figx1)/2
css = open(os.path.join(HERE, 'rig.css')).read()
for k, v in {
  '@FLIP@': pv((midx, (figy0+figy1)/2)), '@FIGURE@': pv((midx, figy1)), '@TORSO@': pv((midx, figy1-8)),
  '@HEAD@': pv(((fx0+fx1)/2, collar_y0+6)), '@ARM_L@': pv(shoulder_l), '@ARM_R@': pv(shoulder_r),
  '@HAND_L@': pv(hand_l), '@HAND_R@': pv(hand_r),
  '@LEG_L@': pv((bootL[0]+bootL[2]/2, bootL[1]+2)), '@LEG_R@': pv((bootR[0]+bootR[2]/2, bootR[1]+2)),
  '@EYE_L@': pv(eyeL[:2]), '@EYE_R@': pv(eyeR[:2]), '@SHADOW@': pv((midx, figy1+2)),
}.items(): css = css.replace(k, v)

svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="-30 -6 265 332" width="265" height="332"
     class="mylo" data-anim="idle" data-prop="none" data-facing="front"
     role="img" aria-labelledby="mylo-title mylo-desc">
  <title id="mylo-title">Mylo, the Mycelium mushroom scout</title>
  <desc id="mylo-desc">A small mushroom scout with a green spotted cap, round glasses, a green neckerchief with a leaf badge, a satchel and green boots.</desc>
  <defs>
    <linearGradient id="mylo-cap" x1="0" y1="0" x2=".3" y2="1">
      <stop offset="0" stop-color="{cap_c}" stop-opacity="1"/><stop offset="1" stop-color="{color(M['cap'] & (lum < 118))}"/>
    </linearGradient>
    <clipPath id="mylo-stem"><path d="{stem_path}"/></clipPath>
  </defs>
  <style>{css}</style>

  <g class="m-flip">
    <ellipse class="m-shadow" cx="{f(midx)}" cy="{f(figy1+2)}" rx="{f((figx1-figx0)*0.42)}" ry="6" fill="#D6C69C" opacity=".45"/>
    <g class="m-figure">

      <g class="m-legs">
        <g class="m-leg-l">
          <rect x="{f(bootL[0])}" y="{f(bootL[1]-10)}" width="{f(bootL[2])}" height="{f(bootL[3]+10)}" rx="{f(bootL[3]*0.48)}" fill="{boot_c}" {LINE}/>
          {E(bootL[0]+bootL[2]*0.45, bootL[1]+7, bootL[2]*0.26, 2.6, fill="#FFFFFF", opacity=".18")}
        </g>
        <g class="m-leg-r">
          <rect x="{f(bootR[0])}" y="{f(bootR[1]-10)}" width="{f(bootR[2])}" height="{f(bootR[3]+10)}" rx="{f(bootR[3]*0.48)}" fill="{boot_c}" {LINE}/>
          {E(bootR[0]+bootR[2]*0.45, bootR[1]+7, bootR[2]*0.26, 2.6, fill="#FFFFFF", opacity=".18")}
        </g>
      </g>

      <!-- satchel, stem, straps: behind the arms -->
      <g class="m-torso m-torso-back">
        <rect x="{f(px0-1)}" y="{f(py0-4)}" width="{f(px1-px0+14)}" height="{f(py1-py0+8)}" rx="6" fill="{pack_c}" {LINE}/>
        <path d="{stem_path}" fill="{belly_c}" {LINE}/>
        <path d="{rib_lines}" fill="none" stroke="{gill_c}" stroke-width="1.6" stroke-linecap="round" opacity=".5"/>
        <g clip-path="url(#mylo-stem)">
          <path d="{smooth(strapL, closed=False)}" fill="none" stroke="{INK}" stroke-width="{f(strap_w+2.4)}" stroke-linecap="round"/>
          <path d="{smooth(strapL, closed=False)}" fill="none" stroke="{strap_c}" stroke-width="{f(strap_w)}" stroke-linecap="round"/>
          <path d="{smooth(strapR, closed=False)}" fill="none" stroke="{INK}" stroke-width="{f(strap_w+2.4)}" stroke-linecap="round"/>
          <path d="{smooth(strapR, closed=False)}" fill="none" stroke="{strap_c}" stroke-width="{f(strap_w)}" stroke-linecap="round"/>
        </g>
      </g>

      <g class="m-head">
        <path d="{head_skin}" fill="{skin_c}" {LINE}/>
        <path d="{gill_path}" fill="{gill_c}" {LINE}/>
        <path d="{gill_lines}" fill="none" stroke="{INK}" stroke-width="1" stroke-linecap="round" opacity=".28"/>
        <path d="{cap_path}" fill="url(#mylo-cap)" {LINE}/>
        {spots_svg}
        {brow_svg(browL)}
        {brow_svg(browR)}
        {E(fx0+9, my0-3, 6, 3.2, fill=blush_c, opacity=".55")}
        {E(fx1-9, my0-3, 6, 3.2, fill=blush_c, opacity=".55")}
        {C(lensL[0], lensL[1], lensL[2], fill=lens_c, fill_opacity=".55")}
        {C(lensR[0], lensR[1], lensR[2], fill=lens_c, fill_opacity=".55")}
        <g class="m-eye-l">{E(*eyeL, fill=eye_c)}{C(*hlL, fill="#FFFFFF") if hlL else ''}</g>
        <g class="m-eye-r">{E(*eyeR, fill=eye_c)}{C(*hlR, fill="#FFFFFF") if hlR else ''}</g>
        {C(lensL[0], lensL[1], lensL[2], fill="none", stroke=INK, stroke_width="3.4")}
        {C(lensR[0], lensR[1], lensR[2], fill="none", stroke=INK, stroke_width="3.4")}
        <path d="M{f(lensL[0]+lensL[2])} {f(lensL[1]-2)}Q{f((lensL[0]+lensR[0])/2)} {f(lensL[1]-7)} {f(lensR[0]-lensR[2])} {f(lensR[1]-2)}" fill="none" stroke="{INK}" stroke-width="2.6" stroke-linecap="round"/>
        <path d="M{f(lensL[0]-lensL[2])} {f(lensL[1]-1)}L{f(row_ext(M['face'], lensL[1]-4)[0]+1)} {f(lensL[1]-4)}M{f(lensR[0]+lensR[2])} {f(lensR[1]-1)}L{f(row_ext(M['face'], lensR[1]-4)[1]-1)} {f(lensR[1]-4)}" fill="none" stroke="{INK}" stroke-width="2.4" stroke-linecap="round"/>
        {E(nose[0], nose[1], 4.2, 3, fill=nose_c)}
        {mouth_svg}
      </g>

      <g class="m-arm-l">
        <path d="{arm_l_path}" fill="{skin_c}" {LINE}/>
        <g class="m-hand-l">{prop_notebook()}</g>
      </g>
      <g class="m-arm-r">
        <path d="{arm_r_path}" fill="{skin_c}" {LINE}/>
        <g class="m-hand-r">{prop_magnifier()}</g>
      </g>

      <!-- collar, badge, sprout: in front of the arms and the neck -->
      <g class="m-torso m-torso-front">
        <path d="{collar_path}" fill="{collar_c}" {LINE}/>
        {C(badge[0], badge[1], badge[2], fill=badge_c, stroke=INK, stroke_width="2")}
        {C(badge[0], badge[1], badge[2]-3, fill="none", stroke=spot_c, stroke_width="1", opacity=".6")}
        <path d="M{f(badge[0])} {f(badge[1]-6)}v12M{f(badge[0])} {f(badge[1]-1)}c-5-1-7-4-7-8 4 0 7 3 7 8Zm0 0c5-1 7-4 7-8-4 0-7 3-7 8Zm0 5c-4-1-6-3-6-6 3 0 5 2 6 6Zm0 0c4-1 6-3 6-6-3 0-5 2-6 6Z" fill="{spot_c}" stroke="{spot_c}" stroke-width="1" stroke-linejoin="round"/>
        <g class="m-sprout">
          <path d="{stem_line}" fill="none" stroke="{sprout_c}" stroke-width="2" stroke-linecap="round"/>
          {leaves_svg}
        </g>
      </g>

      <g class="m-fx m-fx-thought" fill="{sprout_c}" stroke="{INK}" stroke-width="1.4">
        <circle class="m-dot-1" cx="{f(figx1-10)}" cy="{f(figy0+90)}" r="3.4"/><circle class="m-dot-2" cx="{f(figx1+4)}" cy="{f(figy0+72)}" r="5"/><circle class="m-dot-3" cx="{f(figx1+18)}" cy="{f(figy0+50)}" r="6.8"/>
      </g>
      <g class="m-fx m-fx-spark" fill="#D9A93F">
        <path class="m-spark-1" d="M17 82c1.2 5.4 2.4 6.6 7.8 7.8-5.4 1.2-6.6 2.4-7.8 7.8-1.2-5.4-2.4-6.6-7.8-7.8 5.4-1.2 6.6-2.4 7.8-7.8Z" style="transform-origin:17px 89.8px"/>
        <path class="m-spark-2" d="M188 44c1.5 6.6 3 8 9.6 9.6-6.6 1.5-8 3-9.6 9.6-1.5-6.6-3-8-9.6-9.6 6.6-1.5 8-3 9.6-9.6Z" style="transform-origin:188px 53.6px"/>
        <path class="m-spark-3" d="M30 30c1 4.4 2 5.4 6.4 6.4-4.4 1-5.4 2-6.4 6.4-1-4.4-2-5.4-6.4-6.4 4.4-1 5.4-2 6.4-6.4Z" style="transform-origin:30px 36.4px"/>
      </g>
    </g>
  </g>
</svg>
'''
svg = re.sub(r'\n\s*\n', '\n', svg)
open(OUT, 'w').write(svg)
print('INK', INK, 'face px', int(M['face'].sum()), 'gills px', int(M['gills'].sum()))
print('wrote', os.path.abspath(OUT), os.path.getsize(OUT), 'bytes,', svg.count('<path') + svg.count('<ellipse') + svg.count('<circle') + svg.count('<rect'), 'shapes')
print(json.dumps({'shoulder_l': shoulder_l, 'hand_l': hand_l, 'shoulder_r': shoulder_r, 'hand_r': hand_r, 'lensL': lensL, 'eyeL': eyeL, 'mouth': (mx0,my0,mx1,my1), 'badge': badge, 'collar': (collar_x0,collar_y0,collar_x1,collar_y1), 'spots': len(spots), 'leaves': len(leaves), 'brows': (browL, browR)}, default=lambda v: round(float(v),1)))
