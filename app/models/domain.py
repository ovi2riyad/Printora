from dataclasses import dataclass, field, asdict
import uuid
import math

PROCESSING_LIMITS={'denoise':(0,1),'shadows':(-1,1),'temperature':(-1,1),'skin_soften':(0,1)}

def validate_layer_processing(layer):
    for key,(low,high) in PROCESSING_LIMITS.items():
        value=getattr(layer,key,0)
        if type(value) not in (int,float) or not math.isfinite(value) or not low<=value<=high:
            raise ValueError('Invalid image processing setting: '+key)

def uid():
    return uuid.uuid4().hex

@dataclass
class Layer:
    source: str
    mask: str = ''
    x: float = 0.5
    y: float = 0.5
    scale: float = 1.0
    rotation: float = 0
    erosion: int = 0
    feather: float = 0
    label: str = ''
    visible: bool = True
    locked: bool = False
    flip_h: bool = False
    flip_v: bool = False
    brightness: float = 1.0
    contrast: float = 1.0
    saturation: float = 1.0
    sharpness: float = 1.0
    mask_strokes: list = field(default_factory=list)
    defringe: float = 0.0
    group: str = ''
    denoise: float = 0.0
    shadows: float = 0.0
    temperature: float = 0.0
    skin_soften: float = 0.0

@dataclass
class Photo:
    id: str = field(default_factory=uid)
    name: str = 'Photo'
    kind: str = 'Individual'
    profile: str = 'Studio Portrait'
    width: float = 45
    height: float = 55
    quantity: int = 4
    background: str = '#ADD8E6'
    border: bool = True
    border_color: str = '#808080'
    border_mm: float = 0.2
    layers: list = field(default_factory=list)
    composition: dict = field(default_factory=dict)
    provenance: dict = field(default_factory=dict)
    print_rotation: str = 'auto'

    def validate(self):
        for layer in self.layers:validate_layer_processing(layer)
        if self.print_rotation not in ('auto','none','cw','ccw','half'):raise ValueError('Unsupported photo print rotation')
        if not all(math.isfinite(v) and v > 0 for v in (self.width, self.height)):
            raise ValueError('Photo dimensions must be positive finite millimetres.')
        if not 1 <= self.quantity <= 10000:
            raise ValueError('Quantity must be between 1 and 10000.')
        if not math.isfinite(self.border_mm) or not 0 <= self.border_mm < min(self.width, self.height) / 2:
            raise ValueError('Border is too thick for this photograph.')

    def swap(self):
        self.width, self.height = self.height, self.width

    @classmethod
    def from_dict(cls, data):
        data = dict(data)
        data['layers'] = [Layer(**x) for x in data.get('layers', [])]
        result = cls(**data)
        result.validate()
        return result

@dataclass
class Placement:
    photo_id: str
    copy: int
    page: int
    x: float
    y: float
    width: float
    height: float
    rotation: int = 0

@dataclass
class Job:
    id: str = field(default_factory=uid)
    name: str = 'Untitled studio order'
    photos: list = field(default_factory=list)
    placements: list = field(default_factory=list)
    page_count: int = 1
    print_settings: dict = field(default_factory=lambda: dict(landscape=False, margin=10, gap_x=2, gap_y=3, guides=False))

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d):
        d = dict(d)
        d['photos'] = [Photo.from_dict(p) for p in d.get('photos', [])]
        d['placements'] = [Placement(**p) for p in d.get('placements', [])]
        return cls(**d)
