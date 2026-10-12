"""Edit text in an approved DOCX without rebuilding its layout or other parts."""
import hashlib
import io
import os
import tempfile
import zipfile
from difflib import SequenceMatcher
from pathlib import Path
from lxml import etree

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'

def unpack(data):
    archive = zipfile.ZipFile(io.BytesIO(data))
    if sum(i.file_size for i in archive.infolist()) > 50_000_000:
        raise ValueError('Resume file is too large')
    xml = archive.read('word/document.xml')
    if b'<!DOCTYPE' in xml or b'<!ENTITY' in xml:
        raise ValueError('Unsupported document XML')
    root = etree.fromstring(xml, etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False))
    return archive, root

def paragraphs(root):
    return root.findall('.//' + W + 'body/' + W + 'p')

def inspect(data):
    archive, root = unpack(data)
    blocks = []
    for index, p in enumerate(paragraphs(root)):
        runs = []
        for r in p.findall('.//' + W + 'r'):
            for t in r.findall(W + 't'):
                runs.append({'text':t.text or '', 'bold':r.find(W+'rPr/'+W+'b') is not None,
                             'italic':r.find(W+'rPr/'+W+'i') is not None})
        blocks.append({'id':index,'text':''.join(r['text'] for r in runs),'runs':runs})
    archive.close()
    return {'revision':hashlib.sha256(data).hexdigest(),'paragraphs':blocks}

def edit(data, changes):
    archive, root = unpack(data)
    ps = paragraphs(root)
    if not isinstance(changes, list) or len(changes)>1000:
        raise ValueError('Invalid resume edits')
    seen = set()
    for change in changes:
        index, text = change.get('id'), change.get('text')
        if type(index) is not int or index in seen or not 0<=index<len(ps) or not isinstance(text,str) or len(text)>20000:
            raise ValueError('Invalid resume paragraph')
        seen.add(index)
        if '\n' in text or '\r' in text or any(ord(c)<32 and c!='\t' for c in text):
            raise ValueError('Edit one paragraph at a time')
        p = ps[index]
        nodes = p.findall('.//' + W + 't')
        if p.find('.//'+W+'fldChar') is not None or p.find('.//'+W+'instrText') is not None:
            if text != ''.join(n.text or '' for n in nodes):
                raise ValueError('Edit Word fields in Word')
            continue
        if not nodes:
            if not text: continue
            nodes = [etree.SubElement(etree.SubElement(p,W+'r'),W+'t')]
        old = ''.join(n.text or '' for n in nodes)
        owners = [i for i,n in enumerate(nodes) for _ in (n.text or '')]
        output = [''] * len(nodes)
        for op,a,b,c,d in SequenceMatcher(None,old,text,autojunk=False).get_opcodes():
            if op=='equal':
                for offset,char in enumerate(text[c:d]): output[owners[a+offset]] += char
            elif op in ('insert','replace'):
                owner = owners[min(a,len(owners)-1)] if owners else 0
                output[owner] += text[c:d]
        for node,value in zip(nodes,output):
            node.text=value
            node.set('{http://www.w3.org/XML/1998/namespace}space','preserve')
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w') as target:
        for entry in archive.infolist():
            target.writestr(entry,etree.tostring(root,xml_declaration=True,encoding='UTF-8',standalone=True) if entry.filename=='word/document.xml' else archive.read(entry.filename))
    archive.close()
    return buffer.getvalue()

def replace_file(path, data):
    path=Path(path)
    fd,name=tempfile.mkstemp(prefix='.tgtop-resume-',suffix='.tmp',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as f:
            f.write(data); f.flush(); os.fsync(f.fileno())
        os.replace(name,path)
    finally:
        Path(name).unlink(missing_ok=True)
