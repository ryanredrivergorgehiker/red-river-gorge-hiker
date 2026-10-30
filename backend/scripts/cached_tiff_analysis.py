"""Read existing hash-verified cache metadata only; never fetch pixels or URLs."""
import hashlib,json,math,sqlite3,struct
from pathlib import Path

BLOCK=65536
class MissingMetadata(ValueError):pass

class CachedMetadata:
    def __init__(self,root,source,rows):
        self.root=Path(root);self.source=source;self.rows=rows;self.blocks={};self.read_blocks=set()
    def read(self,start,size):
        if not 0<=start<=start+size<=self.source['length'] or size>8*2**20:raise ValueError('Metadata bounds')
        out=[]
        for n in range(start//BLOCK,(start+size-1)//BLOCK+1):
            if n not in self.blocks:
                row=self.rows.get(n);path=self.root/'blocks'/self.source['identity']/str(n)
                if not row or not path.is_file() or path.is_symlink():raise MissingMetadata(f'Unpreserved metadata block {n}')
                raw=path.read_bytes()
                if len(raw)!=row[1] or hashlib.sha256(raw).hexdigest()!=row[0]:raise ValueError('Preserved cache hash mismatch')
                self.blocks[n]=raw
            self.read_blocks.add(n);out.append(self.blocks[n])
        return b''.join(out)[start%BLOCK:start%BLOCK+size]

def tiff_pages(reader):
    h=reader.read(0,16);order={b'II':'<',b'MM':'>'}.get(h[:2])
    if not order:raise ValueError('TIFF byte order')
    magic=struct.unpack(order+'H',h[2:4])[0]
    if magic==42:big=False;ptr=struct.unpack(order+'I',h[4:8])[0]
    elif magic==43 and struct.unpack(order+'HH',h[4:8])==(8,0):big=True;ptr=struct.unpack(order+'Q',h[8:16])[0]
    else:raise ValueError('TIFF header')
    number,entry,slot=('Q',20,8)if big else('H',12,4);countbytes=8 if big else 2;pointer='Q'if big else'I'
    pending=[ptr];seen=set();pages=[];types={1:('B',1),3:('H',2),4:('I',4),12:('d',8),16:('Q',8),18:('Q',8)}
    wanted={256,257,322,323,324,325,330,33550,33922,34735}
    while pending:
        at=pending.pop(0)
        if not at or at in seen:continue
        if len(seen)>=32:raise ValueError('IFD count')
        seen.add(at);n=struct.unpack(order+number,reader.read(at,countbytes))[0]
        if not 1<=n<=256:raise ValueError('IFD entries')
        raw=reader.read(at+countbytes,n*entry+slot);tags={}
        for i in range(n):
            e=raw[i*entry:(i+1)*entry];tag,typ,num=struct.unpack_from(order+('HHQ'if big else'HHI'),e)
            if tag not in wanted:continue
            if typ not in types or not 1<=num<=1_000_000:raise ValueError('Tag type/count')
            spec,size=types[typ];length=size*num;value=e[-slot:]
            data=value[:length]if length<=slot else reader.read(struct.unpack(order+pointer,value)[0],length)
            tags[tag]=list(struct.unpack(order+spec*num,data))
        pending.extend(tags.get(330,[]));pending.append(struct.unpack(order+pointer,raw[-slot:])[0]);pages.append(tags)
    if not pages or any(k not in pages[0]for k in [256,257,33550,33922,34735]):raise ValueError('Georeference missing')
    return pages

def blocks_for_window(pages,source_length,bounds,transform_bounds):
    base=pages[0];keys=base[34735];epsg=None
    for i in range(4,len(keys),4):
        k,loc,n,val=keys[i:i+4]
        if k in(2048,3072)and loc==0 and n==1:epsg=val
    if not epsg:raise ValueError('EPSG missing')
    left,bottom,right,top=transform_bounds('EPSG:4326','EPSG:'+str(epsg),*bounds,densify_pts=21)
    sx,sy=base[33550][:2];tie=base[33922];originx=tie[3]-tie[0]*sx;originy=tie[4]+tie[1]*sy
    result=set()
    for p in pages:
        if not all(k in p for k in[256,257,322,323,324,325]):continue
        w,h=p[256][0],p[257][0];tw,th=p[322][0],p[323][0];dx=sx*base[256][0]/w;dy=sy*base[257][0]/h
        # Conservative full source-tile halo at every TIFF overview level.
        a=max(0,math.floor((left-originx)/dx/tw)-1);b=min(math.ceil(w/tw)-1,math.floor((right-originx)/dx/tw)+1)
        c=max(0,math.floor((originy-top)/dy/th)-1);d=min(math.ceil(h/th)-1,math.floor((originy-bottom)/dy/th)+1)
        offsets,counts=p[324],p[325];stride=math.ceil(w/tw)
        if len(offsets)!=len(counts)or len(offsets)!=stride*math.ceil(h/th):raise ValueError('Tile arrays malformed')
        for y in range(c,d+1):
            for x in range(a,b+1):
                at,size=offsets[y*stride+x],counts[y*stride+x]
                if not size or not 0<=at<at+size<=source_length:raise ValueError('TIFF tile extent')
                result.update(range(at//BLOCK,(at+size-1)//BLOCK+1))
    return result

def inspect_cache(root,graph,inventory,transform_bounds,bbox):
    db=sqlite3.connect('file:'+str((Path(root)/'cache.sqlite').resolve())+'?mode=ro',uri=True)
    byurl={s['url']:(family,s['id'])for family,ss in inventory.items()for s in ss}
    jobs={j['id']:j for j in graph['jobs']};results=[]
    for url,identity,raw in db.execute('select url,identity,metadata from sources order by url'):
        source=json.loads(raw);rows={n:(sha,size)for n,sha,size in db.execute('select number,sha,bytes from blocks where identity=?',(identity,))}
        ref=byurl.get(url);r={'source':source,'cachedBlocks':len(rows),'regionalIdentity':ref,'networkRequests':0}
        try:
            rd=CachedMetadata(root,source,rows);pages=tiff_pages(rd)
            consumers=graph['sourceConsumers'].get('|'.join(ref),[])if ref else[];sets=[];requested=0
            for j in consumers:
                v=jobs[j];blocks=blocks_for_window(pages,source['length'],bbox(v['z'],v['x'],v['y']),transform_bounds)
                blocks.update(rd.read_blocks);sets.append(blocks);requested+=len(blocks)
            union=set().union(*sets)if sets else set();remaining=set(union)-rows.keys()
            r.update(status='metadata-validated',metadataBlocks=sorted(rd.read_blocks),levels=len(pages),width=pages[0][256][0],height=pages[0][257][0],
              consumers=len(consumers),allLevelHaloBlockOccurrences=requested,uniqueAllLevelHaloBlocks=len(union),
              allLevelHaloIndependentBytes=requested*BLOCK,allLevelHaloUniqueBytes=sum(min(BLOCK,source['length']-n*BLOCK)for n in union),
              alreadyPreservedRelevantBlocks=len(union&rows.keys()),missingUniqueBytes=sum(min(BLOCK,source['length']-n*BLOCK)for n in remaining),
              perJobBlockCounts=[len(s)for s in sets],boundNotActualGDALDemand=True)
        except MissingMetadata as e:r.update(status='metadata-unavailable-offline',reason=str(e))
        results.append(r)
    db.close();return results
