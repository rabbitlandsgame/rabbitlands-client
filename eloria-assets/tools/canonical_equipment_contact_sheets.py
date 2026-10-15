"""Make labelled review sheets from the actual Godot and Blender captures.

This only reads renders. It does not recolour, retouch or alter any equipment.
Use a new output directory; individual source images and their hashes are
recorded beside the contact sheets.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import import_generated_equipment as batch


def sheets(preview, output, prefix, catalogue_prefix=None):
    if output.exists():
        raise FileExistsError('Use a new contact-sheet directory')
    output.mkdir(parents=True)
    font_path = Path('C:/Windows/Fonts/arial.ttf')
    font = ImageFont.truetype(str(font_path), 18) if font_path.exists() else ImageFont.load_default(size=18)
    small = ImageFont.truetype(str(font_path), 15) if font_path.exists() else ImageFont.load_default(size=15)
    manifest = {'inputs': {}, 'sheets': [], 'generator_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}

    def read(path):
        manifest['inputs'][str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
        report = path.with_suffix(path.suffix+'.json')
        if report.exists():
            manifest['inputs'][str(report)] = hashlib.sha256(report.read_bytes()).hexdigest()
        return Image.open(path).convert('RGB')

    def save(board, name):
        destination = output/name
        board.save(destination, quality=95)
        manifest['sheets'].append({'path': name, 'sha256': hashlib.sha256(destination.read_bytes()).hexdigest()})
        print(destination, flush=True)

    races = ['luminous_male','luminous_female','glasswarden_male','glasswarden_female',
             'ssarathi_male','ssarathi_female','mycelari_male','mycelari_female']
    for race in races:
        panels = []
        for clip, view in [('Idle_Subtle','front'),('Walk','side')]:
            for tag, label in [('baseline','Shipped'),(prefix+'-militia','Canonical')]:
                path = preview/f'{tag}_{race}_{clip}_{view}.png'
                panels.append((path, f'{label}: {clip}, {view}'))
        if not all(path.exists() for path, _ in panels):
            continue
        for offset in [0, 2]:
            before, after = [json.loads(path.with_suffix('.png.json').read_text())
                             for path, _ in panels[offset:offset+2]]
            for key in ['model_sha256', 'library_sha256', 'clip', 'bone_poses']:
                if before[key] != after[key]:
                    raise ValueError(f'Before/after capture differs in {key}: {race}')
        board = Image.new('RGB',(1600,625),(28,34,39));draw=ImageDraw.Draw(board)
        for i,(path,label) in enumerate(panels):
            im=read(path).crop((330,65,1170,1060));im.thumbnail((400,550))
            board.paste(im,(i*400+(400-im.width)//2,40))
            draw.text((i*400+8,8),label,font=font,fill='white')
        draw.text((8,597),race+' | same camera, scale and clip time',font=font,fill='white')
        save(board,f'before-after-{race}.jpg')

    torsos=[piece for piece in batch.roster() if piece.part==5]
    for start in range(0,len(torsos),16):
        panels=[(piece,preview/f'{catalogue_prefix or prefix}-catalogue-{piece.slug}_glasswarden_female_Idle_Subtle_front.png')
                for piece in torsos[start:start+16]]
        if not all(path.exists() for _,path in panels):
            continue
        board=Image.new('RGB',(1280,1440),(28,34,39));draw=ImageDraw.Draw(board)
        for i,(piece,path) in enumerate(panels):
            im=read(path).crop((400,120,1100,755));im.thumbnail((315,315))
            x=(i%4)*320;y=(i//4)*360;board.paste(im,(x+(320-im.width)//2,y))
            draw.text((x+7,y+315),piece.name,font=font,fill='white')
            draw.text((x+7,y+338),piece.slug,font=small,fill=(160,185,195))
        save(board,f'torso-catalogue-{start//16+1}.jpg')

    for race in races:
        clips=['Idle_Subtle','Walk','Jog','Run_Female','Fighting_Idle']
        paths=[preview/f'{prefix}-militia_{race}_{clip}_{view}_frames/{frame:03d}.png'
               for clip in clips for view in ['front','side'] for frame in [0,8,16]]
        if not all(path.exists() for path in paths):
            continue
        board=Image.new('RGB',(1440,1650),(28,34,39));draw=ImageDraw.Draw(board)
        for row,clip in enumerate(clips):
            draw.text((8,row*330+4),race+' / '+clip+' | front then side, cycle 0 / 1/3 / 2/3',font=font,fill='white')
            for col,path in enumerate(paths[row*6:row*6+6]):
                im=read(path).crop((270,40,1230,1070));im.thumbnail((240,292))
                board.paste(im,(col*240+(240-im.width)//2,row*330+30))
        save(board,f'locomotion-{race}.jpg')

    for name in ['militia','phoenix','amberwood04']:
        panels=[preview/f'{prefix}-{name}-{race}-complete{suffix}.png'
                for race in ['luminous_male','luminous_female'] for suffix in ['', '_worn']]
        if not all(path.exists() for path in panels):
            continue
        board=Image.new('RGB',(1600,850),(28,34,39));draw=ImageDraw.Draw(board)
        for i,path in enumerate(panels):
            im=read(path);im.thumbnail((400,775));board.paste(im,(400*i+(400-im.width)//2,40))
            draw.text((400*i+8,8),['Male set','Male worn','Female set','Female worn'][i],font=font,fill='white')
        draw.text((8,823),name+' | Blender source-arm pose, independent wearable parts',font=font,fill='white')
        save(board,f'complete-set-{name}.jpg')

    all_races = sorted(p.stem for p in
        (Path(__file__).resolve().parents[2]/'godot-client/assets/actors/native/races').glob('*.glb'))
    for start in range(0, len(all_races), 4):
        heads = [(race, label, style, view,
                  preview/f'{prefix}-head-{label}-style{style}_{race}_Idle_Subtle_{view}.png')
                 for race in all_races[start:start+4]
                 for label, style in [('hood', 3), ('rootwrap', 3), ('sunband', 0)]
                 for view in ['front', 'side']]
        if not all(path.exists() for *_, path in heads):
            continue
        board=Image.new('RGB',(1800,1120),(28,34,39));draw=ImageDraw.Draw(board)
        for i,(race,label,style,view,path) in enumerate(heads):
            x=(i%6)*300;y=(i//6)*280
            im=read(path).crop((430,0,1070,500));im.thumbnail((300,238))
            board.paste(im,(x+(300-im.width)//2,y+25))
            draw.text((x+5,y+4),race,font=small,fill='white')
            draw.text((x+5,y+258),f'{label}, style {style}, {view}',font=small,fill='white')
        save(board,f'headwear-{start//4+1}.jpg')

    for filename, expected in manifest['inputs'].items():
        if hashlib.sha256(Path(filename).read_bytes()).hexdigest()!=expected:
            raise ValueError(f'Capture changed while composing: {filename}')
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preview',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--prefix',default='fitted')
    parser.add_argument('--catalogue-prefix',help='Separately captured torso-only catalogue')
    args=parser.parse_args();sheets(args.preview,args.out,args.prefix,args.catalogue_prefix)
