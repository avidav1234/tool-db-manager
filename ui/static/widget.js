(function(){
var H=[],FP=null,MID=0,OPEN=false;
var PG=(function(){
  var p=location.pathname;
  if(p==="/") return "Lista utensili";
  if(p.indexOf("/modifica")>-1) return "Modifica utensile "+p.split("/")[2];
  if(p.indexOf("/nuovo")>-1) return "Nuovo utensile";
  if(p.indexOf("/importa")>-1) return "Import CAM";
  if(p.indexOf("/impostazioni")>-1) return "Impostazioni";
  if(p.indexOf("/log")>-1) return "Log";
  if(p.indexOf("/cam-agent")>-1) return "Agente CAM";
  return p;
})();

function init(){
  var pg=document.getElementById("ai-pg");
  if(pg) pg.textContent=PG;
  var inp=document.getElementById("ai-in");
  if(inp) inp.addEventListener("keydown",function(e){
    if(e.key==="Enter"&&!e.shiftKey){e.preventDefault();window.aiS();}
  });
  document.addEventListener("keydown",function(e){
    if(e.key==="Escape"&&OPEN) window.aiT();
  });
  var fi=document.getElementById("ai-fi");
  if(fi) fi.addEventListener("change",async function(e){
    var f=e.target.files[0];
    if(!f) return;
    var fn=document.getElementById("ai-fn");
    if(fn) fn.textContent=f.name;
    add("s","Caricamento "+f.name+"...");
    try{
      var fd=new FormData();
      fd.append("file",f);
      var xhr=new XMLHttpRequest();
      xhr.open("POST","/cam-agent/upload");
      xhr.onload=function(){
        var d=JSON.parse(xhr.responseText);
        if(d.filepath){FP=d.filepath;add("s","Pronto: "+f.name);}
        else add("e","Errore upload");
      };
      xhr.send(fd);
    }catch(ex){add("e",ex.message);}
  });
}

window.aiT=function(){
  OPEN=!OPEN;
  var panel=document.getElementById("ai-panel");
  var fab=document.getElementById("ai-fab");
  if(panel) panel.style.display=OPEN?"flex":"none";
  if(fab) fab.innerHTML=OPEN?"&#10005;":"&#129302;";
  if(OPEN){
    var inp=document.getElementById("ai-in");
    if(inp) inp.focus();
  }
};

window.aiS=function(){
  var inp=document.getElementById("ai-in");
  var m=(inp?inp.value:"").trim();
  if(!m) return;
  if(inp){inp.value="";inp.style.height="auto";}
  add("u",m);
  var btn=document.getElementById("ai-sb");
  if(btn){btn.disabled=true;btn.textContent="...";}
  var tid=add("t","elaborazione...");
  var ctx=(H.length===0)?("[Pagina: "+PG+"]
"+m):m;
  if(FP) ctx="[File: "+FP+"]
"+ctx;
  var xhr=new XMLHttpRequest();
  xhr.open("POST","/cam-agent/chat");
  xhr.setRequestHeader("Content-Type","application/json");
  xhr.onload=function(){
    rm(tid);
    var d=JSON.parse(xhr.responseText);
    if(d.errore){add("e",d.errore);}
    else{add("a",d.risposta||"");H=d.history||H;}
    if(btn){btn.disabled=false;btn.innerHTML="&#9658;";}
  };
  xhr.onerror=function(){
    rm(tid);
    add("e","Errore connessione");
    if(btn){btn.disabled=false;btn.innerHTML="&#9658;";}
  };
  xhr.send(JSON.stringify({messaggio:ctx,filepath:FP,history:H}));
};

function stile(t){
  if(t==="u") return "background:#1d4ed8;color:#fff;align-self:flex-end;border-radius:10px 10px 2px 10px";
  if(t==="a") return "background:#0f172a;color:#e2e8f0;align-self:flex-start;border-radius:10px 10px 10px 2px";
  if(t==="s") return "background:#0d2d1a;color:#86efac;align-self:center;border-radius:12px";
  if(t==="e") return "background:#450a0a;color:#fca5a5;align-self:flex-start";
  return "color:#475569;font-style:italic;align-self:flex-start";
}

function add(t,txt){
  var ms=document.getElementById("ai-ms");
  if(!ms) return "";
  var id="m"+(++MID);
  var el=document.createElement("div");
  el.id=id;
  el.style.cssText=stile(t)+";font-size:.8rem;line-height:1.5;padding:.55rem .75rem;max-width:95%;white-space:pre-wrap;word-break:break-word;margin-bottom:2px";
  el.textContent=txt||"";
  ms.appendChild(el);
  el.scrollIntoView({behavior:"smooth",block:"end"});
  return id;
}

function rm(id){
  var e=document.getElementById(id);
  if(e) e.remove();
}

if(document.readyState==="loading"){
  document.addEventListener("DOMContentLoaded",init);
} else {
  init();
}

})();