"""End-to-end local runtime diagnostic, also available in the frozen executable."""
from pathlib import Path
import json
import time
from PIL import Image
from app.core.database import data_root
from app.models.domain import Layer,Photo,Job
from app.services.imaging import remove_background,face_position,render_photo
from app.services.layout import auto_layout,validate_layout
from app.services.pdf import export_pdf

def verify_runtime(source,destination):
    output=Path(destination);output.mkdir(parents=True,exist_ok=True);start=time.monotonic()
    try:
        source=str(Path(source).resolve());mask=remove_background(source,data_root()/'models',data_root()/'cache')
        with Image.open(mask) as im:
            alpha=im.getchannel('A');assert alpha.getextrema()[0]<20 and alpha.getextrema()[1]>235
        portrait=Photo(name='Diagnostic portrait',quantity=8,layers=[face_position(Layer(source,mask),45,55)])
        joint=Photo(name='Diagnostic joint',width=55,height=45,quantity=2,kind='Joint composition',layers=[Layer(source,mask,x=.25,scale=.65),Layer(source,mask,x=.75,scale=.65)])
        for name,p in [('portrait',portrait),('joint',joint)]:render_photo(p).save(output/(name+'.png'))
        job=Job(photos=[portrait,joint]);job.placements=auto_layout(job.photos,job.print_settings);job.page_count=max(r.page for r in job.placements)+1;validate_layout(job);export_pdf(job,output/'mixed-order.pdf')
        result=dict(passed=True,seconds=round(time.monotonic()-start,2),checks=['CPU inference','alpha mask','face detection','portrait render','two-person composition','mixed-size PDF'])
    except Exception as e:
        import traceback
        result=dict(passed=False,error=str(e),traceback=traceback.format_exc())
    (output/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    return 0 if result['passed'] else 1
