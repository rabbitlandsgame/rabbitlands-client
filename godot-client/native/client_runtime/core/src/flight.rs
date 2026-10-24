//! Complete heat-bolt lifecycle. POD only; engine objects stay in the bridge.
use std::panic::{catch_unwind, AssertUnwindSafe};

const OK: i32 = 0;
const INVALID: i32 = 1;
const STALE: i32 = 2;
const INTERNAL: i32 = 3;
const MAX_FLIGHTS: usize = 512;
const SEGMENTS: usize = 28;
const AFTERGLOW: f64 = 0.24;
const IMPACT_LIFETIME: f64 = 1.1;
const PI: f64 = std::f64::consts::PI;
type V3 = [f64; 3];

fn add(a: V3, b: V3) -> V3 { [a[0] + b[0], a[1] + b[1], a[2] + b[2]] }
fn sub(a: V3, b: V3) -> V3 { [a[0] - b[0], a[1] - b[1], a[2] - b[2]] }
fn mul(a: V3, b: f64) -> V3 { [a[0] * b, a[1] * b, a[2] * b] }
fn dot(a: V3, b: V3) -> f64 { a[0]*b[0] + a[1]*b[1] + a[2]*b[2] }
fn cross(a: V3, b: V3) -> V3 { [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]] }
fn normalized(a: V3) -> V3 { let n=dot(a,a).sqrt(); if n > 0.0 { mul(a,1.0/n) } else { [0.0;3] } }
fn lerp(a: V3, b: V3, t: f64) -> V3 { add(a,mul(sub(b,a),t)) }
fn unit(x: f64) -> f64 { x.clamp(0.0,1.0) }
fn finite(v: &[f64]) -> bool { v.iter().all(|x| x.is_finite() && x.abs() <= 1e12) }
fn curve(power: i64, midpoint: f64, maximum: f64) -> f64 {
    if power <= 5 { 1.0 + (midpoint-1.0)*(power-1) as f64/4.0 }
    else { midpoint+(maximum-midpoint)*(((power-5) as f64/5.0).powf(1.3)) }
}

#[repr(C)]
#[derive(Clone, Copy, Default)]
pub struct FlightSpec {
    pub id: i64, pub generation: i64, pub effect: i64, pub power: i64, pub priority: i64,
    pub start: V3, pub destination: V3, pub impact: V3, pub tint: [f64;4],
    pub release: f64, pub duration: f64,
}
#[repr(C)]
#[derive(Clone, Copy, Default)]
pub struct Anchor {
    pub id: i64, pub generation: i64, pub source_valid: i64, pub target_valid: i64,
    pub start: V3, pub destination: V3, pub impact: V3,
}
#[repr(C)]
#[derive(Clone, Copy, Default)]
pub struct Camera { pub view: V3, pub right: V3, pub up: V3 }
#[repr(C)]
#[derive(Clone, Copy, Default)]
pub struct Vertex { pub position: V3, pub color: [f64;4], pub uv: [f64;2] }
#[repr(C)]
#[derive(Clone, Copy)]
pub struct Frame {
    pub id: i64, pub generation: i64, pub epoch: i64, pub phase: i64, pub events: i64,
    pub elapsed: f64, pub impact_progress: f64, pub ring_scale: f64, pub alpha: f64,
    pub start: V3, pub destination: V3, pub impact: V3,
    pub bounds_min: V3, pub bounds_max: V3,
    pub ribbon: *const Vertex, pub ribbon_count: usize,
    pub glow: *const Vertex, pub glow_count: usize,
}
#[repr(C)]
pub struct FrameView { pub frames: *const Frame, pub count: usize }
#[repr(C)]
#[derive(Default)]
pub struct Stats {
    pub live: u64, pub admitted: u64, pub skipped: u64, pub expired: u64,
    pub frames: u64, pub vertices: u64, pub allocations: u64, pub retained_geometry_bytes: u64,
    pub state_capacity_bytes: u64,
}

struct Flight {
    spec: FlightSpec, elapsed: f64, launched: bool, arrived: bool, active: bool,
    ribbon: Vec<Vertex>, glow: Vec<Vertex>,
}
impl Flight {
    fn new(spec: FlightSpec) -> Self {
        Self { spec, elapsed: 0.0, launched: false, arrived: false, active: true,
            ribbon: Vec::new(), glow: Vec::new() }
    }
    fn point(&self, p: f64, strand: usize, side: V3, up: V3, arc: f64) -> V3 {
        let p=unit(p); let envelope=(p*PI).sin();
        let offset=add(mul(up,envelope*arc),mul(side,(p*PI*5.0+strand as f64*PI).sin()*envelope*0.035));
        add(lerp(self.spec.start,self.spec.destination,p),offset)
    }
    fn quad(buffer: &mut Vec<Vertex>, p: [V3;4], color: [f64;4]) {
        for (i,uv) in [(0,[0.0,0.0]),(1,[0.0,1.0]),(2,[1.0,1.0]),(0,[0.0,0.0]),(2,[1.0,1.0]),(3,[1.0,0.0])] {
            buffer.push(Vertex { position:p[i], color, uv });
        }
    }
    fn glow(buffer: &mut Vec<Vertex>, centre: V3, radius: f64, color: [f64;4], camera: &Camera) {
        let right=mul(camera.right,radius); let up=mul(camera.up,radius);
        Self::quad(buffer,[sub(sub(centre,right),up),add(sub(centre,right),up),add(add(centre,right),up),sub(add(centre,right),up)],color);
    }
    fn geometry(&mut self, camera: &Camera) -> u64 {
        self.ribbon.clear(); self.glow.clear();
        let time=self.elapsed-self.spec.release;
        if time >= self.spec.duration+AFTERGLOW { return 0; }
        let old_ribbon=self.ribbon.capacity(); let old_glow=self.glow.capacity();
        let magnitude=curve(self.spec.power,1.9,4.2);
        let count=(18.0*curve(self.spec.power,2.08,4.5)).round() as usize;
        self.ribbon.reserve(2*SEGMENTS*6);
        self.glow.reserve((3+count)*6);
        let vector=sub(self.spec.destination,self.spec.start);
        let distance=dot(vector,vector).sqrt();
        let direction=normalized(vector); let mut side=normalized(cross(direction,[0.0,1.0,0.0]));
        if dot(side,side)<0.01 { side=[1.0,0.0,0.0]; }
        let up=normalized(cross(side,direction));
        let arc=(distance*0.055).min(0.36);
        let tail_fraction=0.58_f64.min(1.7/distance.max(0.1));
        let p=unit(time/self.spec.duration);
        let fade_x=unit((time-self.spec.duration)/AFTERGLOW);
        let fade=1.0-fade_x*fade_x*(3.0-2.0*fade_x);
        if time>=0.0 {
            for strand in 0..2 {
                let head=unit((time-strand as f64*0.035)/self.spec.duration);
                let tail=(head-tail_fraction).max(0.0);
                let mut previous=self.point(tail,strand,side,up,arc);
                for i in 0..SEGMENTS {
                    let a=i as f64/SEGMENTS as f64;
                    let next=self.point(tail+(head-tail)*(i+1) as f64/SEGMENTS as f64,strand,side,up,arc);
                    let gold=[1.0,0.91,0.66]; let mut color=self.spec.tint;
                    for c in 0..3 { color[c]+=(gold[c]-color[c])*a*0.42; }
                    color[3]=a.powf(0.7)*fade*if strand==0 {0.85} else {0.42};
                    let half=mul(normalized(cross(sub(next,previous),camera.view)),0.13*(0.15+a*0.85)*magnitude*0.5);
                    Self::quad(&mut self.ribbon,[sub(previous,half),add(previous,half),add(next,half),sub(next,half)],color);
                    previous=next;
                }
            }
        }
        let head=if time<0.0 {self.spec.start} else {self.point(p,0,side,up,arc)};
        let mut size=0.25*magnitude;
        if time<0.0 {size*=0.60+0.15*(time*24.0).sin();}
        let c=self.spec.tint;
        Self::glow(&mut self.glow,head,size*1.8,[c[0],c[1],c[2],fade*0.55],camera);
        Self::glow(&mut self.glow,head,size,[c[0],c[1],c[2],fade],camera);
        Self::glow(&mut self.glow,head,size*0.40,[1.0,0.96,0.83,fade],camera);
        if time>=0.0 {
            for i in 0..count {
                let age=i as f64/count as f64; let sample=p-age*0.42;
                if sample<=0.0 {continue;}
                let angle=i as f64*2.399+time*4.0;
                let drift=mul(add(mul(side,angle.cos()),mul(up,angle.sin())),age*0.38);
                let point=add(self.point(sample,i%2,side,up,arc),drift);
                let mut color=c;
                for channel in 0..3 {color[channel]+=([1.0,0.80,0.32][channel]-color[channel])*0.45;}
                color[3]=(1.0-age)*fade*0.7;
                Self::glow(&mut self.glow,point,(0.025+(i%3) as f64*0.009)*magnitude,color,camera);
            }
        }
        (self.ribbon.capacity()!=old_ribbon) as u64+(self.glow.capacity()!=old_glow) as u64
    }
}

pub struct Flights { epoch:i64, limit:usize, slots:Vec<Flight>, output:Vec<Frame>, stats:Stats }
impl Default for Flights {
    fn default()->Self {Self {epoch:1,limit:48,slots:Vec::new(),output:Vec::new(),stats:Stats::default()}}
}
impl Flights {
    fn reset(&mut self, epoch:i64)->Result<(),i32> {
        if epoch<=self.epoch {return Err(STALE);}
        self.epoch=epoch; self.slots.clear(); self.output.clear(); Ok(())
    }
    fn live(&self)->usize {self.slots.iter().filter(|f|f.active).count()}
    fn cancel(&mut self,id:i64,generation:i64,epoch:i64)->Result<(),i32> {
        if epoch!=self.epoch {return Err(STALE);}
        if id<0 || generation<=0 {return Err(INVALID);}
        match self.slots.iter_mut().find(|f|f.active && f.spec.id==id && f.spec.generation==generation) {
            Some(f)=>{f.active=false;f.ribbon.clear();f.glow.clear();Ok(())},None=>Err(STALE)
        }
    }
    fn validate_spec(s:&FlightSpec)->bool {
        s.id>=0 && s.generation>0 && s.effect==2 && (1..=10).contains(&s.power)
            && (s.priority==0||s.priority==1) && finite(&s.start) && finite(&s.destination)
            && finite(&s.impact) && finite(&s.tint) && s.release.is_finite() && (0.0..=600.0).contains(&s.release)
            && s.duration.is_finite() && (0.001..=600.0).contains(&s.duration)
    }
    fn spawn(&mut self, specs:&[FlightSpec], epoch:i64, limit:usize)->Result<Vec<i64>,i32> {
        if epoch!=self.epoch {return Err(STALE);}
        if specs.len()>MAX_FLIGHTS || limit==0 || limit>MAX_FLIGHTS {return Err(INVALID);}
        for (i,s) in specs.iter().enumerate() {
            if !Self::validate_spec(s) || specs[..i].iter().any(|p|p.id==s.id) {return Err(INVALID);}
            if self.slots.iter().any(|f|f.active && f.spec.id==s.id) {return Err(STALE);}
        }
        self.limit=limit;
        let mut decisions=Vec::with_capacity(specs.len());
        for &s in specs {
            let count=self.live();
            if count>=MAX_FLIGHTS || (s.priority==0 && count>=self.limit) {
                decisions.push(0); self.stats.skipped=self.stats.skipped.saturating_add(1); continue;
            }
            if let Some(slot)=self.slots.iter_mut().find(|f|!f.active) {
                slot.spec=s; slot.elapsed=0.0; slot.launched=false; slot.arrived=false; slot.active=true;
                slot.ribbon.clear(); slot.glow.clear();
            } else {self.slots.push(Flight::new(s));}
            self.stats.admitted=self.stats.admitted.saturating_add(1); decisions.push(1);
        }
        Ok(decisions)
    }
    fn step(&mut self, anchors:&[Anchor], epoch:i64, delta:f64, camera:&Camera)->Result<&[Frame],i32> {
        if epoch!=self.epoch {return Err(STALE);}
        if anchors.len()>MAX_FLIGHTS || !delta.is_finite() || !(0.0..=60.0).contains(&delta)
            || !finite(&camera.view) || !finite(&camera.right) || !finite(&camera.up)
            || (dot(camera.view,camera.view)-1.0).abs()>1e-4
            || (dot(camera.right,camera.right)-1.0).abs()>1e-4
            || (dot(camera.up,camera.up)-1.0).abs()>1e-4 {return Err(INVALID);}
        for (i,a) in anchors.iter().enumerate() {
            if a.id<0 || a.generation<=0 || ![0,1].contains(&a.source_valid) || ![0,1].contains(&a.target_valid)
                || !finite(&a.start) || !finite(&a.destination) || !finite(&a.impact)
                || anchors[..i].iter().any(|p|p.id==a.id) {return Err(INVALID);}
            if !self.slots.iter().any(|f|f.active && f.spec.id==a.id && f.spec.generation==a.generation) {return Err(STALE);}
        }
        // No state changes or output publication before complete input validation.
        self.output.clear();
        for f in self.slots.iter_mut().filter(|f|f.active) {
            if let Some(a)=anchors.iter().find(|a|a.id==f.spec.id) {
                if !f.launched && a.source_valid==1 {f.spec.start=a.start;}
                if !f.arrived && a.target_valid==1 {f.spec.destination=a.destination;f.spec.impact=a.impact;}
            }
            f.elapsed+=delta;
            let mut events=0;
            if !f.launched && f.elapsed>=f.spec.release {f.launched=true;events|=1;}
            let impact_age=f.elapsed-f.spec.release-f.spec.duration;
            if !f.arrived && impact_age>=0.0 {f.arrived=true;events|=2;}
            let progress=unit(impact_age/IMPACT_LIFETIME);
            let phase=if progress>=1.0 {3} else if f.arrived {2} else if f.launched {1} else {0};
            if phase==3 {f.active=false; events|=4; self.stats.expired=self.stats.expired.saturating_add(1);}
            self.stats.allocations=self.stats.allocations.saturating_add(f.geometry(camera));
            self.stats.vertices=self.stats.vertices.saturating_add((f.ribbon.len()+f.glow.len()) as u64);
            let mut min=[0.0;3];let mut max=[0.0;3];
            // Union the whole trajectory/billboard envelope with approved impact
            // particle bounds. Never cull from only the current head position.
            for axis in 0..3 {
                min[axis]=f.spec.start[axis].min(f.spec.destination[axis])-4.0;
                max[axis]=f.spec.start[axis].max(f.spec.destination[axis])+4.0;
                min[axis]=min[axis].min(f.spec.impact[axis]+[-4.0,-2.0,-4.0][axis]);
                max[axis]=max[axis].max(f.spec.impact[axis]+[4.0,6.0,4.0][axis]);
            }
            self.output.push(Frame {id:f.spec.id,generation:f.spec.generation,epoch:self.epoch,phase,events,
                elapsed:f.elapsed,impact_progress:progress,ring_scale:0.55+(1.0-(1.0-progress).powi(3))*0.6,
                alpha:(1.0-progress)*0.65*curve(f.spec.power,1.27,2.7),start:f.spec.start,
                destination:f.spec.destination,impact:f.spec.impact,bounds_min:min,bounds_max:max,
                ribbon:f.ribbon.as_ptr(),ribbon_count:f.ribbon.len(),glow:f.glow.as_ptr(),glow_count:f.glow.len()});
        }
        self.stats.frames=self.stats.frames.saturating_add(1);
        Ok(&self.output)
    }
    fn stats(&self)->Stats {
        Stats {live:self.live() as u64,retained_geometry_bytes:self.slots.iter().map(|f|(f.ribbon.capacity()+f.glow.capacity()) as u64*std::mem::size_of::<Vertex>() as u64).sum(),
            state_capacity_bytes:(self.slots.capacity()*std::mem::size_of::<Flight>()+self.output.capacity()*std::mem::size_of::<Frame>()) as u64,
            admitted:self.stats.admitted,skipped:self.stats.skipped,expired:self.stats.expired,frames:self.stats.frames,
            vertices:self.stats.vertices,allocations:self.stats.allocations}
    }
}

#[unsafe(no_mangle)] pub extern "C" fn rl_flights_abi()->u32 {1}
#[unsafe(no_mangle)] pub extern "C" fn rl_flights_create()->*mut Flights {
    catch_unwind(||Box::into_raw(Box::new(Flights::default()))).unwrap_or(std::ptr::null_mut())
}
#[unsafe(no_mangle)] pub unsafe extern "C" fn rl_flights_destroy(runtime:*mut Flights) {
    if !runtime.is_null(){let _=catch_unwind(AssertUnwindSafe(||unsafe{drop(Box::from_raw(runtime))}));}
}
#[unsafe(no_mangle)] pub unsafe extern "C" fn rl_flights_reset(runtime:*mut Flights,epoch:i64)->i32 {
    if runtime.is_null(){return INVALID;}
    catch_unwind(AssertUnwindSafe(||unsafe{(&mut *runtime).reset(epoch).err().unwrap_or(OK)})).unwrap_or(INTERNAL)
}
#[unsafe(no_mangle)] pub unsafe extern "C" fn rl_flights_cancel(runtime:*mut Flights,id:i64,generation:i64,epoch:i64)->i32 {
    if runtime.is_null(){return INVALID;}
    catch_unwind(AssertUnwindSafe(||unsafe{(&mut *runtime).cancel(id,generation,epoch).err().unwrap_or(OK)})).unwrap_or(INTERNAL)
}
#[unsafe(no_mangle)] pub unsafe extern "C" fn rl_flights_spawn(runtime:*mut Flights,input:*const FlightSpec,count:usize,epoch:i64,limit:usize,decisions:*mut i64)->i32 {
    if runtime.is_null()||count>MAX_FLIGHTS||(count>0&&(input.is_null()||decisions.is_null())){return INVALID;}
    catch_unwind(AssertUnwindSafe(||unsafe{
        let input=if count==0{&[]}else{std::slice::from_raw_parts(input,count)};
        match (&mut *runtime).spawn(input,epoch,limit) {Ok(result)=>{if count>0{std::ptr::copy_nonoverlapping(result.as_ptr(),decisions,count);}OK},Err(status)=>status}
    })).unwrap_or(INTERNAL)
}
#[unsafe(no_mangle)] pub unsafe extern "C" fn rl_flights_step(runtime:*mut Flights,anchors:*const Anchor,count:usize,epoch:i64,delta:f64,camera:*const Camera,view:*mut FrameView)->i32 {
    if runtime.is_null()||camera.is_null()||view.is_null()||count>MAX_FLIGHTS||(count>0&&anchors.is_null()){return INVALID;}
    // The view borrows owned buffers only until the next runtime call. Adapter
    // must copy immediately, on its owner thread, before invoking another API.
    unsafe{*view=FrameView{frames:std::ptr::null(),count:0};}
    catch_unwind(AssertUnwindSafe(||unsafe{
        let input=if count==0{&[]}else{std::slice::from_raw_parts(anchors,count)};
        match (&mut *runtime).step(input,epoch,delta,&*camera) {Ok(result)=>{*view=FrameView{frames:result.as_ptr(),count:result.len()};OK},Err(status)=>status}
    })).unwrap_or(INTERNAL)
}
#[unsafe(no_mangle)] pub unsafe extern "C" fn rl_flights_stats(runtime:*const Flights,stats:*mut Stats)->i32 {
    if runtime.is_null()||stats.is_null(){return INVALID;}
    catch_unwind(AssertUnwindSafe(||unsafe{*stats=(&*runtime).stats();OK})).unwrap_or(INTERNAL)
}

#[cfg(test)] mod tests {
    use super::*;
    fn spec(id:i64)->FlightSpec {FlightSpec{id,generation:1,effect:2,power:5,priority:0,start:[0.0,1.0,0.0],destination:[5.0,1.0,0.0],impact:[5.0,0.0,0.0],tint:[0.8,0.2,0.1,1.0],release:0.2,duration:0.4}}
    fn camera()->Camera {Camera{view:[0.0,0.0,1.0],right:[1.0,0.0,0.0],up:[0.0,1.0,0.0]}}
    #[test] fn full_lifecycle_and_bounded_geometry() {
        let mut r=Flights::default();assert_eq!(r.spawn(&[spec(1)],1,24).unwrap(),[1]);
        let f=r.step(&[],1,0.1,&camera()).unwrap()[0];assert_eq!(f.phase,0);assert_eq!(f.ribbon_count,0);assert_eq!(f.glow_count,18);
        let f=r.step(&[],1,0.1,&camera()).unwrap()[0];assert_eq!(f.phase,1);assert_eq!(f.events&1,1);assert_eq!(f.ribbon_count,336);
        let f=r.step(&[],1,0.401,&camera()).unwrap()[0];assert_eq!(f.phase,2);assert_eq!(f.events&2,2);
        let f=r.step(&[],1,1.1,&camera()).unwrap()[0];assert_eq!(f.phase,3);assert_eq!(f.events&4,4);assert_eq!(f.ribbon_count+f.glow_count,0);assert_eq!(r.live(),0);
    }
    #[test] fn invalid_whole_batch_and_epoch_do_not_mutate() {
        let mut r=Flights::default();let mut bad=spec(2);bad.duration=f64::NAN;
        assert_eq!(r.spawn(&[spec(1),bad],1,24),Err(INVALID));assert_eq!(r.live(),0);
        r.spawn(&[spec(1)],1,24).unwrap();
        let bad_anchor=Anchor{id:1,generation:1,start:[f64::NAN;3],..Anchor::default()};
        assert!(matches!(r.step(&[bad_anchor],1,0.2,&camera()),Err(INVALID)));assert_eq!(r.slots[0].elapsed,0.0);
        assert_eq!(r.reset(2),Ok(()));assert_eq!(r.reset(2),Err(STALE));assert_eq!(r.spawn(&[spec(2)],1,24),Err(STALE));
    }
    #[test] fn launch_freezes_source_removed_target_retains_endpoint() {
        let mut r=Flights::default();r.spawn(&[spec(1)],1,24).unwrap();
        let a=Anchor{id:1,generation:1,source_valid:1,target_valid:1,start:[1.0,2.0,3.0],destination:[7.0,2.0,0.0],impact:[7.0,1.0,0.0]};
        r.step(&[a],1,0.2,&camera()).unwrap();
        let b=Anchor{start:[99.0;3],target_valid:0,..a};let f=r.step(&[b],1,0.1,&camera()).unwrap()[0];
        assert_eq!(f.start,a.start);assert_eq!(f.destination,a.destination);assert_eq!(f.impact,a.impact);
    }
    #[test] fn priority_bypasses_soft_limit_and_expired_slots_reuse_capacity() {
        let mut r=Flights::default();let mut priority=spec(3);priority.priority=1;
        assert_eq!(r.spawn(&[spec(1),spec(2),priority],1,1).unwrap(),[1,0,1]);
        r.step(&[],1,0.3,&camera()).unwrap();let capacity=r.stats().retained_geometry_bytes;
        r.step(&[],1,2.0,&camera()).unwrap();r.spawn(&[spec(4)],1,1).unwrap();r.step(&[],1,0.3,&camera()).unwrap();
        assert_eq!(r.stats().retained_geometry_bytes,capacity);assert_eq!(r.slots.len(),2);
    }
    #[test] fn cancel_requires_current_identity_and_generation() {
        let mut r=Flights::default();r.spawn(&[spec(1)],1,24).unwrap();
        assert_eq!(r.cancel(1,2,1),Err(STALE));assert_eq!(r.live(),1);
        assert_eq!(r.cancel(1,1,2),Err(STALE));assert_eq!(r.live(),1);
        assert_eq!(r.cancel(1,1,1),Ok(()));assert_eq!(r.live(),0);
        let mut next=spec(1);next.generation=2;r.spawn(&[next],1,24).unwrap();
        assert_eq!(r.cancel(1,1,1),Err(STALE));assert_eq!(r.live(),1);
    }
    #[test] fn one_large_step_publishes_all_events_then_nothing() {
        let mut r=Flights::default();r.spawn(&[spec(1)],1,24).unwrap();
        let f=r.step(&[],1,2.0,&camera()).unwrap()[0];
        assert_eq!(f.events,7);assert_eq!(f.phase,3);assert_eq!(f.ribbon_count+f.glow_count,0);
        assert!(r.step(&[],1,0.0,&camera()).unwrap().is_empty());
    }
}
