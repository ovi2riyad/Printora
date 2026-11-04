"""Local integration check using OpenCV's sample image downloaded during development."""
from pathlib import Path
import time
from PIL import Image
from app.core.database import data_root
from app.models.domain import Layer,Photo,Job
from app.services.imaging import remove_background,face_position,render_photo
from app.services.layout import auto_layout,validate_layout
from app.services.pdf import export_pdf

def main():
    source=Path('.tools/face-test.jpg').resolve()
    if not source.exists():raise RuntimeError('Place a local frontal-face test image at .tools/face-test.jpg first.')
    start=time.monotonic();mask=remove_background(str(source),data_root()/'models',data_root()/'cache')
    with Image.open(mask) as im:
        alpha=im.getchannel('A');assert alpha.getextrema()[0]<20 and alpha.getextrema()[1]>235
    layer=face_position(Layer(str(source),mask),45,55)
    photo=Photo(name='Integration portrait',quantity=8,layers=[layer]);render_photo(photo).save('.tools/validated-portrait.png')
    joint=Photo(name='Integration joint',width=55,height=45,quantity=2,kind='Joint composition',layers=[Layer(str(source),mask,x=.25,scale=.65),Layer(str(source),mask,x=.75,scale=.65)])
    render_photo(joint).save('.tools/validated-joint.png')
    job=Job(photos=[photo,joint]);job.placements=auto_layout(job.photos,job.print_settings);job.page_count=max(r.page for r in job.placements)+1;validate_layout(job);export_pdf(job,'.tools/validated-order.pdf')
    print(f'PASS: CPU inference, nontrivial alpha, face detection, 2-person joint and mixed PDF in {time.monotonic()-start:.1f}s')

if __name__=='__main__':main()
