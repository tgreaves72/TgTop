"""Rasterize the code-native TgTop mark for installer/PWA sizes (Pillow)."""
from pathlib import Path
from PIL import Image,ImageDraw
root=Path(__file__).resolve().parent.parent
im=Image.new('RGBA',(512,512),'#1d4ed8');d=ImageDraw.Draw(im)
d.rectangle((115,130,397,197),fill='#dbeafe');d.rectangle((222,194,290,382),fill='#dbeafe');d.ellipse((351,350,416,415),fill='#dbeafe')
im.save(root/'desktop'/'icon.ico',sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])
for size in (192,512): im.resize((size,size),Image.Resampling.LANCZOS).save(root/'web'/f'icon-{size}.png')
