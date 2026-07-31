let dashboard, lastState={},serverInstance="",refreshInFlight=false;
const widgetRenderKeys=new Map();
const slug=decodeURIComponent(location.pathname.split("/").pop());
const splEngine={context:null,analyser:null,bins:null,stream:null,running:false,autoAttempted:false,rawDb:null};
const aWeighting=frequency=>{if(frequency<=0)return-120;const f2=frequency*frequency,numerator=(12200**2)*(f2**2),denominator=(f2+20.6**2)*Math.sqrt((f2+107.7**2)*(f2+737.9**2))*(f2+12200**2);return 20*Math.log10(numerator/denominator)+2};
function setSplStatus(message){document.querySelectorAll("[data-spl-status]").forEach(element=>element.textContent=message)}
async function startSpl(){
  if(splEngine.running){if(splEngine.context?.state==="suspended")await splEngine.context.resume();return}
  if(!navigator.mediaDevices?.getUserMedia){setSplStatus("Microphone input is not supported in this browser");return}
  try{
    splEngine.stream=await navigator.mediaDevices.getUserMedia({audio:{autoGainControl:false,echoCancellation:false,noiseSuppression:false}});splEngine.context=new(window.AudioContext||window.webkitAudioContext)();const source=splEngine.context.createMediaStreamSource(splEngine.stream);splEngine.analyser=splEngine.context.createAnalyser();splEngine.analyser.fftSize=4096;splEngine.analyser.smoothingTimeConstant=.72;splEngine.bins=new Float32Array(splEngine.analyser.frequencyBinCount);source.connect(splEngine.analyser);splEngine.running=true;setSplStatus("Live A-weighted microphone level");requestAnimationFrame(updateSpl)
  }catch(error){setSplStatus(error.name==="NotAllowedError"?"Microphone permission was denied":"Could not open the microphone")}
}
function updateSpl(){
  if(!splEngine.running)return;splEngine.analyser.getFloatFrequencyData(splEngine.bins);let weightedPower=0;const binWidth=splEngine.context.sampleRate/splEngine.analyser.fftSize;
  for(let index=1;index<splEngine.bins.length;index++){const db=splEngine.bins[index];if(Number.isFinite(db))weightedPower+=10**((db+aWeighting(index*binWidth))/10)}
  const measured=weightedPower>0?10*Math.log10(weightedPower):-120;splEngine.rawDb=splEngine.rawDb===null?measured:splEngine.rawDb*.78+measured*.22;
  document.querySelectorAll("[data-spl-meter]").forEach(meter=>{const value=Math.max(0,splEngine.rawDb+Number(meter.dataset.calibration||0)),green=Number(meter.dataset.green),orange=Number(meter.dataset.orange),reading=meter.querySelector("[data-spl-value]");reading.textContent=value.toFixed(1);meter.classList.toggle("spl-green",value<=green);meter.classList.toggle("spl-orange",value>green&&value<=orange);meter.classList.toggle("spl-red",value>orange);const status=meter.querySelector("[data-spl-status]");if(status)status.textContent="Live A-weighted microphone level"});requestAnimationFrame(updateSpl)
}
function maybeAutoStartSpl(){if(splEngine.running||splEngine.autoAttempted)return;if(document.querySelector('[data-spl-meter][data-auto="true"]')){splEngine.autoAttempted=true;startSpl()}}
async function loadBoard(){
  dashboard=await api(`/api/dashboards/${encodeURIComponent(slug)}`);
  document.title=`${dashboard.name} · ChurchBoard`;
  document.documentElement.classList.toggle("theme-light",dashboard.theme==="light");
  const root=document.querySelector("#dashboard");
  root.style.setProperty("--columns",dashboard.columns); root.style.setProperty("--row-height",`${dashboard.row_height}px`);
  root.innerHTML="";widgetRenderKeys.clear();
  await refresh();
}
async function refresh(){
  if(refreshInFlight)return;
  refreshInFlight=true;
  try{lastState=await api("/api/runtime"); render(); updatePlans();}catch(error){console.error(error)}finally{refreshInFlight=false}
}
async function checkServerInstance(){try{const info=await api("/api/app-info");if(serverInstance&&serverInstance!==info.instance_id){location.reload();return}serverInstance=info.instance_id}catch(error){}}
function render(){
  const root=document.querySelector("#dashboard"),widgets=dashboard.widgets||[],existing=new Map([...root.querySelectorAll(":scope > .widget")].map(element=>[String(element.dataset.widget),element])),activeIds=new Set(),timing=lastState.timing||{};
  let changed=false;
  for(const widget of widgets){
    const id=String(widget.id),markup=widgetMarkup(widget,lastState),renderKey=widget.type==="timing"?`timing:${String(timing.current_item?.id||"")}`:markup;
    activeIds.add(id);
    if(widgetRenderKeys.get(id)===renderKey&&existing.has(id))continue;
    const template=document.createElement("template");template.innerHTML=markup.trim();const replacement=template.content.firstElementChild,current=existing.get(id);
    if(current)current.replaceWith(replacement);else root.append(replacement);
    widgetRenderKeys.set(id,renderKey);changed=true;
  }
  for(const [id,element] of existing){if(!activeIds.has(id)){element.remove();widgetRenderKeys.delete(id);changed=true}}
  if(!widgets.length&&root.innerHTML!==`<div class="empty">This dashboard has no widgets.</div>`){root.innerHTML=`<div class="empty">This dashboard has no widgets.</div>`;changed=true}
  updateTimingWidgets();tickClocks();
  if(changed)enhanceDynamicContent(root);
  maybeAutoStartSpl();
}
function updateTimingWidgets(){
  const timing=lastState.timing||{},item=timing.current_item,cells=document.querySelectorAll('[data-widget-type="timing"] .timing-cell');
  if(cells[0]){const label=cells[0].querySelector(".timing-label"),value=cells[0].querySelector(".timing-value");if(label)label.textContent=item?.title||"Current item";if(value){value.textContent=formatDuration(timing.item_delta||0);value.classList.toggle("over",(timing.item_delta||0)>0);value.classList.toggle("ahead",(timing.item_delta||0)<=0)}}
  if(cells[1]){const value=cells[1].querySelector(".timing-value");if(value){value.textContent=formatDuration(timing.overall_delta||0);value.classList.toggle("over",(timing.overall_delta||0)>0);value.classList.toggle("ahead",(timing.overall_delta||0)<=0)}}
}
document.addEventListener("click",async event=>{
  if(event.target.closest("[data-spl-start]")){await startSpl();return}
  const button=event.target.closest("[data-service-action]");if(!button)return;button.disabled=true;const status=button.closest(".service-controls")?.querySelector("[data-control-status]");if(status)status.textContent="Updating…";
  try{lastState=await api(`/api/service-control/${button.dataset.serviceAction}`,{method:"POST"});render();updatePlans()}catch(error){button.disabled=false;if(status)status.textContent=error.message}
});
document.querySelector(".hamburger").addEventListener("click",()=>document.querySelector(".display-menu").classList.toggle("open"));
const fullscreenButton=document.querySelector(".fullscreen-toggle");
const fullscreenElement=()=>document.fullscreenElement||document.webkitFullscreenElement;
function updateFullscreenButton(){const active=!!fullscreenElement();fullscreenButton.classList.toggle("is-fullscreen",active);fullscreenButton.textContent=active?"↙":"⛶";fullscreenButton.setAttribute("aria-label",active?"Exit fullscreen":"Enter fullscreen");fullscreenButton.title=active?"Exit fullscreen":"Enter fullscreen"}
fullscreenButton.addEventListener("click",async()=>{try{if(fullscreenElement()){const exit=document.exitFullscreen||document.webkitExitFullscreen;if(exit)await exit.call(document)}else{const enter=document.documentElement.requestFullscreen||document.documentElement.webkitRequestFullscreen;if(enter)await enter.call(document.documentElement)}}catch(error){console.error(error)}updateFullscreenButton()});
document.addEventListener("fullscreenchange",updateFullscreenButton);document.addEventListener("webkitfullscreenchange",updateFullscreenButton);updateFullscreenButton();
function updatePlans(){const select=document.querySelector("#active-plan"), manual=lastState.manual_plan, current=select.value||(manual?`${manual.service_type_id}:${manual.id}`:"");select.innerHTML='<option value="">Automatic</option>'+(lastState.plans||[]).map(plan=>`<option value="${escapeHtml(plan.service_type_id)}:${escapeHtml(plan.id)}">${escapeHtml(plan.title||plan.service_type_name)} · ${escapeHtml(plan.dates||"")}</option>`).join("");select.value=current}
document.querySelector("#active-plan").addEventListener("change",async event=>{const [service_type_id,id]=event.target.value.split(":");lastState=await api("/api/active-plan",{method:"PUT",body:JSON.stringify(id?{id,service_type_id}:{})});render()});
api("/api/dashboards").then(data=>document.querySelector("#board-links").innerHTML=data.items.map(item=>`<a href="/display/${encodeURIComponent(item.slug)}">${escapeHtml(item.name)}</a>`).join(""));
checkServerInstance();loadBoard(); setInterval(refresh,200); setInterval(tickClocks,250);setInterval(checkServerInstance,5000);
