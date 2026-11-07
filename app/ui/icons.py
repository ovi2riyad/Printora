"""Small code-native line icons shared by navigation and workflow cards."""
from functools import lru_cache
from PySide6.QtCore import QByteArray,Qt
from PySide6.QtGui import QIcon,QPixmap,QPainter
from PySide6.QtSvg import QSvgRenderer

PATHS={
 'import':'<path d="M12 2v13m-5-5 5 5 5-5M3 15v7h18v-7"/>',
 'export':'<path d="M12 17V3m-5 5 5-5 5 5M3 15v7h18v-7"/>',
 'save':'<path d="M3 2h15l3 3v17H3zM7 2v7h10V2M7 22v-9h10v9"/>',
 'dashboard':'<path d="m3 10 9-7 9 7v11h-6v-7H9v7H3z"/>',
 'scan':'<path d="m4 4 16 0 2 11H2zM2 15v5h20v-5M7 17h10"/>',
 'copy':'<rect x="7" y="6" width="14" height="16" rx="2"/><path d="M17 6V2H3v16h4"/>',
 'card':'<rect x="2" y="5" width="20" height="15" rx="2"/><circle cx="8" cy="11" r="2"/><path d="M5 17v-1c0-3 6-3 6 0v1M14 10h5m-5 4h5"/>',
 'portrait':'<circle cx="12" cy="7" r="4"/><path d="M4 22v-3c0-8 16-8 16 0v3"/>',
 'joint':'<circle cx="8" cy="7" r="3"/><circle cx="17" cy="8" r="3"/><path d="M1 22v-3c0-8 13-8 13 0v3M14 14c5-2 9 1 9 5v3"/>',
 'multi':'<path d="M2 2h8v8H2zM14 2h8v8h-8zM2 14h8v8H2zM14 14h8v8h-8z"/>',
 'library':'<rect x="2" y="3" width="20" height="18" rx="2"/><circle cx="7" cy="8" r="2"/><path d="m3 19 6-7 4 4 4-6 5 6"/>',
 'orders':'<path d="M8 4H4v18h16V4h-4M8 2h8v5H8zM8 12h8m-8 4h8"/>',
 'recipes':'<path d="M5 2h14v20H5zM8 7h8m-8 5h8m-8 5h6"/>',
 'tools':'<path d="m3 21 10-10a6 6 0 0 0 8-8l-4 4-4-4 4-4a6 6 0 0 0-8 8L0 18z"/>',
 'settings':'<path d="m10 2-1 3-3 1-3-1-2 4 2 2v3l-2 2 2 4 3-1 3 1 1 3h4l1-3 3-1 3 1 2-4-2-2v-3l2-2-2-4-3 1-3-1-1-3z"/><circle cx="12" cy="12" r="3"/>',
 'print':'<path d="M6 8V2h12v6M6 17H2V8h20v9h-4M6 14h12v8H6z"/>',
 'camera':'<path d="M3 6h4l2-4h6l2 4h4v16H3z"/><circle cx="12" cy="13" r="5"/>',
 'menu':'<path d="M3 5h18M3 12h18M3 19h18"/>',
 'refresh':'<path d="M21 3v6h-6M3 21v-6h6M3 9a9 9 0 0 1 15-5l3 5M3 15l3 5a9 9 0 0 0 15-5"/>'}

@lru_cache(maxsize=128)
def icon(name,color='#b7c9e8',size=24):
    svg=f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="-1 -1 26 26"><g fill="none" stroke="{color}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">{PATHS.get(name,PATHS["camera"])}</g></svg>'
    raster=QPixmap(size*2,size*2);raster.fill(Qt.transparent);p=QPainter(raster);QSvgRenderer(QByteArray(svg.encode())).render(p);p.end();raster.setDevicePixelRatio(2);return QIcon(raster)
