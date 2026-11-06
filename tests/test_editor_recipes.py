import copy
import pytest
from PIL import Image
from app.core.database import Database
from app.models.domain import Photo,Layer,Job
from app.services.profiles import normalize_profile,apply_profile
from app.services.imaging import prepare_layer,render_photo
from app.services.layer_groups import transform_group


def test_recipe_page_defaults_identity_and_snapshot(tmp_path):
    db=Database(tmp_path/'studio.db');p=normalize_profile(dict(name='Custom recipe',width=45,height=55,paper_orientation='landscape',margin=8,gap_x=.4,gap_y=.5,quantity=8))
    db.save_profile(p);db.rename_profile(p['name'],dict(p,name='Renamed'));renamed=next(x for x in db.profiles() if x['name']=='Renamed');assert renamed['recipe_id']==p['recipe_id']
    photo=Photo(layers=[Layer('source.png',x=.31,rotation=12)]);before=copy.deepcopy(photo.layers);settings={}
    apply_profile(photo,renamed,settings);assert photo.layers==before and settings['landscape'] is True and settings['margin']==8 and photo.quantity==8
    renamed['margin']=12;db.save_profile(renamed);assert photo.provenance['recipe_snapshot']['margin']==8
    assert Job.from_dict(Job(photos=[photo]).to_dict()).photos[0].provenance==photo.provenance
    with pytest.raises(ValueError):normalize_profile(dict(p,gap_x=-1))
    db.conn.close()


def test_brush_opacity_hardness_and_legacy_strokes(tmp_path):
    source=tmp_path/'source.png';Image.new('RGBA',(100,100),'red').save(source)
    l=Layer(str(source),mask_strokes=[dict(mode='erase',points=[[.5,.5]],radius=.2,opacity=.5,hardness=1)])
    image=prepare_layer(l);assert 125<=image.getpixel((50,50))[3]<=129
    l.mask_strokes[0]['opacity']=0;assert prepare_layer(l).getpixel((50,50))[3]==255
    l.mask_strokes[0].pop('opacity');l.mask_strokes[0].pop('hardness');assert prepare_layer(l).getpixel((50,50))[3]==0
    assert Image.open(source).getpixel((50,50))[3]==255


def test_group_transform_preserves_geometry_and_skips_locked():
    photo=Photo(width=40,height=60,layers=[Layer('a',x=.25,y=.5,group='g'),Layer('b',x=.75,y=.5,group='g'),Layer('c',x=.75,y=.5,group='g',locked=True)])
    transform_group(photo,0,.3,.6,2,0)
    assert photo.layers[1].x==pytest.approx(1.3) and photo.layers[1].y==pytest.approx(.6) and photo.layers[1].scale==2
    assert photo.layers[2].x==.75 and photo.layers[2].scale==1
    restored=Job.from_dict(Job(photos=[photo]).to_dict());assert restored.photos[0].layers[1].group=='g'
