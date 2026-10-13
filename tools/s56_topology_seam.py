#!/usr/bin/env python3
"""S56 offline lossless, row-varying 4-neighbour foreground-edge cut.
No morphology, CNN/confidence acceptance, template or straight-column sweep.
All constants fixed by reports/s56-seam/PROTOCOL.md; this is NOT a reader route.
"""
import numpy as np

STEP_COST = .05
MAX_EDGE_FRAC = .06
MIN_MASS_FRAC = .15
MIN_HEIGHT_FRAC = .75


def trim(mask):
    y,x=np.where(mask)
    return mask[y.min():y.max()+1,x.min():x.max()+1] if len(x) else mask[:0,:0]


def minimum_seam(mask):
    """Exact DP over seams moving -1/0/+1 per row; all interior boundaries.

    Energy = horizontal crossed foreground edges + vertical crossed foreground
    edges at steps + .05/step. A boundary is BETWEEN pixels, not a removed pixel.
    Returns seam[y] in 1..W-1, energy, integer count of foreground edges cut.
    """
    mask=np.asarray(mask,dtype=bool);h,w=mask.shape
    if h<2 or w<2 or h>256 or w>1024:return None
    n=w-1;parents=np.empty((h,n),dtype=np.int32)
    score=(mask[0,:-1]&mask[0,1:]).astype(float)
    parents[0]=np.arange(n)
    for y in range(1,h):
        horizontal=(mask[y,:-1]&mask[y,1:]).astype(float)
        previous=mask[y-1];current=mask[y]
        choices=np.full((3,n),np.inf)
        choices[0]=score
        # current boundary x=j+1, previous boundary x-1=j: vertical edge at j
        choices[1,1:]=score[:-1]+(current[1:-1]&previous[1:-1])+STEP_COST
        # current boundary x=j+1, previous boundary x+1=j+2: vertical edge at j+1
        choices[2,:-1]=score[1:]+(current[1:-1]&previous[1:-1])+STEP_COST
        pick=choices.argmin(axis=0)
        parents[y]=np.arange(n)+np.choose(pick,[0,-1,1])
        score=horizontal+np.take_along_axis(choices,pick[None,:],axis=0)[0]
    j=int(score.argmin());energy=float(score[j]);seam=np.empty(h,dtype=np.int32)
    for y in range(h-1,-1,-1):
        seam[y]=j+1;j=int(parents[y,j])
    crossed=sum(int(mask[y,x-1] and mask[y,x]) for y,x in enumerate(seam))
    for y in range(1,h):
        if seam[y]!=seam[y-1]:
            x=int(min(seam[y],seam[y-1]));crossed+=int(mask[y,x] and mask[y-1,x])
    assert abs(energy-crossed-STEP_COST*int(np.abs(np.diff(seam)).sum()))<1e-8
    return seam,energy,crossed


def partition(mask,seam):
    left=mask&(np.arange(mask.shape[1])[None,:]<seam[:,None])
    right=mask&~(np.arange(mask.shape[1])[None,:]<seam[:,None])
    assert not (left&right).any() and np.array_equal(left|right,mask)
    return left,right


def split_piece(mask):
    """One optional split; every acceptance condition is geometric only."""
    mask=np.asarray(mask,dtype=bool);result=minimum_seam(mask)
    if result is None or not mask.any():return [mask],{'accepted':False,'reason':'shape-or-empty'}
    seam,energy,crossed=result;left,right=partition(mask,seam);parts=[trim(left),trim(right)]
    mass=int(mask.sum());h=mask.shape[0]
    accepted=(crossed<=max(1,int(MAX_EDGE_FRAC*h)) and
              all(int(p.sum())>=MIN_MASS_FRAC*mass and p.shape[0]>=MIN_HEIGHT_FRAC*h for p in parts))
    meta={'accepted':bool(accepted),'edge_crossings':crossed,'energy':round(energy,6),
          'steps':int(np.abs(np.diff(seam)).sum()),'seam':seam.tolist(),
          'parent_hw':list(mask.shape),'side_ink':[int(left.sum()),int(right.sum())]}
    return parts if accepted else [mask],meta
