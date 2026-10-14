#!/usr/bin/env python3
"""S56 bounded independent-data diagnostic. Does NOT edit or evaluate canonical suites.
OPENBLAS_NUM_THREADS=1 python3 tools/s56_seam_probe.py --out reports/s56-seam --data /tmp/s56-independent
"""
import argparse, collections, hashlib, json, pathlib, subprocess, sys, time
import numpy as np
from PIL import Image
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
import generator as G
import baseline as B
from readers import segmentation as S
from readers.glyphcnn import GlyphCNN,index_to_char
from lex_projection import fix_line
from gen_hard_corpus import make_item
from s56_topology_seam import split_piece,trim,partition

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def tensor(piece):
    piece=np.pad(trim(piece),1)
    return S.normalise_glyph(piece,(0,0,piece.shape[1]-1,piece.shape[0]-1))
def detected_word_crops(mask,records):
    """Read-time S54 word contract, no label or truth argument. Source xyxy inclusive."""
    groups=[]
    for r in records:
        if r['space'] or not groups:groups.append([])
        groups[-1].append(r['box'])
    output=[];h,w=mask.shape
    for boxes in groups:
        x0=max(0,min(b[0] for b in boxes)-3);y0=max(0,min(b[1] for b in boxes)-3)
        x1=min(w-1,max(b[2] for b in boxes)+3);y1=min(h-1,max(b[3] for b in boxes)+3)
        crop=mask[y0:y1+1,x0:x1+1];im=Image.fromarray((crop*255).astype(np.uint8))
        width=max(1,round(im.width*32/im.height));im=im.resize((width,32),Image.Resampling.BILINEAR)
        output.append({'word_bbox_xyxy':[x0,y0,x1,y1],'word_h':32,'word_w':width,'context':3,'crop_sha256':hashlib.sha256(im.tobytes()).hexdigest(),'glyph_offsets':None})
    return output

def read_mask(mask,net,enabled):
    records=[];operations=[];source_count=0
    t=time.perf_counter();capped=False
    for bi,band in enumerate(S.text_bands(mask)):
        boxes=S.glyph_boxes(mask,band)
        for i,(x0,y0,x1,y1,space) in enumerate(boxes):
            if source_count>=128:capped=True;break
            source_count+=1;piece=mask[y0:y1+1,x0:x1+1];parts=[piece]
            if enabled:
                parts,meta=split_piece(piece)
                if meta['accepted']:operations.append({'source_box_xyxy':[x0,y0,x1,y1],**meta})
            for j,p in enumerate(parts):records.append({'box':[x0,y0,x1,y1],'space':bool(space or (bi>0 and i==0)) if j==0 else False,'piece':p})
        if capped:break
    geom=time.perf_counter()-t
    t=time.perf_counter()
    if records:
        crops=np.stack([tensor(r['piece']) for r in records])[:,None].astype(np.float32)
        probs=net.forward(crops)[0];chars=[index_to_char(int(p.argmax())) for p in probs]
    else:chars=[]
    raw=''
    for record,ch in zip(records,chars):raw+=(' ' if record['space'] and raw else '')+ch
    text=fix_line(raw);classify=time.perf_counter()-t
    return {'raw':raw,'text':text,'glyph_count':len(records),'word_count':len(raw.split()),'geometry_seconds':round(geom,6),'classify_lex_seconds':round(classify,6),'total_seconds':round(geom+classify,6),'source_glyph_cap_hit':capped,'accepted_seams':operations,'word_crops':detected_word_crops(mask,records)}

def oracle(img,row,net):
    """Label/boxes accessed only in this separate ORACLE arm; S53 x0,x1,y0,y1."""
    mask=S.ink_mask(img);h,w=mask.shape
    crops=[]
    for x0,x1,y0,y1 in row['char_boxes']:
        box=(max(0,x0-1),max(0,y0-1),min(w-1,x1+1),min(h-1,y1+1))
        crops.append(S.normalise_glyph(mask,box))
    probs=net.forward(np.stack(crops)[:,None].astype(np.float32))[0]
    chars=iter(index_to_char(int(p.argmax())) for p in probs)
    raw=''.join(' ' if ch==' ' else next(chars) for ch in row['label'])
    return {'oracle_raw':raw,'oracle_lex':fix_line(raw),'oracle_raw_exact':raw==row['label'],'oracle_lex_exact':fix_line(raw)==row['label'],'truth_glyph_count':len(crops)}

def table(rows):
    result={}
    for key in sorted({(r['split'],r['family']) for r in rows}):
        group=[r for r in rows if (r['split'],r['family'])==key];out={'n':len(group)}
        for name in ('cnn_off','seam_on','shipping_lex'):
            out[name+'_exact']=sum(r[name]['text']==r['label'] for r in group)
        for base in ('cnn_off','shipping_lex'):
            recovered=[r['id'] for r in group if r['seam_on']['text']==r['label'] and r[base]['text']!=r['label']]
            regressed=[r['id'] for r in group if r['seam_on']['text']!=r['label'] and r[base]['text']==r['label']]
            out['vs_'+base]={'recoveries':len(recovered),'regressions':len(regressed),'net':len(recovered)-len(regressed),'recovered_ids':recovered,'regressed_ids':regressed}
        out['accepted_seams']=sum(len(r['seam_on']['accepted_seams']) for r in group)
        result['/'.join(key)]=out
    return result

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=pathlib.Path,default=ROOT/'reports/s56-seam');ap.add_argument('--data',type=pathlib.Path,required=True);ap.add_argument('--phase',choices=['development','heldout','all'],default='all');a=ap.parse_args()
    a.out.mkdir(parents=True,exist_ok=True);a.data.mkdir(parents=True,exist_ok=True)
    subprocess.run([sys.executable,str(ROOT/'tests/test_s56_topology_seam.py')],check=True)
    net=GlyphCNN.load(str(ROOT/'models/glyphcnn-v7b.npz'))
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    t_all=time.perf_counter();phases=[('development',56003131),('heldout',56004141)]
    if a.phase!='all':phases=[p for p in phases if p[0]==a.phase]
    for phase,seed in phases:
        rows=[];oracles=[];manifest=[];directory=a.data/phase;directory.mkdir(parents=True,exist_ok=True)
        for split in ('easy','hard'):
            fams=['easy'] if split=='easy' else [f for f in G.FAMILIES if f!='easy']
            for i in range(24):
                family=fams[i%len(fams)];idx=i if split=='easy' else i//len(fams)
                img,label=G.generate_one(family,seed=seed,index=idx)
                item_id=f'{split}-{family}-{idx:04d}';file=directory/(item_id+'.png');img.save(file)
                row={'id':item_id,'split':split,'family':family,'label':label,'image':file.name,'image_sha256':sha(file)};manifest.append(row.copy())
                tm=time.perf_counter();mask=S.ink_mask(img);row['mask_seconds']=round(time.perf_counter()-tm,6)
                # Labels/GT do not enter either read-time arm.
                row['cnn_off']=read_mask(mask,net,False);row['seam_on']=read_mask(mask,net,True)
                tm=time.perf_counter();raw,_=B.read_text(img,None);text=fix_line(raw)
                row['shipping_lex']={'raw':raw,'text':text,'total_seconds':round(time.perf_counter()-tm,6)}
                row['truth_counts']={'glyphs':len(label.replace(' ','')),'words':len(label.split())}
                rows.append(row)
                print(f'{phase} {item_id} off={row["cnn_off"]["text"]==label} on={row["seam_on"]["text"]==label} ship={text==label} seams={len(row["seam_on"]["accepted_seams"])}',flush=True)
        for i in range(18):
            img,row=make_item(i,seed,'s56-'+phase);file=directory/('oracle-'+row['id']+'.png');img.save(file)
            row.update(oracle(img,row,net));row['image_sha256']=sha(file);oracles.append(row)
        manifest_bytes='\n'.join(json.dumps(r,sort_keys=True) for r in manifest)+'\n';(directory/'manifest.jsonl').write_text(manifest_bytes)
        summary={split:{'n':24,**{name+'_exact':sum(r[name]['text']==r['label'] for r in rows if r['split']==split) for name in ('cnn_off','seam_on','shipping_lex')}} for split in ('easy','hard')}
        for split in ('easy','hard'):
            group=[r for r in rows if r['split']==split]
            for base in ('cnn_off','shipping_lex'):
                recovered=[r['id'] for r in group if r['seam_on']['text']==r['label'] and r[base]['text']!=r['label']]
                regressed=[r['id'] for r in group if r['seam_on']['text']!=r['label'] and r[base]['text']==r['label']]
                summary[split]['vs_'+base]={'recoveries':len(recovered),'regressions':len(regressed),'net':len(recovered)-len(regressed),'recovered_ids':recovered,'regressed_ids':regressed}
        runtime={name:{'sum_seconds':round(sum(r[name]['total_seconds'] for r in rows),3),'median_seconds':round(float(np.median([r[name]['total_seconds'] for r in rows])),6)} for name in ('cnn_off','seam_on','shipping_lex')}
        report={'source_sha':head,'phase':phase,'seed':seed,'canonical_suites_used':False,'weights_sha256':sha(ROOT/'models/glyphcnn-v7b.npz'),'manifest_sha256':hashlib.sha256(manifest_bytes.encode()).hexdigest(),'summary':summary,'per_family':table(rows),'runtime':runtime,'items':rows,'oracle_controls':{'label':'TRUTH-BOX ORACLE, not read-time/production accuracy; independent S53-style18-item panel','raw_exact':sum(r['oracle_raw_exact'] for r in oracles),'lex_exact':sum(r['oracle_lex_exact'] for r in oracles),'n':len(oracles),'items':oracles},'source_glyph_cap_hits':sum(r['cnn_off']['source_glyph_cap_hit'] for r in rows)}
        (a.out/(phase+'.json')).write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'phase':phase,'summary':summary,'runtime':runtime}),flush=True)
    print(f'Bounded batch complete in {time.perf_counter()-t_all:.1f}s; canonical suites untouched.',flush=True)
    return 0
if __name__=='__main__':raise SystemExit(main())
