(function(){var l=document.createElement('link');l.rel='stylesheet';l.href='/static/redesign.css';document.head.appendChild(l)})();
(function(){var l=document.createElement('link');l.rel='stylesheet';l.href='/static/redesign.css';document.head.appendChild(l)})();
var _aiH=[],_aiFP=null,_aiMID=0,_aiOPEN=false,_aiJOB=null;
var _aiAPI=(location.port==="5001")?"http://localhost:5000":"";
var _aiPG=(function(){var p=location.pathname;if(p.indexOf("/modifica")>-1)return "Modifica";if(p.indexOf("/importa")>-1)return "Import";if(p.indexOf("/impostazioni")>-1)return "Impostazioni";if(p.indexOf("/log")>-1)return "Log";if(p==="/")return "Lista utensili";if(p.indexOf("/analizza")>-1)return "Learner - Analizza";return p;})();
function aiT(){_aiOPEN=!_aiOPEN;var p=document.getElementById("ai-panel");var f=document.getElementById("ai-fab");if(p)p.style.display=_aiOPEN?"flex":"none";if(f)f.textContent=_aiOPEN?"X":"AI";if(_aiOPEN){var i=document.getElementById("ai-in");if(i)i.focus();}}
function aiS(){var inp=document.getElementById("ai-in");if(!inp)return;var m=inp.value.trim();if(!m)return;inp.value="";inp.style.height="auto";_aiAdd("u",m);var btn=document.getElementById("ai-sb");if(btn){btn.disabled=true;btn.textContent="...";}var ctx=(_aiH.length===0)?("[Pagina: "+_aiPG+"] "+m):m;if(_aiFP)ctx="[File: "+_aiFP+"] "+ctx;var tid=_aiAdd("t","avvio job...");var xhr=new XMLHttpRequest();xhr.open("POST",_aiAPI+"/cam-agent/job");xhr.setRequestHeader("Content-Type","application/json");xhr.onload=function(){try{var d=JSON.parse(xhr.responseText);if(d.errore){_aiRm(tid);_aiAdd("e",d.errore);if(btn){btn.disabled=false;btn.textContent=">";}return;}if(d.job_id){_aiRm(tid);_aiPoll(d.job_id,btn,0);}else{_aiRm(tid);_aiAdd("e","Risposta inattesa");if(btn){btn.disabled=false;btn.textContent=">";}}}catch(ex){_aiRm(tid);_aiAdd("e",ex.message);if(btn){btn.disabled=false;btn.textContent=">";}}};xhr.onerror=function(){_aiRm(tid);_aiAdd("e","Errore rete");if(btn){btn.disabled=false;btn.textContent=">";}};xhr.send(JSON.stringify({messaggio:ctx,filepath:_aiFP,history:_aiH}));}
function _aiPoll(jid,btn,dots){var tid=_aiAdd("t","elaborazione"+".".repeat((dots%3)+1));var xhr=new XMLHttpRequest();xhr.open("GET",_aiAPI+"/cam-agent/job/"+jid);xhr.onload=function(){_aiRm(tid);try{var d=JSON.parse(xhr.responseText);if(d.status==="running"){setTimeout(function(){_aiPoll(jid,btn,dots+1);},2000);return;}if(d.status==="done"&&d.result){var r=d.result;if(r.errore){_aiAdd("e",r.errore);}else{_aiAdd("a",r.risposta||"");_aiH=r.history||_aiH;}}else{_aiAdd("e","Job fallito: "+JSON.stringify(d).slice(0,100));}}catch(ex){_aiAdd("e",ex.message);}if(btn){btn.disabled=false;btn.textContent=">";}};xhr.onerror=function(){_aiRm(tid);_aiAdd("e","Errore polling");if(btn){btn.disabled=false;btn.textContent=">";}};xhr.send();}
function _aiAdd(t,txt){var ms=document.getElementById("ai-ms");if(!ms)return "";var id="m"+(++_aiMID);var el=document.createElement("div");el.id=id;var b=";font-size:.8rem;line-height:1.5;padding:.55rem .75rem;max-width:95%;word-break:break-word;margin-bottom:2px";if(t==="u")el.style.cssText="background:#1d4ed8;color:#fff;align-self:flex-end;border-radius:10px 10px 2px 10px"+b;else if(t==="a")el.style.cssText="background:#0f172a;color:#e2e8f0;align-self:flex-start;border-radius:10px 10px 10px 2px"+b;else if(t==="s")el.style.cssText="background:#0d2d1a;color:#86efac;align-self:center;border-radius:12px"+b;else if(t==="e")el.style.cssText="background:#450a0a;color:#fca5a5;align-self:flex-start"+b;else el.style.cssText="color:#475569;font-style:italic;align-self:flex-start"+b;el.textContent=txt||"";ms.appendChild(el);el.scrollIntoView({behavior:"smooth",block:"end"});return id;}
function _aiRm(id){var e=document.getElementById(id);if(e)e.remove();}
function _aiUpload(f){var fn=document.getElementById("ai-fn");if(fn)fn.textContent=f.name;_aiAdd("s","Caricamento "+f.name+"...");var fd=new FormData();fd.append("file",f);var xhr=new XMLHttpRequest();xhr.open("POST",_aiAPI+"/cam-agent/upload");xhr.onload=function(){try{var d=JSON.parse(xhr.responseText);if(d.filepath){_aiFP=d.filepath;_aiAdd("s","OK: "+f.name);}else _aiAdd("e","Errore upload");}catch(ex){_aiAdd("e",ex.message);}};xhr.send(fd);}
function _aiLeggiLog(){
  var log="";
  var selectors=["#log-content","#log",".log-content",".log pre","pre.log","[id*=log] pre","[class*=log] pre","pre[class*=log]","pre"];
  for(var i=0;i<selectors.length;i++){
    var el=document.querySelector(selectors[i]);
    if(el&&el.textContent.trim().length>20){log=el.textContent.trim();break;}
  }
  if(!log){
    var pres=document.querySelectorAll("pre,code");
    for(var j=0;j<pres.length;j++){
      if(pres[j].textContent.length>50&&pres[j].id!=="ai-in"){log=pres[j].textContent.trim();break;}
    }
  }
  if(!log){_aiAdd("e","Nessun log trovato nella pagina");return;}
  var inp=document.getElementById("ai-in");
  if(inp){inp.value="Analizza questo log e applica i fix necessari:\n"+log.slice(0,3000);}
  _aiAdd("s","Log acquisito ("+log.length+" chars) - invio...");
  aiS();
}
function _aiInit(){var pg=document.getElementById("ai-pg");if(pg)pg.textContent=_aiPG;
  var sb=document.getElementById("ai-sb");
  if(sb&&sb.parentNode){
    var lb=document.createElement("button");
    lb.textContent="Log";lb.title="Leggi log dalla pagina e invia all'agente";
    lb.onclick=_aiLeggiLog;
    lb.style.cssText="background:#0f172a;color:#86efac;border:1px solid #334155;border-radius:8px;padding:.5rem .7rem;cursor:pointer;font-size:.75rem;font-weight:600;white-space:nowrap";
    sb.parentNode.insertBefore(lb,sb);
  }var inp=document.getElementById("ai-in");if(inp)inp.onkeydown=function(e){if(e.key==="Enter"&&!e.shiftKey){e.preventDefault();aiS();}};var fi=document.getElementById("ai-fi");if(fi)fi.onchange=function(e){if(e.target.files[0])_aiUpload(e.target.files[0]);};}
if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",_aiInit);else _aiInit();