"""The dashboard's own ledger, modelled on mlb-edge-lab's My Ledger.

Same idea, adapted to a ladder. Tap "+ Ledger" on any candidate and it lands at
that price with the rung's stake prefilled. Tap the stake to change it. Tap the
button again to remove it. Entries settle themselves against
docs/data/results.json, which every build publishes.

The difference from a flat bet ledger: a ladder is sequential. Rung N's stake is
rung N-1's return, so the whole chain is recomputed from scratch on every change.
Editing one stake reflows everything after it.

Storage is this browser's localStorage, per device, and nothing leaves the page.
Export writes JSON or CSV; import merges by id without duplicating.
"""

LEDGER_CSS = """
.lgr{margin-top:26px}
.lgr .row{background:var(--panel);border:1px solid var(--line);border-radius:12px;
  padding:11px 13px;margin-bottom:8px}
.lgr .row.pend{border-color:rgba(240,180,41,.4)}
.lgr .top{display:flex;justify-content:space-between;gap:10px;align-items:baseline}
.lgr .nm{font-weight:640;font-size:14px}
.lgr .sub2{color:var(--dim);font-size:12px;margin-top:2px}
.lgr .line{display:flex;align-items:center;gap:8px;margin-top:8px;flex-wrap:wrap;
  font-size:12.5px}
.lgr input.stk{background:var(--bg);border:1px solid var(--line);color:var(--ink);
  border-radius:6px;padding:5px 8px;width:84px;font-size:13px;
  font-family:ui-monospace,monospace;font-variant-numeric:tabular-nums}
.lgr input.stk:focus{outline:none;border-color:var(--gold)}
.lgr .x{background:none;border:1px solid var(--line);color:var(--dim);
  border-radius:6px;padding:5px 9px;font-size:11px;cursor:pointer}
.lgr .x:hover{color:var(--loss);border-color:var(--loss)}
.addbtn{background:rgba(240,180,41,.12);border:1px solid rgba(240,180,41,.45);
  color:var(--gold);border-radius:7px;padding:8px 12px;font-size:12px;
  cursor:pointer;font-weight:600}
.addbtn:hover{background:rgba(240,180,41,.22)}
.addbtn.on{background:rgba(46,204,113,.15);border-color:rgba(46,204,113,.5);
  color:var(--win)}
.tools{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}
.exp{background:var(--bg);border:1px solid var(--line);border-radius:8px;
  padding:10px;margin-top:10px;font-size:11px;font-family:ui-monospace,monospace;
  color:var(--dim);max-height:170px;overflow:auto;white-space:pre-wrap;
  word-break:break-all}
"""

LEDGER_HTML = """
<section class=lgr>
  <h2>My ladder <span id=lgr-count style="color:var(--dim);font-weight:400"></span></h2>
  <div class=grid id=lgr-stats></div>
  <div id=lgr-rows></div>
  <div class=tools>
    <button class=mini id=lgr-json type=button>Export JSON</button>
    <button class=mini id=lgr-csv type=button>Export CSV</button>
    <button class=mini id=lgr-imp type=button>Import</button>
    <button class=mini id=lgr-clear type=button>Clear</button>
  </div>
  <div class=exp id=lgr-out style="display:none"></div>
  <div class=k style="margin-top:10px;text-transform:none;letter-spacing:0">
    Stored in this browser only, per device. Nothing leaves the page. Export to
    move it or to survive a cleared browser.
  </div>
</section>
"""

LEDGER_JS = r"""
<script>
(function(){
  var KEY='ladder.ledger.v1', D=null, RESULTS={};
  try{ D=JSON.parse(document.getElementById('ladder-data').textContent); }catch(e){ return; }
  var CFG=D.state, CANDS=D.candidates;

  function load(){ try{ return JSON.parse(localStorage.getItem(KEY))||[]; }catch(e){ return []; } }
  function save(e){ try{ localStorage.setItem(KEY, JSON.stringify(e)); }catch(err){} }
  var entries = load();

  function money(v){ return '$'+(v||0).toFixed(2); }
  function d2a(d){ return d>=2 ? (d-1)*100 : -100/(d-1); }
  function esc(s){ return String(s==null?'':s).replace(/[&<>"]/g,function(c){
    return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]; }); }

  // A ladder is sequential: recompute the whole chain whenever anything changes.
  function reflow(){
    entries.sort(function(a,b){ return (a.added||'').localeCompare(b.added||''); });
    var rung=0, stake=CFG.base_stake, inc=CFG.stake_increment||0.01;
    var net=0, cashed=0, bust=0;
    entries.forEach(function(e){
      var want = Math.floor(stake/inc+1e-9)*inc;
      if(!e.stake_edited) e.stake = want;
      e.rung = rung;
      // Round the payout to cents BEFORE compounding — a book pays whole cents,
      // and carrying full float precision drifts from the Python ladder.
      e.to_return = Math.round(e.stake * e.decimal * 100) / 100;
      if(e.result==='win'){
        e.returned = e.to_return;
        stake = e.to_return; rung += 1;
        if(rung >= CFG.max_rung){ net += stake - CFG.base_stake; cashed++;
          e.cashed_out = stake; rung=0; stake=CFG.base_stake; }
        else { e.cashed_out = null; }
      } else if(e.result==='loss'){
        e.returned = 0; net -= CFG.base_stake; bust++;
        rung=0; stake=CFG.base_stake; e.cashed_out=null;
      } else if(e.result==='push'){
        e.returned = e.stake; e.cashed_out=null;
      } else {
        e.returned = null; e.cashed_out=null;
      }
      e.running_net = Math.round(net*100)/100;
    });
    return {rung:rung, stake:Math.floor(stake/inc+1e-9)*inc, net:net,
            cashed:cashed, bust:bust};
  }

  // Self-settlement, same shape as the CLI's grade step.
  function autoSettle(){
    var changed=false;
    entries.forEach(function(e){
      if(e.result || !e.event_id) return;
      var r = RESULTS[e.event_id];
      if(!r || !r.completed) return;
      var res = (r.winner === e.side) ? 'win'
              : (r.winner === 'draw' ? (e.side==='draw'?'win':'loss') : 'loss');
      e.result = res; e.settled_at = r.date || new Date().toISOString().slice(0,10);
      e.score = r.score || ''; changed=true;
    });
    if(changed) save(entries);
  }

  function draw(){
    var st = reflow();
    var host = document.getElementById('lgr-rows');
    document.getElementById('lgr-count').textContent =
      entries.length ? '— '+entries.length+' bet'+(entries.length>1?'s':'') : '';

    var done = entries.filter(function(e){ return e.result==='win'||e.result==='loss'; });
    var w = done.filter(function(e){ return e.result==='win'; }).length;
    var stats = document.getElementById('lgr-stats');
    stats.innerHTML =
      card('Rung', st.rung+' / '+CFG.max_rung, 'gold') +
      card('Next stake', money(st.stake), '') +
      card('Net', (st.net>=0?'+':'')+st.net.toFixed(2), st.net>0?'pos':st.net<0?'neg':'') +
      card('Record', done.length? w+'-'+(done.length-w) : '—', '');

    if(!entries.length){
      host.innerHTML='<div class=empty>No bets yet. Tap <b>+ Ledger</b> on a '+
        'candidate above to start the ladder.</div>';
      return;
    }
    host.innerHTML = entries.slice().reverse().map(function(e,i){
      var idx = entries.length-1-i;
      var pill = e.result ? '<span class="pill '+e.result+'">'+e.result+'</span>'
                          : '<span class="pill live">pending</span>';
      return '<div class="row'+(e.result?'':' pend')+'">'+
        '<div class=top><span class=nm>R'+e.rung+' &middot; '+esc(e.pick)+'</span>'+
        '<span class=price>'+(e.american>=0?'+':'')+Math.round(e.american)+'</span></div>'+
        '<div class=sub2>'+esc((e.league||'').toUpperCase())+' '+esc(e.matchup||'')+
        (e.score?' &middot; '+esc(e.score):'')+'</div>'+
        '<div class=line>'+
          '<span style="color:var(--dim)">stake</span>'+
          '<input class=stk type=number step=0.01 value="'+e.stake.toFixed(2)+
          '" data-i="'+idx+'">'+
          '<span>&rarr; <b>'+money(e.to_return)+'</b></span>'+
          pill+
          '<button class=x data-del="'+idx+'" type=button>remove</button>'+
          '<span style="margin-left:auto;color:var(--dim)">net '+
          (e.running_net>=0?'+':'')+e.running_net.toFixed(2)+'</span>'+
        '</div></div>';
    }).join('');

    host.querySelectorAll('input.stk').forEach(function(el){
      el.addEventListener('change', function(){
        var v=parseFloat(el.value); if(!v||v<=0) return;
        var e=entries[+el.dataset.i]; e.stake=v; e.stake_edited=true;
        save(entries); draw(); syncButtons();
      });
    });
    host.querySelectorAll('button[data-del]').forEach(function(el){
      el.addEventListener('click', function(){
        entries.splice(+el.dataset.del,1); save(entries); draw(); syncButtons();
      });
    });
  }

  function card(k,v,cls){
    return '<div class=card><div class=k>'+k+'</div>'+
           '<div class="v '+cls+'">'+v+'</div></div>';
  }

  function has(c){ return entries.some(function(e){
    return e.event_id ? (e.event_id===c.event_id && e.side===c.side)
                      : (e.pick===c.pick && !e.result); }); }

  function syncButtons(){
    CANDS.forEach(function(c,i){
      var b=document.getElementById('add'+i); if(!b) return;
      var on=has(c);
      b.className='addbtn'+(on?' on':'');
      b.textContent = on ? 'in ledger' : '+ Ledger';
    });
  }

  window.ladderAdd = function(i, decimal){
    var c=CANDS[i];
    if(has(c)){
      entries = entries.filter(function(e){
        return !(e.event_id===c.event_id && e.side===c.side && !e.result); });
    } else {
      entries.push({id:'b'+Date.now()+'_'+i, added:new Date().toISOString(),
        event_id:c.event_id||'', league:c.league||'', matchup:c.matchup||'',
        pick:c.pick, side:c.side||'', decimal:decimal, american:d2a(decimal),
        stake:0, stake_edited:false, result:null});
    }
    save(entries); draw(); syncButtons();
  };

  function toCSV(){
    var cols=['added','settled_at','league','matchup','pick','rung','decimal',
              'american','stake','to_return','result','returned','running_net'];
    var out=[cols.join(',')];
    entries.forEach(function(e){
      out.push(cols.map(function(k){
        var v=e[k]==null?'':e[k];
        return /[",\n]/.test(String(v)) ? '"'+String(v).replace(/"/g,'""')+'"' : v;
      }).join(','));
    });
    return out.join('\n');
  }

  function show(text, name, mime){
    var box=document.getElementById('lgr-out');
    box.style.display='block'; box.textContent=text;
    try{
      var b=new Blob([text],{type:mime}), u=URL.createObjectURL(b);
      var a=document.createElement('a'); a.href=u; a.download=name; a.click();
      setTimeout(function(){ URL.revokeObjectURL(u); },2000);
    }catch(err){}   // embedded viewers block downloads; the text above still works
  }

  document.getElementById('lgr-json').onclick=function(){
    show(JSON.stringify(entries,null,1),'ladder-ledger.json','application/json'); };
  document.getElementById('lgr-csv').onclick=function(){
    show(toCSV(),'ladder-ledger.csv','text/csv'); };
  document.getElementById('lgr-clear').onclick=function(){
    if(confirm('Delete all '+entries.length+' ledger entries on this device?')){
      entries=[]; save(entries); draw(); syncButtons(); } };
  document.getElementById('lgr-imp').onclick=function(){
    var t=prompt('Paste exported ledger JSON'); if(!t) return;
    var inc; try{ inc=JSON.parse(t); }catch(e){ alert('That is not valid JSON'); return; }
    if(!Array.isArray(inc)){ alert('Expected a JSON array'); return; }
    var seen={}; entries.forEach(function(e){ seen[e.id]=1; });
    var added=0;
    inc.forEach(function(e){ if(e && e.id && !seen[e.id]){ entries.push(e); added++; } });
    save(entries); draw(); syncButtons();
    alert('Merged '+added+' new '+(added===1?'entry':'entries')+
          ', skipped '+(inc.length-added)+' already here.');
  };

  fetch('data/results.json',{cache:'no-store'})
    .then(function(r){ return r.ok ? r.json() : {}; })
    .then(function(j){ RESULTS=j.games||{}; autoSettle(); draw(); syncButtons(); })
    .catch(function(){ draw(); syncButtons(); });

  draw(); syncButtons();
})();
</script>
"""
