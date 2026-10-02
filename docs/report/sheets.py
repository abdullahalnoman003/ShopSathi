import pypdfium2 as pdfium, sys
from PIL import Image
pdf=pdfium.PdfDocument('out/ShopSathi_Final_Report.pdf')
n=len(pdf)
per=12; cols=4; W=370; H=524
import os
os.makedirs('out/sheets',exist_ok=True)
for s in range(0,n,per):
    sheet=Image.new('RGB',(cols*(W+8),3*(H+8)),'#888888')
    for k,i in enumerate(range(s,min(n,s+per))):
        im=pdf[i].render(scale=0.62).to_pil().convert('RGB').resize((W,H))
        sheet.paste(im,((k%cols)*(W+8),(k//cols)*(H+8)))
    sheet.save(f'out/sheets/s{s//per+1:02d}.png')
print(n)
