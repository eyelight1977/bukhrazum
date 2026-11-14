"""Crop OCR-located text bounds, avoiding table rules. No reference values."""
from pathlib import Path
import json, math
from PIL import Image

def prepare(workspace):
    p=Path(workspace)
    im=Image.open(p/'input/scan.png').convert('RGB')
    data=json.loads((p/'runs/extracted_initial.json').read_text())
    jobs=[]
    for col in data['columns'][2:]:
        words=col['words']
        if not words:continue
        box=[math.floor(min(w['bbox'][0] for w in words)),math.floor(min(w['bbox'][1] for w in words)),
             math.ceil(max(w['bbox'][2] for w in words)),math.ceil(max(w['bbox'][3] for w in words))]
        crop=im.crop(box); crop=crop.resize((crop.width*4,crop.height*4),Image.Resampling.LANCZOS)
        padded=Image.new('RGB',(crop.width+40,crop.height+40),'white');padded.paste(crop,(20,20))
        name=f'evidence/text_only_{col["number"]:02d}.png';padded.save(p/name)
        jobs.append({'id':f'text_only_{col["number"]:02d}','image':name,'psm':7,'whitelist':'0123456789.,- ',
                     'source_bbox':box})
    # For header text use the same grid crop but sparse mode as a diagnostic fallback.
    for h in data['headers']:
        if len(h['columns'])==1:
            jobs.append({'id':h['id']+'_sparse','image':'evidence/recognize_'+Path(h['evidence']).name,'psm':11})
    (p/'runs/confirmation_jobs.json').write_text(json.dumps(jobs,ensure_ascii=False,indent=2))
