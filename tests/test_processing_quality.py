"""Measured retouching quality and real-widget regressions for the 3.4 follow-up."""
import hashlib
import numpy as np
import pytest
from PIL import Image
from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QApplication
from app.models.domain import Layer, Photo, Job
from app.services.imaging import prepare_layer
from test_preview_refinement import window, settle, textured_photo


@pytest.mark.parametrize('width', [1366, 1050, 800])
def test_crop_header_widgets_never_overlap(window, width):
    w=window;w.resize(width,740);w.open_cropper(load_source=False)
    w.studio.import_customer.setText('Customer: A very long customer name that must never cover Crop')
    settle(w);c=w.cropper
    widgets=[c.header.itemAt(i).widget() for i in range(c.header.count())]
    widgets=[item for item in widgets if item and item.isVisible()]
    bounds=[(item,item.geometry()) for item in widgets]
    details=[(getattr(item,'text',lambda:'')(),rect,item.minimumWidth(),item.sizeHint().width()) for item,rect in bounds]
    for i,(first,a) in enumerate(bounds):
        assert c.rect().contains(a), (details,c.rect())
        for second,b in bounds[i+1:]:
            assert not a.intersects(b), (getattr(first,'text',lambda:'')(),a,getattr(second,'text',lambda:'')(),b)


def test_fitted_photo_uses_available_height(window,textured_photo):
    w=window;w.resize(1366,740);w.start_workflow('portrait')
    w.photo.layers=[Layer(str(textured_photo))];w.sync_controls();settle(w)
    w.canvas.fit_preview()
    rect=w.canvas.mapFromScene(w.canvas.photo_rect).boundingRect()
    assert rect.height()>=w.canvas.viewport().height()*.91
    assert rect.width()/rect.height()==pytest.approx(w.photo.width/w.photo.height,abs=.015)
    assert rect.right()<w.editor_panel.mapTo(w.canvas.viewport(),QPoint()).x()+8


def test_color_denoise_reduces_chroma_without_blurring_luminance(tmp_path):
    import cv2
    rng=np.random.default_rng(42);lab=np.zeros((160,180,3),np.uint8)
    lab[:,:,0]=np.tile(np.where(np.arange(180)<90,95,180),(160,1));lab[:,:,1:]=128
    noisy=lab.copy();noisy[:,:,1:]=np.clip(128+rng.normal(0,13,(160,180,2)),0,255)
    path=tmp_path/'noisy.png';Image.fromarray(cv2.cvtColor(noisy,cv2.COLOR_LAB2RGB)).save(path)
    before=cv2.cvtColor(np.asarray(prepare_layer(Layer(str(path))).convert('RGB')),cv2.COLOR_RGB2LAB)
    after=cv2.cvtColor(np.asarray(prepare_layer(Layer(str(path),color_denoise=1)).convert('RGB')),cv2.COLOR_RGB2LAB)
    assert after[10:-10,10:70,1:].std()<before[10:-10,10:70,1:].std()*.6
    assert abs(float(after[:,:80,0].mean())-float(before[:,:80,0].mean()))<1.5
    assert float(after[:,100:,0].mean()-after[:,:80,0].mean())>70


def test_softening_reduces_cheek_texture_and_keeps_features(tmp_path,monkeypatch):
    from app.services import framing
    monkeypatch.setattr(framing,'detect_faces',lambda image:[(10,10,180,220)])
    rng=np.random.default_rng(4);rgb=np.clip([185,132,107]+rng.normal(0,13,(240,200,3)),0,255).astype(np.uint8)
    path=tmp_path/'face.png';Image.fromarray(rgb).save(path);digest=hashlib.sha256(path.read_bytes()).digest()
    result=np.asarray(prepare_layer(Layer(str(path),skin_soften=.8)).convert('RGB'))
    assert result[125:155,35:60].std(axis=(0,1)).mean()<rgb[125:155,35:60].std(axis=(0,1)).mean()*.75
    assert np.array_equal(result[65:100,70:130],rgb[65:100,70:130])
    assert np.array_equal(result[:8],rgb[:8])
    assert hashlib.sha256(path.read_bytes()).digest()==digest


def test_luminance_denoise_retains_step_edges_and_has_no_tile_seam(tmp_path):
    import cv2
    from app.services.portrait_processing import _denoise_channel
    rng=np.random.default_rng(77)
    gray=np.clip(np.tile(np.where(np.arange(180)<90,90,180),(530,1))+rng.normal(0,10,(530,180)),0,255).astype(np.uint8)
    result=_denoise_channel(gray,.8)
    assert result[10:240,10:70].std()<gray[10:240,10:70].std()*.6
    assert float(result[:,100:].mean()-result[:,:80].mean())>85
    reference=cv2.fastNlMeansDenoising(gray,None,18,7,21)
    assert np.array_equal(result[240:275],reference[240:275])


@pytest.mark.parametrize('key,value',[('denoise',.8),('color_denoise',.9),('brightness',1.2),('contrast',1.2),('saturation',.7),('shadows',.4),('temperature',.5),('tint',.4),('sharpness',2)])
def test_each_processing_control_changes_pixels_and_preserves_alpha(textured_photo,key,value):
    baseline=prepare_layer(Layer(str(textured_photo)))
    layer=Layer(str(textured_photo));setattr(layer,key,value);result=prepare_layer(layer)
    assert result.size==baseline.size and result.getchannel('A').tobytes()==baseline.getchannel('A').tobytes()
    assert np.mean(np.abs(np.asarray(result.convert('RGB'),float)-np.asarray(baseline.convert('RGB'),float)))>.2
    assert prepare_layer(layer,before=True).tobytes()==baseline.tobytes()


def test_warmth_and_tint_retain_black(tmp_path):
    path=tmp_path/'black.png';Image.new('RGB',(50,60),'black').save(path)
    assert np.max(np.asarray(prepare_layer(Layer(str(path),temperature=.8,tint=.8))))==255  # alpha only
    assert not np.asarray(prepare_layer(Layer(str(path),temperature=.8,tint=.8)).convert('RGB')).any()


def test_auto_fix_is_repeatable_uses_foreground_and_reduces_cast(monkeypatch):
    from app.services import portrait_processing as processing
    monkeypatch.setattr(processing,'portrait_faces',lambda image:[])
    rng=np.random.default_rng(10);pixels=np.zeros((200,240,4),np.uint8)
    pixels[30:170,40:200,:3]=np.clip([96,111,101]+rng.normal(0,6,(140,160,3)),0,255)
    pixels[30:170,40:200,3]=255;image=Image.fromarray(pixels)
    first,found=processing.auto_adjustments(image);second,_=processing.auto_adjustments(image)
    assert first==second and not found and first['skin_soften']==0
    assert first['brightness']>1 and first['tint']>0 and first['denoise']>0 and first['color_denoise']>0
    corrected=processing.process_portrait(image.convert('RGB'),Layer('not-read',**{key:first[key] for key in processing.LIMITS}))
    before=pixels[50:150,60:180,:3].mean(axis=(0,1));after=np.asarray(corrected)[50:150,60:180].mean(axis=(0,1))
    assert abs(after[1]-(after[0]+after[2])/2)<abs(before[1]-(before[0]+before[2])/2)


def test_auto_fix_ui_undo_locking_and_job_roundtrip(window,textured_photo,monkeypatch):
    from app.services import portrait_processing as processing
    monkeypatch.setattr(processing,'portrait_faces',lambda image:[(20,20,150,180)])
    w=window;w.start_workflow('joint');w.photo.layers=[Layer(str(textured_photo)),Layer(str(textured_photo),locked=True,brightness=.8)]
    w.sync_controls();settle(w);original=Job.from_dict(w.job.to_dict()).to_dict()
    w.auto_fix.click();settle(w)
    assert w.photo.layers[0].skin_soften>0 and w.photo.layers[1].brightness==.8 and w.photo.layers[1].skin_soften==0
    actual=w.job.to_dict();assert Job.from_dict(actual).to_dict()==actual
    w.auto_fix.click();settle(w);assert w.job.to_dict()==actual
    w.undo_edit();settle(w);w.undo_edit();settle(w);assert w.job.to_dict()==original
    w.color_denoise.setValue(.8);w.tint.setValue(.4);settle(w)
    w.reset_adjustments();settle(w);assert w.photo.layers[0].color_denoise==w.photo.layers[0].tint==0


def test_processed_cache_is_transform_independent_copy_safe_and_invalidates_source(textured_photo,monkeypatch):
    from app.services import imaging
    imaging.clear_processed_cache();calls=[];original=imaging._prepare_layer
    def counted(*args,**kwargs):calls.append(1);return original(*args,**kwargs)
    monkeypatch.setattr(imaging,'_prepare_layer',counted)
    layer=Layer(str(textured_photo),color_denoise=.7);first=imaging.prepare_layer(layer)
    first.putpixel((0,0),(1,2,3,4));layer.x=.3;layer.rotation=25
    second=imaging.prepare_layer(layer);assert len(calls)==1 and second.getpixel((0,0))!=(1,2,3,4)
    Image.new('RGBA',(90,120),'#8593a1').save(textured_photo)
    assert imaging.prepare_layer(layer).size==(90,120) and len(calls)==2
    layer.color_denoise=0;imaging.prepare_layer(layer);assert len(calls)==3


@pytest.mark.parametrize('field,value',[('color_denoise',2),('tint',float('nan'))])
def test_new_fields_validate_and_old_documents_keep_neutral_defaults(field,value,textured_photo):
    data=Job(photos=[Photo(layers=[Layer(str(textured_photo))])]).to_dict()
    for key in ('color_denoise','tint'):data['photos'][0]['layers'][0].pop(key)
    layer=Job.from_dict(data).photos[0].layers[0];assert layer.color_denoise==layer.tint==0
    data['photos'][0]['layers'][0][field]=value
    with pytest.raises(ValueError,match='processing'):Job.from_dict(data)


def test_auto_white_balance_never_uses_pale_skin_as_neutral_reference(monkeypatch):
    from app.services import portrait_processing as processing
    monkeypatch.setattr(processing,'portrait_faces',lambda image:[(25,20,150,180)])
    image=Image.new('RGB',(200,240),'white')
    image.paste((203,183,174),(25,20,175,200))
    settings,found=processing.auto_adjustments(image)
    assert found and settings['temperature']==settings['tint']==0


def test_noise_estimate_uses_subject_instead_of_white_background():
    from app.services.portrait_processing import noise_level
    rng=np.random.default_rng(44);image=np.full((300,240),255,np.uint8);mask=np.zeros(image.shape,bool)
    mask[100:200,80:160]=True;image[mask]=np.clip(130+rng.normal(0,10,mask.sum()),0,255)
    assert noise_level(image,mask)>5


def test_processing_values_have_room_for_sign_and_both_decimals(window,textured_photo):
    w=window;w.start_workflow('portrait');w.photo.layers=[Layer(str(textured_photo))];w.sync_controls();settle(w)
    for key in ('denoise','color_denoise','temperature','tint','sharpness'):
        edit=getattr(w,key).lineEdit()
        assert edit.width()>=edit.fontMetrics().horizontalAdvance('-1.00')+12
