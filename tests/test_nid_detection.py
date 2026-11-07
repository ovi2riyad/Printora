"""Rounded, low-contrast NID boundaries, including the private supplied scans."""
import hashlib
from pathlib import Path
import cv2
import numpy as np
import pytest
from PIL import Image,ImageDraw,ImageEnhance,ImageFilter
from app.services.documents import detect_cards,detect_card,propose_card,DocumentPage
from app.services.cropping import order_quad,extract_region,CropRegion


def coverage(points,expected):
    a=order_quad(points);b=order_quad(expected)
    intersection=cv2.intersectConvexConvex(a,b)[0]
    return intersection/(cv2.contourArea(a)+cv2.contourArea(b)-intersection)


@pytest.mark.parametrize('name,expected',[
    ('front.jpg',[(575,650),(1585,688),(1565,1325),(555,1285)]),
    ('back.jpg',[(470,620),(1475,540),(1520,1180),(505,1255)]),
])
@pytest.mark.parametrize('limit',[1000,1500,1800])
def test_supplied_scans_find_one_full_card_at_multiple_preview_sizes(name,expected,limit):
    path=Path(__file__).resolve().parents[1]/'Demo/nid'/name
    if not path.is_file():pytest.skip('Private studio scan is not in source checkout')
    before=hashlib.sha256(path.read_bytes()).hexdigest()
    with Image.open(path) as raw:image=raw.convert('RGB')
    original=image.size;image.thumbnail((limit,limit));regions=detect_cards(image)
    assert len(regions)==1 # Never substitute the barcode or split one side into two.
    scaled=[(x*image.width/original[0],y*image.height/original[1]) for x,y in expected]
    assert coverage(regions[0],scaled)>.94
    crop=extract_region(image,CropRegion(regions[0]));assert 1.5<crop.width/crop.height<1.7
    assert hashlib.sha256(path.read_bytes()).hexdigest()==before


@pytest.mark.parametrize('level',[185,225,242])
def test_pale_rounded_card_keeps_outer_edge_instead_of_internal_barcode(level):
    im=Image.new('RGB',(1000,1400),'white');d=ImageDraw.Draw(im)
    d.rounded_rectangle((170,300,850,730),radius=24,fill=(level,level,level),outline=(level-15,)*3,width=2)
    for x in range(210,800,5):d.line((x,340,x,405),fill='black',width=2)
    for y in (470,525,590,650):d.text((220,y),'FICTIONAL TEST CARD - NOT VALID ID',fill='black')
    regions=detect_cards(im.filter(ImageFilter.GaussianBlur(.6)))
    assert len(regions)==1 and coverage(regions[0],[(170,300),(850,300),(850,730),(170,730)])>.94


def test_blank_and_text_only_scans_do_not_invent_a_card():
    im=Image.new('RGB',(1000,1400),'white');assert detect_cards(im)==[]
    d=ImageDraw.Draw(im)
    for y in range(100,1200,30):d.text((80,y),'Ordinary page text without a rectangular card boundary',fill='black')
    assert detect_cards(im)==[]


def test_two_pale_cards_are_separate_and_keep_reading_order():
    im=Image.new('RGB',(1000,1400),'white');d=ImageDraw.Draw(im)
    for y in (100,800):d.rounded_rectangle((200,y,800,y+380),radius=20,fill=(235,239,235),outline=(210,215,210),width=2)
    result=detect_cards(im);assert len(result)==2
    assert coverage(result[0],[(200,100),(800,100),(800,480),(200,480)])>.94
    assert coverage(result[1],[(200,800),(800,800),(800,1180),(200,1180)])>.94


def test_real_import_mapping_keeps_both_original_scans_and_finds_full_sides():
    root=Path(__file__).resolve().parents[1]/'Demo/nid'
    if not all((root/name).is_file() for name in ('front.jpg','back.jpg')):pytest.skip('Private studio scans absent')
    for name in ('front.jpg','back.jpg'):
        path=root/name;before=path.read_bytes();regions=propose_card(DocumentPage(str(path)))
        assert len(regions)==1 and cv2.contourArea(order_quad(regions[0]))>590_000
        assert path.read_bytes()==before
