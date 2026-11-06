import copy
from PIL import Image
from pypdf import PdfReader
from app.core.database import Database
from app.models.domain import Job,Photo,Layer
from app.services.print_sessions import PrintSessionStore,add_composition,choose_orientation
from app.services.layout import validate_layout,resize_copies
from app.services.pdf import export_pdf


def test_mixed_person_quantities_orientations_and_saved_session(tmp_path):
    db=Database(tmp_path/'studio.db');store=PrintSessionStore(db);source=tmp_path/'person.png';Image.new('RGB',(180,220),'red').save(source)
    original=Job(photos=[Photo(name='A',quantity=4,layers=[Layer(str(source))]),Photo(name='B',quantity=8,layers=[Layer(str(source))]),Photo(name='C',quantity=2,layers=[Layer(str(source))]),Photo(name='D',width=55,height=45,kind='Joint',quantity=4,layers=[Layer(str(source))]),Photo(name='E',quantity=4,layers=[Layer(str(source))])]);db.save_job(original);before=db.load_job(original.id).to_dict()
    job=Job(print_settings=dict(margin=10,gap_x=.2,gap_y=.2,landscape=False,layout='auto',enforce_margins=True))
    for photo in original.photos:add_composition(job,photo,original.id)
    assert {p.id for p in original.photos}.isdisjoint(p.id for p in job.photos)
    job.print_settings,job.placements,job.page_count=choose_orientation(job.photos,job.print_settings)
    validate_layout(job);assert len(job.placements)==22
    for landscape in (False,True):
        settings,placements,pages=choose_orientation(job.photos,dict(job.print_settings,landscape=landscape),False)
        assert settings['landscape']==landscape and job.page_count<=pages
    # A small physical manual move survives quantity changes and session reopen.
    job.placements[0].x+=.05;position=copy.deepcopy(job.placements[0]);job.photos[0].quantity+=2;resize_copies(job)
    assert next(r for r in job.placements if (r.photo_id,r.copy)==(position.photo_id,position.copy)).x==position.x
    id=store.save(job);restored=store.load(id);assert restored.to_dict()==job.to_dict()
    path=tmp_path/'mixed.pdf';export_pdf(restored,path, dpi=100);assert len(PdfReader(path).pages)==job.page_count
    assert db.load_job(original.id).to_dict()==before
    db.conn.close()


def test_orientation_tie_preserves_current_and_fit_failure(tmp_path):
    photo=Photo(quantity=1);settings=dict(margin=10,gap_x=.2,gap_y=.2,landscape=True,layout='auto')
    selected,_,_=choose_orientation([photo],settings);assert selected['landscape'] is True
    import pytest
    with pytest.raises(ValueError):choose_orientation([Photo(width=500,height=500)],settings)
