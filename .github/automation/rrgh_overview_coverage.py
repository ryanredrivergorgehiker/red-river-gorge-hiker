"""Exact alpha coverage of the fixed native tile grid at every overview zoom.

The original renderer omits children outside tile_coords(). This module proves
that omission geometrically; it never permits a missing child inside that grid.
"""
from functools import lru_cache
import hashlib
import math
from PIL import Image

BOUNDS=(-83.8,37.65,-83.4,37.95)
MIN_ZOOM=10
NATIVE_ZOOM=16

def require(ok,message):
    if not ok:raise ValueError(message)

@lru_cache(maxsize=7)
def grid(z):
    require(type(z) is int and MIN_ZOOM<=z<=NATIVE_ZOOM,'Unsupported coverage zoom')
    def xy(lon,lat):
        n=2**z
        return math.floor((lon+180)/360*n),math.floor((1-math.asinh(math.tan(math.radians(lat)))/math.pi)/2*n)
    left,bottom=xy(BOUNDS[0],BOUNDS[1]);right,top=xy(BOUNDS[2],BOUNDS[3])
    return left,top,right,bottom

def inside(z,x,y):
    left,top,right,bottom=grid(z)
    return left<=x<=right and top<=y<=bottom

def child_positions(z,x,y):
    require(MIN_ZOOM<=z<NATIVE_ZOOM and inside(z,x,y),'Approved overview position required')
    return [(z+1,2*x+dx,2*y+dy) for dx in range(2) for dy in range(2)
        if inside(z+1,2*x+dx,2*y+dy)]

@lru_cache(maxsize=2048)
def alpha(z,x,y):
    require(all(type(v) is int for v in (z,x,y)) and 0<=x<2**z and 0<=y<2**z,'Invalid tile position')
    if not inside(z,x,y):return bytes(256*256)
    factor=2**(NATIVE_ZOOM-z);left,top,right,bottom=grid(NATIVE_ZOOM)
    if left<=x*factor and (x+1)*factor-1<=right and top<=y*factor and (y+1)*factor-1<=bottom:
        return b'\xff'*(256*256)
    require(z<NATIVE_ZOOM,'Native tiles must be fully covered')
    canvas=Image.new('L',(512,512),0)
    for zz,xx,yy in child_positions(z,x,y):
        child=Image.frombytes('L',(256,256),alpha(zz,xx,yy))
        canvas.paste(child,((xx-2*x)*256,(yy-2*y)*256))
    return canvas.resize((256,256),Image.Resampling.LANCZOS).tobytes()

def verify(image,z,x,y):
    require(inside(z,x,y) and image.size==(256,256),'Coverage tile scope or grid changed')
    expected=alpha(z,x,y);actual=image.convert('RGBA').getchannel('A').tobytes()
    require(actual==expected,'Tile has missing regional pixels or invented exterior coverage')
    return dict(format='rrgh-fixed-native-grid-coverage-v1',nativeZoom=NATIVE_ZOOM,
        boundsWGS84=list(BOUNDS),alphaSHA256=hashlib.sha256(expected).hexdigest(),
        opaquePixels=expected.count(255),transparentPixels=expected.count(0),
        antialiasedBoundaryPixels=sum(0<v<255 for v in expected),allRequiredChildrenPresent=True)
