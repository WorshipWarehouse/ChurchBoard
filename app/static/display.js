let dashboard,lastState={},serverInstance="",refreshInFlight=false,planOptionsKey="",planSelectionInFlight=false,lastFullRefresh=0,compactEtag="";
const widgetRenderKeys=new Map();
const objectIds=new WeakMap();let nextObjectId=1;
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
  dashboard.background_color=applyDashboardAppearance(document.body,dashboard.background_color);
  const root=document.querySelector("#dashboard");
  root.style.setProperty("--columns",dashboard.columns); root.style.setProperty("--row-height",`${dashboard.row_height}px`);
  root.innerHTML="";widgetRenderKeys.clear();
  await refresh(true);
}
const sameJson=(left,right)=>JSON.stringify(left)===JSON.stringify(right);
const retainCachedValue=(previous,next)=>previous!==undefined&&sameJson(previous,next)?previous:next;
function mergeFullState(fresh){
  if(!Object.keys(lastState).length)return fresh;
  for(const key of ["service","people","plans","planning_center_media"]){
    if(key in fresh)fresh[key]=retainCachedValue(lastState[key],fresh[key]);
  }
  if(fresh.timing&&lastState.timing&&fresh.timing.service_items){
    fresh.timing.service_items=retainCachedValue(lastState.timing.service_items,fresh.timing.service_items);
  }
  return fresh;
}
function mergeCompactState(fresh){
  const previousTiming=lastState.timing||{},incomingTiming=fresh.timing||{};
  return {...lastState,...fresh,timing:{...previousTiming,...incomingTiming,service_items:previousTiming.service_items}};
}
async function compactRuntime(){
  const response=await fetch("/api/runtime?compact=true",{headers:compactEtag?{"If-None-Match":compactEtag}:{}});
  if(response.status===304)return null;
  if(!response.ok)throw new Error((await response.json().catch(()=>({}))).detail||`Request failed (${response.status})`);
  compactEtag=response.headers.get("ETag")||"";return response.json();
}
async function refresh(forceFull=false){
  if(refreshInFlight)return;
  refreshInFlight=true;
  try{
    const now=Date.now(),full=forceFull||!lastFullRefresh||now-lastFullRefresh>=5000,fresh=full?await api("/api/runtime"):await compactRuntime();
    if(!fresh)return;
    lastState=full?mergeFullState(fresh):mergeCompactState(fresh);if(full)lastFullRefresh=now;
    render();updatePlans();
  }catch(error){console.error(error)}finally{refreshInFlight=false}
}
async function checkServerInstance(){try{const info=await api("/api/app-info");if(serverInstance&&serverInstance!==info.instance_id){location.reload();return}serverInstance=info.instance_id}catch(error){}}
function render(){
  const root=document.querySelector("#dashboard"),widgets=dashboard.widgets||[],existing=new Map([...root.querySelectorAll(":scope > .widget")].map(element=>[String(element.dataset.widget),element])),activeIds=new Set(),timing=lastState.timing||{};
  let changed=false;
  for(const widget of widgets){
    const id=String(widget.id),renderKey=widgetStateKey(widget,lastState);
    activeIds.add(id);
    if(widgetRenderKeys.get(id)===renderKey&&existing.has(id))continue;
    const markup=widgetMarkup(widget,lastState);
    const template=document.createElement("template");template.innerHTML=markup.trim();const replacement=template.content.firstElementChild,current=existing.get(id);
    if(current)current.replaceWith(replacement);else root.append(replacement);
    widgetRenderKeys.set(id,renderKey);changed=true;
  }
  for(const [id,element] of existing){if(!activeIds.has(id)){element.remove();widgetRenderKeys.delete(id);changed=true}}
  if(!widgets.length&&root.innerHTML!==`<div class="empty">This dashboard has no widgets.</div>`){root.innerHTML=`<div class="empty">This dashboard has no widgets.</div>`;changed=true}
  updateTimingWidgets();updateOrderTimingWidgets();
  if(changed){tickClocks();enhanceDynamicContent(root)}
  maybeAutoStartSpl();
}
function objectId(value){if(!value||typeof value!=="object")return String(value);if(!objectIds.has(value))objectIds.set(value,nextObjectId++);return objectIds.get(value)}
function leaderMicKey(mics){return(mics||[]).map(mic=>[mic.id,mic.name,mic.receiver,mic.assignment?.person_id,mic.assignment?.id,mic.assignment?.name,mic.assignment?.position_key])}
function widgetStateKey(widget,state){
  const timing=state.timing||{},service=state.service||{},pp=state.propresenter||{},settings=widget.settings||{};
  if(widget.type==="clock"||widget.type==="spl"||widget.type==="text")return`${widget.type}:static`;
  if(widget.type==="service")return`service:${objectId(service)}:${timing.source||""}:${timing.state||""}`;
  if(widget.type==="timing")return`timing:${String(timing.current_item?.id||"")}:${timing.rehearsal===true}`;
  if(["assignments","mics"].includes(widget.type))return`${widget.type}:${JSON.stringify([state.people||[],state.mics||[],state.planning_center_media||{}])}`;
  if(widget.type==="slides")return`slides:${JSON.stringify(pp)}`;
  if(widget.type==="notes")return`notes:${String(pp.current?.notes||"")}`;
  if(widget.type==="order")return`order:${objectId(timing.service_items||service.items)}:${objectId(state.people)}:${JSON.stringify(leaderMicKey(state.mics))}:${String(timing.current_item?.id||"")}:${timing.service_time_id||""}:${settings.show_leader!==false}:${settings.show_mic!==false}`;
  if(widget.type==="people"||widget.type==="person")return`${widget.type}:${objectId(state.people)}`;
  if(widget.type==="controls")return`controls:${JSON.stringify([state.planning_center_live||{},state.service_control||{},timing.current_item?.id,timing.current_item?.title])}`;
  return`${widget.type}:${JSON.stringify(state)}`;
}
function fitOrderService(root=document){
  root.querySelectorAll(".order-list").forEach(list=>{
    const rows=[...list.querySelectorAll("li")];if(!rows.length)return;
    rows.forEach(row=>row.classList.remove("order-hidden"));
    const foundActive=rows.findIndex(row=>row.classList.contains("active")),activeIndex=foundActive>=0?foundActive:0,heights=rows.map(row=>Math.ceil(row.getBoundingClientRect().height)),available=Math.max(0,list.clientHeight-2),priority=[];
    priority.push(activeIndex);
    for(let offset=1;offset<=3;offset++)if(activeIndex+offset<rows.length)priority.push(activeIndex+offset);
    for(let offset=1;offset<=2;offset++)if(activeIndex-offset>=0)priority.push(activeIndex-offset);
    for(let offset=4;activeIndex+offset<rows.length;offset++)priority.push(activeIndex+offset);
    for(let offset=3;activeIndex-offset>=0;offset++)priority.push(activeIndex-offset);
    const visible=new Set();let used=0;
    for(const index of priority){const height=heights[index];if(!visible.size||used+height<=available){visible.add(index);used+=height}}
    rows.forEach((row,index)=>row.classList.toggle("order-hidden",!visible.has(index)));list.scrollTop=0;
  });
}
function updateTimingWidgets(){
  const timing=lastState.timing||{},item=timing.current_item,cells=document.querySelectorAll('[data-widget-type="timing"] .timing-cell');
  if(cells[0]){const label=cells[0].querySelector(".timing-label"),value=cells[0].querySelector(".timing-value"),labelText=item?.title||"Current item",valueText=formatDuration(timing.item_delta||0);if(label&&label.textContent!==labelText)label.textContent=labelText;if(value){if(value.textContent!==valueText)value.textContent=valueText;value.classList.toggle("over",(timing.item_delta||0)>0);value.classList.toggle("ahead",(timing.item_delta||0)<=0)}}
  if(cells[1]){const value=cells[1].querySelector(".timing-value"),valueText=formatDuration(timing.overall_delta||0);if(value){if(value.textContent!==valueText)value.textContent=valueText;value.classList.toggle("over",(timing.overall_delta||0)>0);value.classList.toggle("ahead",(timing.overall_delta||0)<=0)}}
}
function updateOrderTimingWidgets(){
  const timing=lastState.timing||{},service=lastState.service||{},adjusting=["running","live","controlled"].includes(timing.state),drift=Number(timing.overall_delta||0),driftLabel=adjusting&&Math.abs(drift)>=30?`${formatDuration(drift)} ${drift>0?"late":"early"}`:"On time",start=Date.parse(timing.service_start_at||service.starts_at||"");
  document.querySelectorAll("[data-order-drift]").forEach(element=>{if(element.textContent!==driftLabel)element.textContent=driftLabel});
  document.querySelectorAll("[data-order-eta]").forEach(element=>{const value=Number.isFinite(start)?formatClockTime(new Date(start+Number(element.dataset.startsAfter||0)*1000+(adjusting?drift:0)*1000),lastState.timezone):"—";if(element.textContent!==value)element.textContent=value});
}
document.addEventListener("click",async event=>{
  if(event.target.closest("[data-spl-start]")){await startSpl();return}
  const button=event.target.closest("[data-service-action]");if(!button)return;button.disabled=true;const status=button.closest(".service-controls")?.querySelector("[data-control-status]");if(status)status.textContent="Updating…";
  try{lastState=await api(`/api/service-control/${button.dataset.serviceAction}`,{method:"POST"});render();updatePlans()}catch(error){button.disabled=false;if(status)status.textContent=error.message}
});
const displayMenu=document.querySelector(".display-menu"),menuButton=document.querySelector(".hamburger");
function setMenuOpen(open){displayMenu.classList.toggle("open",open);displayMenu.setAttribute("aria-hidden",String(!open));menuButton.setAttribute("aria-expanded",String(open));menuButton.setAttribute("aria-label",open?"Close menu":"Open menu")}
menuButton.addEventListener("click",event=>{event.stopPropagation();setMenuOpen(!displayMenu.classList.contains("open"))});
document.addEventListener("click",event=>{if(displayMenu.classList.contains("open")&&!displayMenu.contains(event.target)&&!menuButton.contains(event.target))setMenuOpen(false)});
document.addEventListener("keydown",event=>{if(event.key==="Escape"&&displayMenu.classList.contains("open")){setMenuOpen(false);menuButton.focus()}});
const fullscreenButton=document.querySelector(".fullscreen-toggle");
const fullscreenElement=()=>document.fullscreenElement||document.webkitFullscreenElement;
function updateFullscreenButton(){const active=!!fullscreenElement();fullscreenButton.classList.toggle("is-fullscreen",active);fullscreenButton.textContent=active?"↙":"⛶";fullscreenButton.setAttribute("aria-label",active?"Exit fullscreen":"Enter fullscreen");fullscreenButton.title=active?"Exit fullscreen":"Enter fullscreen"}
fullscreenButton.addEventListener("click",async()=>{try{if(fullscreenElement()){const exit=document.exitFullscreen||document.webkitExitFullscreen;if(exit)await exit.call(document)}else{const enter=document.documentElement.requestFullscreen||document.documentElement.webkitRequestFullscreen;if(enter)await enter.call(document.documentElement)}}catch(error){console.error(error)}updateFullscreenButton()});
document.addEventListener("fullscreenchange",updateFullscreenButton);document.addEventListener("webkitfullscreenchange",updateFullscreenButton);updateFullscreenButton();
function updatePlans(){
  const select=document.querySelector("#active-plan"),plans=lastState.plans||[],optionsKey=JSON.stringify(plans.map(plan=>[plan.service_type_id,plan.id,plan.title||plan.service_type_name,plan.dates||""]));
  if(optionsKey!==planOptionsKey){select.innerHTML='<option value="">Automatic</option>'+plans.map(plan=>`<option value="${escapeHtml(plan.service_type_id)}:${escapeHtml(plan.id)}">${escapeHtml(plan.title||plan.service_type_name)} · ${escapeHtml(plan.dates||"")}</option>`).join("");planOptionsKey=optionsKey}
  if(planSelectionInFlight)return;
  const manual=lastState.manual_plan,desired=manual?`${manual.service_type_id}:${manual.id}`:"";
  if(select.value!==desired)select.value=desired;
}
document.querySelector("#active-plan").addEventListener("change",async event=>{
  const select=event.currentTarget,status=document.querySelector("#active-plan-status"),[service_type_id,id]=select.value.split(":");
  planSelectionInFlight=true;select.disabled=true;status.textContent="Selecting service…";
  try{lastState=await api("/api/active-plan",{method:"PUT",body:JSON.stringify(id?{id,service_type_id}:{})});render();status.textContent="";setMenuOpen(false)}
  catch(error){status.textContent=error.message}
  finally{planSelectionInFlight=false;select.disabled=false;updatePlans()}
});
api("/api/dashboards").then(data=>document.querySelector("#board-links").innerHTML=data.items.map(item=>`<div class="board-menu-row"><a class="board-menu-open" href="/display/${encodeURIComponent(item.slug)}">${escapeHtml(item.name)}</a><a class="board-menu-edit" href="/editor/${encodeURIComponent(item.slug)}" aria-label="Edit ${escapeHtml(item.name)}">Edit</a></div>`).join(""));
checkServerInstance();loadBoard(); setInterval(refresh,75); setInterval(tickClocks,250);setInterval(checkServerInstance,5000);
