const SITE = 'https://redrivergorgehiker.com';
const STORE = 'https://store.redrivergorgehiker.com';
const photos = [
  ['RRGH-0001','double-rainbow-at-eagles-point-buttress-ryan-d-lewis','RRGH-0001-Double_Rainbow_at_Eagles_Point_Buttress-SOCIAL-WM.jpg'],
  ['RRGH-0004','winter-at-red-byrd-arch-ryan-d-lewis','RRGH-0004-Winter_at_Red-byrd_Arch-SOCIAL-WM.jpg'],
  ['RRGH-0005','sunrise-at-eagles-nest-ryan-d-lewis','RRGH-0005-Sunrise_at_Eagles_Nest-SOCIAL-WM.jpg'],
  ['RRGH-0002','dog-fork-falls-in-winter-ryan-d-lewis','RRGH-0002-Dog_Fork_Falls_in_Winter-SOCIAL-WM.jpg'],
  ['RRGH-0007','ice-at-west-of-copperas-pillar-ryan-d-lewis','RRGH-0007-Ice_at_West_of_Copperas_Pillar-SOCIAL-WM.jpg'],
  ['RRGH-0003','splatter-falls-ryan-d-lewis','RRGH-0003-Splatter_Falls-SOCIAL-WM.jpg']
];
const formats = ['art-print','canvas-print','framed-print','metal-print','acrylic-print','wood-print','poster'];
const ua = {'user-agent':'Mozilla/5.0 (compatible; RRGH-Catalog-Image-Probe/1.0)','accept-language':'en-US,en;q=0.9'};
async function get(url){ const r=await fetch(url,{redirect:'follow',headers:ua}); if(!r.ok)throw new Error(`${r.status} ${url}`); return r; }
function dims(b){
  if(b[0]===0xff&&b[1]===0xd8){let o=2;while(o<b.length){if(b[o]!==0xff){o++;continue;}const m=b[o+1];o+=2;if(m===0xd8||m===0xd9)continue;const l=b.readUInt16BE(o);if([0xc0,0xc1,0xc2,0xc3,0xc5,0xc6,0xc7,0xc9,0xca,0xcb,0xcd,0xce,0xcf].includes(m))return {w:b.readUInt16BE(o+5),h:b.readUInt16BE(o+3)};o+=l;} }
  if(b.subarray(1,4).toString()==='PNG') return {w:b.readUInt32BE(16),h:b.readUInt32BE(20)};
  throw new Error('unknown image type');
}
function meta(html,key){
 const e=key.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
 const r1=new RegExp(`<meta[^>]+(?:property|name)=["']${e}["'][^>]+content=["']([^"']+)["'][^>]*>`,'i');
 const r2=new RegExp(`<meta[^>]+content=["']([^"']+)["'][^>]+(?:property|name)=["']${e}["'][^>]*>`,'i');
 return html.match(r1)?.[1]??html.match(r2)?.[1]??null;
}
async function imageDims(url){ const r=await get(url.replaceAll('&amp;','&')); const b=Buffer.from(await r.arrayBuffer()); return {...dims(b),bytes:b.length,type:r.headers.get('content-type')}; }
for(const [id,slug,file] of photos){
 const social=`${SITE}/assets/social/${encodeURIComponent(file)}`;
 console.log('SOCIAL',id,social,await imageDims(social));
 for(const format of formats){
   const link=`${STORE}/featured/${slug}.html?product=${format}`;
   const html=await (await get(link)).text();
   const image=meta(html,'og:image');
   if(!image) throw new Error(`no og:image ${link}`);
   console.log('OG',id,format,image,await imageDims(image));
 }
}
const cardLink=`${STORE}/featured/double-rainbow-at-eagles-point-ryan-d-lewis.html?product=greeting-card`;
const cardHtml=await (await get(cardLink)).text();
const cardImage=meta(cardHtml,'og:image');
console.log('OG','RRGH-0001','greeting-card',cardImage,await imageDims(cardImage));
