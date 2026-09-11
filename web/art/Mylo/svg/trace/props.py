"""Trace the magnifying glass and notebook from the sheet's props panel and
position them in Mylo's hands (source-pixel space of the front-view crop)."""
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__))
_REPO = _os.path.abspath(_os.path.join(_HERE, '..', '..', '..', '..', '..'))
SRC = _os.path.join(_REPO, 'docs', 'Resources', 'myloCharacterCard.png')
BUILD = _os.path.join(_HERE, 'build')          # scratch: pbm layers, json hand-offs (git-ignored)
_os.makedirs(BUILD, exist_ok=True); _os.chdir(BUILD)
import json, re, subprocess, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

UP = 4
sheet = Image.open(SRC).convert('RGB')
piv = json.load(open('pivots.json'))
num = r'-?\d+(?:\.\d+)?'

def dil(m,k):
    for _ in range(k):
        n=m.copy(); n[1:,:]|=m[:-1,:]; n[:-1,:]|=m[1:,:]; n[:,1:]|=m[:,:-1]; n[:,:-1]|=m[:,1:]; m=n
    return m
def ero(m,k):
    for _ in range(k):
        n=m.copy(); n[1:,:]&=m[:-1,:]; n[:-1,:]&=m[1:,:]; n[:,1:]&=m[:,:-1]; n[:,:-1]&=m[:,1:]; m=n
    return m

def transform_d(d, H):
    toks = re.findall(r'[MmCcLlZz]|'+num, d); out=[]; i=0; cur=None
    def P(x,y): return '%.1f %.1f' % (x*0.1/UP, (H - y*0.1)/UP)
    while i < len(toks):
        t = toks[i]
        if t in 'Zz': out.append('Z'); i+=1; continue
        if t in 'Mm':
            x,y = float(toks[i+1]), float(toks[i+2]); i+=3
            if t=='m' and cur is not None: x+=cur[0]; y+=cur[1]
            cur=(x,y); out.append('M'+P(x,y)); continue
        if t in 'Ll':
            while i+2 < len(toks) and re.fullmatch(num,toks[i+1]) and re.fullmatch(num,toks[i+2]):
                x,y = float(toks[i+1]), float(toks[i+2]); i+=2
                if t=='l': x+=cur[0]; y+=cur[1]
                cur=(x,y); out.append('L'+P(x,y))
            i+=1; continue
        if t in 'Cc':
            while i+6 < len(toks) and all(re.fullmatch(num,toks[i+k]) for k in range(1,7)):
                v=[float(toks[i+k]) for k in range(1,7)]; i+=6
                if t=='c': v=[v[0]+cur[0],v[1]+cur[1],v[2]+cur[0],v[3]+cur[1],v[4]+cur[0],v[5]+cur[1]]
                cur=(v[4],v[5]); out.append('C'+' '.join(P(v[k],v[k+1]) for k in (0,2,4)))
            i+=1; continue
        i+=1
    return ''.join(out)

def trace(mask, fn, H):
    Image.fromarray(((~mask)*255).astype(np.uint8)).save(fn+'.pbm')
    out = subprocess.run(['potrace', fn+'.pbm', '-s', '-o', '-', '-t', '30', '-a', '1.25', '-O', '1.0'], capture_output=True, text=True, check=True).stdout
    return ''.join(transform_d(d, H) for d in re.findall(r'<path d="([^"]+)"', out))

def hexc(c): return '#%02X%02X%02X' % tuple(int(v) for v in c)

def trace_prop(box, name, k):
    crop = sheet.crop(box); im = crop.resize((crop.width*UP, crop.height*UP), Image.LANCZOS)
    W,H = im.size; a = np.asarray(im).astype(int)
    bgim = im.copy()
    for xy in [(2,2),(W-3,2),(2,H-3),(W-3,H-3)]: ImageDraw.floodfill(bgim, xy, (255,0,255), thresh=26)
    bg = (np.asarray(bgim)==(255,0,255)).all(axis=2)
    white = a.min(axis=2) > 238
    for _ in range(12):                      # eat the sticker halo, not the cream pages
        bg = bg | (dil(bg,1) & white)
    fig = ero(~bg, 3)
    med = np.median(a[fig], axis=0)
    src = np.asarray(im).copy(); src[~fig] = med
    pim = Image.fromarray(src.astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.2))
    q = pim.quantize(colors=k, method=Image.Quantize.MEDIANCUT, kmeans=6, dither=Image.Dither.NONE)
    pal = np.array(q.getpalette()[:k*3]).reshape(-1,3).astype(float)
    l = np.asarray(Image.fromarray(np.asarray(q).astype(np.uint8),'L').filter(ImageFilter.ModeFilter(7))).astype(int)
    paths = []
    cols = sorted([(int(((l==c)&fig).sum()), c) for c in range(k)], reverse=True)
    for n,c in cols:
        if n < 60: continue
        d = trace((l==c)&fig, f'prop_{name}_{c}', H)
        if d: paths.append(f'<path fill="{hexc(pal[c])}" stroke="{hexc(pal[c])}" stroke-width=".5" stroke-linejoin="round" d="{d}"/>')
    ys,xs = np.nonzero(fig)
    return '\n'.join(paths), fig, (W,H)

# ---- magnifying glass: anchor = handle tip (lowest point), axis to the lens centre
gpaths, gfig, (GW,GH) = trace_prop((445, 870, 550, 990), 'glass', 6)
ys,xs = np.nonzero(gfig); ymax = ys.max(); tip = (xs[ys>ymax-6].mean()/UP, ymax/UP)
top = ys < ys.min() + (ymax-ys.min())*0.55; lens = (xs[top].mean()/UP, ys[top].mean()/UP)
ang = np.degrees(np.arctan2(lens[1]-tip[1], lens[0]-tip[0]))      # axis angle, image coords
rot = 90 - ang                                                    # make the axis point straight down from the hand
hx,hy = piv['hand-r']; s = 0.42
glass = f'<g transform="translate({hx:.1f} {hy-2:.1f}) rotate({rot:.1f}) scale({s}) translate({-tip[0]:.1f} {-tip[1]:.1f})">\n{gpaths}\n</g>'

# ---- notebook: anchor = lower-left corner, held upright below the left hand
npaths, nfig, (NW,NH) = trace_prop((575, 870, 700, 990), 'notebook', 8)
ys,xs = np.nonzero(nfig); x0,y0,x1,y1 = xs.min()/UP, ys.min()/UP, xs.max()/UP, ys.max()/UP
anchor = (x0 + (x1-x0)*0.22, y0 + (y1-y0)*0.08)                 # a point just inside the top-left, near the spiral
hx,hy = piv['hand-l']; s = 0.44
notebook = f'<g transform="translate({hx-2:.1f} {hy-1:.1f}) rotate(-8) scale({s}) translate({-anchor[0]:.1f} {-anchor[1]:.1f})">\n{npaths}\n</g>'

json.dump({'magnifier': glass, 'notebook': notebook}, open('props.json','w'))
print('glass tip', tip, 'lens', lens, 'rot', round(rot,1), '| notebook bbox', (x0,y0,x1,y1), file=sys.stderr)
