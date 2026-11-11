"""Du Fu-only raw-art adapter; reused composition/text/map are deliberately absent.

Copying this file or changing a name does not create another person's artwork.
The generic renderer loads a different per-project draw_art implementation.
"""
from functools import lru_cache
import importlib.util
import json
from pathlib import Path
import sys
from PIL import Image, ImageDraw, ImageFont


def _skill_root():
    locator=Path(__file__).resolve().parent/'reference_root.json'
    if locator.is_file():
        configured=(locator.parent/json.loads(locator.read_text(encoding='utf-8'))['skill_root_relative']).resolve()
        if (configured/'scripts/series_frame.py').is_file() and (configured/'assets/dufu-reference').is_dir():
            return configured
        raise RuntimeError('The explicit relative Skill reference is missing; regenerate this example after relocating it')
    for parent in Path(__file__).resolve().parents:
        if (parent/'scripts/series_frame.py').is_file() and (parent/'assets/dufu-reference').is_dir():
            return parent
    raise RuntimeError('Keep the relative Skill reference together with this example; create a new art provider for a new person')


ROOT=_skill_root()
STYLE=json.loads((ROOT/'assets/series/series_style.json').read_text(encoding='utf-8'))
REFERENCE=ROOT/'assets/dufu-reference/工程'
sys.path.insert(0,str(REFERENCE))
spec=importlib.util.spec_from_file_location('series_dufu_raw_reference',REFERENCE/'render_dufu.py')
reference=importlib.util.module_from_spec(spec);sys.modules[spec.name]=reference;spec.loader.exec_module(reference)


@lru_cache(maxsize=48)
def _font(size,bold=False,sans=False):
    role=('sans' if sans else 'serif')+('_bold' if bold else '_regular')
    path=ROOT/'assets/series'/STYLE['fonts'][role]
    return ImageFont.truetype(str(path),size)


@lru_cache(maxsize=1)
def _scroll_letters():
    result=[];font=_font(60)
    for char in '此心在人间':
        tile=Image.new('RGBA',(68,88),(0,0,0,0))
        ImageDraw.Draw(tile).text((4,8),char,font=font,fill='#1E2A26',anchor='lt');result.append(tile)
    return tuple(result)


# Scene initialization measures its old UI even though this adapter uses only
# Scene.art(). Bind those measurements and the in-art scroll to packaged fonts.
reference.font=_font
reference.draw_environment.__globals__['_scroll_letters']=_scroll_letters


def _existing_layers(scene_id):
    replacements={'S01':('mid',),'S02':('fg',),'S05':('fg',),'S07':('fg',),
                  'S08':('mid',),'S09':('mid',),'S10':('fg',),'S11':('mid','fg')}
    result={}
    for role in replacements.get(scene_id,()):
        path=ROOT/'assets/dufu-reference/素材/动画底层'/f'{scene_id}_{role}.png'
        if not path.is_file():raise FileNotFoundError(f'Prepared reference layer missing: {path}')
        result[role]=Image.open(path).convert('RGBA')
    return result


# Do not invoke the legacy SVG-cache builder or mutate a packaged reference.
reference.get_base_layers=_existing_layers
_DUFU_COLORS=json.loads((ROOT/'assets/series/themes/dufu.json').read_text(encoding='utf-8'))['colors']


@lru_cache(maxsize=12)
def _scene(scene_id):
    index=next((i for i,s in enumerate(reference.SCENES) if s['id']==scene_id),None)
    if index is None:raise ValueError('Unknown supplied Du Fu scene')
    return reference.Scene(index)


def draw_art(scene_id,t,duration,theme):
    if theme.get('person')!='杜甫':
        raise ValueError('This example is Du Fu-specific; another person needs its own art provider and backgrounds')
    if theme.get('colors')!=_DUFU_COLORS:
        raise ValueError('Supplied reference art is bound to the supplied Du Fu theme; a different palette needs corresponding art')
    scene=_scene(scene_id)
    if abs(scene.duration-duration)>1e-6:raise ValueError('Du Fu reference duration differs from canonical slot')
    return scene.art(t)
