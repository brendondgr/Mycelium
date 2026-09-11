"""Trace the front view of Mylo from the character sheet into a rigged SVG.

Pipeline: crop+x4 upscale -> background flood -> ink/blob masks -> seeded region
floods -> group assignment (parts) with priority outline claiming -> underpaint
-> global colour quantisation -> per-part stacked potrace -> SVG with pivots.
"""
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__))
_REPO = _os.path.abspath(_os.path.join(_HERE, '..', '..', '..', '..', '..'))
SRC = _os.path.join(_REPO, 'docs', 'Resources', 'myloCharacterCard.png')
BUILD = _os.path.join(_HERE, 'build')          # scratch: pbm layers, json hand-offs (git-ignored)
_os.makedirs(BUILD, exist_ok=True); _os.chdir(BUILD)
import json, subprocess, sys, re, os
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

UP = 4
NCOLORS = int(os.environ.get('NCOLORS', 16))

sheet = Image.open(SRC).convert('RGB')
front = sheet.crop((500, 235, 705, 552))
SW, SH = front.size
im = front.resize((SW*UP, SH*UP), Image.LANCZOS)
W, H = im.size
a = np.asarray(im).astype(np.int16)

# ---------------------------------------------------------------- morphology
def erode(m, k):
    for _ in range(k):
        n = m.copy(); n[1:,:] &= m[:-1,:]; n[:-1,:] &= m[1:,:]; n[:,1:] &= m[:,:-1]; n[:,:-1] &= m[:,1:]; m = n
    return m
def dilate(m, k):
    for _ in range(k):
        n = m.copy(); n[1:,:] |= m[:-1,:]; n[:-1,:] |= m[1:,:]; n[:,1:] |= m[:,:-1]; n[:,:-1] |= m[:,1:]; m = n
    return m
def flood(mask, xy, ):
    m = Image.fromarray((mask*255).astype(np.uint8)).copy()
    ImageDraw.floodfill(m, xy, 128)
    return np.asarray(m) == 128

# ---------------------------------------------------------------- background
bgim = im.copy()
for xy in [(2,2),(W-3,2),(2,H-3),(W-3,H-3),(W//2,2),(W//2,H-3),(2,H//2),(W-3,H//2)]:
    ImageDraw.floodfill(bgim, xy, (255,0,255), thresh=26)
bg = (np.asarray(bgim) == (255,0,255)).all(axis=2)
fig = erode(~bg, 3)

# ---------------------------------------------------------------- ink
R,G,B = a[...,0], a[...,1], a[...,2]
lum = 0.299*R + 0.587*G + 0.114*B
dark = (((lum < 150) & ((R - G) > -12)) | (lum < 75)) & fig
thick = dilate(erode(dark, 5), 6) & dark
ink = dark & ~thick

# hand-drawn barrier where the painting has no line: cap underside / forehead
barrier = Image.new('L', (W,H), 0)
ImageDraw.Draw(barrier).line([(60,520),(110,488),(170,450),(260,424),(410,414),(560,424),(650,450),(710,488),(760,520)], fill=255, width=7)
barrier = np.asarray(barrier) > 0

wall = dilate(ink, 2) | thick | barrier
free = fig & ~wall

# ---------------------------------------------------------------- regions
seeds = {
  'cap':     ('free',  [(410,250),(300,180),(560,200)]),
  'gills':   ('free',  [(410,360),(250,420),(580,420),(150,470),(670,470)]),
  'face':    ('free',  [(410,470),(230,640),(600,640),(410,600),(560,660)]),
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
names = list(seeds)
idx = {n:i+1 for i,n in enumerate(names)}
lab = np.zeros((H,W), np.int32)
for name,(kind,pts) in seeds.items():
    src = free if kind=='free' else thick
    for (x,y) in pts:
        if not src[y,x] or lab[y,x]: continue
        got = flood(src & (lab==0), (x,y))
        lab[got] = idx[name]
        print(f'{name:8s} {x:4d},{y:4d}: {got.sum():7d} px', file=sys.stderr)

# sprout: whatever is unlabelled inside this polygon
poly = Image.new('L', (W,H), 0)
ImageDraw.Draw(poly).polygon([(100,600),(215,600),(230,690),(205,720),(180,830),(95,830)], fill=255)
sprout_zone = (np.asarray(poly) > 0) & fig & (lab==0)
idx['sprout'] = len(names)+1; names.append('sprout')
lab[sprout_zone & ~dark] = idx['sprout']

# ---------------------------------------------------------------- parts
parts = {   # draw order, first = bottom
  'boot-l': ['boot-l'], 'boot-r': ['boot-r'],
  'head':   ['cap','gills','face','lens-l','lens-r','mouth'],
  'eye-l':  ['eye-l'], 'eye-r': ['eye-r'],
  'torso':  ['collar','badge','belly','strap-l','strap-r','pack','sprout'],
  'arm-l':  ['arm-l'], 'arm-r': ['arm-r'],
}
# who wins a shared outline: arms over torso over legs over head; eyes never claim
priority = ['arm-l','arm-r','torso','boot-l','boot-r','head']
part_of = {}
for p, regs in parts.items():
    for r in regs: part_of[idx[r]] = p
part_ids = {p:i+1 for i,p in enumerate(parts)}
pl = np.zeros((H,W), np.int32)            # part label per pixel
for rid, p in part_of.items(): pl[lab==rid] = part_ids[p]

# 1) unlabelled *bright* leftovers (tongue, highlights, leaf, nose specks): nearest part
unassigned = fig & (pl==0) & ~dark
for _ in range(40):
    if not unassigned.any(): break
    grown = pl.copy()
    for p in parts:
        m = dilate(pl==part_ids[p], 1) & unassigned
        grown[m & (grown==0)] = part_ids[p]
    unassigned &= (grown==0); pl = grown
# highlights inside an eye belong to the eye
for e in ('eye-l','eye-r'):
    inside = flood(~(pl==part_ids[e]) , (1,1)) == False
    pl[inside & (pl!=part_ids[e]) & fig & ~dark & (dilate(pl==part_ids[e],3))] = part_ids[e]

# 2) dark pixels (outlines, unlabelled blobs): highest-priority part within reach
claim = fig & (pl==0)
REACH = 12
reach = {p: dilate(pl==part_ids[p], REACH) for p in priority}
for p in priority:                          # first in list wins
    m = claim & reach[p]
    pl[m] = part_ids[p]; claim &= ~m
# whatever is left: nearest
for _ in range(30):
    if not claim.any(): break
    grown = pl.copy()
    for p in parts:
        m = dilate(pl==part_ids[p], 1) & claim
        grown[m & (grown==0)] = part_ids[p]
    claim &= (grown==0); pl = grown

# ---------------------------------------------------------------- colour (per part)
KCOL = {'head': 12, 'torso': 9, 'arm-l': 5, 'arm-r': 5, 'boot-l': 4, 'boot-r': 4, 'eye-l': 3, 'eye-r': 3}
BLUR = {'torso': 2.4, 'arm-l': 2.0, 'arm-r': 2.0, 'boot-l': 1.6, 'boot-r': 1.6}
MEDIAN = {'torso': 9, 'arm-l': 7, 'arm-r': 7, 'head': 5}
MERGE = {'head': 16, 'torso': 18, 'arm-l': 18, 'arm-r': 18, 'boot-l': 14, 'boot-r': 14, 'eye-l': 30, 'eye-r': 30}
def region_color(mask):
    return np.median(a[mask], axis=0)

rasters = {}   # part -> (mask, label image, palette)
for p in parts:
    m = pl == part_ids[p]
    under = {}   # underpaint mask -> reference colour
    if p == 'head':
        for e in ('eye-l','eye-r'):
            under[e] = (pl == part_ids[e], region_color((lab==idx['lens-l'])|(lab==idx['lens-r'])))
        neck = dilate(lab==idx['face'], 22) & (pl==part_ids['torso']) & ~dilate(lab==idx['sprout'],4)
        under['neck'] = (neck, region_color(lab==idx['face']))
    if p == 'torso':
        for arm in ('arm-l','arm-r'):
            under[arm] = (dilate(lab==idx['belly'], 28) & (pl==part_ids[arm]), region_color(lab==idx['belly']))
    if p in ('boot-l','boot-r'):
        under['up'] = (dilate(lab==idx[p], 22) & (pl==part_ids['torso']), region_color(lab==idx[p]))
    full = m.copy()
    for um,_ in under.values(): full |= um
    # quantise this part alone: everything else is painted its median so no slot is wasted
    med = region_color(m)
    src = np.asarray(im).copy(); src[~m] = med
    pim = Image.fromarray(src.astype(np.uint8))
    if p in MEDIAN: pim = pim.filter(ImageFilter.MedianFilter(MEDIAN[p]))   # calm the soft rib texture
    pim = pim.filter(ImageFilter.GaussianBlur(BLUR.get(p, 1.1)))
    q = pim.quantize(colors=KCOL[p], method=Image.Quantize.MEDIANCUT, kmeans=6, dither=Image.Dither.NONE)
    pal = np.array(q.getpalette()[:KCOL[p]*3]).reshape(-1,3).astype(float)
    l = np.asarray(q).astype(np.int32)
    # merge near-identical palette entries: fewer, cleaner layers
    remap = list(range(len(pal)))
    for i in range(len(pal)):
        for j in range(i):
            if remap[j] == j and remap[i] == i and np.sqrt(((pal[i]-pal[j])**2).sum()) < MERGE.get(p, 14):
                remap[i] = j; break
    keep = sorted(set(remap)); newidx = {old:k for k,old in enumerate(keep)}
    l = np.vectorize(lambda v: newidx[remap[v]])(l)
    pal = pal[keep]
    li = Image.fromarray(l.astype(np.uint8), 'L').filter(ImageFilter.ModeFilter(7))
    l = np.asarray(li).astype(np.int32)
    for um, ref in under.values():
        l[um] = int(np.argmin(((pal - ref)**2).sum(1)))
    rasters[p] = (full, l, pal)
    print(p, 'palette', [tuple(int(v) for v in c) for c in pal], file=sys.stderr)

# ---------------------------------------------------------------- potrace
def trace_mask(mask, fn):
    Image.fromarray(((~mask)*255).astype(np.uint8)).save(fn+'.pbm')
    out = subprocess.run(['potrace', fn+'.pbm', '-s', '-o', '-', '-t', '36', '-a', '1.25', '-O', '1.0'],
                         capture_output=True, text=True, check=True).stdout
    return re.findall(r'<path d="([^"]+)"', out)

num = r'-?\d+(?:\.\d+)?'
def transform_d(d):
    # potrace: coordinates in 0.1 px, y flipped (translate(0,H) scale(.1,-.1)); we want source px (/UP)
    toks = re.findall(r'[MmCcLlZz]|'+num, d)
    out = []; i = 0; cur = None
    while i < len(toks):
        t = toks[i]
        if t in 'Zz': out.append('Z'); i += 1; continue
        if t in 'Mm':
            x, y = float(toks[i+1]), float(toks[i+2]); i += 3
            if t == 'm' and cur is not None: x += cur[0]; y += cur[1]
            cur = (x, y); out.append('M%.1f %.1f' % (x*0.1/UP, (H - y*0.1)/UP))
            # potrace follows M with implicit l pairs? it uses explicit commands, keep going
            continue
        if t in 'Ll':
            while i+2 < len(toks)+0 and re.fullmatch(num, toks[i+1]) and re.fullmatch(num, toks[i+2]):
                x, y = float(toks[i+1]), float(toks[i+2]); i += 2
                if t == 'l': x += cur[0]; y += cur[1]
                cur = (x, y); out.append('L%.1f %.1f' % (x*0.1/UP, (H - y*0.1)/UP))
            i += 1; continue
        if t in 'Cc':
            while i+6 < len(toks)+0 and all(re.fullmatch(num, toks[i+k]) for k in range(1,7)):
                v = [float(toks[i+k]) for k in range(1,7)]; i += 6
                if t == 'c':
                    v = [v[0]+cur[0], v[1]+cur[1], v[2]+cur[0], v[3]+cur[1], v[4]+cur[0], v[5]+cur[1]]
                cur = (v[4], v[5])
                out.append('C' + ' '.join('%.1f %.1f' % (v[k]*0.1/UP, (H - v[k+1]*0.1)/UP) for k in (0,2,4)))
            i += 1; continue
        i += 1
    return ''.join(out)

def hexc(c): return '#%02X%02X%02X' % tuple(int(v) for v in c)

svg_parts = {}
total_paths = 0
for p, (m, l, pal) in rasters.items():
    cols = [(int((l[m]==c).sum()), c) for c in range(len(pal))]
    cols = [(n,c) for n,c in cols if n > 40]
    cols.sort(reverse=True)
    layers = []
    for k,(n,c) in enumerate(cols):
        ds = trace_mask(m & (l==c), f'layer_{p}_{k}')
        if ds:
            col = hexc(pal[c])
            layers.append(f'<path fill="{col}" stroke="{col}" stroke-width=".5" stroke-linejoin="round" d="{"".join(transform_d(d) for d in ds)}"/>')
            total_paths += 1
    svg_parts[p] = '\n'.join(layers)
    print(f'{p}: {len(cols)} colours', file=sys.stderr)

# ---------------------------------------------------------------- pivots (source px)
def bbox(mask):
    ys, xs = np.nonzero(mask); return xs.min()/UP, ys.min()/UP, xs.max()/UP, ys.max()/UP
def centroid(mask):
    ys, xs = np.nonzero(mask); return xs.mean()/UP, ys.mean()/UP
piv = {}
for arm in ('arm-l','arm-r'):
    m = lab==idx[arm]; x0,y0,x1,y1 = bbox(m)
    top = m[int(y0*UP):int(y0*UP)+8*UP].any(axis=0); xs = np.nonzero(top)[0]
    piv[arm] = (xs.mean()/UP, y0+3)
    bot = m[int(y1*UP)-8*UP:int(y1*UP)+1].any(axis=0); xs = np.nonzero(bot)[0]
    piv['hand-'+arm[-1]] = (xs.mean()/UP, y1-3)
for boot in ('boot-l','boot-r'):
    m = lab==idx[boot]; x0,y0,x1,y1 = bbox(m); piv[boot] = ((x0+x1)/2, y0+2)
fx0,fy0,fx1,fy1 = bbox(lab==idx['face']); cx0,cy0,cx1,cy1 = bbox(lab==idx['collar'])
piv['head'] = ((fx0+fx1)/2, cy0+6)
piv['eye-l'] = centroid(lab==idx['eye-l']); piv['eye-r'] = centroid(lab==idx['eye-r'])
bx0,by0,bx1,by1 = bbox(fig)
piv['figure'] = ((bx0+bx1)/2, by1); piv['torso'] = ((bx0+bx1)/2, by1-8)
piv['sprout'] = (bbox(lab==idx['sprout'])[2], bbox(lab==idx['sprout'])[3])
piv['bounds'] = (bx0,by0,bx1,by1)
json.dump({k:[round(float(v),1) for v in vv] for k,vv in piv.items()}, open('pivots.json','w'), indent=1)
json.dump(svg_parts, open('parts.json','w'))
print('paths:', total_paths, 'pivots:', json.dumps({k:[round(float(v),1) for v in vv] for k,vv in piv.items()}), file=sys.stderr)

# quick diagnostic renders
vis = np.zeros((H,W,3), np.uint8)
rng = np.random.RandomState(5); cols = rng.randint(50,255,(len(parts)+1,3)).astype(np.uint8)
vis[:] = cols[pl]; vis[bg] = 0
Image.fromarray(vis).save('parts_vis.png')
