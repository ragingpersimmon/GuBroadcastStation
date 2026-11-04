"""Static assets: stylesheet, script, favicon. Written to /assets/ on build."""

FONTS = ("https://fonts.googleapis.com/css2?family=Archivo:wdth,wght@62..125,400..900"
         "&family=Source+Serif+4:opsz,wght@8..60,400..700&display=swap")

CSS = r"""
:root{
  --paper:#ffffff; --ink:#1b1f27; --slate:#5b6372; --rule:#e3e5ea; --wash:#f5f6f8;
  --red:#c8102e; --gold:#f2c14e; --onair:#1b1f27; --onair-ink:#f4f5f7;
  --sans:"Archivo",system-ui,-apple-system,"Segoe UI",sans-serif;
  --serif:"Source Serif 4",Georgia,"Times New Roman",serif;
  --w:1240px; --gut:24px;
}
@media (prefers-color-scheme:dark){
  :root{--paper:#14171d;--ink:#e9ebef;--slate:#a1a8b5;--rule:#2b3039;--wash:#1b1f27;--onair:#0c0e12}
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--paper);color:var(--ink);font:400 17px/1.5 var(--sans)}
a{color:inherit;text-decoration:none}
a:hover{text-decoration:underline;text-decoration-thickness:1px;text-underline-offset:3px}
:focus-visible{outline:3px solid var(--gold);outline-offset:2px}
img{max-width:100%;display:block}
.wrap{max-width:var(--w);margin:0 auto;padding:0 var(--gut)}
.skip{position:absolute;left:-999px;top:0;background:var(--gold);color:#000;padding:8px 12px;z-index:9}
.skip:focus{left:8px}
.vh{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}

/* On-air bar: the station's signature, on every page */
.onair{background:var(--onair);color:var(--onair-ink);font-size:13px}
.onair .wrap{display:flex;align-items:center;gap:14px;min-height:36px;flex-wrap:wrap}
.tally{display:inline-flex;align-items:center;gap:8px;font-weight:700;letter-spacing:.02em}
.tally i{width:10px;height:10px;border-radius:50%;background:var(--red);box-shadow:0 0 0 0 rgba(200,16,46,.7);animation:tally 2.4s ease-out 1}
@keyframes tally{0%{box-shadow:0 0 0 0 rgba(200,16,46,.7)}100%{box-shadow:0 0 0 12px rgba(200,16,46,0)}}
.onair a{color:var(--onair-ink)}
.onair .show{font-weight:600}
.onair .with{color:#b9bfca}
.onair .right{margin-left:auto;display:flex;gap:16px;align-items:center;color:#b9bfca}
.onair .pulse b{color:var(--gold);font-weight:600}
.onair time{font-variant-numeric:tabular-nums;color:var(--onair-ink)}

/* Masthead */
.mast{border-bottom:1px solid var(--rule)}
.mast .wrap{display:flex;align-items:center;gap:20px;padding-top:18px;padding-bottom:14px}
.brand{display:flex;align-items:baseline;gap:10px}
.brand .gu{font:900 46px/0.9 var(--sans);font-stretch:62%;color:var(--red);letter-spacing:-.01em}
.brand .full{font:600 15px/1.1 var(--sans);font-stretch:85%;color:var(--slate);max-width:9em}
.mast .tools{margin-left:auto;display:flex;gap:10px;align-items:center}
.btn{display:inline-flex;align-items:center;gap:6px;font:600 14px/1 var(--sans);padding:10px 14px;border-radius:2px;border:1px solid var(--ink);background:transparent;color:var(--ink);cursor:pointer}
.btn.solid{background:var(--red);border-color:var(--red);color:#fff}
.btn:hover{text-decoration:none;filter:brightness(1.05)}
.navtoggle{display:none}

/* Primary nav with section drop-downs */
nav.primary{border-bottom:3px solid var(--ink)}
nav.primary ul{list-style:none;margin:0;padding:0;display:flex;flex-wrap:wrap}
nav.primary li{position:relative}
nav.primary > .wrap > ul > li > a{display:block;padding:12px 14px 11px;font:700 15px/1 var(--sans);font-stretch:90%}
nav.primary li:first-child > a{padding-left:0}
nav.primary a[aria-current="page"]{box-shadow:inset 0 -3px 0 var(--red)}
nav.primary .sub{display:none;position:absolute;left:0;top:100%;min-width:200px;background:var(--paper);border:1px solid var(--rule);border-top:3px solid var(--red);z-index:5;padding:6px 0}
nav.primary .sub a{display:block;padding:8px 16px;font:500 15px/1.2 var(--sans)}
nav.primary li:hover > .sub,nav.primary li:focus-within > .sub{display:block}

/* Breaking banner */
.breaking{background:var(--red);color:#fff}
.breaking .wrap{display:flex;gap:14px;align-items:baseline;padding-top:12px;padding-bottom:12px}
.breaking strong{font:800 15px/1 var(--sans);font-stretch:80%;white-space:nowrap}
.breaking a{font:600 17px/1.3 var(--sans);color:#fff}

/* Ad slots */
.ad{margin:22px 0;border:1px solid var(--rule);background:var(--wash);padding:12px 16px;font-size:14px}
.ad .lbl{display:block;font-size:12px;color:var(--slate);margin-bottom:4px}
.ad a{display:block}
.ad strong{display:block;font-size:16px}
.ad-top{margin:14px auto}

/* Type */
.kicker{display:inline-block;font:700 13px/1 var(--sans);color:var(--red);margin-bottom:6px}
.hl{font-family:var(--sans);font-weight:800;font-stretch:78%;letter-spacing:-.005em;line-height:1.08;margin:0}
.hl-xl{font-size:clamp(30px,4.2vw,50px)}
.hl-l{font-size:clamp(22px,2.4vw,30px)}
.hl-m{font-size:20px;font-weight:750}
.hl-s{font-size:17px;font-weight:700;font-stretch:88%;line-height:1.22}
.deck{font:400 18px/1.5 var(--serif);color:var(--slate);margin:10px 0 0}
.meta{font-size:13px;color:var(--slate);margin-top:8px;display:flex;gap:10px;flex-wrap:wrap}
.meta a{color:var(--ink);font-weight:600}
.badge-video{display:inline-flex;align-items:center;gap:5px;font:700 12px/1 var(--sans);color:var(--ink);background:var(--gold);padding:4px 7px;border-radius:2px;margin-right:6px;vertical-align:2px}
.badge-video::before{content:"";border-left:7px solid currentColor;border-top:4px solid transparent;border-bottom:4px solid transparent}

/* Home: lead package. The lead headline sits on the video lower-third motif. */
.lead{display:grid;grid-template-columns:minmax(0,2.1fr) minmax(0,1fr) minmax(0,.95fr);gap:0;margin-top:22px}
.lead > *{padding:0 22px;border-left:1px solid var(--rule)}
.lead > :first-child{padding-left:0;border-left:0}
.lead > :last-child{padding-right:0}
.lead-more{display:grid;grid-template-columns:1fr 1fr;gap:18px 22px;margin-top:20px;padding-top:18px;border-top:1px solid var(--rule)}
.lowerthird{border-left:6px solid var(--gold);padding:14px 0 14px 18px;background:linear-gradient(90deg,var(--wash),transparent 80%)}
.lead .player{margin-bottom:14px}
.stack > article{padding:0 0 14px;margin:0 0 14px;border-bottom:1px solid var(--rule)}
.stack > article:last-child{border-bottom:0;margin-bottom:0}
.latest h2,.rail h2,.block-title{font:800 19px/1 var(--sans);font-stretch:80%;margin:0 0 12px;padding-bottom:8px;border-bottom:2px solid var(--ink);display:flex;justify-content:space-between;align-items:baseline}
.block-title a,.rail h2 a,.latest h2 a{font:600 14px/1 var(--sans);color:var(--slate)}
.latest ol{list-style:none;margin:0;padding:0}
.latest li{display:grid;grid-template-columns:52px 1fr;gap:8px;padding:9px 0;border-bottom:1px solid var(--rule);font:600 15px/1.3 var(--sans)}
.latest time{font:500 13px/1.3 var(--sans);color:var(--slate);font-variant-numeric:tabular-nums}

/* Now on Gu (show open) */
.nowon{margin:30px 0;display:grid;grid-template-columns:auto 1fr auto;gap:20px;align-items:center;background:var(--onair);color:var(--onair-ink);padding:20px 22px}
.nowon .who{display:flex;gap:14px;align-items:center}
.nowon .open{font:400 19px/1.45 var(--serif)}
.nowon a{color:var(--onair-ink)}

/* Section rails */
.rails{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:34px 30px;margin:30px 0}
.rail .first{margin-bottom:10px}
.rail ul{list-style:none;margin:0;padding:0}
.rail li{padding:9px 0;border-top:1px solid var(--rule)}

/* Generic grids */
.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:26px 24px}
.grid-3{grid-template-columns:repeat(3,minmax(0,1fr))}
.card .player,.card .mono{margin-bottom:10px}
.page-head{padding:26px 0 14px;border-bottom:1px solid var(--rule);margin-bottom:22px}
.page-head h1{font:850 clamp(32px,4vw,48px)/1 var(--sans);font-stretch:70%;margin:0}
.page-head p{margin:10px 0 0;color:var(--slate);font:400 18px/1.5 var(--serif);max-width:62ch}
.subnav{display:flex;gap:6px;flex-wrap:wrap;margin-top:14px}
.subnav a{font:600 14px/1 var(--sans);padding:8px 12px;border:1px solid var(--rule);border-radius:2px}
.subnav a[aria-current="page"]{border-color:var(--ink);background:var(--ink);color:var(--paper)}
.cols{display:grid;grid-template-columns:minmax(0,1fr) 300px;gap:40px}
.listing{list-style:none;margin:0;padding:0}
.listing li{display:grid;grid-template-columns:110px 1fr;gap:16px;padding:16px 0;border-bottom:1px solid var(--rule)}
.listing time{font-size:13px;color:var(--slate)}
.empty{padding:30px;background:var(--wash);font:400 18px/1.5 var(--serif)}

/* Media */
.player{position:relative;background:#000;aspect-ratio:16/9}
.player video{width:100%;height:100%;display:block}
.mono{aspect-ratio:1/1;display:grid;place-items:center;background:var(--wash);color:var(--ink);font:850 30px/1 var(--sans);font-stretch:70%;border-radius:50%}
.portrait{width:64px;height:64px;border-radius:50%;object-fit:cover;flex:none;background:var(--wash)}
.portrait.mono{width:64px;height:64px;font-size:22px}
.portrait.lg{width:160px;height:160px;font-size:52px}

/* Article */
.article{max-width:760px}
.crumbs{font-size:14px;color:var(--slate);margin:22px 0 10px;display:flex;gap:8px}
.crumbs a{color:var(--red);font-weight:600}
.byline{display:flex;gap:14px;align-items:center;padding:16px 0;margin:18px 0;border-top:1px solid var(--rule);border-bottom:1px solid var(--rule)}
.byline .name{font-weight:700}
.byline .role,.byline .when{font-size:14px;color:var(--slate)}
.body{font:400 20px/1.65 var(--serif);max-width:68ch}
.body p{margin:0 0 1.1em}
.sponsor-box{border:1px solid var(--gold);background:color-mix(in srgb,var(--gold) 12%,var(--paper));padding:14px 18px;margin:26px 0;font:400 17px/1.5 var(--serif)}
.sponsor-box .lbl{display:block;font:700 13px/1 var(--sans);margin-bottom:6px}
.sources{margin:30px 0;padding:18px 20px;background:var(--wash)}
.sources h2{font:800 17px/1 var(--sans);margin:0 0 10px}
.sources ul{margin:0;padding-left:18px}
.sources li{margin:4px 0}
.sources a{text-decoration:underline;text-underline-offset:3px}
.note{font-size:14px;color:var(--slate);border-left:3px solid var(--rule);padding-left:12px;margin:20px 0}
.note a{text-decoration:underline;text-underline-offset:3px}
* + .block-title{margin-top:38px}
.person > div{min-width:0;overflow-wrap:anywhere}
.share{display:flex;gap:8px;flex-wrap:wrap;margin:24px 0}
.share a,.share button{font:600 14px/1 var(--sans);padding:9px 12px;border:1px solid var(--rule);background:transparent;color:var(--ink);border-radius:2px;cursor:pointer}
.related{margin:40px 0}

/* Prose pages */
.prose{max-width:720px;font:400 19px/1.65 var(--serif)}
.prose h2{font:800 24px/1.15 var(--sans);font-stretch:85%;margin:1.6em 0 .5em}
.prose h3{font:700 19px/1.2 var(--sans);margin:1.4em 0 .4em}
.prose a{text-decoration:underline;text-underline-offset:3px}
.prose ul{padding-left:22px}
.prose table{border-collapse:collapse;width:100%;font:400 15px/1.4 var(--sans);margin:1em 0}
.prose th,.prose td{text-align:left;border-bottom:1px solid var(--rule);padding:9px 8px;vertical-align:top}
.prose th{font-weight:700}
.legal-flag{font:600 14px/1.4 var(--sans);background:var(--wash);padding:12px 14px;border-left:4px solid var(--gold)}

/* People + shows */
.people{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:22px}
.person{display:flex;gap:14px;align-items:center;padding:14px 0;border-top:1px solid var(--rule)}
.person .t{font-size:14px;color:var(--slate)}
.profile{display:flex;gap:26px;align-items:center;padding:26px 0}
.showcard{border-top:4px solid var(--ink);padding-top:14px}
.showcard.live{border-top-color:var(--red)}
.sched{font-size:15px;color:var(--slate)}

/* Markets / weather widgets */
.pulse-card{padding:22px;background:var(--onair);color:var(--onair-ink);margin-bottom:24px}
.pulse-card .regime{font:900 48px/1 var(--sans);font-stretch:62%;color:var(--gold)}
.pulse-card ul{margin:12px 0 0;padding-left:18px;color:#cfd3da}

/* Forms */
form.stack-form{display:flex;gap:10px;flex-wrap:wrap;max-width:520px}
input[type=email],input[type=search],input[type=text]{font:400 17px/1 var(--sans);padding:11px 12px;border:1px solid var(--slate);border-radius:2px;background:var(--paper);color:var(--ink);flex:1;min-width:220px}
.newsletter-band{margin:36px 0;padding:26px;border:1px solid var(--rule);display:grid;grid-template-columns:1fr auto;gap:20px;align-items:center}
.newsletter-band h2{font:800 24px/1.1 var(--sans);font-stretch:80%;margin:0 0 6px}
.newsletter-band p{margin:0;color:var(--slate)}
#results li{display:block}

/* Footer */
footer.site{margin-top:60px;background:var(--onair);color:#cfd3da;font-size:15px}
footer.site .wrap{padding-top:36px;padding-bottom:30px}
footer.site .cols5{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:24px}
footer.site h2{font:700 15px/1 var(--sans);color:#fff;margin:0 0 12px}
footer.site ul{list-style:none;margin:0;padding:0}
footer.site li{margin:7px 0}
footer.site a{color:#cfd3da}
footer.site .base{border-top:1px solid #2e333d;margin-top:28px;padding-top:18px;display:flex;gap:18px;flex-wrap:wrap;justify-content:space-between;color:#9aa1ad;font-size:14px}
footer.site .base .gu{font:900 28px/1 var(--sans);font-stretch:62%;color:var(--red)}

.cookie{position:fixed;left:16px;right:16px;bottom:16px;max-width:560px;background:var(--paper);color:var(--ink);border:1px solid var(--ink);padding:16px;display:none;z-index:20}
.cookie.show{display:block}

@media (max-width:1000px){
  .lead{grid-template-columns:1fr 1fr}.lead > :first-child{grid-column:1/-1;padding-right:0;margin-bottom:22px}
  .lead > :nth-child(2){padding-left:0;border-left:0}
  .rails,.grid{grid-template-columns:repeat(2,minmax(0,1fr))}
  .cols{grid-template-columns:1fr}
  footer.site .cols5{grid-template-columns:repeat(2,minmax(0,1fr))}
  .nowon{grid-template-columns:1fr}
}
@media (max-width:640px){
  :root{--gut:16px}
  .lead,.rails,.grid,.grid-3,.lead-more{grid-template-columns:1fr}
  .lead > *{padding:0;border-left:0;margin-bottom:22px}
  .navtoggle{display:inline-flex}
  .mast .tools .btn.solid{display:none}
  .mast .wrap{gap:10px}
  .brand .gu{font-size:38px}
  .brand .full{display:none}
  nav.primary ul.top{display:none;flex-direction:column}
  nav.primary.open ul.top{display:flex}
  nav.primary .sub{position:static;display:block;border:0;padding:0 0 6px 12px}
  nav.primary > .wrap > ul > li > a{padding-left:0}
  .listing li{grid-template-columns:1fr;gap:4px}
  .onair .right{margin-left:0}
  .newsletter-band{grid-template-columns:1fr}
  .body{font-size:19px}
}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
@media print{.onair,nav.primary,.ad,footer.site,.share,.cookie{display:none}}
"""

JS = r"""
(function(){
  // live clock in the on-air bar (station time zone)
  var t=document.getElementById('clock');
  if(t){var tz=t.dataset.tz;function tick(){try{t.textContent=new Date().toLocaleTimeString('en-CA',{hour:'numeric',minute:'2-digit',timeZone:tz})+' '+(t.dataset.abbr||'')}catch(e){}}tick();setInterval(tick,20000)}
  // mobile nav
  var b=document.querySelector('.navtoggle'),n=document.querySelector('nav.primary');
  if(b&&n){b.addEventListener('click',function(){var o=n.classList.toggle('open');b.setAttribute('aria-expanded',o)})}
  // copy link
  document.querySelectorAll('[data-copy]').forEach(function(el){el.addEventListener('click',function(){
    navigator.clipboard&&navigator.clipboard.writeText(location.href).then(function(){el.textContent='Link copied'})})});
  // relative times
  document.querySelectorAll('time[data-rel]').forEach(function(el){
    var d=new Date(el.getAttribute('datetime')),m=Math.round((Date.now()-d)/60000);
    if(isNaN(m))return; el.textContent=m<1?'Just now':m<60?m+' min ago':m<1440?Math.round(m/60)+' hr ago':el.textContent});
  // cookie notice (only rendered when the ad network is on)
  var c=document.querySelector('.cookie');
  if(c){var k='gu-consent';var v=null;try{v=localStorage.getItem(k)}catch(e){}
    if(!v)c.classList.add('show');
    c.querySelectorAll('button').forEach(function(x){x.addEventListener('click',function(){try{localStorage.setItem(k,x.dataset.v)}catch(e){};c.classList.remove('show')})})}
  // search page
  var f=document.getElementById('search-form');
  if(f){var q=new URLSearchParams(location.search).get('q')||'',inp=f.querySelector('input'),out=document.getElementById('results'),st=document.getElementById('search-status');
    inp.value=q;
    fetch('/search-index.json').then(function(r){return r.json()}).then(function(idx){
      function run(){var terms=inp.value.toLowerCase().split(/\s+/).filter(Boolean);out.innerHTML='';
        if(!terms.length){st.textContent='Type a word or a name to search the last 30 days of stories.';return}
        var hits=idx.filter(function(a){var h=(a.t+' '+a.s+' '+a.p+' '+a.d).toLowerCase();return terms.every(function(w){return h.indexOf(w)>-1})});
        st.textContent=hits.length?hits.length+' stories match "'+inp.value+'"':'No stories match "'+inp.value+'". Try fewer words or check the spelling.';
        hits.slice(0,100).forEach(function(a){var li=document.createElement('li');
          li.innerHTML='<time></time><div><span class="kicker"></span><h3 class="hl hl-s"><a></a></h3><p class="meta"></p></div>';
          li.querySelector('time').textContent=a.date;li.querySelector('.kicker').textContent=a.d;
          var l=li.querySelector('a');l.href=a.u;l.textContent=a.t;li.querySelector('.meta').textContent=a.p;out.appendChild(li)})}
      run();inp.addEventListener('input',run)})}
})();
"""

FAVICON = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="10" fill="#1b1f27"/><text x="32" y="44" text-anchor="middle" font-family="Arial Narrow,Arial,sans-serif" font-weight="900" font-size="34" fill="#c8102e">Gu</text><circle cx="52" cy="12" r="5" fill="#c8102e"/></svg>"""
