import copy
import pytest
from PIL import Image
from pypdf import PdfReader
from app.models.domain import Photo,Layer,Job
from app.core.database import Database,starter_profiles
from app.services.layout import mm_to_pt,auto_layout,validate_layout,page_size
from app.services.imaging import import_info,render_photo,remove_background
from app.services.pdf import export_pdf,calibration_pdf

@pytest.fixture
def source(tmp_path):
    path=tmp_path/'portrait.png';Image.new('RGB',(900,1100),'red').save(path);return str(path)

def job_with(photos,**settings):
    j=Job(photos=photos);j.print_settings.update(settings);j.placements=auto_layout(j.photos,j.print_settings);j.page_count=max((r.page+1 for r in j.placements),default=1);return j

def test_units():assert mm_to_pt(25.4)==72

def test_dimensions_and_swap(source):
    p=Photo(layers=[Layer(source)]);assert render_photo(p).size==(531,650);p.swap();assert (p.width,p.height)==(55,45);assert render_photo(p).size==(650,531)

@pytest.mark.parametrize('quantity,rows',[ (4,[4]),(6,[4,2]),(8,[4,4]),(12,[4,4,4])])
def test_quantities_and_centered_rows(quantity,rows):
    p=Photo(quantity=quantity);j=job_with([p]);assert len(j.placements)==quantity;assert len({r.copy for r in j.placements})==quantity
    grouped={}
    for r in j.placements:grouped.setdefault(r.y,[]).append(r)
    assert [len(v) for v in grouped.values()]==rows
    for row in grouped.values():assert row[0].x==pytest.approx(210-(row[-1].x+row[-1].width))
    assert j.placements[0].y==10

def test_mixed_and_multipage():
    j=job_with([Photo(width=45,height=55,quantity=40),Photo(width=55,height=45,quantity=12),Photo(width=35,height=45,quantity=2)])
    assert j.page_count>1;validate_layout(j)
    assert len(j.placements)==54
    for p in j.photos:assert all((r.width,r.height)==(p.width,p.height) for r in j.placements if r.photo_id==p.id)

def test_landscape():
    j=job_with([Photo(quantity=25)],landscape=True);assert page_size(j.print_settings)==(297,210);validate_layout(j)

def test_oversize_and_invalid():
    with pytest.raises(ValueError):job_with([Photo(width=200,height=290)])
    with pytest.raises(ValueError):Photo(width=float('nan')).validate()
    with pytest.raises(ValueError):Photo(border_mm=30).validate()
    with pytest.raises(ValueError):Photo(quantity=0).validate()

def test_manual_validation():
    j=job_with([Photo(quantity=4)]);j.placements[0].x=-1
    with pytest.raises(ValueError,match='beyond'):validate_layout(j)
    j=job_with([Photo(quantity=4)]);j.placements[0].x=j.placements[1].x
    with pytest.raises(ValueError,match='overlap'):validate_layout(j)

def test_import_original_preserved(source,tmp_path):
    original=open(source,'rb').read();path,size,thumb=import_info(source);assert size==(900,1100);assert max(thumb.size)<=160
    render_photo(Photo(layers=[Layer(source,rotation=15)]));assert open(source,'rb').read()==original
    bad=tmp_path/'broken.png';bad.write_text('broken')
    with pytest.raises(Exception):import_info(str(bad))

def test_joint_alpha_composition(tmp_path):
    paths=[]
    for color in ('red','green'):
        im=Image.new('RGBA',(200,300),(0,0,0,0))
        from PIL import ImageDraw
        ImageDraw.Draw(im).rectangle((50,20,150,299),fill=color);p=tmp_path/(color+'.png');im.save(p);paths.append(str(p))
    photo=Photo(width=55,height=45,layers=[Layer(paths[0],x=.25,scale=.7),Layer(paths[1],x=.75,scale=.7)])
    im=render_photo(photo);assert im.getpixel((0,0))==(173,216,230);assert any(r>200 and g<20 for r,g,b in im.getdata());assert any(g>100 and r<20 for r,g,b in im.getdata())

def test_pdf_exact_dimensions_and_border(source,tmp_path):
    j=job_with([Photo(quantity=22,layers=[Layer(source)]),Photo(width=55,height=45,quantity=2,layers=[Layer(source)])]);target=tmp_path/'order.pdf';export_pdf(j,target)
    reader=PdfReader(target);assert len(reader.pages)==j.page_count
    image_placements=[];borders=[]
    for page in reader.pages:
        assert float(page.mediabox.width)==pytest.approx(mm_to_pt(210),abs=.0001);assert float(page.mediabox.height)==pytest.approx(mm_to_pt(297),abs=.0001)
        operations=page.get_contents().operations;matrix=None
        for operands,operator in operations:
            if operator==b'cm':matrix=[float(x) for x in operands]
            if operator==b'Do':image_placements.append(matrix)
            if operator==b're':borders.append([float(x) for x in operands])
    assert len(image_placements)==24
    for actual,expected in zip(image_placements,j.placements):
        assert actual[0]==pytest.approx(mm_to_pt(expected.width),abs=.0001);assert actual[3]==pytest.approx(mm_to_pt(expected.height),abs=.0001)
    assert borders[0][2]==pytest.approx(mm_to_pt(45-.2),abs=.0001)
    one=tmp_path/'one.pdf';export_pdf(j,one,current_page=0);assert len(PdfReader(one).pages)==1

def test_profile_and_job_roundtrip(tmp_path,source):
    db=Database(tmp_path/'studio.db');profiles=db.profiles();assert len(profiles)==len(starter_profiles())
    p=dict(profiles[0],name='Custom test',width=60,height=40,kind='Joint');db.save_profile(p)
    db.set('theme','Light');j=job_with([Photo(layers=[Layer(source)],quantity=8)]);db.save_job(j);db.conn.close()
    db=Database(tmp_path/'studio.db');assert db.get('theme')=='Light';assert next(p for p in db.profiles() if p['name']=='Custom test')['width']==60;assert db.load_job(j.id).to_dict()==j.to_dict();db.delete_profile('Custom test');assert len(db.profiles())==len(starter_profiles());db.conn.close()

def test_missing_sources_and_model(tmp_path,monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path))
    with pytest.raises(FileNotFoundError):render_photo(Photo(layers=[Layer(str(tmp_path/'missing.jpg'))]))
    with pytest.raises(ValueError,match='model'):remove_background('unused',tmp_path,tmp_path)

def test_calibration(tmp_path):
    path=tmp_path/'cal.pdf';calibration_pdf(path);page=PdfReader(path).pages[0]
    rectangles=[args for args,op in page.get_contents().operations if op==b're'];assert float(rectangles[0][2])==pytest.approx(mm_to_pt(100),abs=.0001)
