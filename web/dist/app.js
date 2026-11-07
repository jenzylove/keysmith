/* Keysmith web app, dependency free, served from web/dist.
 * Drives the recovery flow against the API in docs/ARCHITECTURE.md:
 *   landing -> start -> interview -> plan -> wallet -> live run -> result -> proof
 * The found password is shown once from the live SSE stream and never re-stored. */
"use strict";

const app = document.getElementById("app");
const state = { walletTypes:null, demos:null, job:null, landingData:null };

/* ---------- helpers ---------- */
const h=(html)=>{const t=document.createElement("template");t.innerHTML=html.trim();return t.content.firstElementChild;};
const esc=(s)=>String(s==null?"":s).replace(/[&<>"']/g,(c)=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const $=(s,r=document)=>r.querySelector(s);
const $$=(s,r=document)=>Array.from(r.querySelectorAll(s));
const fmtInt=(n)=>Number(n).toLocaleString("en-US");
const WALLET_LABELS={metamask:"MetaMask",bitcoin_core:"Bitcoin Core",electrum:"Electrum",blockchain:"Blockchain.com",bip39_seed:"Seed phrase"};
const walletLabel=(id)=>WALLET_LABELS[id]||String(id||"").replace(/_/g," ");

async function api(path,opts={}){
  const res=await fetch(path,opts);let body=null;
  try{body=await res.json();}catch(_){/*non json*/}
  if(!res.ok){throw new Error((body&&(body.detail||body.error))||`request failed (${res.status})`);}
  return body;
}
function toast(msg){const el=h(`<div class="toast">${esc(msg)}</div>`);document.body.appendChild(el);setTimeout(()=>el.remove(),3200);}
function humanDuration(sec){sec=Number(sec);if(!isFinite(sec)||sec<1)return"under a second";
  for(const [name,size] of [["day",86400],["hour",3600],["minute",60],["second",1]]){
    if(sec>=size){const n=Math.round(sec/size);return`${n} ${name}${n!==1?"s":""}`;}}return"under a second";}
const rangeText=(p)=>`${humanDuration(p[0])} to ${humanDuration(p[1])}`;

function render(node){app.innerHTML="";app.appendChild(node);window.scrollTo(0,0);wireReveal();setActiveNav();}
function errorScreen(msg){render(h(`<div class="appwrap"><div class="panel error-box"><h2>Something went wrong</h2>
  <p class="sub">${esc(msg)}</p><a class="btn secondary" href="#/" data-nav>Back home</a></div></div>`));}

/* scroll reveal */
let io;
function wireReveal(){
  if(io)io.disconnect();
  io=new IntersectionObserver((es)=>es.forEach((e)=>{if(e.isIntersecting){e.target.classList.add("in");io.unobserve(e.target);}}),{threshold:.12});
  $$(".reveal").forEach((el)=>io.observe(el));
}

/* ---------- persistent nav ---------- */
const KEY_GLYPH=`<svg viewBox="0 0 64 64" aria-hidden="true"><circle cx="22" cy="22" r="12" fill="none" stroke="var(--brass)" stroke-width="5"/><path d="M30 30 L52 52 M44 44 l7 -7 M50 50 l6 -6" stroke="var(--brass)" stroke-width="5" fill="none" stroke-linecap="square"/></svg>`;
function mountNav(){
  if(document.querySelector(".nav"))return;
  const nav=h(`<div class="nav"><div class="nav-inner">
    <a class="brand" href="#/" data-nav>${KEY_GLYPH}<span>Keysmith</span></a>
    <nav class="nav-links">
      <a href="#/#how" data-nav>How it works</a>
      <a href="#/proof" data-nav>Proof</a>
      <a href="#/#faq" data-nav>FAQ</a>
    </nav>
    <button class="icon-btn" id="theme" title="Toggle light and dark">◑</button>
    <a class="btn sm" href="#/app" data-nav>Start a recovery</a>
  </div></div>`);
  document.body.insertBefore(nav,document.body.firstChild);
  $("#theme",nav).onclick=()=>{
    const cur=document.body.getAttribute("data-theme")==="light"?"dark":"light";
    document.body.setAttribute("data-theme",cur);
    document.documentElement.setAttribute("data-theme",cur);
    try{localStorage.setItem("ks-theme",cur);}catch(_){}
  };
}
function setActiveNav(){}

/* ---------- the key visual ---------- */
function teethPath(seed){
  // horizontal key blade outline in a 300x200 box; teeth cut from the string.
  const n=11,x0=150,x1=272,top=86,base=112;
  let hcode=0;for(const c of (seed||"key"))hcode=(hcode*31+c.charCodeAt(0))>>>0;
  const pts=[];for(let i=0;i<n;i++){
    hcode=(hcode*1103515245+12345)>>>0;
    const depth=4+((hcode>>8)%15);                 // 4..18 px cut
    const x=x1-(x1-x0)*(i/(n-1));
    pts.push([x,base-(i%2?depth:depth*0.5)]);
  }
  let d=`M76,${top} L280,${top} L280,${base} L${x1},${base} `;
  for(const [x,y] of pts)d+=`L${x.toFixed(1)},${y.toFixed(1)} `;
  d+=`L76,${base} Z`;
  return d;
}
function keySvg(){
  return h(`<div class="keywrap">
    <svg viewBox="0 0 300 200">
      <circle class="bow" cx="40" cy="99" r="30"/>
      <circle class="cyl" cx="40" cy="99" r="12"/>
      <path class="blade" d="${teethPath("Keysmith")}"/>
    </svg>
    <div class="keyguess mono"></div>
  </div>`);
}
let keyTimer;
function animateKey(node,guesses){
  const blade=$(".blade",node),label=$(".keyguess",node);
  let i=0;const list=guesses.length?guesses:["Rocky1999!","Sara_Max7","summerbreeze2011!!","Liverp00l.1892","milo22"];
  const tick=()=>{const g=list[i%list.length];i++;blade.setAttribute("d",teethPath(g));label.textContent=g;};
  tick();clearInterval(keyTimer);keyTimer=setInterval(tick,1700);
}

/* ---------- footer status ---------- */
function statusStrip(health){
  const live=health&&health.runner==="vm";
  const model=health&&health.model?health.model:"inference not configured";
  return `<div class="statusline"><span class="dot ${live?"live":""}"></span>
    ${live?"Sealed box runner online":"Runner not configured (demo build)"} · model ${esc(model)}</div>`;
}

/* ================= LANDING ================= */
async function viewLanding(){
  if(!state.landingData){
    const [health,demos,proof]=await Promise.all([
      api("/api/health").catch(()=>null),
      api("/api/demo").catch(()=>[]),
      api("/api/proof").catch(()=>({status:"not run"})),
    ]);
    state.landingData={health,demos,proof};state.demos=demos;
  }
  const {health,demos,proof}=state.landingData;

  const demoRows=(demos||[]).map((d)=>`
    <div class="demo reveal">
      <div><div class="wt"><span class="demo-badge">Live demo</span><span class="wt2">${esc(walletLabel(d.wallet_type))} wallet, no funds</span></div>
        <h3>${esc(d.owner_story||"A forgotten wallet")}</h3>
        <p>What they remember: ${esc(d.notes||"a few fuzzy details")}</p></div>
      <a class="btn sm" href="#/app?demo=${esc(d.id)}" data-nav>Run this recovery</a>
    </div>`).join("")||`<p class="note">Demo wallets are loading on this deployment.</p>`;

  let proofMini;
  if(proof&&proof.status!=="not run"){
    const cs=proof.cases||proof.results||[];
    const tot=cs.length||20;
    const rec=cs.filter((c)=>c.found).length;
    const base=cs.filter((c)=>c.baseline_found).length;
    proofMini=`<div class="proofbar">
      <div class="pstat"><div class="n">${rec}/${tot}</div><div class="k">recovered from memory</div></div>
      <div class="pstat"><div class="n">${base}/${tot}</div><div class="k">recovered by plain defaults</div></div>
    </div><p class="sec-sub">We publish the misses, not only the wins.</p>`;
  }else{
    proofMini=`<p class="sec-sub">The answer key of 20 test wallets is written blind, 15 recoverable and 5 honest misses. Results publish here once the full set runs on Vultr.</p>`;
  }

  const node=h(`<div>
    <section class="hero"><div class="wrap hero-center">
      <div class="eyebrow">Vultr Agent Rush · sealed recovery</div>
      <h1>Your old wallet is <span class="pill-word">still</span> there.</h1>
      <p class="lede">Tell Keysmith what you half remember, a name, a year, the way you swap letters for numbers. It becomes a short list of targeted guesses, tried inside a sealed box that cannot send your wallet anywhere, not even to us.</p>
      <div class="cta-row center">
        <a class="btn" href="#/app" data-nav>Start a recovery</a>
        <a class="btn secondary" href="#/app?demo=1" data-nav>Watch a demo wallet open</a>
      </div>
      ${statusStrip(health)}
      <div class="keystage"></div>
    </div></section>

    <section class="band" id="problem"><div class="wrap">
      <div class="sec-no reveal">01 / The problem</div>
      <h2 class="sec-h reveal">Losing the password is not the hard part. Finding help you can trust is.</h2>
      <div class="rows">
        <div class="lrow reveal"><div class="idx">01</div><div>
          <h3>The money is real and the stories are recent</h3>
          <p>In May 2026 a holder recovered 5 BTC, about 400 thousand dollars, from an 11 year old wallet after weeks of guessing. The coverage warned about the real risk: uploading your wallet file to a cloud AI.</p>
          <a class="src" href="https://www.coindesk.com/tech/2026/05/14/claude-helps-recover-usd395-000-in-bitcoin-trapped-on-a-computer-for-years" target="_blank" rel="noopener">coindesk.com</a>
        </div></div>
        <div class="lrow reveal"><div class="idx">02</div><div>
          <h3>Help today means a stranger holding your wallet</h3>
          <p>Recovery firms work by hand, take roughly 20 percent of the coins, and need the wallet file in their hands before they start.</p>
        </div></div>
        <div class="lrow reveal"><div class="idx">03</div><div>
          <h3>The space is full of scams</h3>
          <p>The FBI has warned about fake crypto recovery services in 2023, 2024 and 2025, including fake law firms that take an upfront fee and vanish.</p>
          <a class="src" href="https://www.bleepingcomputer.com/news/security/fbi-warns-of-fake-law-firms-targeting-crypto-scam-victims/" target="_blank" rel="noopener">fbi warning</a>
        </div></div>
      </div>
    </div></section>

    <section class="band" id="how"><div class="wrap">
      <div class="sec-no reveal">02 / How it works</div>
      <h2 class="sec-h reveal">Four steps, and you see every one.</h2>
      <ol class="timeline">
        <li class="tl reveal"><div class="tl-dot"></div><div class="step-k">Step one</div>
          <h3>Remember</h3><p>You answer a short interview about what you half recall. A model running on Vultr turns those fragments into a structured profile, never a wild guess.</p></li>
        <li class="tl reveal"><div class="tl-dot"></div><div class="step-k">Step two</div>
          <h3>Guess</h3><p>We compile the profile into a few hundred ordered guesses and show you the exact list first. What you approve is literally what runs, with no hidden expansion.</p></li>
        <li class="tl reveal"><div class="tl-dot"></div><div class="step-k">Step three</div>
          <h3>Seal</h3><p>A fresh Vultr box opens with its network switched off, your wallet mounted read only, and the reasoning agent locked away from the file entirely.</p></li>
        <li class="tl reveal"><div class="tl-dot"></div><div class="step-k">Step four</div>
          <h3>Destroy</h3><p>The box tries the guesses, hands you the result once, then is deleted. A teardown receipt proves the wallet left zero bytes behind.</p></li>
      </ol>
    </div></section>

    <section class="band" id="try"><div class="wrap">
      <div class="sec-no reveal">03 / Try it now</div>
      <h2 class="sec-h reveal">Run a real recovery, no wallet of your own needed.</h2>
      <p class="sec-sub reveal">These are live demos. Each one is a real encrypted wallet we made with a password we then forgot on purpose, holding no funds. Pick one, play the owner, and watch the sealed box open it end to end.</p>
      <div class="rows">${demoRows}</div>
    </div></section>

    <section class="band" id="box"><div class="wrap">
      <div class="sec-no reveal">04 / Why you can trust it</div>
      <h2 class="sec-h reveal">Your wallet goes into a box with no way to talk back.</h2>
      <div class="vault-wrap">
        <div class="vault reveal">
          <span class="vault-tag">one sealed Vultr box, per job</span>
          <div class="vault-io in"><span class="arr">↓</span> your wallet goes in, mounted read only</div>
          <ul class="vault-core">
            <li><span>Network</span><span class="g">switched off</span></li>
            <li><span>Your wallet file</span><span class="g">read only</span></li>
            <li><span>The reasoning agent</span><span class="g">no access</span></li>
            <li><span>Outbound traffic</span><span class="g">all blocked</span></li>
          </ul>
          <div class="vault-io out"><span class="arr">↑</span> nothing comes back out</div>
          <div class="vault-foot">then the box is destroyed · wallet bytes that left: 0</div>
        </div>
        <div>
          <p class="trust-lead reveal">Recovery firms ask you to hand over your wallet and trust a stranger. Keysmith asks you to trust <b>no one</b>, including us.</p>
          <p class="sec-sub reveal">The box is built so that even if our server were hostile, or a poisoned hint tried to make the agent misbehave, your wallet still could not leave. You do not take that on faith: during any recovery, press <b>Run the break in test</b> and watch a real exfiltration attempt get denied, live and on camera.</p>
        </div>
      </div>

      <div class="sec-no reveal" style="margin-top:56px">Why this needs Vultr</div>
      <h2 class="sec-h reveal">The trust comes from the infrastructure, not a promise.</h2>
      <div class="vultr">
        <div class="vrow reveal"><div class="vk">Serverless Inference</div>
          <div><h4>Your memories never leave for a third party</h4>
            <p>The interview that reads your hints runs on Vultr Serverless Inference, an open model on the same infrastructure. Your private details never go to OpenAI or Anthropic, the way they did in the viral case that inspired this.</p></div></div>
        <div class="vrow reveal"><div class="vk">Cloud Compute</div>
          <div><h4>A machine that exists only for your job</h4>
            <p>Each recovery spins up a throwaway Vultr VM through the API, seals it, then deletes it when done. There is no shared server holding wallets, nothing persistent to breach, and a receipt that proves the teardown.</p></div></div>
        <div class="vrow reveal"><div class="vk">Your own account</div>
          <div><h4>Or cut us out entirely</h4>
            <p>Because it is all Vultr and all open, you can run the exact same thing in your own Vultr account with one command. Then the wallet never touches a server we control. That option is the strongest promise we can make.</p></div></div>
      </div>
    </div></section>

    <section class="band" id="proof"><div class="wrap">
      <div class="sec-no reveal">05 / Proof</div>
      <h2 class="sec-h reveal">Memory beats brute force. Here is the measurement.</h2>
      ${proofMini}
      <a class="btn secondary reveal" href="#/proof" data-nav>See the full answer key</a>
    </div></section>

    <section class="band" id="own"><div class="wrap">
      <div class="sec-no reveal">06 / Your own account</div>
      <h2 class="sec-h reveal">Trust no one, including us.</h2>
      <p class="sec-sub reveal">The whole thing is open. Run it in your own Vultr account and the wallet never reaches a server we control.</p>
      <div class="cmd-block reveal"><code>git clone https://github.com/jenzylove/keysmith &amp;&amp; cd keysmith &amp;&amp; ./keysmith-local</code>
        <button class="btn sm" id="copycmd">Copy</button></div>
    </div></section>

    <section class="band" id="faq"><div class="wrap">
      <div class="sec-no reveal">07 / Questions</div>
      <h2 class="sec-h reveal" style="margin-bottom:24px">Straight answers.</h2>
      <details class="faq reveal"><summary>Do you ever see my wallet?</summary><p>No. For a hosted job the file goes straight into the sealed box over an inbound only channel and is never written to our database. For full certainty, run it in your own Vultr account.</p></details>
      <details class="faq reveal"><summary>What if my password was random?</summary><p>Then Keysmith will not find it, and it tells you so before you spend time. It works when your password came from things you can still half remember.</p></details>
      <details class="faq reveal"><summary>Which wallets work?</summary><p>MetaMask, Bitcoin Core, Electrum, Blockchain.com, and BIP39 seed phrases with a couple of missing words.</p></details>
      <details class="faq reveal"><summary>What does it cost?</summary><p>Free during the hackathon. The honest model is a small flat fee per job, never a percentage of your coins.</p></details>
      <details class="faq reveal"><summary>Could someone run this on a wallet that is not theirs?</summary><p>We cannot verify ownership, and we say so plainly. Keysmith adds no new capability: the underlying open tool already exists. We never store files and we keep no copy.</p></details>
      <details class="faq reveal"><summary>Why Vultr?</summary><p>The work needs a throwaway machine you can seal and destroy on demand, and a model that runs on the same infrastructure so your memories never leave for a third party. Vultr gives both.</p></details>
    </div></section>

    <section class="closing"><div class="wrap">
      <h2 class="reveal">The coins are still on chain.<br/>Go remember the key.</h2>
      <div class="cta-row reveal" style="justify-content:center">
        <a class="btn" href="#/app" data-nav>Start a recovery</a>
        <a class="btn secondary" href="#/app?demo=1" data-nav>Watch a demo first</a>
      </div>
    </div></section>

    <footer class="foot"><div class="wrap">
      <div class="foot-grid">
        <div><div class="foot-brand">${KEY_GLYPH}<span>Keysmith</span></div>
          <p>Recover a forgotten crypto wallet password from what you half remember, inside a sealed box that cannot leak it. Built for the Vultr Agent Rush hackathon.</p></div>
        <div class="foot-col"><h4>Product</h4>
          <a href="#/app" data-nav>Start a recovery</a>
          <a href="#/app?demo=1" data-nav>Demo wallet</a>
          <a href="#/proof" data-nav>Proof</a></div>
        <div class="foot-col"><h4>Build</h4>
          <a href="https://github.com/jenzylove/keysmith" target="_blank" rel="noopener">GitHub repo</a>
          <a href="#/#how" data-nav>How it works</a>
          <a href="#/#box" data-nav>The sealed box</a></div>
      </div>
      <div class="foot-mark">Keysmith</div>
      <div class="foot-legal">Runs on Vultr Cloud Compute and Vultr Serverless Inference. Only run it on wallets you own.</div>
    </div></footer>
  </div>`);

  const stage=$(".keystage",node);stage.appendChild(keySvg());
  const g=(demos||[]).map((d)=>d.sample_guess).filter(Boolean);
  render(node);animateKey(node,g);
  const cc=$("#copycmd",node);if(cc)cc.onclick=()=>{navigator.clipboard?.writeText("git clone https://github.com/jenzylove/keysmith && cd keysmith && ./keysmith-local").then(()=>toast("copied"));};
  // smooth-scroll to #anchor if present
  const anchor=(location.hash.split("?")[0].split("#")[2]);
  if(anchor){const t=document.getElementById(anchor);if(t)setTimeout(()=>t.scrollIntoView({behavior:"smooth"}),60);}
}

/* ================= RECOVERY FLOW ================= */
function crumbs(step){
  const steps=[["type","Wallet"],["interview","Memory"],["plan","Plan"],["wallet","Wallet in"],["run","Live run"]];
  const i=steps.findIndex((s)=>s[0]===step);
  return`<div class="crumbs">${steps.map((s,k)=>`<span class="c ${k<i?"done":""} ${k===i?"on":""}">${esc(s[1])}</span>${k<steps.length-1?"<span>/</span>":""}`).join("")}</div>`;
}

async function viewStart(demoFlag){
  render(h(`<div class="appwrap"><div class="panel"><h2>Loading…</h2></div></div>`));
  try{
    if(!state.walletTypes)state.walletTypes=await api("/api/wallet-types");
    if(!state.demos)state.demos=await api("/api/demo");
  }catch(e){return errorScreen(e.message);}

  const demoRows=(state.demos||[]).map((d)=>`
    <div class="demo"><div><div class="wt">${esc(d.wallet_type)} · test wallet</div>
      <h3>${esc(d.owner_story||"A forgotten wallet")}</h3><p>${esc(d.notes||"")}</p></div>
      <button class="btn sm" data-demo="${esc(d.id)}">Open it</button></div>`).join("");
  const typeRows=(state.walletTypes||[]).map((w)=>`
    <div class="demo"><div><h3>${esc(w.label)}</h3><p>${esc(w.notes)}</p>
      <div class="note">${fmtInt(w.speed_pw_s)} guesses/sec · ${w.input==="seed"?"seed phrase":"wallet file"}</div></div>
      <button class="btn sm secondary" data-type="${esc(w.id)}">Choose</button></div>`).join("");

  const node=h(`<div class="appwrap">
    ${crumbs("type")}
    <div class="panel"><h2>Watch a demo wallet open</h2>
      <p class="sub">Public test wallets, no funds. You play the owner: answer the interview and watch it open end to end.</p>
      <div class="rows">${demoRows||'<p class="note">No demo wallets on this build yet.</p>'}</div></div>
    <div class="panel"><h2>Recover your own wallet</h2>
      <p class="sub">Pick your wallet type. You see every guess before anything runs, and nothing is uploaded until you accept the plan.</p>
      <div class="rows">${typeRows}</div></div>
  </div>`);
  $$("[data-type]",node).forEach((b)=>b.onclick=()=>beginJob({wallet_type:b.dataset.type}));
  $$("[data-demo]",node).forEach((b)=>b.onclick=()=>beginJob({demo_id:b.dataset.demo}));
  render(node);
  if(demoFlag&&demoFlag!=="1"){const b=$(`[data-demo="${demoFlag}"]`,node);if(b)b.click();}
}

async function beginJob(payload){
  try{
    const res=await api("/api/jobs",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
    const wt=payload.wallet_type||((state.demos||[]).find((d)=>d.id===payload.demo_id)||{}).wallet_type;
    state.job={id:res.job_id,wallet_type:wt,demo_id:res.demo_id||payload.demo_id||null,
      prefill:res.prefill_answers||{},walletLoaded:!!(res.demo_id||payload.demo_id)};
    viewInterview();
  }catch(e){toast(e.message);}
}

const INTERVIEW_FIELDS=[
  ["names","Names, pets, places, teams","Your dog, a child, a street, a football club, whatever you would reach for."],
  ["years","Years","A year or a rough range. Late 90s is fine."],
  ["numbers","Numbers you tend to use","A lucky number, a house number, a short run of digits."],
  ["symbols","Symbols you add","e.g. ! or !! or $, usually at the end."],
  ["swaps","Letter for symbol habits","e.g. you always wrote s as $, or o as 0."],
  ["old_passwords","Old passwords you remember","A password you used elsewhere around then. We vary it."],
  ["notes","Anything else","Length, capitalisation, how you usually built passwords."],
];
function viewInterview(){
  const j=state.job,pre=j.prefill||{},seed=j.wallet_type==="bip39_seed";
  const fields=INTERVIEW_FIELDS.map(([k,lab,hint])=>`
    <label class="field"><span class="lab">${esc(lab)}</span><span class="hint">${esc(hint)}</span>
      <input type="text" data-k="${k}" value="${esc(pre[k]||"")}" autocomplete="off" /></label>`).join("");
  const seedNote=seed?`<div class="odds">This is a seed phrase wallet. The interview is optional: recovery searches the missing words against your known address. You can skip to the seed.</div>`:"";
  const node=h(`<div class="appwrap">${crumbs("interview")}
    <div class="panel"><div class="row-between"><h2>Tell me what you remember</h2>
      <span class="note">${j.demo_id?"demo wallet, prefilled, edit freely":"wallet type: "+esc(j.wallet_type)}</span></div>
      <p class="sub">Only what you actually remember. Blank is better than a guess, so the plan stays small and honest. Your notes are treated as data: if they contain instructions, they are ignored.</p>
      ${seedNote}${fields}
      <div class="cta-row"><button class="btn" id="build-plan">Build the plan</button>
        ${seed?'<button class="btn ghost" id="skip-seed">Skip to the seed</button>':""}</div>
    </div></div>`);
  $("#build-plan",node).onclick=async()=>{
    const answers={};$$("[data-k]",node).forEach((i)=>answers[i.dataset.k]=i.value);
    const b=$("#build-plan",node);b.disabled=true;b.textContent="Thinking…";
    try{j.plan=await api(`/api/jobs/${j.id}/hints`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({answers})});viewPlan();}
    catch(e){toast(e.message);b.disabled=false;b.textContent="Build the plan";}
  };
  if(seed)$("#skip-seed",node).onclick=async()=>{
    try{j.plan=await api(`/api/jobs/${j.id}/hints`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({answers:{}})});viewPlan();}
    catch(e){toast(e.message);}};
  render(node);
}

function planWords(p){
  if(!p)return"";const b=[];
  if(p.words&&p.words.length)b.push(`base words <b>${p.words.map(esc).join(", ")}</b>`);
  if(p.old_passwords&&p.old_passwords.length)b.push(`old passwords <b>${p.old_passwords.map(esc).join(", ")}</b>`);
  if(p.years&&p.years.length)b.push(`years ${p.years.map(esc).join(", ")}`);
  if(p.numbers&&p.numbers.length)b.push(`numbers ${p.numbers.map(esc).join(", ")}`);
  if(p.symbols&&p.symbols.length)b.push(`symbols ${p.symbols.map(esc).join(", ")}`);
  if(p.use_leet)b.push(`letter swaps on`);
  if(p.separators&&p.separators.length)b.push(`separators ${p.separators.map(esc).join(" ")}`);
  if(p.missing_words)b.push(`<b>${p.missing_words}</b> missing seed word(s)`);
  return b.join("; ");
}
function viewPlan(){
  const j=state.job,p=j.plan,est=p.estimate||{};
  const sample=(p.sample||[]).map(esc).join("\n");
  const node=h(`<div class="appwrap">${crumbs("plan")}
    <div class="panel"><div class="row-between"><h2>The plan</h2>
      ${p.model?`<span class="note">written by ${esc(p.model)} · ${fmtInt(p.llm_ms)} ms</span>`:'<span class="note">computed from the seed</span>'}</div>
      <p class="sub">In plain words: ${planWords(p.profile)||"your remembered details"}.</p>
      <div class="stat-row">
        <div class="stat"><div class="n">${fmtInt(p.candidate_count)}</div><div class="k">guesses, in order</div></div>
        <div class="stat"><div class="n">${est.pw_per_sec?fmtInt(est.pw_per_sec):"n/a"}</div><div class="k">guesses/sec on the box</div></div></div>
      <div class="odds">
        <div><b>Expected</b> (found about halfway): ${est.expected_s?esc(rangeText(est.expected_s)):"n/a"}.</div>
        <div><b>Worst case</b> (full scan): ${est.worst_case_s?esc(rangeText(est.worst_case_s)):"n/a"}.</div>
        <div style="margin-top:6px" class="note">${esc(est.reasoning||"")}</div></div>
      <details class="raw"><summary>Show the raw guesses we will try (first ${(p.sample||[]).length})</summary>
        <div class="codelist">${sample||"(none)"}</div>
        <p class="note">This is literally what runs, no hidden expansion.</p></details>
      <div class="cta-row"><button class="btn" id="accept-plan">Accept and ${j.walletLoaded?"open the box":"continue"}</button>
        <button class="btn ghost" id="redo">Change my hints</button></div>
    </div></div>`);
  $("#redo",node).onclick=()=>viewInterview();
  $("#accept-plan",node).onclick=()=>(j.walletLoaded?startRun():viewWallet());
  render(node);
}

function viewWallet(){
  const j=state.job,seed=j.wallet_type==="bip39_seed";
  const body=seed?`
    <label class="field"><span class="lab">Your seed words</span>
      <span class="hint">Space separated. Write <b>?</b> for any word you have lost or are unsure of, up to 2.</span>
      <textarea data-seed rows="3" placeholder="legal winner thank ? zebra ? ..."></textarea></label>
    <label class="field"><span class="lab">One address from this wallet</span>
      <span class="hint">Any address you know belongs to it. Recovery checks guesses against it.</span>
      <input type="text" data-addr placeholder="bc1q… or 0x…" /></label>`:`
    <label class="field"><span class="lab">Your wallet file</span>
      <span class="hint">It goes straight into the sealed box over an inbound only channel. Max 5 MB. Never stored.</span>
      <input type="file" data-file /></label>`;
  const node=h(`<div class="appwrap">${crumbs("wallet")}
    <div class="panel"><h2>${seed?"Enter your seed":"Upload your wallet"}</h2>
      <p class="sub">Only now, after you accepted the plan. ${seed?"":"The file never touches our database and never leaves the box."}</p>
      ${body}
      <div class="odds">Only run this on a wallet you own. We have no way to verify ownership, and we say so plainly.</div>
      <button class="btn" id="to-run">Seal the box and begin</button></div></div>`);
  $("#to-run",node).onclick=async()=>{
    try{
      if(seed){
        const words=($("[data-seed]",node).value||"").trim().split(/\s+/).filter(Boolean);
        const address=($("[data-addr]",node).value||"").trim();
        if(!words.length)return toast("enter your seed words");
        if(!address)return toast("enter one known address");
        await api(`/api/jobs/${j.id}/wallet`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({seed_words:words,address})});
      }else{
        const f=$("[data-file]",node).files[0];if(!f)return toast("choose your wallet file");
        const fd=new FormData();fd.append("file",f);
        await api(`/api/jobs/${j.id}/wallet`,{method:"POST",body:fd});
      }
      startRun();
    }catch(e){toast(e.message);}
  };
  render(node);
}

const STAGE_ORDER=["queued","creating_box","sealing","uploading","running","found","destroying","destroyed"];
const STAGE_LABEL={queued:"queued",creating_box:"creating box",sealing:"sealing",uploading:"uploading",running:"running",found:"found",not_found:"not found",destroying:"destroying",destroyed:"destroyed",error:"error"};

async function startRun(){
  const j=state.job;
  const node=h(`<div class="appwrap">${crumbs("run")}
    <div class="row-between"><h2>Live recovery</h2><span class="note" id="box-label">opening the box…</span></div>
    <div class="stages" id="stages"></div>
    <div class="run-grid">
      <div><div class="panel"><h2>Progress</h2>
        <div class="bar"><i id="bar"></i></div><div class="progress-meta" id="pmeta">waiting…</div>
        <div class="spacer"></div><div class="log" id="log"></div></div>
        <div id="result-panel" style="display:none"></div></div>
      <div><div class="panel"><h2>Containment</h2>
        <ul class="seal" id="seal"><li><span>waiting for seal…</span></li></ul>
        <div class="spacer"></div><button class="btn danger" id="attack-btn" disabled>Run the break in test</button>
        <div id="attacks" style="margin-top:12px"></div></div>
        <div id="receipt-panel" style="display:none"></div></div>
    </div></div>`);
  render(node);renderStages(node,null);
  try{await api(`/api/jobs/${j.id}/start`,{method:"POST"});}catch(e){return errorScreen(e.message);}
  const es=new EventSource(`/api/jobs/${j.id}/events`);
  const logEl=$("#log",node),attackBtn=$("#attack-btn",node);
  attackBtn.onclick=async()=>{attackBtn.disabled=true;try{await api(`/api/jobs/${j.id}/attack`,{method:"POST"});}catch(e){toast(e.message);attackBtn.disabled=false;}};
  es.onmessage=(msg)=>{let ev;try{ev=JSON.parse(msg.data);}catch(_){return;}handleEvent(node,ev,{logEl,attackBtn,j});if(ev.type==="receipt")es.close();};
  es.onerror=()=>{};
}
function renderStages(node,current){
  const el=$("#stages",node);
  const idx=current?STAGE_ORDER.indexOf(current==="not_found"?"found":current):-1;
  el.innerHTML=STAGE_ORDER.map((s,i)=>{let cls="stage-pill";
    if(current==="error")cls+=i===0?" err":"";else if(i<idx)cls+=" done";else if(i===idx)cls+=" active";
    return`<span class="${cls}">${esc(STAGE_LABEL[s])}</span>`;}).join("");
}
function handleEvent(node,ev,ctx){
  const {logEl,attackBtn}=ctx;
  switch(ev.type){
    case"stage":renderStages(node,ev.stage);if(ev.stage==="error")$("#box-label",node).textContent="stopped";break;
    case"box":$("#box-label",node).innerHTML=`<span class="dot live"></span>box ${esc(ev.vm_id)} · ${esc(ev.region)} · ${esc(ev.plan)} · ip hidden`;break;
    case"seal":{const ok=(v)=>/none|read only|blocked|runsc/i.test(v);
      $("#seal",node).innerHTML=(ev.checks||[]).map((c)=>`<li><span>${esc(c.name.replace(/_/g," "))}</span>
        <span class="v">${esc(c.value)} <span class="badge ${ok(c.value)?"ok":"no"}">${ok(c.value)?"held":"check"}</span></span></li>`).join("");
      attackBtn.disabled=false;break;}
    case"progress":{const pct=ev.total?Math.min(100,Math.round((ev.tried/ev.total)*100)):0;
      $("#bar",node).style.width=pct+"%";$("#pmeta",node).textContent=`${fmtInt(ev.tried)} / ${fmtInt(ev.total)} guesses · ${fmtInt(ev.rate)} /sec`;break;}
    case"log":logEl.textContent+=ev.line+"\n";logEl.scrollTop=logEl.scrollHeight;break;
    case"attack":$("#attacks",node).appendChild(h(`<div class="attack-item">
      <div><b>${esc(ev.step)}</b> <span class="badge ${ev.held?"ok":"no"}">${ev.held?"blocked":"GOT THROUGH"}</span></div>
      <div class="cmd">$ ${esc(ev.command)}</div><div class="res">→ ${esc(ev.result)}</div></div>`));break;
    case"result":showResult(node,ev);break;
    case"receipt":showReceipt(node,ev.receipt);break;
    case"error":{const p=$("#result-panel",node);p.style.display="block";p.className="panel error-box";
      p.innerHTML=`<h2>Couldn't finish</h2><p class="sub">${esc(ev.message)}</p>`;break;}
  }
}
function showResult(node,ev){
  const panel=$("#result-panel",node);panel.style.display="block";panel.className="panel";
  if(ev.found){
    panel.innerHTML=`<h2>Found it</h2><div class="reveal-pw" id="pw">${esc(ev.password)}</div>
      <div class="once">Shown once. Copy it now: it is never stored and the box is being destroyed.</div>
      <div class="cta-row" style="margin-top:12px"><button class="btn" id="copy">Copy password</button></div>`;
    $("#copy",panel).onclick=()=>navigator.clipboard?.writeText(ev.password).then(()=>toast("copied"));
  }else{
    panel.innerHTML=`<h2>No match in this plan</h2>
      <p class="sub">An honest miss. The guesses you approved did not include it. Try again with more detail, a different year, a symbol, an old password, and we will build a new plan.</p>
      <a class="btn secondary" href="#/app" data-nav>Try again</a>`;
  }
}
function showReceipt(node,r){
  if(!r)return;const panel=$("#receipt-panel",node);panel.style.display="block";panel.className="panel";
  const row=(k,v)=>`<div class="row"><span>${esc(k)}</span><span>${esc(v)}</span></div>`;
  panel.innerHTML=`<h2>Teardown receipt</h2>
    <div class="center" style="margin:6px 0 12px"><span class="badge ${r.containment_held?"ok":"no"}">${r.containment_held?"containment held":"containment check"}</span></div>
    <div class="receipt">${row("job",r.job_id)}${row("mode",r.mode)}${row("outcome",r.outcome)}${row("vm id",r.vm_id)}
      ${row("created",r.created_at)}${row("destroyed",r.destroyed_at)}${row("guesses tried",fmtInt(r.guesses_tried))}
      ${row("wallet bytes egressed",r.bytes_egressed_wallet)}${row("cracker network",r.network_mode)}
      ${row("agent wallet mounts",r.agent_wallet_mounts)}${row("api delete",r.api_delete_status||"n/a")}</div>`;
}

/* ================= PROOF ================= */
async function viewProof(){
  render(h(`<div class="appwrap"><div class="panel"><h2>Loading proof…</h2></div></div>`));
  let data;try{data=await api("/api/proof");}catch(e){return errorScreen(e.message);}
  if(!data||data.status==="not run"){
    return render(h(`<div class="appwrap"><div class="panel"><h2>Proof</h2>
      <p class="sub">The answer key of 20 test wallets is written blind, 15 recoverable and 5 honest misses, and lives at <code>data/proof/cases.json</code>. Results appear here after the full set runs on Vultr: our rules against plain defaults, same time budget, misses published with the fix.</p>
      <div class="odds">Status: not run yet on this deployment. We publish the misses, not only the wins.</div></div></div>`));
  }
  const rows=(data.cases||data.results||[]).map((c)=>`<tr>
    <td>${esc(c.id)}</td><td>${esc(c.wallet_type)}</td>
    <td><span class="tag ${c.found?"found":"miss"}">${c.found?"recovered":"miss"}</span></td>
    <td>${c.guesses!=null?fmtInt(c.guesses):"n/a"}</td><td>${esc(c.note||c.why||"")}</td></tr>`).join("");
  render(h(`<div class="appwrap"><div class="panel">
    <h2>Proof: our rules against plain defaults</h2>
    <p class="sub">${esc(data.summary||"20 test wallets, hints written before any run.")}</p>
    <table class="proof"><thead><tr><th>case</th><th>type</th><th>result</th><th>guesses</th><th>note</th></tr></thead>
    <tbody>${rows||'<tr><td colspan="5">no rows</td></tr>'}</tbody></table></div></div>`));
}

/* ================= ROUTER ================= */
function route(){
  const hash=location.hash||"#/";
  const path=hash.split("?")[0].split("#")[1]||"/";
  const query=hash.split("?")[1]||"";
  const base="/"+ (path.split("/")[1]||"");
  if(base==="/"||base==="/#"||path===""||path==="/")viewLanding();
  else if(base==="/app"){const m=query.match(/demo=([^&]+)/);viewStart(m?m[1]:null);}
  else if(base==="/start"){const m=query.match(/demo=([^&]+)/);viewStart(m?m[1]:null);}
  else if(base==="/proof")viewProof();
  else viewLanding();
}
window.addEventListener("hashchange",route);
window.addEventListener("DOMContentLoaded",()=>{
  try{const t=localStorage.getItem("ks-theme");if(t){document.body.setAttribute("data-theme",t);document.documentElement.setAttribute("data-theme",t);}}catch(_){}
  mountNav();route();
});
try{const t=localStorage.getItem("ks-theme");if(t)document.body.setAttribute("data-theme",t);}catch(_){}
if(document.readyState!=="loading"){mountNav();route();}
